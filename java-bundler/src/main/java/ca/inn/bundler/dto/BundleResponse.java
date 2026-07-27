package ca.inn.bundler.dto;

import ca.inn.bundler.model.BundleStatus;
import lombok.*;

import java.time.Instant;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BundleResponse {

    private String id;
    private BundleStatus status;
    private Instant createdAt;
    private Instant updatedAt;
    private Instant startedAt;
    private Instant completedAt;
    private Instant archiveStartedAt;
    private Instant archiveCompletedAt;
    private Instant uploadStartedAt;
    private Instant uploadCompletedAt;
    private Long archiveDurationMillis;
    private Long uploadDurationMillis;
    private Long totalDurationMillis;
    private String resultObjectKey;
    private String errorMessage;
}
