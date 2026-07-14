from __future__ import annotations

import re

_LABEL_RE = re.compile(r"[^a-z0-9_]+")


def normalize_folder_full_path(full_path: str) -> str:
    """Normalize folder paths to a POSIX-like display path.

    Rules:
    - Always starts with '/'
    - Always ends with '/'
    - Collapses repeated '/'
    - Input: "//demo/sub"
    - Output: "/demo/sub/"

    """
    full_path = full_path.strip()
    if not full_path:
        return "/"
    # collapse repeated slashes
    while "//" in full_path:
        full_path = full_path.replace("//", "/")
    if not full_path.startswith("/"):
        full_path = "/" + full_path
    if not full_path.endswith("/"):
        full_path = full_path + "/"
    return full_path


def split_segments(folder_full_path: str) -> list[str]:
    '''
    - Input: "/demo/sub/"
    - Output: ["demo", "sub"]
    '''
    p = normalize_folder_full_path(folder_full_path)
    if p == "/":
        return []
    # remove leading and trailing '/'
    inner = p[1:-1]
    return [seg for seg in inner.split("/") if seg]


def to_ltree_label(segment: str) -> str:
    """Convert a folder name segment to a safe ltree label.

    ltree labels allow: [A-Za-z0-9_]
    We normalize to lowercase and replace other chars with '_'.
    Input: "My Folder!"
    Output: "my_folder"
    """
    s = segment.strip().lower()
    s = s.replace(" ", "_")
    s = _LABEL_RE.sub("_", s)
    s = s.strip("_") or "_"
    return s


def build_ltree_path(segments: list[str]) -> str:
    '''
    Input: ["demo", "sub"]
    Output: "root.demo.sub"
    '''
    labels = ["root"] + [to_ltree_label(s) for s in segments]
    return ".".join(labels)


def join_child_full_path(parent_full_path: str, child_name: str) -> str:
    '''
    Input: ("/demo/", "sub")
    Output: "/demo/sub/"
    '''
    parent_full_path = normalize_folder_full_path(parent_full_path)
    child = child_name.strip("/")
    if parent_full_path == "/":
        return f"/{child}/"
    return f"{parent_full_path}{child}/"


def build_object_key(folder_full_path: str, filename: str) -> str:
    """
        Map folder display path + filename to an object storage key.
        Input: ", "file.txt")
        Otput: file.txt"
    """
    folder_full_path = normalize_folder_full_path(folder_full_path)
    name = filename.strip("/")
    if folder_full_path == "/":
        return name
    return folder_full_path.lstrip("/") + name
