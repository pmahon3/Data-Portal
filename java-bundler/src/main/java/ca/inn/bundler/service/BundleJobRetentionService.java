package ca.inn.bundler.service;

import ca.inn.bundler.model.BundleJob;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

@Slf4j
@Service
@RequiredArgsConstructor
public class BundleJobRetentionService {
    private final JpaBundleJobMetadataService bundleJobMetadataService;

    @Value("${bundler.job.retention-enabled:true}")
    private boolean retentionEnabled;

    @Value("${bundler.job.completed-retention-hours:168}")
    private long completedRetentionHours;

    @Value("${bundler.job.retention-batch-size:100}")
    private int retentionBatchSize;

    @Scheduled(
            initialDelayString = "${bundler.job.retention-initial-delay-millis:60000}",
            fixedDelayString = "${bundler.job.retention-scan-delay-millis:3600000}"
    )
    public void cleanupExpiredJobs() {
        if (!retentionEnabled) {
            return;
        }

        Instant completedBefore = Instant.now().minusSeconds(effectiveCompletedRetentionHours() * 3600);
        List<String> bundleIds = bundleJobMetadataService.findRetentionEligibleJobIds(
                completedBefore,
                effectiveRetentionBatchSize()
        );

        for (String bundleId : bundleIds) {
            cleanupJob(bundleId);
        }

        if (!bundleIds.isEmpty()) {
            log.info("Bundle retention cleanup scanned terminal jobs: count={} completedBefore={}", bundleIds.size(), completedBefore);
        }
    }

    private void cleanupJob(String bundleId) {
        BundleJob job = bundleJobMetadataService.findById(bundleId).orElse(null);
        if (job == null) {
            return;
        }

        if (!deleteArchiveIfPresent(job)) {
            return;
        }

        bundleJobMetadataService.deleteById(bundleId);
        log.info("Bundle job metadata cleaned up by retention: bundleId={}", bundleId);
    }

    private boolean deleteArchiveIfPresent(BundleJob job) {
        Path archivePath = job.getArchivePath();
        if (archivePath == null) {
            return true;
        }

        try {
            boolean deleted = Files.deleteIfExists(archivePath);
            if (deleted) {
                log.info("Bundle archive deleted by retention: bundleId={} archivePath={}", job.getId(), archivePath);
            }
            return true;
        } catch (IOException exception) {
            log.warn(
                    "Bundle archive retention delete failed; metadata retained for retry: bundleId={} archivePath={} message={}",
                    job.getId(),
                    archivePath,
                    exception.getMessage()
            );
            return false;
        }
    }

    private long effectiveCompletedRetentionHours() {
        return completedRetentionHours > 0 ? completedRetentionHours : 168;
    }

    private int effectiveRetentionBatchSize() {
        return retentionBatchSize > 0 ? retentionBatchSize : 100;
    }
}
