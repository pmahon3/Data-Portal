package ca.inn.bundler.controller;


import ca.inn.bundler.dto.BundleResponse;
import ca.inn.bundler.dto.CreateBundleRequest;
import ca.inn.bundler.service.BundleService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.nio.file.Path;
import java.util.List;

@RestController
// For now, keep legacy(v1), current (with no version), and v2 bundle routes on the same handler while their behavior is identical.

@RequestMapping({
        "/bundles",
        "/v1/bundles",
        "/v2/bundles"
})
@Slf4j
@RequiredArgsConstructor
public class BundleController {

    private final BundleService bundleService;

    @PostMapping
    public ResponseEntity<BundleResponse> createBundle(
            @Valid @RequestBody CreateBundleRequest request
    ){
        log.info(
                "Bundle create request received: folderName={} fileCount={} compression={}",
                request.getFolderName(),
                request.getFiles().size(),
                request.getCompression()
        );
        BundleResponse bundleResponse = bundleService.createBundle(request);
        log.info("Bundle create request accepted: bundleId={}", bundleResponse.getId());
        return ResponseEntity.accepted().body(bundleResponse);
    }

    //Return metadata/status about the bundle job.
    // accepted means 202 http code. Means the request accepted but the bundle is going to be created in async mode.
    @GetMapping("/{bundleId}")
    public ResponseEntity<BundleResponse> getBundle(@PathVariable String bundleId) {
        log.info("Bundle status requested: bundleId={}", bundleId);
        BundleResponse bundleResponse = bundleService.getBundle(bundleId);
        return ResponseEntity.accepted().body(bundleResponse);
    }

    @GetMapping("/admin/jobs")
    public ResponseEntity<List<BundleResponse>> getAllBundles() {
        log.info("All bundle jobs requested");
        return ResponseEntity.ok(bundleService.getAllBundles());
    }

    //The download request was accepted, but the ZIP is not ready yet, and I am not returning any file body.
    @GetMapping("/{bundleId}/download")
    public ResponseEntity<FileSystemResource> downloadBundle(@PathVariable String bundleId) {
        log.info("Bundle download requested: bundleId={}", bundleId);
        //Checking the status in the service layer
        Path archivePath=bundleService.getArchivePath(bundleId);

        // We return a Spring Resource here instead of manually writing to an OutputStream.
        // The archive already exists on disk, so Spring can stream the file response for us
        // and keep the controller focused on HTTP status/headers rather than file copy logic.
        // A manual streaming version would look roughly like:
        // StreamingResponseBody body = outputStream -> {
        //     try (InputStream inputStream = Files.newInputStream(archivePath)) {
        //         inputStream.transferTo(outputStream);
        //     }
        // };
        // We are not doing that here because the archive already exists on disk and a
        // FileSystemResource a wrapper around the file that is later being used by Spring MVC to stream the file to client (using io internally)

        FileSystemResource resource=new FileSystemResource(archivePath);
        log.info("Bundle download ready: bundleId={} archivePath={}", bundleId, archivePath);

        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"bundle.zip\"")
                .body(resource);
    }


}
