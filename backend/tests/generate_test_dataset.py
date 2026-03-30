#!/usr/bin/env python3
"""
generate_test_dataset.py

This script generates a recursive directory structure populated with dummy files. 
It is designed to create large-scale nested datasets for testing file-system 
traversal, backup logic, or backend processing pipelines.

Usage:
    python generate_test_dataset.py [root_path] [max_depth] [folders] [files]

Arguments:
    root_path (str):  The directory where generation starts. Defaults to './DeepStructure'.
    max_depth (int):  How many levels deep the nesting goes. Defaults to 7.
    folders (int):    Number of subdirectories to create per level. Defaults to 3.
    files (int):      Number of dummy .txt files to create per level. Defaults to 2.

Example:
    python generate_test_dataset.py ./TestData 3 5 10
"""

import sys
import pathlib

def create_structure(current_path, depth, max_depth, folders_per_level, files_per_level, stats):
    """Recursively creates folders and files."""
    if depth > max_depth:
        return

    # Create the directory
    path = pathlib.Path(current_path)
    if not path.exists():
        path.mkdir(parents=True, exist_ok=True)
        stats['folders'] += 1

    # 1. Create files
    for i in range(1, files_per_level + 1):
        file_name = f"File_Level{depth}_{i}.txt"
        file_path = path / file_name
        file_path.touch()
        stats['files'] += 1

    # 2. Create folders and recurse
    if depth < max_depth:
        for j in range(1, folders_per_level + 1):
            folder_name = f"Folder_Level{depth}_{j}"
            new_path = path / folder_name
            create_structure(new_path, depth + 1, max_depth, folders_per_level, files_per_level, stats)

def main():
    # Setup defaults or take from command line arguments
    # Usage: python script.py [root_path] [max_depth] [folders] [files]
    root_path = sys.argv[1] if len(sys.argv) > 1 else "./DeepStructure"
    max_depth = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    folders_per_level = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    files_per_level = int(sys.argv[4]) if len(sys.argv) > 4 else 2

    stats = {'folders': 0, 'files': 0}

    print(f"\033[36mGenerating structure at: {root_path}\033[0m")
    print(f"Settings: Max Depth: {max_depth}, Folders/Lvl: {folders_per_level}, Files/Lvl: {files_per_level}")

    try:
        create_structure(root_path, 0, max_depth, folders_per_level, files_per_level, stats)
        
        print(f"\n\033[32mDone!\033[0m")
        print("-" * 27)
        print(f"Folders created: {stats['folders']}")
        print(f"Files created:   {stats['files']}")
        print(f"Total items:     {stats['folders'] + stats['files']}")
        print("-" * 27)
    except KeyboardInterrupt:
        print("\n\033[31mProcess cancelled by user.\033[0m")

if __name__ == "__main__":
    main()
