"""
Reminders before a policy ends (AC-8, C6): administrators, and the managers of each project the
instance belongs to, are told ahead of a policy's end date and on the day, once each. MongoDB and
Keycloak are replaced by fakes.

Verifies: AC-8.
"""
import datetime
from types import SimpleNamespace
from uuid import UUID

import pytest

from core.services import notifications
from core.services.policies import end_reminders
from core.services.policies.models import Policy
from tests.test_notifications import FakeCollection

DAY = datetime.date(2026, 11, 1)
ADMIN, MANAGER, OTHER_MANAGER, HOLDER = (UUID(int=i) for i in (1, 2, 3, 4))
STUDY, OTHER = UUID(int=10), UUID(int=11)


def policy(ends, instance=STUDY, resource="study/patient-7/*"):
    return Policy(user_uuid=HOLDER, instance_uuid=instance, resource=resource, action="read", ends=ends)


class Users:
    names = {ADMIN: "ada", MANAGER: "max", OTHER_MANAGER: "otto", HOLDER: "alice"}

    def get_all_users(self):
        return [SimpleNamespace(uuid=u, roles=["admin"] if u == ADMIN else ["user"]) for u in self.names]

    def get_user_slug(self, uuid):
        return self.names[uuid]

    def get_user_uuid(self, slug):
        return {v: k for k, v in self.names.items()}[slug]


class Projects:
    def get_all_projects(self):
        return ["neuro", "other"]

    def get_project_storage_instances(self, project):
        return {"neuro": ["study-store"], "other": ["other-store"]}[project]

    def get_project_managers(self, project):
        return {"neuro": ["max"], "other": ["otto"]}[project]


class Instances:
    def get_instance_by_uuid(self, uuid):
        return SimpleNamespace(name={STUDY: "study-store", OTHER: "other-store"}[uuid])


@pytest.fixture
def store(monkeypatch):
    collection = FakeCollection()
    monkeypatch.setattr(notifications.store, "_collection", lambda: collection)
    monkeypatch.setattr(notifications.store, "CHANNELS", [])
    return collection


def send(policies, on=DAY):
    return end_reminders.send(policies, Users(), Projects(), Instances(), on=on, lead_days=14)


def test_a_policy_is_due_a_reminder_ahead_of_its_end_and_on_the_day():
    due = end_reminders.due([policy(DAY + datetime.timedelta(days=14)), policy(DAY), policy(None),
                             policy(DAY + datetime.timedelta(days=3))], on=DAY, lead_days=14)
    assert [(p.ends, kind) for p, kind in due] == [(DAY + datetime.timedelta(days=14), "policy_ending_soon"),
                                                    (DAY, "policy_ending_today")]


def test_administrators_and_the_instances_project_managers_are_reminded(store):
    send([policy(DAY)])
    assert sorted(d["user"] for d in store.docs) == sorted([str(ADMIN), str(MANAGER)])
    assert "alice can read study/patient-7/* on study-store" in store.docs[0]["message"]


def test_each_reminder_is_sent_once_however_often_the_job_runs(store):
    send([policy(DAY)])
    send([policy(DAY)])
    assert len(store.docs) == 2


def test_policies_with_no_end_date_never_cause_a_reminder(store):
    send([policy(None)])
    assert store.docs == []


def test_a_reminder_email_names_no_files():
    from core.services.notifications.email_channel import _text
    text = _text({"kind": "policy_ending_soon", "ends": "2026-11-15", "message": "alice can read study/patient-7/*"})
    assert "2026-11-15" in text and "patient-7" not in text and "alice" not in text
