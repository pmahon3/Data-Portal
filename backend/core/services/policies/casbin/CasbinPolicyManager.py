import os
from uuid import UUID

from casbin import Enforcer
from casbin_pymongo_adapter import Adapter

from core.db import get_mongo_database
from core.db.mongodb.mongo_client import POLICY_RULE_COLLECTION
from core.services.policies.models import Policy, Agreement
from core.services.policies.rules import Checker, Rule


class CasbinPolicyManager:
    """
    PolicyManager:

    Class that provides methods for managing user policies and permissions.

    Attributes:
        enforcer (Enforcer): Stores and manages policies through the casbin-pymongo adapter.
            Permission decisions are made by checker() (core/services/policies/rules.py).
        _actions (list): A list of actions that can be performed on resources.
    """

    def __init__(self, uuids=None):
        """
        Initialise the policy manager backed by MongoDB.

        The adapter loads all existing policy rules from MongoDB on construction.
        The ``uuids`` parameter is accepted for backward compatibility but is no longer required — the adapter handles policy loading automatically.

        :param uuids: Unused; kept for backward compatibility.
        """

        # Create Casbin MongoDB adapter using an existing client
        database = get_mongo_database()
        adapter = Adapter(client=database.client, db_name=database.name, collection=POLICY_RULE_COLLECTION)
        self._rules = database[POLICY_RULE_COLLECTION]

        # Pass the adapter to the Enforcer so it owns policy persistence
        self.enforcer = Enforcer(os.environ['ENFORCER_MODEL'], adapter, enable_log=False)
        self.enforcer.enable_auto_save(True)
        self._actions = ['read', 'write', 'share']

    @property
    def actions(self) -> list[str]:
        return self._actions

    def get_user_policies(self, user_uuid: UUID) -> list[Policy]:
        """
        Get the user policies.

        :return: The filtered user policies.
        :rtype: list[str]
        """
        user_uuid = user_uuid.__str__()
        policies = self.enforcer.get_filtered_policy(0, user_uuid)
        result = []
        for policy in policies:
            # Unpacking order is hard-coded to match the policy definition in model.conf
            p_user_uuid, p_instance_uuid, res, act = policy
            result.append(Policy(
                user_uuid=UUID(p_user_uuid),
                instance_uuid=UUID(p_instance_uuid),
                resource=res,
                action=act
            ))
            
        return result

    def get_instance_policies(self, instance_uuid: UUID) -> list[Policy]:
        """
        Get the access point policies.

        :return: The filtered access point policies.
        :rtype: list[str]
        """
        instance_uuid = instance_uuid.__str__()

        policies = self.enforcer.get_filtered_policy(1, instance_uuid)
        result = []
        for policy in policies:
            # Unpacking order is hard-coded to match the policy definition in model.conf
            p_user_uuid, p_instance_uuid, res, act = policy
            result.append(Policy(
                user_uuid=UUID(p_user_uuid),
                instance_uuid=UUID(p_instance_uuid),
                resource=res,
                action=act
            ))

        return result

    def filter_policies(self, filter_: Policy) -> list[Policy]:
        """
        Get all policies under a user according the given filters.

        """

        def convert_to_str(value: object | None) -> str:
            return value.__str__() if value is not None else ""

        filter_ = tuple(map(convert_to_str, filter_.dict().values()))

        # Retrieve the policies matching the filter
        policies = self.enforcer.get_filtered_policy(0, *filter_)

        # Sort by access points
        result = []
        for policy in policies:
            # Unpacking order is hard-coded to match the policy definition in model.conf
            p_user_uuid, p_instance_uuid, res, act = policy
            result.append(Policy(
                user_uuid=UUID(p_user_uuid),
                instance_uuid=UUID(p_instance_uuid),
                resource=res,
                action=act
            ))

        return result

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
        result = self.enforcer.add_policy(*filter_)
        if result:
            return True
        elif self.enforcer.has_policy(*filter_):
            raise ValueError("Policy already exists.")
        else:
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
        Remove a policy from the enforcer.

        :param policy: The policy to be removed.
        :type policy: Policy
        """
        user_uuid = policy.user_uuid.__str__()
        instance_uid = policy.instance_uuid.__str__()
        resource = policy.resource
        action = policy.action

        filter_ = (user_uuid, instance_uid, resource, action)
        result = self.enforcer.remove_filtered_policy(0, *filter_)
        if result:
            return True
        else:
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
        self.enforcer.remove_filtered_policy(0, user_uuid.__str__())
        return True

    def checker(self, user_uuid: UUID, instance_uuid: UUID) -> Checker:
        """
        The user's rules on one storage instance, read from MongoDB with one indexed query.

        Decisions are made from these rules (core/services/policies/rules.py), not by Casbin's
        enforcer, so a policy change applies to the next request in every backend process.
        Build one checker per request and reuse it for every path the request checks.
        """
        rows = self._rules.find(
            {"ptype": "p", "v0": str(user_uuid), "v1": str(instance_uuid)},
            {"_id": 0, "v2": 1, "v3": 1},
        )
        return Checker(Rule(row.get("v2", ""), row.get("v3", "")) for row in rows)

    def validate_policy(self, policy: Policy) -> bool:
        """
        May the policy's user do its action on its resource?
        """
        checker = self.checker(policy.user_uuid, policy.instance_uuid)
        return checker.allows(policy.resource, policy.action)

    def create_agreement(self, agreement: Agreement) -> bool:
        """
        Create an agreement.
        :param agreement: The agreement to be created.
        :type agreement: Agreement
        :return: True if successful, False otherwise.
        """
        NotImplementedError("create_agreement method is not implemented.")

    def remove_agreement(self, agreement: Agreement) -> bool:
        """
        Remove an agreement.
        :param agreement: The agreement to be removed.
        :type agreement: Agreement
        :return: True if successful, False otherwise.
        """
        NotImplementedError("remove_agreement method is not implemented.")
