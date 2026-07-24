package ca.inn.bundler.model;

import jakarta.persistence.Column;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.FetchType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OrderColumn;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.Instant;
import java.util.List;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
@Entity
@Table(name = "bundle_jobs")
public class BundleJobEntity {
    @Id
    private String id;

    @Column(nullable = false)
    private BundleStatus status;

    private String folderName;

    @Column(nullable = false)
    private String compression;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(name = "bundle_job_files", joinColumns = @JoinColumn(name = "bundle_job_id"))
    @OrderColumn(name = "file_order")
    private List<BundleSourceFile> files;

    private String archivePath;
    private String resultUrl;

    @Column(length = 4096)
    private String errorMessage;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private Instant updatedAt;

    private Instant startedAt;
    private Instant completedAt;
    private String lockedBy;
    private Instant lockExpiresAt;

    @Column(nullable = false)
    private int attemptCount;

    private String bundleFingerprint;
    private String fingerprintAlgorithm;
}
