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
import org.springframework.stereotype.Service;

import java.nio.file.Path;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.RejectedExecutionException;

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

    @Value("${bundler.archive.strategy:current}")
    private String archiveStrategy;

    // This needs to be changed in future to a database or in memory database
    private final Map<String, BundleJob> jobs=new ConcurrentHashMap<>();

    public BundleResponse createBundle(CreateBundleRequest request){
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
        jobs.put(id, job);
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
            jobs.remove(id);
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
        BundleJob job=jobs.get(bundleId);
        if (job==null){
            log.warn("Bundle lookup failed: bundleId={} not found", bundleId);
            throw new BundleNotFoundException(bundleId);
        }
        return toResponse(job);
    }

    public List<BundleResponse> getAllBundles() {
        log.info("Listing all in-memory bundle jobs: count={}", jobs.size());
        return jobs.values().stream()
                .map(this::toResponse)
                .toList();
    }

    private BundleResponse toResponse(BundleJob job) {
        return BundleResponse.builder()
                .id(job.getId())
                .status(job.getStatus())
                .createdAt(job.getCreatedAt())
                .updatedAt(job.getUpdatedAt())
                .resultUrl(job.getResultUrl())
                .errorMessage(job.getErrorMessage())
                .build();
    }

    public BundleResponse transitionBundle(String bundleId, BundleStatus nextStatus){
        BundleJob job=jobs.get(bundleId);
        if (job==null){
            log.warn("Bundle transition failed: bundleId={} not found", bundleId);
            throw new BundleNotFoundException(bundleId);
        }
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
        BundleJob job=jobs.get(bundleId);
        if (job==null){
            log.warn("Bundle status lookup failed: bundleId={} not found", bundleId);
            throw new BundleNotFoundException(bundleId);
        }
        return job.getStatus();
    }

    public Path getArchivePath(String bundleId){
        BundleJob job=jobs.get(bundleId);
        if (job==null){
            log.warn("Bundle archive lookup failed: bundleId={} not found", bundleId);
            throw new BundleNotFoundException(bundleId);
        }
        if (job.getStatus() == BundleStatus.FAILED) {
            log.warn(
                    "Bundle archive requested after failure: bundleId={} errorMessage={}",
                    bundleId,
                    job.getErrorMessage()
            );
            throw new BundleFailedException(bundleId, job.getErrorMessage());
        }
        if (job.getStatus() != BundleStatus.COMPLETE || job.getArchivePath() == null) {
            log.warn(
                    "Bundle archive requested before ready: bundleId={} status={} hasArchivePath={}",
                    bundleId,
                    job.getStatus(),
                    job.getArchivePath() != null
            );
            throw new BundleNotReadyException(bundleId);
        }
        return job.getArchivePath();
    }


    //########################### Helper function
    private void processBundle(String bundleId) {
        try{
            log.info("Bundle processing started: bundleId={}", bundleId);
            transitionBundle(bundleId, BundleStatus.PROCESSING);

            BundleJob job=jobs.get(bundleId);
            Path archivePath = buildArchiveWithConfiguredStrategy(job);
            synchronized (job) {
                job.setArchivePath(archivePath);
            }
            transitionBundle(bundleId, BundleStatus.COMPLETE);
            log.info("Bundle processing completed: bundleId={} archivePath={}", bundleId, archivePath);

        }

        catch (Exception exception){
            BundleJob job = jobs.get(bundleId);
            if (job != null) {
                synchronized (job) {
                    job.setErrorMessage(exception.getMessage());
                }
            }
            log.error("Bundle processing failed: bundleId={} message={}", bundleId, exception.getMessage(), exception);
            transitionBundle(bundleId, BundleStatus.FAILED);
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


}
