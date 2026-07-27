package ca.inn.bundler.service;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.extern.slf4j.Slf4j;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.S3ClientBuilder;
import software.amazon.awssdk.services.s3.S3Configuration;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

import java.net.URI;
import java.nio.file.Path;
import java.time.Duration;

@Slf4j
@Service
public class BundleObjectStorageService {
    // Bundle output workflow:
    // 1. The archive service builds a ZIP on local disk.
    // 2. This service uploads that ZIP to S3-compatible object storage.
    // 3. The object key is saved with the bundle job, and download requests get a fresh presigned URL.
    // 4. Retention cleanup later deletes both the local ZIP and the uploaded object.
    @Getter
    @AllArgsConstructor
    public static class UploadResult {
        private String objectKey;
        private String presignedUrl;
    }

    @Value("${bundler.output.object-storage.endpoint:}")
    private String endpoint;

    @Value("${bundler.output.object-storage.region:us-east-1}")
    private String region;

    @Value("${bundler.output.object-storage.bucket:}")
    private String bucket;

    @Value("${bundler.output.object-storage.key-prefix:bundles}")
    private String keyPrefix;

    @Value("${bundler.output.object-storage.access-key-id:}")
    private String accessKeyId;

    @Value("${bundler.output.object-storage.secret-access-key:}")
    private String secretAccessKey;

    @Value("${bundler.output.object-storage.path-style-access:true}")
    private boolean pathStyleAccess;

    @Value("${bundler.output.object-storage.presigned-url-expiration-seconds:3600}")
    private long presignedUrlExpirationSeconds;

    public UploadResult uploadBundle(String bundleId, Path archivePath) {
        requireConfigured();
        String objectKey = buildObjectKey(bundleId);

        // Upload the completed local ZIP; source files are still downloaded through backend-generated URLs.
        try (S3Client client = s3Client()) {
            client.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket.trim())
                            .key(objectKey)
                            .contentType("application/zip")
                            .build(),
                    RequestBody.fromFile(archivePath)
            );
        }

        String presignedUrl = createDownloadUrl(objectKey);
        log.info("Bundle archive uploaded to object storage: bundleId={} bucket={} objectKey={}", bundleId, bucket, objectKey);
        return new UploadResult(objectKey, presignedUrl);
    }

    public String createDownloadUrl(String objectKey) {
        requireConfigured();
        if (objectKey == null || objectKey.isBlank()) {
            throw new IllegalArgumentException("Object key is required to create a bundle download URL");
        }

        // Generate URLs on demand so callers receive a fresh link after the bundle is complete.
        try (S3Presigner presigner = s3Presigner()) {
            GetObjectRequest getObjectRequest = GetObjectRequest.builder()
                    .bucket(bucket.trim())
                    .key(objectKey)
                    .responseContentType("application/zip")
                    .responseContentDisposition("attachment; filename=\"" + downloadFileName(objectKey) + "\"")
                    .build();

            GetObjectPresignRequest presignRequest = GetObjectPresignRequest.builder()
                    .signatureDuration(Duration.ofSeconds(effectivePresignedUrlExpirationSeconds()))
                    .getObjectRequest(getObjectRequest)
                    .build();

            return presigner.presignGetObject(presignRequest).url().toString();
        }
    }

    public boolean deleteBundleObject(String bundleId, String objectKey) {
        if (objectKey == null || objectKey.isBlank()) {
            return true;
        }
        requireConfigured();

        try (S3Client client = s3Client()) {
            client.deleteObject(DeleteObjectRequest.builder()
                    .bucket(bucket.trim())
                    .key(objectKey)
                    .build());
            log.info("Bundle object deleted by retention: bundleId={} bucket={} objectKey={}", bundleId, bucket, objectKey);
            return true;
        } catch (RuntimeException exception) {
            log.warn(
                    "Bundle object retention delete failed; metadata retained for retry: bundleId={} bucket={} objectKey={} message={}",
                    bundleId,
                    bucket,
                    objectKey,
                    exception.getMessage()
            );
            return false;
        }
    }

    private S3Client s3Client() {
        S3ClientBuilder builder = S3Client.builder()
                .region(Region.of(effectiveRegion()))
                .credentialsProvider(credentialsProvider())
                .serviceConfiguration(s3Configuration());

        if (endpoint != null && !endpoint.isBlank()) {
            builder.endpointOverride(URI.create(endpoint.trim()));
        }
        return builder.build();
    }

    private S3Presigner s3Presigner() {
        S3Presigner.Builder builder = S3Presigner.builder()
                .region(Region.of(effectiveRegion()))
                .credentialsProvider(credentialsProvider())
                .serviceConfiguration(s3Configuration());

        if (endpoint != null && !endpoint.isBlank()) {
            builder.endpointOverride(URI.create(endpoint.trim()));
        }
        return builder.build();
    }

    private StaticCredentialsProvider credentialsProvider() {
        return StaticCredentialsProvider.create(
                AwsBasicCredentials.create(accessKeyId.trim(), secretAccessKey.trim())
        );
    }

    private S3Configuration s3Configuration() {
        return S3Configuration.builder()
                .pathStyleAccessEnabled(pathStyleAccess)
                .build();
    }

    private String buildObjectKey(String bundleId) {
        String prefix = keyPrefix == null ? "" : keyPrefix.trim();
        if (prefix.startsWith("/")) {
            prefix = prefix.substring(1);
        }
        if (prefix.endsWith("/")) {
            prefix = prefix.substring(0, prefix.length() - 1);
        }
        String fileName = "bundle-" + bundleId + ".zip";
        return prefix.isBlank() ? fileName : prefix + "/" + fileName;
    }

    private String downloadFileName(String objectKey) {
        int slashIndex = objectKey.lastIndexOf('/');
        String fileName = slashIndex >= 0 ? objectKey.substring(slashIndex + 1) : objectKey;
        return fileName.isBlank() ? "bundle.zip" : fileName.replace("\"", "");
    }

    private void requireConfigured() {
        // The object-storage flow is the only bundle delivery path, so missing config is a job failure.
        if (bucket == null || bucket.isBlank()) {
            throw new IllegalStateException("Bundle object-storage bucket is not configured");
        }
        if (accessKeyId == null || accessKeyId.isBlank() || secretAccessKey == null || secretAccessKey.isBlank()) {
            throw new IllegalStateException("Bundle object-storage credentials are not configured");
        }
    }

    private String effectiveRegion() {
        return region == null || region.isBlank() ? "us-east-1" : region.trim();
    }

    private long effectivePresignedUrlExpirationSeconds() {
        return presignedUrlExpirationSeconds > 0 ? presignedUrlExpirationSeconds : 3600;
    }
}
