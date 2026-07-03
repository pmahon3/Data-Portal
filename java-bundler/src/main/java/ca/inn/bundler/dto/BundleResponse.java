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
    private String resultUrl;
    private String errorMessage;
}
