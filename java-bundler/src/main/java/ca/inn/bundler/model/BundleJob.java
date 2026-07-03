package ca.inn.bundler.model;

import lombok.*;

import java.nio.file.Path;
import java.time.Instant;
import java.util.List;

@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class BundleJob {
    private String id;
    private BundleStatus status;
    private Instant createdAt;
    private Instant updatedAt;
    private String folderName;
    private String compression;
    private List<BundleSourceFile> files;
    private Path archivePath;
    private String resultUrl;
    private String errorMessage;
}
