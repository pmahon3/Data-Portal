package ca.inn.bundler.dto;

import ca.inn.bundler.model.BundleSourceFile;
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotEmpty;
import lombok.*;

import java.util.List;

@Getter
@Setter
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class CreateBundleRequest {
    private String folderName;

    @Valid
    @NotEmpty
    private List<BundleSourceFile> files;

    @Builder.Default
    private String compression= "zip";

}
