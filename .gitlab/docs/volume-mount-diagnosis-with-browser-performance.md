# Browser performance job volume mount report

## Summary

The Auto DevOps `browser_performance` job (Sitespeed.io + `gitlab-exporter`) relies on a bind mount:

```bash
docker run -v "$(pwd)":/sitespeed.io ...
```

On this runner, the bind mount did **not** expose the job’s repository contents to the Sitespeed container, causing the plugin path `./gitlab-exporter/index.js` to be missing at runtime and preventing generation of `sitespeed-results/data/performance.json`.

## Impact / symptoms

- **Job container** shows repository contents at `pwd=/builds/rcg/INN-Data-Portal` (including `gitlab-exporter/`).
- A child container started by `docker run -v "$(pwd)":/mnt ...` does **not** see the same contents. Diagnostic output showed `.gitlab-ci.yml` was missing from `/mnt`.
- As a consequence, Sitespeed’s plugin load target `./gitlab-exporter/index.js` is not present inside the Sitespeed container, and `performance.json` is not generated.

## Reproduction (situation that recreates the issue)

This occurs when all of the following are true:

- GitLab Runner executor is **docker**.
- Jobs talk to the **host Docker daemon** via `/var/run/docker.sock`.
- The job build directory `/builds/...` inside the job container is backed by a **Docker volume** (default runner behavior) rather than a host directory at the same absolute path.
- A job runs a nested container using a bind mount of a path that only exists inside the job container:

```bash
docker run --rm -v "$(pwd)":/mnt alpine sh -c 'head -1 /mnt/.gitlab-ci.yml'
```

Result: `/mnt/.gitlab-ci.yml` is missing (or unrelated), proving the host daemon cannot bind-mount the job’s checkout by path.

## Root cause

With the docker executor, the job’s checkout directory (`/builds/...`) can be provided as a **Docker volume** mounted into the job container. That directory is real inside the job container, but **not a host directory** at the same path.

When the job runs:

```bash
docker run -v /builds/rcg/INN-Data-Portal:/sitespeed.io ...
```

the **host Docker daemon** resolves `/builds/rcg/INN-Data-Portal` on the **host filesystem**, not inside the job container. If the host doesn’t have that path populated with the checkout, the Sitespeed container will see empty/wrong content.

## Fix

Make the build directory a **host path** and mount it into job containers at the same location.

### Runner config (docker executor)

In the runner’s `config.toml`:

```toml
[runners.docker]
  volumes = [
    "/cache",
    "/dind-cache:/dind-cache",
    "/var/run/docker.sock:/var/run/docker.sock",
    "/builds:/builds"
  ]
```

On the host:

```bash
sudo mkdir -p /builds
sudo chmod 1777 /builds
```

If the runner itself is containerized (docker-compose), also mount `/builds:/builds` into the runner container so the path exists consistently from the runner’s POV.

## Verification

Re-run the diagnostic in CI:

```bash
docker run --rm -v "$(pwd)":/mnt alpine sh -c \
  'head -1 /mnt/.gitlab-ci.yml && ls /mnt/gitlab-exporter | head -3'
```

Expected:

- First line of `.gitlab-ci.yml` prints (file exists).
- `gitlab-exporter` directory entries are visible.

Once this is true, the original Auto DevOps job’s `-v "$(pwd)":/sitespeed.io` will mount the correct checkout into the Sitespeed container and the plugin path will resolve.

## Notes on `gitlab-exporter` / `performance.json`

- In the stock GitLab template, `performance.json` is expected at `sitespeed-results/data/performance.json` and then renamed to `browser-performance.json`.
- The `gitlab-exporter` plugin is responsible for producing that GitLab-format JSON. If it can’t be loaded (missing path due to mount mismatch), the file will not be created.

## Potential next steps (DinD and other options)

### DinD (docker:dind service)

If you enable DinD for the job (`services: [docker:dind]`), nested `docker run -v "$(pwd)":...` binds paths relative to the **DinD daemon container’s filesystem**, not the job container and not the host. Unless you also arrange for the checkout to exist in the DinD container at the same absolute path, the same class of failure returns.

For browser performance testing that needs bind-mounting the repo into a nested container, the simplest approach is:

- Use the **host socket** (no DinD) for this job, and
- Ensure builds are on a **host path** (the fix above).

### Fallback approaches (if you can’t change runner filesystem)

- **`docker cp` workflow**: create a Sitespeed container, `docker cp` the checkout into `/sitespeed.io`, run it, then `docker cp` results out. This bypasses bind-mount assumptions but is slower and more complex.
- **Artifacts-only debugging**: keep the debug override job (logs + artifacts) to isolate plugin vs runtime vs environment issues.
