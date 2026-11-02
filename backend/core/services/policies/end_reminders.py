"""
Reminders before a policy ends (AC-8; C6: "end date + review reminders for upcoming end dates").

A policy with an end date is due a reminder ``POLICY_END_REMINDER_DAYS`` (default 14) before it, and
on the day. The administrators, and the managers of every project the policy's instance belongs to,
each get one notification per reminder, in the portal and by email (the email names no files). The
backend checks once an hour; a reminder already sent isn't sent again, so several backend processes
or restarts are harmless.
"""
import asyncio
import datetime
import logging
import os
from collections.abc import Iterable

from core.services.notifications import store
from core.services.policies.models import Policy
from core.services.policies.rules import today

logger = logging.getLogger(__name__)

LEAD_DAYS = int(os.getenv("POLICY_END_REMINDER_DAYS", "14"))
CHECK_EVERY_SECONDS = 3600


def due(policies: Iterable[Policy], on: datetime.date, lead_days: int) -> list[tuple[Policy, str]]:
    """The policies due a reminder on that day, with the kind of reminder."""
    found = []
    for policy in policies:
        if policy.ends == on + datetime.timedelta(days=lead_days):
            found.append((policy, "policy_ending_soon"))
        elif policy.ends == on:
            found.append((policy, "policy_ending_today"))
    return found


def recipients(instance_name: str, users, projects) -> set[str]:
    """Administrators, and the managers of each project that includes the instance (user UUIDs)."""
    found = {str(user.uuid) for user in users.get_all_users() if "admin" in (user.roles or [])}
    for project in projects.get_all_projects():
        if instance_name in projects.get_project_storage_instances(project):
            found |= {str(users.get_user_uuid(name)) for name in projects.get_project_managers(project)}
    return found


def send(policies: Iterable[Policy], users, projects, instances, on: datetime.date | None = None,
         lead_days: int = LEAD_DAYS) -> int:
    """Send the reminders due on that day (today by default); returns how many were sent."""
    on = on or today()
    sent = 0
    for policy, kind in due(policies, on, lead_days):
        instance = instances.get_instance_by_uuid(policy.instance_uuid).name
        holder = users.get_user_slug(policy.user_uuid)
        when = "today" if kind == "policy_ending_today" else f"on {policy.ends}"
        message = f"A policy ends {when}: {holder} can {policy.action} {policy.resource} on {instance}"
        key = f"{policy.user_uuid}|{policy.instance_uuid}|{policy.resource}|{policy.action}|{policy.ends}|{kind}"
        for user in sorted(recipients(instance, users, projects)):
            if store.notify_once(user, key, kind, message, ends=policy.ends.isoformat()):
                sent += 1
    return sent


async def run_hourly(policy_manager, users, projects, instances) -> None:
    """Check for due reminders every hour, for as long as the backend runs."""
    while True:
        try:
            policies = [p for p in policy_manager.get_all_policies() if p.ends]
            sent = await asyncio.to_thread(send, policies, users, projects, instances)
            if sent:
                logger.info("sent %s policy end reminders", sent)
        except Exception:
            logger.exception("policy end reminders failed; trying again in an hour")
        await asyncio.sleep(CHECK_EVERY_SECONDS)
