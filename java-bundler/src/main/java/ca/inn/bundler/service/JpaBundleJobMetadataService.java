package ca.inn.bundler.service;

import ca.inn.bundler.model.BundleJob;
import ca.inn.bundler.model.BundleJobEntity;
import ca.inn.bundler.repository.BundleJobJpaRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;
import java.util.Optional;

@Service
@RequiredArgsConstructor
public class JpaBundleJobMetadataService {
    private final BundleJobJpaRepository repository;

    @Transactional
    public BundleJob create(BundleJob job) {
        return toDomain(repository.save(toEntity(job)));
    }

    @Transactional(readOnly = true)
    public Optional<BundleJob> findById(String id) {
        return repository.findById(id).map(this::toDomain);
    }

    @Transactional(readOnly = true)
    public List<BundleJob> findAll() {
        return repository.findAll(Sort.by(Sort.Direction.DESC, "createdAt"))
                .stream()
                .map(this::toDomain)
                .toList();
    }

    @Transactional(readOnly = true)
    public List<String> findClaimableJobIds(Instant now, int limit) {
        return repository.findClaimableJobIds(now, limit);
    }

    @Transactional(readOnly = true)
    public List<String> findRetentionEligibleJobIds(Instant completedBefore, int limit) {
        return repository.findRetentionEligibleJobIds(completedBefore, limit);
    }

    @Transactional
    public BundleJob save(BundleJob job) {
        return toDomain(repository.save(toEntity(job)));
    }

    @Transactional
    public Optional<BundleJob> claimForProcessing(String id, String instanceId, Instant now, Instant lockExpiresAt) {
        int claimedRows = repository.claimForProcessing(id, instanceId, now, lockExpiresAt);
        if (claimedRows == 0) {
            return Optional.empty();
        }
        return findById(id);
    }

    @Transactional
    public boolean completeClaimedJob(String id, String instanceId, Path archivePath, Instant now) {
        return repository.completeClaimedJob(id, instanceId, pathToString(archivePath), now) == 1;
    }

    @Transactional
    public boolean failClaimedJob(String id, String instanceId, String errorMessage, Instant now) {
        return repository.failClaimedJob(id, instanceId, errorMessage, now) == 1;
    }

    @Transactional
    public void deleteById(String id) {
        repository.deleteById(id);
    }

    private BundleJobEntity toEntity(BundleJob job) {
        return BundleJobEntity.builder()
                .id(job.getId())
                .status(job.getStatus())
                .folderName(job.getFolderName())
                .compression(job.getCompression())
                .files(job.getFiles())
                .archivePath(pathToString(job.getArchivePath()))
                .resultUrl(job.getResultUrl())
                .errorMessage(job.getErrorMessage())
                .createdAt(job.getCreatedAt())
                .updatedAt(job.getUpdatedAt())
                .startedAt(job.getStartedAt())
                .completedAt(job.getCompletedAt())
                .lockedBy(job.getLockedBy())
                .lockExpiresAt(job.getLockExpiresAt())
                .attemptCount(job.getAttemptCount())
                .bundleFingerprint(job.getBundleFingerprint())
                .fingerprintAlgorithm(job.getFingerprintAlgorithm())
                .build();
    }

    private BundleJob toDomain(BundleJobEntity entity) {
        return BundleJob.builder()
                .id(entity.getId())
                .status(entity.getStatus())
                .folderName(entity.getFolderName())
                .compression(entity.getCompression())
                .files(entity.getFiles())
                .archivePath(entity.getArchivePath() == null ? null : Path.of(entity.getArchivePath()))
                .resultUrl(entity.getResultUrl())
                .errorMessage(entity.getErrorMessage())
                .createdAt(entity.getCreatedAt())
                .updatedAt(entity.getUpdatedAt())
                .startedAt(entity.getStartedAt())
                .completedAt(entity.getCompletedAt())
                .lockedBy(entity.getLockedBy())
                .lockExpiresAt(entity.getLockExpiresAt())
                .attemptCount(entity.getAttemptCount())
                .bundleFingerprint(entity.getBundleFingerprint())
                .fingerprintAlgorithm(entity.getFingerprintAlgorithm())
                .build();
    }

    private String pathToString(Path path) {
        return path == null ? null : path.toString();
    }
}
