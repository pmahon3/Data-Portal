package ca.inn.bundler.service;

import ca.inn.bundler.model.BundleJob;
import ca.inn.bundler.model.BundleSourceFile;
import ca.inn.bundler.model.BundleStatus;
import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Test;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.zip.ZipFile;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

public class CurrentBundleArchiveServiceTest {

    @Test
    @Disabled("Requires a real downloadable URL; archive download logic is not isolated from network yet.")
    void buildArchiveCreatEmptyZipFile() throws Exception {
        ExecutorService downloadExecutor = Executors.newFixedThreadPool(2);
        CurrentBundleArchiveService service = new CurrentBundleArchiveService(
                System.getProperty("java.io.tmpdir"),
                5,
                60,
                3,
                500,
                4,
                downloadExecutor
        );
        BundleJob job = BundleJob.builder()
                .id("test-id")
                .status(BundleStatus.PROCESSING)
                .createdAt(Instant.now())
                .updatedAt(Instant.now())
                .folderName("test")
                .compression("zip")
                .files(List.of(
                        BundleSourceFile.builder()
                                .url("https://example.com/file.txt")
                                .relativePath("folder/file.txt")
                                .build()
                ))
                .build();

        Path archivePath = service.buildArchive(job);
        try {
            assertTrue(Files.exists(archivePath));
            try (ZipFile zipFile = new ZipFile(archivePath.toFile())) {
                assertEquals(0, zipFile.size());
            }
        } finally {
            Files.deleteIfExists(archivePath);
        }
    }
}
