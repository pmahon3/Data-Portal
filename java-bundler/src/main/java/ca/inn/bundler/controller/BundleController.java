package ca.inn.bundler.controller;


import ca.inn.bundler.dto.BundleResponse;
import ca.inn.bundler.dto.BundleDownloadUrlResponse;
import ca.inn.bundler.dto.CreateBundleRequest;
import ca.inn.bundler.service.BundleService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

@RestController
@Slf4j
@RequiredArgsConstructor
public class BundleController {

    private final BundleService bundleService;

    @PostMapping("/bundles")
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
    @GetMapping("/bundles/{bundleId}")
    public ResponseEntity<BundleResponse> getBundle(@PathVariable String bundleId) {
        log.debug("Bundle status requested: bundleId={}", bundleId);
        BundleResponse bundleResponse = bundleService.getBundle(bundleId);
        return ResponseEntity.accepted().body(bundleResponse);
    }

    @GetMapping("/bundles/admin/jobs")
    public ResponseEntity<List<BundleResponse>> getAllBundles() {
        log.info("All bundle jobs requested");
        return ResponseEntity.ok(bundleService.getAllBundles());
    }

    @GetMapping("/bundles/{bundleId}/download")
    public ResponseEntity<BundleDownloadUrlResponse> getBundleDownloadUrl(@PathVariable String bundleId) {
        log.info("Bundle download URL requested: bundleId={}", bundleId);
        BundleResponse bundleResponse = bundleService.getBundle(bundleId);
        String resultUrl = bundleService.getBundleDownloadUrl(bundleId);
        return ResponseEntity.ok(BundleDownloadUrlResponse.builder()
                .id(bundleId)
                .resultUrl(resultUrl)
                .resultObjectKey(bundleResponse.getResultObjectKey())
                .build());
    }

}
