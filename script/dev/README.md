# create_sample_dataset_v1.py

Create a synthetic local folder dataset for development and UI upload testing.

This script only creates files and folders on your local filesystem. It does
not call the backend, Keycloak, MinIO, or any upload API. After generation, use
the application UI to upload the generated folder.

## Location

```bash
script/dev/create_sample_dataset_v1.py
```

## Basic Usage

From the git repo root:

```bash
python3 script/dev/create_sample_dataset_v1.py \
  --output-path /tmp/sample_dataset_v1
```

Defaults:

- total size: `4gb`
- total files: `120`
- total folders: `60`
- root entries: `30`
- chunk size: `8mib`
- deterministic content seed: `sample_dataset_v1`

## Dry Run

Use `--dry-run` to inspect the planned layout without creating files:

```bash
python3 script/dev/create_sample_dataset_v1.py \
  --output-path /tmp/sample_dataset_v1 \
  --dry-run
```

## All Configurable Parameters

```bash
python3 script/dev/create_sample_dataset_v1.py \
  --output-path /tmp/sample_dataset_v1 \
  --total-size 4gb \
  --total-files 120 \
  --total-folders 60 \
  --root-entries 30 \
  --chunk-size 8mib \
  --seed sample_dataset_v1 \
  --progress-every 5 \
  --overwrite-files \
  --dry-run
```

Notes:

- `--output-path` is required.
- `--total-size` accepts values like `500mb`, `4gb`, `4gib`, or raw bytes.
- `--total-files` must be greater than or equal to `--total-folders`, so each folder can contain at least one file.
- `--root-entries` is the number of direct files/folders under `--output-path`.
- Remove `--dry-run` when you want to actually create the dataset.
- Use `--overwrite-files` only when you want to replace existing generated files.

## Example: Smaller Dataset

```bash
python3 script/dev/create_sample_dataset_v1.py \
  --output-path /tmp/sample_dataset_small \
  --total-size 500mb \
  --total-files 50 \
  --total-folders 20 \
  --root-entries 15
```

## Example: Default 4 GB Dataset

```bash
python3 script/dev/create_sample_dataset_v1.py \
  --output-path /tmp/sample_dataset_v1
```

After this finishes, upload `/tmp/sample_dataset_v1` through the application UI.
