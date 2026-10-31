"""
The repository's Markdown links work: every relative link reaches a file, every #anchor into a
Markdown file reaches a heading or an anchor in it, and every requirement ID mentioned in prose links
to its row in the requirements register (when that register exists on this branch).
"""
import os
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
REGISTERS = {"AC": "access-control.md", "NT": "notifications.md", "STD": "data-standards.md",
             "PX": "posix-storage.md"}
LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
PROTECT = re.compile(r"```.*?```|`[^`\n]*`|<!--.*?-->|\[[^\]]*\]\([^)]*\)|<a id=\"[^\"]*\"></a>[A-Z]+-\d+", re.S)


def markdown_files():
    if not (REPO / "docs").is_dir():  # e.g. inside the backend container, which mounts backend/ only
        return []
    return sorted(Path(root) / name for root, _, names in os.walk(REPO) for name in names
                  if name.endswith(".md") and not {"node_modules", ".git", "bundler"} & set(Path(root).parts))


def anchors(path: Path) -> set[str]:
    text = path.read_text()
    slugs = {re.sub(r"[^\w\- ]", "", h.strip().lower()).replace(" ", "-") for h in re.findall(r"^#+ (.+)$", text, re.M)}
    return slugs | set(re.findall(r'<a id="([^"]+)"', text))


FILES = markdown_files()


@pytest.mark.skipif(not FILES, reason="needs the repository's docs/")
@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(REPO)))
def test_links_reach_what_they_name(path):
    broken = []
    for target in LINK.findall(path.read_text()):
        if re.match(r"[a-z]+:", target):  # http:, mailto: and the like aren't checked here
            continue
        file, _, anchor = target.partition("#")
        dest = (path.parent / file).resolve() if file else path
        if not dest.exists():
            broken.append(target)
        elif anchor and dest.suffix == ".md" and anchor.lower() not in anchors(dest):
            broken.append(target)
    assert not broken, f"broken links: {broken}"


@pytest.mark.skipif(not FILES, reason="needs the repository's docs/")
@pytest.mark.parametrize("path", FILES, ids=lambda p: str(p.relative_to(REPO)))
def test_requirement_ids_link_to_their_register(path):
    present = [p for p, f in REGISTERS.items() if (REPO / "docs" / "requirements" / f).exists()]
    bare = re.compile(r"(?<![\w#/-])(?:" + "|".join(present) + r")-\d+(?![\w-])")
    prose = PROTECT.sub(" ", path.read_text())
    assert not bare.findall(prose), "link these to their register rows: " + ", ".join(sorted(set(bare.findall(prose))))
