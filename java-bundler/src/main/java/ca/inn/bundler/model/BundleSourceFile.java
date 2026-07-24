package ca.inn.bundler.model;

import jakarta.persistence.Embeddable;
import jakarta.persistence.Column;
import jakarta.validation.constraints.NotBlank;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
@Embeddable
public class BundleSourceFile
{
    @NotBlank
    @Column(columnDefinition = "text")
    private String url;

    @NotBlank
    @Column(columnDefinition = "text")
    private String relativePath;

}
