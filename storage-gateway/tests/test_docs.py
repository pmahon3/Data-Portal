"""
The documentation's checked diagrams against the code (docs/diagrams/posix-*.md).

- Module diagrams: every solid arrow is an import, and every import among the drawn modules is drawn.
- Deployment diagram: the accounts, groups, modes and owners it names match the Dockerfile and the
  entrypoint that build the container (the running container is checked in e2e).
- The web side never imports the privileged side (import-linter).
Runtime sequences and the ID lifecycle are checked in e2e/ and tests_os/.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

import doccheck

GATEWAY = Path(__file__).resolve().parents[1]
BACKEND = GATEWAY.parent / "backend"


@pytest.mark.parametrize("diagram,component", [
    ("gateway-modules", GATEWAY),
    ("backend-posix-modules", BACKEND),
])
def test_module_diagram_matches_the_imports(diagram, component):
    body = doccheck.block("diagrams/posix-components.md", diagram)
    nodes = {n: label for n, label in doccheck.flowchart_nodes(body).items() if "/" in label.split("<br/>")[0]}
    drawn = doccheck.flowchart_imports(body)
    actual = doccheck.import_edges(component, nodes)
    assert drawn - actual == set(), f"drawn but not imported: {sorted(drawn - actual)}"
    assert actual - drawn == set(), f"imported but not drawn: {sorted(actual - drawn)}"


def deployment_facts():
    body = doccheck.block("diagrams/posix-deployment.md", "deployment")
    return doccheck.flowchart_nodes(body)


def test_deployment_accounts_match_the_dockerfile():
    labels = " ".join(deployment_facts().values())
    dockerfile = (GATEWAY / "Dockerfile").read_text()
    created = {int(u) for u in re.findall(r"--uid (\d+)", dockerfile)} | {int(g) for g in re.findall(r"--gid (\d+)", dockerfile)}
    for uid in {int(u) for u in re.findall(r"uid (\d+)", labels)} - {0, 2000000}:
        assert uid in created, f"diagram names uid {uid}, which the Dockerfile doesn't create"
    for _, gid in re.findall(r"owner (\d+):(\d+)", labels):
        assert int(gid) == 0 or int(gid) in created
    assert "group 10010" in labels and "--gid 10010 posix-traverse" in dockerfile


def test_deployment_modes_match_the_entrypoint():
    entrypoint = (GATEWAY / "entrypoint.sh").read_text()
    for label in deployment_facts().values():
        m = re.search(r"path (\S+) · mode (\d{4})", label)
        if m:
            path, mode = m.groups()
            assert f"chmod {mode} {path}" in entrypoint, f"entrypoint doesn't set {path} to {mode}"


def test_the_web_side_never_imports_the_privileged_side():
    if shutil.which("lint-imports") is None:
        pytest.skip("import-linter not installed")
    result = subprocess.run(["lint-imports"], cwd=GATEWAY, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
