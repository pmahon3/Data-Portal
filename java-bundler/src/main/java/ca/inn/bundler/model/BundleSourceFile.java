package ca.inn.bundler.model;

import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BundleSourceFile
{
    @NotBlank
    private String url;
    @NotBlank
    private String relativePath;

}
