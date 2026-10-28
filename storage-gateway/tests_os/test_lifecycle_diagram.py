"""
The temporary-ID lifecycle diagram (docs/diagrams/posix-link-lifecycle.md) against the helper.

The helper is driven through every situation: first use, clean expiry, expiry after a granted file
was moved, the end of quarantine, and reuse. The state of every ID is read from the helper's own
records before and after each step. The transitions observed must be exactly the diagram's.
Linux and root only.
"""
import os
import sys
import time

import pytest

if sys.platform != "linux" or os.geteuid() != 0:
    pytest.skip("needs Linux and root", allow_module_level=True)

import doccheck  # noqa: E402
from tests_os.test_isolation import NS, close_env, make_env, token  # noqa: E402

IDS = range(2_000_000, 2_000_003)


def states(helper, now):
    s = helper.ids.state
    active = {link["uid"] for link in s["links"].values()}
    result = {}
    for uid in IDS:
        if uid in active:
            result[uid] = "Active"
        elif str(uid) in s["retired"]:
            result[uid] = "Retired"
        elif s["quarantine"].get(str(uid), 0) > now:
            result[uid] = "Quarantined"
        else:
            result[uid] = "Free"
    return result


def test_the_lifecycle_diagram_is_exactly_what_the_helper_does(monkeypatch):
    e = make_env(id_count=len(IDS), quarantine_seconds=100)
    helper, access = e["helper"], e["access"]
    observed = set()
    clock = time.time()
    snapshot = states(helper, clock)

    def step(action, at):
        nonlocal snapshot
        action()
        after = states(helper, at)
        observed.update((snapshot[u], after[u]) for u in IDS if snapshot[u] != after[u])
        snapshot = after

    def read(name, ttl=60):
        return lambda: os.close(access.open_read(token(f"{NS}/study/{name}", "read", ttl=ttl), f"{NS}/study/{name}", None)[0])

    def write(name):
        def go():
            t = token(f"{NS}/new/{name}", "write", ttl=60)
            pending = access.begin_write(t, f"{NS}/new/{name}", None)
            pending.write(b"x")
            pending.commit()
        return go

    try:
        step(read("a.nii.gz"), clock)                                    # Free -> Active
        step(write("u.csv"), clock)                                      # Free -> Active (upload)
        step(read("b.nii.gz"), clock)                                    # Free -> Active
        os.rename(e["data"] / "study" / "b.nii.gz", e["data"] / "study" / "moved.nii.gz")
        step(lambda: helper.sweep(now=clock + 120), clock + 120)         # Active -> Quarantined, -> Retired
        step(lambda: None, clock + 400)                                  # Quarantined -> Free (time passes)
        reuse = token(f"{NS}/study/a.nii.gz", "read", ttl=10_000)
        import app.helper as helper_module

        monkeypatch.setattr(helper_module.time, "time", lambda: clock + 400)  # the helper's clock moves on too
        step(lambda: os.close(access.open_read(reuse, f"{NS}/study/a.nii.gz", None)[0]), clock + 400)  # Free -> Active
    finally:
        close_env(e)

    diagram = doccheck.state_transitions(doccheck.block("diagrams/posix-link-lifecycle.md", "link-lifecycle"))
    drawn = {t for t in diagram if "[*]" not in t}
    assert observed == drawn, f"observed {sorted(observed)}, diagram {sorted(drawn)}"
