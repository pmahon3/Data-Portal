package ca.inn.bundler.repository;

import ca.inn.bundler.model.BundleJobEntity;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.time.Instant;
import java.util.List;

public interface BundleJobJpaRepository extends JpaRepository<BundleJobEntity, String> {
    @Query(value = """
            select id
            from bundle_jobs
            where status = 'pending'
               or (status = 'processing' and lock_expires_at < :now)
            order by created_at asc
            limit :limit
            """, nativeQuery = true)
    List<String> findClaimableJobIds(@Param("now") Instant now, @Param("limit") int limit);

    @Query(value = """
            select id
            from bundle_jobs
            where status in ('complete', 'failed')
              and completed_at is not null
              and completed_at < :completedBefore
            order by completed_at asc
            limit :limit
            """, nativeQuery = true)
    List<String> findRetentionEligibleJobIds(
            @Param("completedBefore") Instant completedBefore,
            @Param("limit") int limit
    );

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query(value = """
            update bundle_jobs
            set status = 'processing',
                locked_by = :instanceId,
                lock_expires_at = :lockExpiresAt,
                started_at = coalesce(started_at, :now),
                updated_at = :now,
                completed_at = null,
                error_message = null,
                attempt_count = attempt_count + 1
            where id = :id
              and (
                    status = 'pending'
                    or (status = 'processing' and lock_expires_at < :now)
                  )
            """, nativeQuery = true)
    int claimForProcessing(
            @Param("id") String id,
            @Param("instanceId") String instanceId,
            @Param("now") Instant now,
            @Param("lockExpiresAt") Instant lockExpiresAt
    );

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query(value = """
            update bundle_jobs
            set status = 'complete',
                archive_path = :archivePath,
                updated_at = :now,
                completed_at = :now,
                locked_by = null,
                lock_expires_at = null
            where id = :id
              and status = 'processing'
              and locked_by = :instanceId
            """, nativeQuery = true)
    int completeClaimedJob(
            @Param("id") String id,
            @Param("instanceId") String instanceId,
            @Param("archivePath") String archivePath,
            @Param("now") Instant now
    );

    @Modifying(clearAutomatically = true, flushAutomatically = true)
    @Query(value = """
            update bundle_jobs
            set status = 'failed',
                error_message = :errorMessage,
                updated_at = :now,
                completed_at = :now,
                locked_by = null,
                lock_expires_at = null
            where id = :id
              and status = 'processing'
              and locked_by = :instanceId
            """, nativeQuery = true)
    int failClaimedJob(
            @Param("id") String id,
            @Param("instanceId") String instanceId,
            @Param("errorMessage") String errorMessage,
            @Param("now") Instant now
    );
}
