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
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Future;
import java.util.stream.Stream;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/**
 * Implements the "hybrid" archive strategy.
 *
 * This strategy keeps a bounded number of downloads in flight, stages each
 * completed file under a safe temporary name, writes it into the single ZIP
 * writer, and deletes the staged file after it has been zipped.
 * Remember: ZipOutputStream cannot safely accept concurrent writes
 */
@Slf4j
@Service
public class BundleArchiveHybridService {
    private static final class PermanentDownloadFailureException extends IOException {
        PermanentDownloadFailureException(String message) {
            super(message);
        }
    }

    // Planned work for one source file before download starts: where to fetch it
    // from, where it belongs inside the ZIP, and where to stage it temporarily.
    private record DownloadPlan(BundleSourceFile sourceFile, Path entryPath, Path stagePath) {
    }

    // Result produced by one completed download: the staged file is ready on
    // disk and can be consumed by the single ZIP writer.
    private record StagedDownload(Path entryPath, Path stagePath, String relativePath) {
    }

    private final Path tempDirRoot;
    private final Duration requestTimeout;
    private final int maxAttempts;
    private final Duration retryDelay;
    private final int downloadParallelism;
    private final HttpClient httpClient;
    private final ExecutorService bundleDownloadExecutor;

    public BundleArchiveHybridService(
            @Value("${bundler.archive.temp-dir:${java.io.tmpdir}}") String tempDirRoot,
            @Value("${bundler.download.connect-timeout-seconds:5}") long connectTimeoutSeconds,
            @Value("${bundler.download.request-timeout-seconds:60}") long requestTimeoutSeconds,
            @Value("${bundler.download.max-attempts:3}") int maxAttempts,
            @Value("${bundler.download.retry-delay-millis:500}") long retryDelayMillis,
            @Value("${bundler.download.parallelism:4}") int downloadParallelism,
            @Qualifier("bundleDownloadExecutor") ExecutorService bundleDownloadExecutor
    ) {
        this.tempDirRoot = Path.of(tempDirRoot);
        this.requestTimeout = Duration.ofSeconds(requestTimeoutSeconds);
        this.maxAttempts = maxAttempts;
        this.retryDelay = Duration.ofMillis(retryDelayMillis);
        this.downloadParallelism = downloadParallelism;
        this.bundleDownloadExecutor = bundleDownloadExecutor;
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(connectTimeoutSeconds))
                .build();
    }

    public Path buildArchiveHybrid(BundleJob job) throws IOException {
        long buildStartNanos = System.nanoTime();
        Path stageDir = Files.createTempDirectory(tempDirRoot, "bundle-stage-hybrid-" + job.getId() + "-");
        Path archivePath = Files.createTempFile(tempDirRoot, "bundle-hybrid-" + job.getId() + "-", ".zip");
        List<Future<StagedDownload>> submittedFutures = new ArrayList<>();

        try {
            log.info(
                    "Hybrid archive build started: bundleId={} folderName={} fileCount={} downloadParallelism={}",
                    job.getId(),
                    job.getFolderName(),
                    job.getFiles().size(),
                    downloadParallelism
            );

            List<DownloadPlan> downloadPlans = createDownloadPlans(job, stageDir);
            ExecutorCompletionService<StagedDownload> completionService =
                    new ExecutorCompletionService<>(bundleDownloadExecutor);

            int submittedCount = 0;
            int completedCount = 0;
            long downloadStartNanos = System.nanoTime();
            long zipStartNanos = System.nanoTime();
            boolean downloadSideLogged = false;

            // Start only a bounded number of downloads. Every time the ZIP writer
            // consumes one completed file, we submit one more download. This keeps
            // network IO and ZIP writing overlapped without staging the whole bundle.
            while (submittedCount < downloadPlans.size() && submittedCount < downloadParallelism) {
                submittedFutures.add(submitDownload(completionService, downloadPlans.get(submittedCount), job.getId()));
                submittedCount++;
            }

            try (ZipOutputStream zipOut = new ZipOutputStream(Files.newOutputStream(archivePath))) {
                while (completedCount < downloadPlans.size()) {
                    StagedDownload stagedDownload = takeCompletedDownload(completionService);
                    completedCount++;

                    // Submit the next download before zipping the completed file so
                    // slow compression can overlap with the next network request.
                    if (submittedCount < downloadPlans.size()) {
                        submittedFutures.add(submitDownload(completionService, downloadPlans.get(submittedCount), job.getId()));
                        submittedCount++;
                    }

                    if (!downloadSideLogged && completedCount == downloadPlans.size()) {
                        downloadSideLogged = true;
                        log.info(
                                "Hybrid archive download side completed: bundleId={} elapsedMs={} fileCount={}",
                                job.getId(),
                                elapsedMillis(downloadStartNanos),
                                downloadPlans.size()
                        );
                    }

                    writeStagedFileToZip(zipOut, stagedDownload);
                    Files.deleteIfExists(stagedDownload.stagePath());
                }
            }

            log.info(
                    "Hybrid archive zip side completed: bundleId={} elapsedMs={}",
                    job.getId(),
                    elapsedMillis(zipStartNanos)
            );
            log.info(
                    "Hybrid archive build completed: bundleId={} archivePath={} totalElapsedMs={}",
                    job.getId(),
                    archivePath,
                    elapsedMillis(buildStartNanos)
            );
            return archivePath;
        } catch (Exception exception) {
            for (Future<StagedDownload> future : submittedFutures) {
                future.cancel(true);
            }
            Files.deleteIfExists(archivePath);
            log.error(
                    "Hybrid archive build failed: bundleId={} elapsedMs={} message={}",
                    job.getId(),
                    elapsedMillis(buildStartNanos),
                    exception.getMessage(),
                    exception
            );
            if (exception instanceof IOException ioException) {
                throw ioException;
            }
            throw new IOException("Hybrid archive build failed", exception);
        } finally {
            deleteDirectoryRecursively(stageDir);
        }
    }

    // Builds one safe download plan per source file before any download starts.
    // The plan separates the temporary staging path from the final ZIP entry path.
    private List<DownloadPlan> createDownloadPlans(BundleJob job, Path stageDir) throws IOException {
        List<DownloadPlan> plans = new ArrayList<>();
        int index = 0;
        for (BundleSourceFile sourceFile : job.getFiles()) {
            Path entryPath = prepareArchiveEntryPath(job.getFolderName(), sourceFile.getRelativePath());

            // Keep two paths for the same file:
            // - stagePath is the temporary server-side download path.
            // - entryPath is the final path the user sees inside the ZIP.
            //
            // stagePath intentionally uses generated names like download-00001.bin
            // instead of sourceFile.getRelativePath(). User/source paths can contain
            // folders, duplicate names, or unsafe segments such as "../". The staged
            // file only needs to hold bytes until the ZIP writer consumes it.
            //
            // entryPath preserves the real relative path inside the ZIP after it has
            // been normalized and validated by prepareArchiveEntryPath(...).
            Path stagePath = stageDir.resolve(String.format("download-%05d.bin", ++index));
            plans.add(new DownloadPlan(sourceFile, entryPath, stagePath));
        }
        return plans;
    }

    // Submits one download task to the completion service. When the task
    // finishes, it returns the staged file metadata needed by the ZIP writer.
    private Future<StagedDownload> submitDownload(
            ExecutorCompletionService<StagedDownload> completionService,
            DownloadPlan plan,
            String bundleId
    ) {
        return completionService.submit(() -> {
            downloadFileToStage(
                    plan.sourceFile().getUrl(),
                    plan.stagePath(),
                    plan.sourceFile().getRelativePath(),
                    bundleId
            );
            return new StagedDownload(
                    plan.entryPath(),
                    plan.stagePath(),
                    plan.sourceFile().getRelativePath()
            );
        });
    }

    // Waits for whichever submitted download finishes next and unwraps its
    // result. This is what lets hybrid ZIP files in completion order.
    private StagedDownload takeCompletedDownload(
            ExecutorCompletionService<StagedDownload> completionService
    ) throws IOException {
        try {
            return completionService.take().get();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IOException("Hybrid archive download pipeline was interrupted", exception);
        } catch (ExecutionException exception) {
            Throwable cause = exception.getCause();
            if (cause instanceof IOException ioException) {
                throw ioException;
            }
            if (cause instanceof RuntimeException runtimeException
                    && runtimeException.getCause() instanceof IOException ioException) {
                throw ioException;
            }
            throw new IOException("Hybrid archive download failed", cause);
        }
    }

    // Writes one fully downloaded staged file into the ZIP. Only this method
    // touches ZipOutputStream, keeping ZIP writes single-threaded and safe.
    private void writeStagedFileToZip(ZipOutputStream zipOut, StagedDownload stagedDownload) throws IOException {
        String zipEntryName = stagedDownload.entryPath().toString().replace("\\", "/");
        ZipEntry entry = new ZipEntry(zipEntryName);
        zipOut.putNextEntry(entry);
        try (InputStream inputStream = Files.newInputStream(stagedDownload.stagePath())) {
            inputStream.transferTo(zipOut);
        } finally {
            zipOut.closeEntry();
        }
        log.info(
                "Hybrid bundle file zipped: relativePath={}",
                stagedDownload.relativePath()
        );
    }

    // Converts the source relative path into the path that will appear inside
    // the ZIP, rejecting absolute paths or paths that escape the archive root.
    private Path prepareArchiveEntryPath(String folderName, String sourceRelativePath) throws IOException {
        Path relativePath = Path.of(sourceRelativePath).normalize();
        if (relativePath.isAbsolute()) {
            throw new IOException("Relative path must not be absolute: " + sourceRelativePath);
        }
        if (relativePath.startsWith("..")) {
            throw new IOException("Relative path escapes archive root: " + sourceRelativePath);
        }

        Path entryPath = Path.of(folderName).resolve(relativePath).normalize();
        if (entryPath.isAbsolute() || entryPath.startsWith("..")) {
            throw new IOException("Archive entry path escapes archive root: " + sourceRelativePath);
        }
        return entryPath;
    }

    // Downloads one source URL into its temporary staged file. Retryable HTTP
    // failures are retried; permanent 4xx failures stop immediately.
    private Path downloadFileToStage(
            String sourceUrl,
            Path targetFile,
            String relativePath,
            String bundleId
    ) throws IOException {
        IOException lastException = null;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                log.info(
                        "Hybrid bundle file download started: bundleId={} relativePath={} attempt={}/{}",
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
                } catch (InterruptedException exception) {
                    Thread.currentThread().interrupt();
                    throw new IOException("Download was interrupted", exception);
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
                log.info(
                        "Hybrid bundle file download completed: bundleId={} relativePath={} attempt={}/{}",
                        bundleId,
                        relativePath,
                        attempt,
                        maxAttempts
                );
                return targetFile;
            } catch (IOException exception) {
                lastException = exception;
                log.warn(
                        "Hybrid bundle file download attempt failed: bundleId={} relativePath={} attempt={}/{} message={}",
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
                "Hybrid download failed after " + maxAttempts + " attempts for relativePath=" + relativePath,
                lastException
        );
    }

    // Converts a System.nanoTime() start value into elapsed milliseconds for logs.
    private long elapsedMillis(long startNanos) {
        return Duration.ofNanos(System.nanoTime() - startNanos).toMillis();
    }

    // Deletes the staging directory after success or failure, walking children
    // before parents so non-empty directories can be removed.
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
