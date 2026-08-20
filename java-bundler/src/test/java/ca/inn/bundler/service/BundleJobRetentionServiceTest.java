package ca.inn.bundler.service;

import ca.inn.bundler.model.BundleJob;
import ca.inn.bundler.model.BundleSourceFile;
import ca.inn.bundler.model.BundleStatus;
import ca.inn.bundler.repository.BundleJobJpaRepository;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertFalse;

@SpringBootTest(properties = {
        "bundler.job.retention-enabled=true",
        "bundler.job.completed-retention-hours=1",
        "bundler.job.retention-initial-delay-millis=3600000"
})
class BundleJobRetentionServiceTest {
    @Autowired
    private BundleJobRetentionService retentionService;

    @Autowired
    private JpaBundleJobMetadataService bundleJobMetadataService;

    @Autowired
    private BundleJobJpaRepository bundleJobJpaRepository;

    @BeforeEach
    void setUp() {
        bundleJobJpaRepository.deleteAll();
    }

    @Test
    void cleanupExpiredJobsDeletesArchiveAndMetadata() throws Exception {
        Path archivePath = Files.createTempFile("retention-test-", ".zip");
        Instant completedAt = Instant.now().minusSeconds(7200);

        bundleJobMetadataService.create(BundleJob.builder()
                .id("retention-job-1")
                .status(BundleStatus.COMPLETE)
                .folderName("retention")
                .compression("zip")
                .files(List.of(BundleSourceFile.builder()
                        .url("http://localhost/file.csv")
                        .relativePath("file.csv")
                        .build()))
                .archivePath(archivePath)
                .createdAt(completedAt.minusSeconds(60))
                .updatedAt(completedAt)
                .completedAt(completedAt)
                .attemptCount(1)
                .build());

        retentionService.cleanupExpiredJobs();

        assertFalse(Files.exists(archivePath));
        assertFalse(bundleJobMetadataService.findById("retention-job-1").isPresent());
    }
}
