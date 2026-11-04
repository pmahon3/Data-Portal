from uuid import UUID

from core.db import get_mongo_database
from core.db.mongodb.mongo_client import POLICY_RULE_COLLECTION
from core.services.policies.models import Policy
from core.services.policies.rules import Checker, Rule, conditions_json, rule_from_stored


def policy_from_row(row: list[str]) -> Policy:
    """
    Build a Policy from a stored row (sub, dom, obj, act, cond as in model.conf). Rows saved before
    policies had conditions have no fifth field.
    """
    p_user_uuid, p_instance_uuid, res, act, *cond = row
    rule = rule_from_stored(res, act, cond[0] if cond else "")
    return Policy(
        user_uuid=UUID(p_user_uuid),
        instance_uuid=UUID(p_instance_uuid),
        resource=res,
        action=act,
        ends=rule.ends,
        excluded=list(rule.excluded),
        endings=list(rule.endings),
        kinds=list(rule.kinds),
        dataset=rule.dataset or None,
        standard=rule.standard or None,
    )


class CasbinPolicyManager:
    """
    PolicyManager:

    Class that provides methods for managing user policies and permissions.

    Policies are stored in MongoDB in the Casbin adapter's format (``casbin_rule``: ptype, v0 user,
    v1 instance, v2 path, v3 action, v4 conditions; see model.conf) and read and written there
    directly. Permission decisions are made by checker() (core/services/policies/rules.py).
    """

    def __init__(self, uuids=None):
        """
        Initialise the policy manager backed by MongoDB.

        :param uuids: Unused; kept for backward compatibility.
        """
        self._rules = get_mongo_database()[POLICY_RULE_COLLECTION]

    def _stored(self, **fields: str) -> list[Policy]:
        """
        Return the stored policies whose fields match. Read from MongoDB on every call, so every
        backend process (production runs two) sees the same policies.

        Example: ``_stored(v0=user_uuid)`` -> that user's policies on every instance
        """
        rows = self._rules.find({"ptype": "p", **fields}, {"_id": 0, "ptype": 0})
        policies = []
        for row in rows:
            values = [row.get(f"v{i}", "") for i in range(5)]
            # a policy saved before policies had conditions has no fifth field
            if not values[4]:
                values = values[:4]
            policies.append(policy_from_row(values))
        return policies

    def get_all_policies(self) -> list[Policy]:
        """Return every stored policy."""
        return self._stored()

    def get_user_policies(self, user_uuid: UUID) -> list[Policy]:
        """
        Get the user policies.

        :return: The filtered user policies.
        :rtype: list[str]
        """
        return self._stored(v0=str(user_uuid))

    def get_instance_policies(self, instance_uuid: UUID) -> list[Policy]:
        """
        Get the access point policies.

        :return: The filtered access point policies.
        :rtype: list[str]
        """
        return self._stored(v1=str(instance_uuid))

    def filter_policies(self, filter_: Policy) -> list[Policy]:
        """
        Get all policies under a user according the given filters.

        """

        # Only the fields a stored rule has (p = sub, dom, obj, act in model.conf); a field left
        # out matches anything
        values = (filter_.user_uuid, filter_.instance_uuid, filter_.resource, filter_.action)
        fields = {}
        for i, value in enumerate(values):
            if value is not None and str(value) != "":
                fields[f"v{i}"] = str(value)
        return self._stored(**fields)

    def add_policy(self, policy: Policy) -> bool:
        """
        Adds a user policy to the system.

        :param policy: The policy to be added.
        :type policy: Policy
        """
        user_uuid = policy.user_uuid.__str__()
        instance_uuid = policy.instance_uuid.__str__()
        resource = policy.resource
        action = policy.action

        filter_ = (user_uuid, instance_uuid, resource, action)
        # One policy per person, instance, path and action, whatever its conditions
        if self._stored(v0=user_uuid, v1=instance_uuid, v2=resource, v3=action):
            raise ValueError("Policy already exists.")
        rule = Rule(
            resource,
            action,
            ends=policy.ends,
            excluded=tuple(policy.excluded),
            endings=tuple(policy.endings),
            kinds=tuple(policy.kinds),
            dataset=policy.dataset or "",
            standard=policy.standard or "",
        )
        conditions = conditions_json(rule)
        # a policy without conditions keeps the four fields it always had
        # Written in the adapter's storage format. A policy without conditions keeps the four fields
        # it always had.
        row = {"ptype": "p", "v0": user_uuid, "v1": instance_uuid, "v2": resource, "v3": action}
        if conditions:
            row["v4"] = conditions
        if self._rules.insert_one(row).acknowledged:
            return True
        raise ValueError("Failed to add policy.")
        
    def add_policies(self, policies: list[Policy]) -> bool:
        """
        Add a list of policies.

        :param policies: The list of policies to be added.
        :return: True if all added successfully, False otherwise.
        """
        for policy in policies:
            if not self.add_policy(policy):
                return False
        return True

    def remove_policy(self, policy: Policy) -> bool:
        """
        Remove a policy from the store.

        :param policy: The policy to be removed.
        :type policy: Policy
        """
        user_uuid = policy.user_uuid.__str__()
        instance_uid = policy.instance_uuid.__str__()
        resource = policy.resource
        action = policy.action

        removed = self._rules.delete_many({
            "ptype": "p",
            "v0": user_uuid,
            "v1": instance_uid,
            "v2": resource,
            "v3": action,
        })
        if removed.deleted_count:
            return True
        raise ValueError("Failed to remove policy.")
        
    def remove_policies(self, policies: list[Policy]) -> bool:
        """
        Remove a list of policies.

        :param policies: The list of policies to be removed.
        :return: True if all removed successfully, False otherwise.
        """
        for policy in policies:
            if not self.remove_policy(policy):
                return False
        return True

    def remove_user_policy_store(self, user_uuid: UUID) -> bool:
        """
        Remove all policies belonging to ``user_uuid`` from MongoDB.
        """
        self._rules.delete_many({"ptype": "p", "v0": str(user_uuid)})
        return True

    def checker(self, user_uuid: UUID, instance_uuid: UUID) -> Checker:
        """
        Return the user's rules on one storage instance, read from MongoDB with one indexed query.

        Decisions are made from these rules (core/services/policies/rules.py), read on every
        request, so a policy change applies to the next request in every backend process.
        Build one checker per request and reuse it for every path the request checks.
        """
        return Checker(self.rules_for(user_uuid, instance_uuid))

    def rules_for(self, user_uuid: UUID, instance_uuid: UUID) -> list[Rule]:
        """Return the user's rules on one storage instance, read from MongoDB with one indexed query."""
        rows = self._rules.find(
            {"ptype": "p", "v0": str(user_uuid), "v1": str(instance_uuid)},
            {"_id": 0, "v2": 1, "v3": 1, "v4": 1},
        )
        return [rule_from_stored(row.get("v2", ""), row.get("v3", ""), row.get("v4", "")) for row in rows]

    def validate_policy(self, policy: Policy) -> bool:
        """
        Return whether the policy's user may do its action on its resource.
        """
        checker = self.checker(policy.user_uuid, policy.instance_uuid)
        return checker.allows(policy.resource, policy.action)

