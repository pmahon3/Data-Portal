package ca.inn.bundler.service;

import ca.inn.bundler.model.BundleJob;
import ca.inn.bundler.model.BundleSourceFile;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/**
 * Implements the "streaming" archive strategy.
 *
 * This comparison strategy downloads one source file at a time and writes its
 * response stream directly into the ZIP entry. It avoids per-file staging, but
 * downloads are sequential because ZipOutputStream has one active entry writer.
 */
@Slf4j
@Service
public class StreamingBundleArchiveService {
    private static final class PermanentDownloadFailureException extends IOException {
        PermanentDownloadFailureException(String message) {
            super(message);
        }
    }

    private final Path tempDirRoot;
    private final Duration requestTimeout;
    private final int maxAttempts;
    private final Duration retryDelay;
    private final HttpClient httpClient;

    public StreamingBundleArchiveService(
            @Value("${bundler.archive.temp-dir:${java.io.tmpdir}}") String tempDirRoot,
            @Value("${bundler.download.connect-timeout-seconds:5}") long connectTimeoutSeconds,
            @Value("${bundler.download.request-timeout-seconds:60}") long requestTimeoutSeconds,
            @Value("${bundler.download.max-attempts:3}") int maxAttempts,
            @Value("${bundler.download.retry-delay-millis:500}") long retryDelayMillis
    ) {
        this.tempDirRoot = Path.of(tempDirRoot);
        this.requestTimeout = Duration.ofSeconds(requestTimeoutSeconds);
        this.maxAttempts = maxAttempts;
        this.retryDelay = Duration.ofMillis(retryDelayMillis);
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(connectTimeoutSeconds))
                .build();
    }

    public Path buildArchive(BundleJob job) throws IOException {
        long buildStartNanos = System.nanoTime();
        Path archivePath = Files.createTempFile(tempDirRoot, "bundle-streaming-" + job.getId() + "-", ".zip");

        try {
            log.info(
                    "Streaming archive build started: bundleId={} folderName={} fileCount={}",
                    job.getId(),
                    job.getFolderName(),
                    job.getFiles().size()
            );

            long zipPhaseStartNanos = System.nanoTime();
            try (ZipOutputStream zipOut = new ZipOutputStream(Files.newOutputStream(archivePath))) {
                for (BundleSourceFile sourceFile : job.getFiles()) {
                    Path entryPath = prepareArchiveEntryPath(job.getFolderName(), sourceFile.getRelativePath());
                    long fileZipStartNanos = System.nanoTime();
                    streamFileToZip(sourceFile.getUrl(), zipOut, entryPath, sourceFile.getRelativePath(), job.getId());
                    log.debug(
                            "Streaming bundle file zipped: bundleId={} relativePath={} zipElapsedMs={}",
                            job.getId(),
                            sourceFile.getRelativePath(),
                            elapsedMillis(fileZipStartNanos)
                    );
                }
            }

            log.info(
                    "Streaming archive zip phase completed: bundleId={} elapsedMs={}",
                    job.getId(),
                    elapsedMillis(zipPhaseStartNanos)
            );
            log.info(
                    "Streaming archive build completed: bundleId={} archivePath={} totalElapsedMs={}",
                    job.getId(),
                    archivePath,
                    elapsedMillis(buildStartNanos)
            );
            return archivePath;
        } catch (Exception exception) {
            Files.deleteIfExists(archivePath);
            log.error(
                    "Streaming archive build failed: bundleId={} elapsedMs={} message={}",
                    job.getId(),
                    elapsedMillis(buildStartNanos),
                    exception.getMessage(),
                    exception
            );
            throw exception;
        }
    }

    private long elapsedMillis(long startNanos) {
        return Duration.ofNanos(System.nanoTime() - startNanos).toMillis();
    }

    private Path prepareArchiveEntryPath(String folderName, String sourceRelativePath) throws IOException {
        Path relativePath = Path.of(sourceRelativePath).normalize();
        if (relativePath.isAbsolute()) {
            throw new IOException("Relative path must not be absolute: " + sourceRelativePath);
        }
        if (relativePath.startsWith("..")) {
            throw new IOException("Relative path escapes archive root: " + sourceRelativePath);
        }
        return Path.of(folderName).resolve(relativePath).normalize();
    }

    private void streamFileToZip(
            String sourceUrl,
            ZipOutputStream zipOut,
            Path entryPath,
            String relativePath,
            String bundleId
    ) throws IOException {
        IOException lastException = null;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                log.debug(
                        "Streaming bundle file download started: bundleId={} relativePath={} attempt={}/{}",
                        bundleId,
                        relativePath,
                        attempt,
                        maxAttempts
                );
                HttpRequest httpRequest = HttpRequest.newBuilder()
                        .uri(URI.create(sourceUrl))
                        .timeout(requestTimeout)
                        .GET()
                        .build();
                HttpResponse<InputStream> response;
                try {
                    response = httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofInputStream());
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Download was interrupted", e);
                }

                int statusCode = response.statusCode();
                if (statusCode >= 400 && statusCode < 500
                        && statusCode != 408
                        && statusCode != 429) {
                    throw new PermanentDownloadFailureException(
                            "Permanent download failure with HTTP status " + statusCode
                    );
                }
                if (statusCode < 200 || statusCode >= 300) {
                    throw new IOException("Retryable download failure with HTTP status " + statusCode);
                }

                zipOut.putNextEntry(new ZipEntry(entryPath.toString()));
                try (InputStream inputStream = response.body()) {
                    inputStream.transferTo(zipOut);
                } finally {
                    zipOut.closeEntry();
                }

                log.debug(
                        "Streaming bundle file download completed: bundleId={} relativePath={} attempt={}/{}",
                        bundleId,
                        relativePath,
                        attempt,
                        maxAttempts
                );
                return;
            } catch (IOException exception) {
                lastException = exception;
                log.warn(
                        "Streaming bundle file download attempt failed: bundleId={} relativePath={} attempt={}/{} message={}",
                        bundleId,
                        relativePath,
                        attempt,
                        maxAttempts,
                        exception.getMessage()
                );
                if (exception instanceof PermanentDownloadFailureException) {
                    break;
                }
                if (attempt == maxAttempts) {
                    break;
                }
                try {
                    Thread.sleep(retryDelay.toMillis());
                } catch (InterruptedException interruptedException) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Retry delay was interrupted", interruptedException);
                }
            }
        }

        throw new IOException(
                "Streaming download failed after " + maxAttempts + " attempts for relativePath=" + relativePath,
                lastException
        );
    }
}
