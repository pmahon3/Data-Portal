"""The diagram generator reads imports, Compose files and Nomad jobs as they are.

    uv run --no-project --with pyyaml --with pytest pytest docs/diagrams/test_generate.py
"""
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent))
import generate  # noqa: E402


def write(root: Path, files: dict[str, str]) -> Path:
    for name, text in files.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


def test_imports_resolve_absolute_relative_and_imported_names(tmp_path):
    root = write(tmp_path, {
        "core/__init__.py": "",
        "core/db.py": "",
        "core/services/__init__.py": "",
        "core/services/policies.py": "from core.db import session\nfrom . import users\n",
        "core/services/users.py": "import core.db\nimport os\n",
        "api/routes.py": "from core.services.policies import check\n",
        "tests/test_x.py": "import core.db\n",
    })
    assert generate.imports(root) == {
        "core.db": set(), "core.services.policies": {"core.db", "core.services.users"},
        "core.services.users": {"core.db"}, "api.routes": {"core.services.policies"}}


def test_modules_group_into_their_folders(tmp_path):
    root = write(tmp_path, {"core/db.py": "", "core/services/policies/rules.py": "import core.db\n",
                            "core/services/policies/casbin/manager.py": "import core.services.policies.rules\n"})
    assert generate.collapse(generate.imports(root), 3) == {
        "core": set(), "core.services.policies": {"core"}}


def test_a_nomad_job_gives_each_group_its_count_tasks_and_services(tmp_path):
    write(tmp_path, {"a.nomad": '''
job "app" {
  group "web" {
    count = 2
    task "server" {
      config { image = "registry/app:1" }
      env = {
        A = "b"
      }
      template {
        data = <<EOF
{{ with secret "x" }}{{ end }}
EOF
      }
      service {
        name = "app-http"
      }
    }
    task "db" {
      config {
        image = "mysql:8"
      }
    }
  }
}
'''})
    assert generate.nomad_jobs(tmp_path / "a.nomad") == [("app", "web", 2, [("server", "registry/app:1"), ("db", "mysql:8")], ["app-http"])]


def test_compose_follows_includes_and_applies_overrides(tmp_path, monkeypatch):
    monkeypatch.setattr(generate, "ROOT", tmp_path)
    write(tmp_path, {
        "local/compose.yaml": "include:\n  - ../svc/compose.yml\nservices:\n  db:\n    image: postgres\n",
        "svc/compose.yml": "services:\n  api:\n    build: .\n    ports: ['8000:8000']\n    depends_on: [db]\n",
        "local/prod.yaml": "services:\n  api:\n    deploy:\n      replicas: 2\n",
    })
    services = generate.merged([tmp_path / "local/compose.yaml", tmp_path / "local/prod.yaml"], yaml)
    assert services["api"]["build"] == "svc" and services["api"]["deploy"]["replicas"] == 2
    chart = generate.deployment(services)
    assert 'api["api<br/>build svc<br/>ports 8000:8000<br/>replicas 2"]' in chart and "api --> db" in chart


def test_the_committed_diagrams_are_what_the_code_gives():
    assert generate.main(["--check"]) == 0, "run docs/diagrams/generate.py and commit the result"


@pytest.mark.parametrize("name", sorted(generate.pages()))
def test_each_page_says_it_is_generated(name):
    assert generate.pages()[name].startswith(generate.HEADER)
