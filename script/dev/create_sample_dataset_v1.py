#!/usr/bin/env python3
"""
Create a synthetic local folder dataset for development and UI upload testing.

This script only writes files and folders to a local path. It does not contact
the AMS backend, Keycloak, MinIO, or any other service.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
import time
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TOTAL_SIZE = "4gb"
DEFAULT_TOTAL_FILES = 120
DEFAULT_TOTAL_FOLDERS = 60
DEFAULT_ROOT_ENTRIES = 30
DEFAULT_CHUNK_SIZE = 8 * 1024 * 1024
DEFAULT_SEED = "sample_dataset_v1"


@dataclass(frozen=True)
class GeneratedFile:
    folder_path: str
    name: str
    size: int


class DeterministicBytes:
    def __init__(self, seed: str, total_size: int, chunk_size: int) -> None:
        self.seed = seed.encode("utf-8")
        self.remaining = total_size
        self.chunk_size = chunk_size
        self.counter = 0

    def read(self) -> bytes:
        if self.remaining <= 0:
            return b""

        wanted = min(self.chunk_size, self.remaining)
        out = bytearray()
        while len(out) < wanted:
            block_seed = self.seed + self.counter.to_bytes(8, "big")
            out.extend(hashlib.sha256(block_seed).digest())
            self.counter += 1

        data = bytes(out[:wanted])
        self.remaining -= len(data)
        return data


def parse_size(value: str) -> int:
    raw = value.strip().lower()
    units = {
        "b": 1,
        "kb": 1000,
        "mb": 1000**2,
        "gb": 1000**3,
        "tb": 1000**4,
        "kib": 1024,
        "mib": 1024**2,
        "gib": 1024**3,
        "tib": 1024**4,
    }
    for suffix in sorted(units, key=len, reverse=True):
        if raw.endswith(suffix):
            return int(float(raw[: -len(suffix)].strip()) * units[suffix])
    return int(raw)


def human_size(num_bytes: int) -> str:
    if num_bytes == 0:
        return "0 B"
    units = ("B", "KiB", "MiB", "GiB", "TiB")
    idx = min(int(math.log(num_bytes, 1024)), len(units) - 1)
    return f"{num_bytes / (1024 ** idx):.2f} {units[idx]}"


def remote_join(*parts: str) -> str:
    return "/".join(part.strip("/") for part in parts if part and part.strip("/"))


def generate_layout(
    total_files: int,
    total_folders: int,
    root_entries: int,
    total_size: int,
) -> tuple[list[str], list[GeneratedFile]]:
    if total_files < 1:
        raise ValueError("--total-files must be at least 1")
    if total_folders < 0:
        raise ValueError("--total-folders must be non-negative")
    if root_entries < 1:
        raise ValueError("--root-entries must be at least 1")
    if total_files + total_folders < root_entries:
        raise ValueError("--total-files + --total-folders must be >= --root-entries")
    if total_folders > 0 and total_files < total_folders:
        raise ValueError("--total-files must be >= --total-folders so each folder can contain a file")
    if total_size < total_files:
        raise ValueError("--total-size must be at least --total-files bytes")

    root_folders = min(total_folders, max(1 if total_folders else 0, root_entries // 2))
    root_files = root_entries - root_folders
    if root_files > total_files:
        root_files = total_files
        root_folders = root_entries - root_files
    if root_folders > total_folders:
        root_folders = total_folders
        root_files = root_entries - root_folders

    folders = [f"folder_{i:04d}" for i in range(1, root_folders + 1)]
    parent_index = 0
    for i in range(root_folders + 1, total_folders + 1):
        parent = folders[parent_index % len(folders)]
        folders.append(f"{parent}/folder_{i:04d}")
        parent_index += 1

    file_locations = [""] * root_files
    remaining_files = total_files - root_files

    for folder in folders:
        if remaining_files <= 0:
            break
        file_locations.append(folder)
        remaining_files -= 1

    targets = folders or [""]
    idx = 0
    while remaining_files > 0:
        file_locations.append(targets[idx % len(targets)])
        idx += 1
        remaining_files -= 1

    base_size = total_size // total_files
    extra = total_size % total_files
    files: list[GeneratedFile] = []
    for i, folder_path in enumerate(file_locations, start=1):
        size = base_size + (1 if i <= extra else 0)
        files.append(GeneratedFile(folder_path=folder_path, name=f"file_{i:05d}.bin", size=size))

    return folders, files


def write_file(path: Path, size: int, seed: str, chunk_size: int, overwrite: bool) -> None:
    if path.exists() and not overwrite:
        raise FileExistsError(f"{path} already exists. Use --overwrite-files to replace generated files.")

    stream = DeterministicBytes(seed, size, chunk_size)
    with path.open("wb") as file_obj:
        while True:
            chunk = stream.read()
            if not chunk:
                break
            file_obj.write(chunk)


def create_dataset(args: argparse.Namespace) -> None:
    output_path = Path(args.output_path).expanduser().resolve()
    total_size = parse_size(args.total_size)
    folders, files = generate_layout(args.total_files, args.total_folders, args.root_entries, total_size)

    print(
        "Planned local dataset: "
        f"{len(files)} files, {len(folders)} folders, {human_size(sum(f.size for f in files))}, "
        f"root entries={args.root_entries}"
    )
    print(f"Output path: {output_path}")

    if args.dry_run:
        print("Dry run only. First 10 generated files:")
        for file in files[:10]:
            relative_path = remote_join(file.folder_path, file.name)
            print(f"  {relative_path} ({human_size(file.size)})")
        return

    output_path.mkdir(parents=True, exist_ok=True)
    for folder in folders:
        (output_path / folder).mkdir(parents=True, exist_ok=True)

    started = time.time()
    written_bytes = 0
    for index, file in enumerate(files, start=1):
        folder_path = output_path / file.folder_path if file.folder_path else output_path
        folder_path.mkdir(parents=True, exist_ok=True)
        file_path = folder_path / file.name
        seed = remote_join(args.seed, file.folder_path, file.name)
        write_file(file_path, file.size, seed, args.chunk_size, args.overwrite_files)
        written_bytes += file.size

        if index == 1 or index == len(files) or index % args.progress_every == 0:
            elapsed = max(time.time() - started, 0.001)
            rate = written_bytes / elapsed
            print(f"[{index}/{len(files)}] wrote {human_size(written_bytes)} at {human_size(int(rate))}/s")

    print(f"Done. Created {human_size(written_bytes)} at {output_path}")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a local sample folder dataset.")
    parser.add_argument("--output-path", required=True, help="Local directory where the dataset will be created.")
    parser.add_argument("--total-size", default=DEFAULT_TOTAL_SIZE, help="Total generated bytes, for example 4gb or 4gib.")
    parser.add_argument("--total-files", type=int, default=DEFAULT_TOTAL_FILES)
    parser.add_argument("--total-folders", type=int, default=DEFAULT_TOTAL_FOLDERS)
    parser.add_argument("--root-entries", type=int, default=DEFAULT_ROOT_ENTRIES, help="Files/folders directly under output path.")
    parser.add_argument("--chunk-size", type=parse_size, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--seed", default=DEFAULT_SEED, help="Seed for deterministic file content.")
    parser.add_argument("--progress-every", type=int, default=5)
    parser.add_argument("--overwrite-files", action="store_true", help="Replace generated files if they already exist.")
    parser.add_argument("--dry-run", action="store_true", help="Print the planned layout without creating files.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        create_dataset(parse_args(argv))
        return 0
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
