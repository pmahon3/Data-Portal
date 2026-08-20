package ca.inn.bundler.service;

import ca.inn.bundler.dto.BundleResponse;
import ca.inn.bundler.dto.CreateBundleRequest;
import ca.inn.bundler.exception.BundleFailedException;
import ca.inn.bundler.exception.BundleNotFoundException;
import ca.inn.bundler.exception.BundleNotReadyException;
import ca.inn.bundler.exception.BundleQueueFullException;
import ca.inn.bundler.exception.InvalidBundleStateTransitionException;
import ca.inn.bundler.model.BundleJob;
import ca.inn.bundler.model.BundleStatus;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

@Slf4j
@RequiredArgsConstructor
@Service
public class BundleService {
    // Injecting necessary beans
    private final ExecutorService bundleExecutor;
    private final CurrentBundleArchiveService currentBundleArchiveService;
    private final BatchBundleArchiveService batchBundleArchiveService;
    private final StreamingBundleArchiveService streamingBundleArchiveService;
    private final BundleArchiveHybridService bundleArchiveHybridService;
    private final JpaBundleJobMetadataService bundleJobMetadataService;
    private final BundleObjectStorageService bundleObjectStorageService;

    @Value("${bundler.archive.strategy:current}")
    private String archiveStrategy;

    @Value("${bundler.instance-id:${NOMAD_ALLOC_ID:${HOSTNAME:}}}")
    private String configuredInstanceId;

    @Value("${bundler.job.lock-duration-seconds:600}")
    private long lockDurationSeconds;

    @Value("${bundler.job.claim-scan-enabled:true}")
    private boolean claimScanEnabled;

    @Value("${bundler.job.claim-scan-batch-size:20}")
    private int claimScanBatchSize;

    private final String fallbackInstanceId = "bundler-" + UUID.randomUUID();

    public BundleResponse createBundle(CreateBundleRequest request) {
        Instant now=Instant.now();
        String id=UUID.randomUUID().toString();
        BundleJob job= BundleJob.builder()
                .id(id)
                .status(BundleStatus.PENDING)
                .createdAt(now)
                .updatedAt(now)
                .folderName(request.getFolderName())
                .compression(request.getCompression())
                .files(request.getFiles())
                .build();
        bundleJobMetadataService.create(job);
        log.info(
                "Bundle accepted: bundleId={} folderName={} fileCount={}",
                id,
                request.getFolderName(),
                request.getFiles().size()
        );

        try {
            bundleExecutor.submit(() -> processBundle(job.getId()));
            log.info("Bundle queued: bundleId={}", id);
        } catch (RejectedExecutionException exception) {
            bundleJobMetadataService.deleteById(id);
            log.warn("Bundle rejected because worker queue is full: bundleId={}", id);
            throw new BundleQueueFullException();
        }
        /*
         equivalent to:
         boundleExecutor.submit(new Runnable(){
         @Override
         public void run(){
         processBundle(job.getId();
         }
         });
        */

        return toResponse(job);

    }


    public BundleResponse getBundle(String bundleId){
        BundleJob job=getRequiredJob(bundleId, "Bundle lookup failed");
        return toResponse(job);
    }

    public List<BundleResponse> getAllBundles() {
        List<BundleJob> jobs = bundleJobMetadataService.findAll();
        log.info("Listing all bundle jobs: count={}", jobs.size());
        return jobs.stream()
                .map(this::toResponse)
                .toList();
    }

    private BundleResponse toResponse(BundleJob job) {
        return BundleResponse.builder()
                .id(job.getId())
                .status(job.getStatus())
                .createdAt(job.getCreatedAt())
                .updatedAt(job.getUpdatedAt())
                .startedAt(job.getStartedAt())
                .completedAt(job.getCompletedAt())
                .archiveStartedAt(job.getArchiveStartedAt())
                .archiveCompletedAt(job.getArchiveCompletedAt())
                .uploadStartedAt(job.getUploadStartedAt())
                .uploadCompletedAt(job.getUploadCompletedAt())
                .archiveDurationMillis(job.getArchiveDurationMillis())
                .uploadDurationMillis(job.getUploadDurationMillis())
                .totalDurationMillis(job.getTotalDurationMillis())
                .resultObjectKey(job.getResultObjectKey())
                .errorMessage(job.getErrorMessage())
                .build();
    }

    @Scheduled(fixedDelayString = "${bundler.job.claim-scan-delay-millis:5000}")
    public void enqueueClaimableJobs() {
        if (!claimScanEnabled) {
            return;
        }

        List<String> bundleIds = bundleJobMetadataService.findClaimableJobIds(
                Instant.now(),
                effectiveClaimScanBatchSize()
        );
        for (String bundleId : bundleIds) {
            try {
                bundleExecutor.submit(() -> processBundle(bundleId));
            } catch (RejectedExecutionException exception) {
                log.warn(
                        "Claimable bundle not queued because worker queue is full: bundleId={} instanceId={}",
                        bundleId,
                        instanceId()
                );
                return;
            }
        }
        if (!bundleIds.isEmpty()) {
            log.info("Claimable bundles queued: count={} instanceId={}", bundleIds.size(), instanceId());
        }
    }

    public BundleResponse transitionBundle(String bundleId, BundleStatus nextStatus){
        BundleJob job=getRequiredJob(bundleId, "Bundle transition failed");
        // Only one thread at a time can transition this specific bundle job
        //Before running this block, acquire the lock associated with the job object. Only one thread can hold that lock at a time.
        synchronized (job) {
            BundleStatus currentStatus = job.getStatus();

            if (!currentStatus.canTransitionTo(nextStatus)) {
                log.warn(
                        "Invalid bundle status transition requested: bundleId={} currentStatus={} nextStatus={}",
                        bundleId,
                        currentStatus,
                        nextStatus
                );
                throw new InvalidBundleStateTransitionException(currentStatus, nextStatus);
            }
            job.setStatus(nextStatus);
            job.setUpdatedAt(Instant.now());
            if (nextStatus == BundleStatus.PROCESSING && job.getStartedAt() == null) {
                job.setStartedAt(job.getUpdatedAt());
                job.setAttemptCount(job.getAttemptCount() + 1);
            }
            if (nextStatus == BundleStatus.COMPLETE || nextStatus == BundleStatus.FAILED) {
                job.setCompletedAt(job.getUpdatedAt());
                job.setLockedBy(null);
                job.setLockExpiresAt(null);
            }
            bundleJobMetadataService.save(job);
            log.info(
                    "Bundle status transitioned: bundleId={} fromStatus={} toStatus={}",
                    bundleId,
                    currentStatus,
                    nextStatus
            );
        }

        return toResponse(job);
    }

    //###########################################

    public BundleStatus getBundleStatusValue(String bundleId){
        BundleJob job=getRequiredJob(bundleId, "Bundle status lookup failed");
        return job.getStatus();
    }

    public String getBundleDownloadUrl(String bundleId) {
        BundleJob job=getRequiredJob(bundleId, "Bundle download URL lookup failed");
        if (job.getStatus() == BundleStatus.FAILED) {
            log.warn(
                    "Bundle download URL requested after failure: bundleId={} errorMessage={}",
                    bundleId,
                    job.getErrorMessage()
            );
            throw new BundleFailedException(bundleId, job.getErrorMessage());
        }
        if (job.getStatus() != BundleStatus.COMPLETE || job.getResultObjectKey() == null) {
            log.warn(
                    "Bundle download URL requested before ready: bundleId={} status={} hasResultObjectKey={}",
                    bundleId,
                    job.getStatus(),
                    job.getResultObjectKey() != null
            );
            throw new BundleNotReadyException(bundleId);
        }
        return bundleObjectStorageService.createDownloadUrl(job.getResultObjectKey());
    }


    //########################### Helper function
    private void processBundle(String bundleId) {
        String instanceId = instanceId();
        ScheduledExecutorService lockHeartbeat = null;
        try{
            Instant now = Instant.now();
            Instant lockExpiresAt = now.plusSeconds(effectiveLockDurationSeconds());
            BundleJob claimedJob = bundleJobMetadataService.claimForProcessing(
                    bundleId,
                    instanceId,
                    now,
                    lockExpiresAt
            ).orElse(null);

            if (claimedJob == null) {
                log.info("Bundle processing skipped because claim was not acquired: bundleId={} instanceId={}", bundleId, instanceId);
                return;
            }

            log.info(
                    "Bundle processing claimed: bundleId={} instanceId={} lockExpiresAt={}",
                    bundleId,
                    instanceId,
                    lockExpiresAt
            );

            lockHeartbeat = startClaimHeartbeat(bundleId, instanceId);

            Instant archiveStartedAt = Instant.now();
            Path archivePath = buildArchiveWithConfiguredStrategy(claimedJob);
            Instant archiveCompletedAt = Instant.now();
            // After the ZIP is created locally, upload it and persist the object key for later downloads.
            Instant uploadStartedAt = Instant.now();
            BundleObjectStorageService.UploadResult uploadResult = bundleObjectStorageService.uploadBundle(
                    claimedJob.getId(),
                    archivePath
            );
            Instant uploadCompletedAt = Instant.now();
            Instant completedAt = Instant.now();
            boolean completed = bundleJobMetadataService.completeClaimedJob(
                    bundleId,
                    instanceId,
                    archivePath,
                    uploadResult == null ? null : uploadResult.getObjectKey(),
                    archiveStartedAt,
                    archiveCompletedAt,
                    uploadStartedAt,
                    uploadCompletedAt,
                    durationMillis(archiveStartedAt, archiveCompletedAt),
                    durationMillis(uploadStartedAt, uploadCompletedAt),
                    durationMillis(claimedJob.getStartedAt(), completedAt),
                    completedAt
            );
            if (!completed) {
                log.warn(
                        "Bundle processing completed locally but DB claim was lost before completion: bundleId={} instanceId={} archivePath={}",
                        bundleId,
                        instanceId,
                        archivePath
                );
                return;
            }
            log.info(
                    "Bundle processing completed: bundleId={} instanceId={} archivePath={} archiveDurationMs={} uploadDurationMs={} totalProcessingDurationMs={}",
                    bundleId,
                    instanceId,
                    archivePath,
                    durationMillis(archiveStartedAt, archiveCompletedAt),
                    durationMillis(uploadStartedAt, uploadCompletedAt),
                    durationMillis(claimedJob.getStartedAt(), completedAt)
            );

        }

        catch (Exception exception){
            boolean failed = bundleJobMetadataService.failClaimedJob(bundleId, instanceId, exception.getMessage(), Instant.now());
            if (failed) {
                log.error("Bundle processing failed: bundleId={} instanceId={} message={}", bundleId, instanceId, exception.getMessage(), exception);
            } else {
                log.error(
                        "Bundle processing failed locally but DB claim was not owned by this instance: bundleId={} instanceId={} message={}",
                        bundleId,
                        instanceId,
                        exception.getMessage(),
                        exception
                );
            }
        }
        finally {
            if (lockHeartbeat != null) {
                lockHeartbeat.shutdownNow();
            }
        }
    }

    private ScheduledExecutorService startClaimHeartbeat(String bundleId, String instanceId) {
        long intervalSeconds = effectiveLockHeartbeatIntervalSeconds();
        ScheduledExecutorService heartbeat = Executors.newSingleThreadScheduledExecutor(runnable -> {
            Thread thread = new Thread(runnable, "bundle-lock-heartbeat-" + bundleId);
            thread.setDaemon(true);
            return thread;
        });
        heartbeat.scheduleWithFixedDelay(
                () -> refreshClaimLock(bundleId, instanceId),
                intervalSeconds,
                intervalSeconds,
                TimeUnit.SECONDS
        );
        return heartbeat;
    }

    private void refreshClaimLock(String bundleId, String instanceId) {
        try {
            Instant now = Instant.now();
            Instant lockExpiresAt = now.plusSeconds(effectiveLockDurationSeconds());
            boolean refreshed = bundleJobMetadataService.refreshClaimLock(bundleId, instanceId, now, lockExpiresAt);
            if (refreshed) {
                log.debug(
                        "Bundle processing claim refreshed: bundleId={} instanceId={} lockExpiresAt={}",
                        bundleId,
                        instanceId,
                        lockExpiresAt
                );
            } else {
                log.warn(
                        "Bundle processing claim refresh skipped because claim is no longer owned: bundleId={} instanceId={}",
                        bundleId,
                        instanceId
                );
            }
        } catch (Exception exception) {
            log.warn(
                    "Bundle processing claim refresh failed: bundleId={} instanceId={} message={}",
                    bundleId,
                    instanceId,
                    exception.getMessage()
            );
        }
    }

    private Path buildArchiveWithConfiguredStrategy(BundleJob job) throws Exception {
        String strategy = archiveStrategy == null ? "current" : archiveStrategy.trim().toLowerCase();
        log.info("Bundle archive strategy selected: bundleId={} strategy={}", job.getId(), strategy);
        long strategyStartNanos = System.nanoTime();

        // Switch strategies from application.properties:
        // - current: concurrent downloads to staging, then one sequential ZIP pass
        // - batch: old fixed-size batch download comparison
        // - streaming: sequential direct download-to-ZIP comparison
        // - hybrid: bounded concurrent download prefetch feeding one ZIP writer
        try {
            Path archivePath = switch (strategy) {
                case "batch" -> batchBundleArchiveService.buildArchive(job);
                case "streaming" -> streamingBundleArchiveService.buildArchive(job);
                case "hybrid" -> bundleArchiveHybridService.buildArchiveHybrid(job);
                case "current" -> currentBundleArchiveService.buildArchive(job);
                default -> {
                    log.warn(
                            "Unknown bundle archive strategy requested: bundleId={} strategy={} fallingBackTo=current",
                            job.getId(),
                            strategy
                    );
                    strategy = "current";
                    yield currentBundleArchiveService.buildArchive(job);
                }
            };
            log.info(
                    "Bundle archive strategy completed: bundleId={} strategy={} totalElapsedMs={} archivePath={}",
                    job.getId(),
                    strategy,
                    elapsedMillis(strategyStartNanos),
                    archivePath
            );
            return archivePath;
        } catch (Exception exception) {
            log.error(
                    "Bundle archive strategy failed: bundleId={} strategy={} totalElapsedMs={} message={}",
                    job.getId(),
                    strategy,
                    elapsedMillis(strategyStartNanos),
                    exception.getMessage()
            );
            throw exception;
        }
    }

    private long elapsedMillis(long startNanos) {
        return Duration.ofNanos(System.nanoTime() - startNanos).toMillis();
    }

    private Long durationMillis(Instant startedAt, Instant completedAt) {
        if (startedAt == null || completedAt == null) {
            return null;
        }
        return Duration.between(startedAt, completedAt).toMillis();
    }

    private BundleJob getRequiredJob(String bundleId, String logMessage) {
        return bundleJobMetadataService.findById(bundleId)
                .orElseThrow(() -> {
                    log.warn("{}: bundleId={} not found", logMessage, bundleId);
                    return new BundleNotFoundException(bundleId);
                });
    }

    private String instanceId() {
        if (configuredInstanceId != null && !configuredInstanceId.isBlank()) {
            return configuredInstanceId.trim();
        }
        return fallbackInstanceId;
    }

    private long effectiveLockDurationSeconds() {
        return lockDurationSeconds > 0 ? lockDurationSeconds : 600;
    }

    private long effectiveLockHeartbeatIntervalSeconds() {
        return Math.max(10, Math.min(300, effectiveLockDurationSeconds() / 3));
    }

    private int effectiveClaimScanBatchSize() {
        return claimScanBatchSize > 0 ? claimScanBatchSize : 20;
    }

}
