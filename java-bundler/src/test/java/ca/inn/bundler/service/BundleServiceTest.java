package ca.inn.bundler.service;


import ca.inn.bundler.dto.BundleResponse;
import ca.inn.bundler.dto.CreateBundleRequest;
import ca.inn.bundler.exception.BundleFailedException;
import ca.inn.bundler.exception.BundleQueueFullException;
import ca.inn.bundler.exception.InvalidBundleStateTransitionException;
import ca.inn.bundler.model.BundleJob;
import ca.inn.bundler.model.BundleSourceFile;
import ca.inn.bundler.model.BundleStatus;
import ca.inn.bundler.support.RejectingExecutorService;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.nio.file.Path;
import java.util.List;
import java.util.concurrent.AbstractExecutorService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

public class BundleServiceTest {
    private final ExecutorService executor = new NoOpExecutorService();
    private final ExecutorService downloadExecutor = Executors.newFixedThreadPool(2);

    private final BundleService service = new BundleService(
            executor,
            newCurrentArchiveService(downloadExecutor),
            newBatchArchiveService(downloadExecutor),
            newStreamingArchiveService(),
            newHybridArchiveService(downloadExecutor)
    );

    @AfterEach
    void shutdownExecutor() {
        executor.shutdownNow();
        downloadExecutor.shutdownNow();
    }

    @Test
    void transitionBundleAllowsPendingToProcessing(){

        BundleResponse created= service.createBundle(CreateBundleRequest.builder()
                .folderName("test")
                .files(List.of(testSourceFile()))
                .compression("zip")
                .build());
        BundleResponse updated= service.transitionBundle(created.getId(), BundleStatus.PROCESSING);
        assertEquals(BundleStatus.PROCESSING, updated.getStatus());
    }

    @Test
    void transitionBundleRejectInvalidTransition(){
        BundleResponse created=service.createBundle(CreateBundleRequest.builder()
                .folderName("test")
                .files(List.of(testSourceFile()))
                .compression("zip")
                .build());
        service.transitionBundle(created.getId(), BundleStatus.PROCESSING);
        service.transitionBundle(created.getId(), BundleStatus.COMPLETE);
        assertThrows(InvalidBundleStateTransitionException.class, () -> service.transitionBundle(created.getId(), BundleStatus.PROCESSING));

    }

    @Test
    @Disabled("Requires a real downloadable URL; background processing currently performs real network download.")
    void createBundleProcessesJobInBackground() throws Exception {
        BundleResponse created=service.createBundle(CreateBundleRequest.builder()
                .folderName("test")
                .files(List.of(testSourceFile()))
                .compression("zip")
                .build());
        Thread.sleep(700);
        BundleResponse status = service.getBundle(created.getId());
        assertEquals(BundleStatus.COMPLETE, status.getStatus());


    }

    @Test
    void createBundleThrowsQueueFullWhenExecutorRejectsJob() {
        // a fake executer
        BundleService rejectingService = new BundleService(
                new RejectingExecutorService(),
                newCurrentArchiveService(Executors.newFixedThreadPool(2)),
                newBatchArchiveService(Executors.newFixedThreadPool(2)),
                newStreamingArchiveService(),
                newHybridArchiveService(Executors.newFixedThreadPool(2))
        );

        assertThrows(
                BundleQueueFullException.class,
                () -> rejectingService.createBundle(validRequest())
        );
    }

    @Test
    void failedBundleExposesErrorMessageInResponse() throws Exception {
        ExecutorService failingExecutor = Executors.newSingleThreadExecutor();
        BundleService failingService = new BundleService(
                failingExecutor,
                new FailingCurrentBundleArchiveService(),
                newBatchArchiveService(Executors.newFixedThreadPool(2)),
                newStreamingArchiveService(),
                newHybridArchiveService(Executors.newFixedThreadPool(2))
        );

        try {
            BundleResponse created = failingService.createBundle(validRequest());

            Thread.sleep(200);

            BundleResponse status = failingService.getBundle(created.getId());
            assertEquals(BundleStatus.FAILED, status.getStatus());
            assertEquals("Simulated archive failure", status.getErrorMessage());
            assertThrows(BundleFailedException.class, () -> failingService.getArchivePath(created.getId()));
        } finally {
            failingExecutor.shutdownNow();
        }
    }

    private CreateBundleRequest validRequest() {
        return CreateBundleRequest.builder()
                .folderName("test")
                .files(List.of(testSourceFile()))
                .compression("zip")
                .build();
    }

    private BundleSourceFile testSourceFile() {
        return BundleSourceFile.builder()
                .url("https://example.com/file.txt")
                .relativePath("folder/file.txt")
                .build();
    }

    private static CurrentBundleArchiveService newCurrentArchiveService(ExecutorService downloadExecutor) {
        return new CurrentBundleArchiveService(
                System.getProperty("java.io.tmpdir"),
                5,
                60,
                3,
                500,
                4,
                downloadExecutor
        );
    }

    private static BatchBundleArchiveService newBatchArchiveService(ExecutorService downloadExecutor) {
        return new BatchBundleArchiveService(
                System.getProperty("java.io.tmpdir"),
                5,
                60,
                3,
                500,
                4,
                downloadExecutor
        );
    }

    private static StreamingBundleArchiveService newStreamingArchiveService() {
        return new StreamingBundleArchiveService(
                System.getProperty("java.io.tmpdir"),
                5,
                60,
                3,
                500
        );
    }

    private static BundleArchiveHybridService newHybridArchiveService(ExecutorService downloadExecutor) {
        return new BundleArchiveHybridService(
                System.getProperty("java.io.tmpdir"),
                5,
                60,
                3,
                500,
                4,
                downloadExecutor
        );
    }

    private static class FailingCurrentBundleArchiveService extends CurrentBundleArchiveService {
        FailingCurrentBundleArchiveService() {
            super(
                    System.getProperty("java.io.tmpdir"),
                    5,
                    60,
                    3,
                    500,
                    4,
                    Executors.newFixedThreadPool(2)
            );
        }

        @Override
        public Path buildArchive(BundleJob job) throws IOException {
            throw new IOException("Simulated archive failure");
        }
    }

    private static class NoOpExecutorService extends AbstractExecutorService {
        private boolean shutdown;

        @Override
        public void shutdown() {
            shutdown = true;
        }

        @Override
        public List<Runnable> shutdownNow() {
            shutdown = true;
            return List.of();
        }

        @Override
        public boolean isShutdown() {
            return shutdown;
        }

        @Override
        public boolean isTerminated() {
            return shutdown;
        }

        @Override
        public boolean awaitTermination(long timeout, TimeUnit unit) {
            return shutdown;
        }

        @Override
        public void execute(Runnable command) {
            // Transition tests need the job to be accepted without a background
            // worker racing the explicit status transitions under assertion.
        }
    }


}
