# Java Bundler Action Plan

This plan is for building a Java Spring Boot version of the Bundler service step by step. The goal is not only to replace the current implementation, but to use the core Java concepts needed for large file bundling: thread pools, async execution, streaming I/O, memory control, backpressure, retries, and horizontal scaling.

## Action Plan

1. Define the target Bundler contract
   - Read the current Bundler OpenAPI contract in `bundler/openapi.yaml`.
   - Keep the first Java version API-compatible with the current routes:
     - `POST /bundles`
     - `GET /bundles/{bundleId}`
     - `GET /bundles/{bundleId}/download`
   - Confirm the request shape stays URL-based at first: backend sends presigned source URLs to Bundler.
   - Decide which fields are required for the Java MVP: `id`, `status`, `createdAt`, `updatedAt`, and optionally `resultUrl`.

2. Create a minimal Spring Boot service
   - Create a separate Java service directory, for example `bundler-java/`.
   - Use Spring Boot with Java 21.
   - Add only the first required dependencies:
     - Spring Web
     - Validation
     - Actuator
     - Test
   - Implement a simple `GET /health` or use Actuator health first.
   - Learn the Spring Boot request lifecycle before adding async work.

3. Implement the synchronous API skeleton
   - Add request and response DTOs matching the Bundler contract.
   - Implement `POST /bundles` so it validates input and returns a generated bundle ID with `pending` or `processing`.
   - Implement `GET /bundles/{bundleId}` using an in-memory map.
   - Implement `GET /bundles/{bundleId}/download` as a placeholder that returns `404` or `202`.
   - Keep this version intentionally simple so the HTTP contract is clear.

4. Model bundle job state explicitly
   - Create a `BundleJob` model with:
     - ID
     - status
     - source URLs
     - created and updated timestamps
     - output archive location
     - error message
   - Define allowed transitions:
     - `pending -> processing`
     - `processing -> complete`
     - `processing -> failed`
   - Add tests for valid and invalid state transitions.
   - Learn why explicit state transitions matter for background jobs.

5. Add a bounded worker thread pool
   - Create a Spring-managed `ThreadPoolTaskExecutor` or Java `ExecutorService`.
   - Start with a small fixed-size pool.
   - Submit bundle jobs from `POST /bundles` instead of processing them in the request thread.
   - Learn:
     - difference between request threads and worker threads
     - fixed thread pools
     - queue capacity
     - rejection policies
     - how a saturated worker pool behaves

6. Build the first ZIP using local staging
   - For the first working version, download each presigned URL to a temporary local file.
   - After all files download, create a ZIP file from the staged files.
   - Return the ZIP from `GET /bundles/{bundleId}/download`.
   - This intentionally mirrors the current design so it is easy to compare behavior.
   - Measure:
     - memory usage
     - temp disk usage
     - time to complete
     - behavior with many files

7. Replace full-file memory loading with streaming downloads
   - Ensure downloads use streaming APIs, not `byte[]` or full response buffering.
   - Use Java HTTP client or a mature HTTP client library with response streaming.
   - Write each response stream to disk using a fixed-size buffer.
   - Learn:
     - `InputStream`
     - `OutputStream`
     - buffer sizes
     - try-with-resources
     - why large files should not be loaded into heap memory

8. Add per-job download concurrency
   - Allow multiple source files in one bundle to download concurrently.
   - Use a bounded executor, semaphore, or structured concurrency pattern.
   - Keep a limit such as 4 downloads per bundle at first.
   - Learn:
     - global worker pool vs per-job concurrency
     - avoiding unbounded threads
     - `CompletableFuture`
     - semaphores
     - failure handling across parallel tasks

9. Add backpressure and limits
   - Add configurable limits:
     - max files per bundle
     - max active jobs
     - max queued jobs
     - max concurrent downloads
     - max temp disk usage if practical
   - Decide what HTTP response to return when the service is overloaded.
   - Learn:
     - bounded queues
     - load shedding
     - protecting the service from one large request

10. Improve archive path handling
    - Preserve folder hierarchy inside the ZIP.
    - Decode URL paths carefully.
    - Prevent path traversal entries like `../file`.
    - Add tests for nested folders, encoded spaces, duplicate names, empty folders, and unsafe paths.
    - Learn how archive names differ from local filesystem paths.

11. Stream ZIP creation directly from source URLs
    - Build a second implementation path that writes source streams directly into `ZipOutputStream`.
    - Avoid staging the full source files on local disk.
    - Start with sequential streaming first.
    - Learn:
      - `ZipOutputStream`
      - streaming one ZIP entry at a time
      - why ZIP output is naturally sequential
      - tradeoff between parallel downloads and sequential ZIP writing

12. Add a producer-consumer pipeline
    - Experiment with downloading files concurrently while ZIP writing remains sequential.
    - Use bounded queues between downloader tasks and the ZIP writer.
    - Ensure the queue stores bounded temporary chunks or bounded staged files, not unlimited data.
    - Learn:
      - producer-consumer design
      - blocking queues
      - backpressure between downloaders and writer
      - memory limits in streaming pipelines

13. Write completed archives to object storage
    - Instead of keeping completed ZIP files only on local disk, upload the result archive to object storage.
    - Return or store an object key for the generated ZIP.
    - Generate a presigned download URL for the final archive when the job completes.
    - Until that object-storage output path exists, consider a temporary Bundler-side capability URL model:
      - random download token
      - token expiry timestamp
      - download requires both bundle ID and valid unexpired token
    - Treat that as an interim measure, not the final security model.
    - This addresses horizontal scaling because any service instance can return job status and the user can download from object storage.

14. Add durable job metadata
    - Move job metadata from an in-memory map to a database or durable store.
    - Store:
      - bundle ID
      - request fingerprint
      - status
      - source URL count
      - output archive key
      - timestamps
      - error message
    - Learn why in-memory state breaks when containers restart or scale horizontally.

15. Add retry and timeout behavior
    - Add per-file download timeout.
    - Add retry with bounded attempts for transient failures.
    - Avoid retrying forever.
    - Track which file failed and why.
    - Learn:
      - transient vs permanent errors
      - timeout configuration
      - retry backoff
      - cancellation

16. Handle presigned URL expiry
    - Measure whether large jobs can exceed the source URL lifetime.
    - If needed, change the backend-Bundler contract so Bundler can request fresh URLs or receive longer-lived URLs.
    - Consider whether Bundler should receive file IDs instead of URLs in a future version.
    - Keep authorization in the backend unless the security model is intentionally redesigned.

17. Add observability
    - Add structured logs for job lifecycle events.
    - Add metrics:
      - active jobs
      - queued jobs
      - completed jobs
      - failed jobs
      - bytes downloaded
      - bytes zipped
      - job duration
      - download duration per file
    - Use Spring Boot Actuator metrics.
    - Learn how metrics reveal bottlenecks better than guesses.

18. Benchmark against realistic workloads
    - Create test datasets that represent expected production use:
      - many small files
      - few very large files
      - many large files
      - deeply nested folders
    - Record:
      - wall-clock time
      - heap memory
      - CPU
      - network throughput
      - temp disk usage
      - failure rate
    - Compare:
      - current Python Bundler
      - Java local-staging version
      - Java streaming version
      - Java object-storage-output version

19. Decide the deployment model
    - Decide whether Bundler should run as:
      - one API plus worker service
      - combined API and worker service
      - multiple worker replicas behind a queue
    - For large jobs, prefer separating API and worker responsibilities if the system grows.
    - Learn how horizontal scaling changes the need for durable queues and shared storage.

20. Plan backend integration changes
    - Keep the first integration compatible with the existing backend URL-based Bundler call.
    - Later, consider a v2 contract for better scaling:
      - backend sends file IDs and instance info
      - Bundler asks backend for fresh presigned URLs as needed
      - Bundler writes final ZIP to object storage
      - backend returns final archive status and download URL
    - Document security implications before changing what Bundler is allowed to access.

21. Add cleanup and retention
    - Define how long completed archives are retained.
    - Delete temporary files after job completion or failure.
    - Delete old generated ZIP objects from object storage.
    - Learn why large-file services need lifecycle management.

22. Add failure recovery
    - Decide what happens if the service restarts while jobs are running.
    - With durable job state, mark interrupted jobs as failed or retryable.
    - Avoid leaving jobs permanently stuck in `processing`.
    - Add startup repair logic for stale jobs.

23. Review security boundaries
    - Confirm Bundler does not bypass backend authorization.
    - Avoid logging presigned URLs.
    - Avoid exposing source URLs in status responses.
    - Validate archive paths.
    - Ensure generated archive URLs expire.
    - If Bundler serves temporary direct download URLs before object-storage output exists, require:
      - random download token
      - short expiry
      - rejection of expired or missing tokens

24. Make a migration decision
    - After benchmarks and operational review, decide whether to:
      - keep Python Bundler and improve it
      - replace it with Java Bundler
      - run both behind a feature flag
    - Base the decision on measured behavior, not language preference.
