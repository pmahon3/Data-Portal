package ca.inn.bundler.service;

import ca.inn.bundler.model.BundleJob;
import ca.inn.bundler.model.BundleSourceFile;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Qualifier;
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
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Semaphore;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/**
 * Implements the "current" archive strategy.
 *
 * This strategy downloads all source files into a temporary staging directory
 * using bounded per-bundle concurrency, then creates the ZIP in one sequential
 * pass from the staged files.
 */
@Slf4j
@Service
public class CurrentBundleArchiveService {
    private static final class PermanentDownloadFailureException extends IOException {
        PermanentDownloadFailureException(String message) {
            super(message);
        }
    }

    private final Path tempDirRoot;
    private final Duration connectTimeout;
    private final Duration requestTimeout;
    private final int maxAttempts;
    private final Duration retryDelay;
    private final HttpClient httpClient;
    private final ExecutorService bundleDownloadExecutor;
    private final int downloadParallelism;

    public CurrentBundleArchiveService(
            @Value("${bundler.archive.temp-dir:${java.io.tmpdir}}") String tempDirRoot,
            @Value("${bundler.download.connect-timeout-seconds:5}") long connectTimeoutSeconds,
            @Value("${bundler.download.request-timeout-seconds:60}") long requestTimeoutSeconds,
            @Value("${bundler.download.max-attempts:3}") int maxAttempts,
            @Value("${bundler.download.retry-delay-millis:500}") long retryDelayMillis,
            @Value("${bundler.download.parallelism:4}") int downloadParallelism,
            @Qualifier("bundleDownloadExecutor") ExecutorService bundleDownloadExecutor
    ) {
        this.tempDirRoot = Path.of(tempDirRoot);
        this.connectTimeout = Duration.ofSeconds(connectTimeoutSeconds);
        this.requestTimeout = Duration.ofSeconds(requestTimeoutSeconds);
        this.maxAttempts = maxAttempts;
        this.retryDelay = Duration.ofMillis(retryDelayMillis);
        this.downloadParallelism = downloadParallelism;
        this.bundleDownloadExecutor = bundleDownloadExecutor;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(this.connectTimeout)
                .build();
    }

    public Path buildArchive(BundleJob job) throws IOException {
        long buildStartNanos = System.nanoTime();
        Path stageDir = Files.createTempDirectory(tempDirRoot, "bundle-stage-" + job.getId() + "-");
        Path archivePath = Files.createTempFile(tempDirRoot, "bundle-" + job.getId() + "-", ".zip");
        try {
            Path bundleRoot = stageDir.resolve(job.getFolderName()).normalize();
            log.info(
                    "Current archive build started: bundleId={} folderName={} fileCount={}",
                    job.getId(),
                    job.getFolderName(),
                    job.getFiles().size()
            );

            long downloadPhaseStartNanos = System.nanoTime();
            downloadFiles(job, bundleRoot);
            log.info(
                    "Current archive download phase completed: bundleId={} elapsedMs={}",
                    job.getId(),
                    elapsedMillis(downloadPhaseStartNanos)
            );

            long zipPhaseStartNanos = System.nanoTime();
            try (ZipOutputStream zipOut = new ZipOutputStream(Files.newOutputStream(archivePath));
                 Stream<Path> paths = Files.walk(stageDir)) {
                paths.filter(Files::isRegularFile)
                        .forEach(file -> {
                            try {
                                Path relativePath = stageDir.relativize(file);
                                ZipEntry entry = new ZipEntry(relativePath.toString());
                                zipOut.putNextEntry(entry);
                                try (InputStream in = Files.newInputStream(file)) {
                                    in.transferTo(zipOut);
                                }
                                zipOut.closeEntry();
                            } catch (IOException e) {
                                throw new RuntimeException(e);
                            }
                        });
            }
            log.info(
                    "Current archive zip phase completed: bundleId={} elapsedMs={}",
                    job.getId(),
                    elapsedMillis(zipPhaseStartNanos)
            );

            log.info(
                    "Current archive build completed: bundleId={} archivePath={} totalElapsedMs={}",
                    job.getId(),
                    archivePath,
                    elapsedMillis(buildStartNanos)
            );
            return archivePath;
        } catch (Exception exception) {
            Files.deleteIfExists(archivePath);
            log.error(
                    "Current archive build failed: bundleId={} elapsedMs={} message={}",
                    job.getId(),
                    elapsedMillis(buildStartNanos),
                    exception.getMessage(),
                    exception
            );
            throw exception;
        } finally {
            deleteDirectoryRecursively(stageDir);
        }
    }

    private void downloadFiles(BundleJob job, Path bundleRoot) throws IOException {
        Semaphore semaphore = new Semaphore(downloadParallelism);
        List<CompletableFuture<Void>> futures = new ArrayList<>();

        for (BundleSourceFile sourceFile : job.getFiles()) {
            try {
                semaphore.acquire();
            } catch (InterruptedException exception) {
                Thread.currentThread().interrupt();
                throw new IOException("Bundle download scheduling was interrupted", exception);
            }

            futures.add(CompletableFuture.runAsync(() -> {
                try {
                    Path targetFile = prepareTargetFile(bundleRoot, sourceFile.getRelativePath());
                    downloadFileToStage(
                            sourceFile.getUrl(),
                            targetFile,
                            sourceFile.getRelativePath(),
                            job.getId()
                    );
                } catch (IOException exception) {
                    throw new RuntimeException(exception);
                } finally {
                    semaphore.release();
                }
            }, bundleDownloadExecutor));
        }

        waitForDownloads(futures, "Concurrent download phase failed");
    }

    private void waitForDownloads(List<CompletableFuture<Void>> futures, String failureMessage) throws IOException {
        try {
            CompletableFuture.allOf(futures.toArray(new CompletableFuture[0])).join();
        } catch (CompletionException exception) {
            Throwable cause = exception.getCause();
            if (cause instanceof IOException ioException) {
                throw ioException;
            }
            if (cause instanceof RuntimeException runtimeException
                    && runtimeException.getCause() instanceof IOException ioException) {
                throw ioException;
            }
            throw new IOException(failureMessage, cause);
        }
    }

    private long elapsedMillis(long startNanos) {
        return Duration.ofNanos(System.nanoTime() - startNanos).toMillis();
    }

    private Path prepareTargetFile(Path bundleRoot, String sourceRelativePath) throws IOException {
        Path relativePath = Path.of(sourceRelativePath).normalize();
        if (relativePath.isAbsolute()) {
            throw new IOException("Relative path must not be absolute: " + sourceRelativePath);
        }

        Path targetFile = bundleRoot.resolve(relativePath).normalize();
        if (!targetFile.startsWith(bundleRoot)) {
            throw new IOException("Relative path escapes staging directory: " + sourceRelativePath);
        }

        Path parent = targetFile.getParent();
        if (parent != null) {
            Files.createDirectories(parent);
        }

        return targetFile;
    }

    private Path downloadFileToStage(
            String sourceUrl,
            Path targetFile,
            String relativePath,
            String bundleId
    ) throws IOException {
        IOException lastException = null;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                log.debug(
                        "Current bundle file download started: bundleId={} relativePath={} attempt={}/{}",
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
                try (InputStream inputStream = response.body()) {
                    Files.copy(inputStream, targetFile, java.nio.file.StandardCopyOption.REPLACE_EXISTING);
                }
                log.debug(
                        "Current bundle file download completed: bundleId={} relativePath={} attempt={}/{}",
                        bundleId,
                        relativePath,
                        attempt,
                        maxAttempts
                );
                return targetFile;
            } catch (IOException exception) {
                lastException = exception;
                log.warn(
                        "Current bundle file download attempt failed: bundleId={} relativePath={} attempt={}/{} message={}",
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
                "Download failed after " + maxAttempts + " attempts for relativePath=" + relativePath,
                lastException
        );
    }

    private void deleteDirectoryRecursively(Path directory) throws IOException {
        if (!Files.exists(directory)) {
            return;
        }
        try (Stream<Path> paths = Files.walk(directory)) {
            paths.sorted((a, b) -> b.compareTo(a))
                    .forEach(path -> {
                        try {
                            Files.deleteIfExists(path);
                        } catch (IOException e) {
                            throw new RuntimeException(e);
                        }
                    });
        } catch (RuntimeException exception) {
            if (exception.getCause() instanceof IOException ioException) {
                throw ioException;
            }
            throw exception;
        }
    }
}
