import logging
import os
from pathlib import Path

from uuid import UUID
from casbin import Enforcer
from core.management.policies.models import Policy, Agreement


class CasbinPolicyManager:
    """
    PolicyManager:

    Class that provides methods for managing user policies and permissions.

    Attributes:
        enforcer (Enforcer): An instance of the Enforcer class for enforcing access control policies.
        user_policies_folder (str): The path to the folder where user policies are stored.
        _actions (list): A list of actions that can be performed on resources.
    """

    def __init__(self, uuids):

        """
        Load user policies from files.

        :param uuids: A list of UUIDs representing the users.
        :type uuids: list[UUID]
        """

        self.enforcer = Enforcer(os.getenv('ENFORCER_MODEL'), os.getenv('ENFORCER_POLICY'), enable_log=True)
        self.user_policies_folder = os.getenv('USER_POLICIES')
        self._actions = ['read', 'write', 'share']

        # Load all user policies to enforcer
        for uuid in uuids:
            policy_file = Path(self.user_policies_folder) / (uuid.__str__() + '.policies')

            try:
                with open(policy_file, 'r') as f:
                    for line in f.readlines():
                        self.enforcer.add_policy(*line.strip().split(", ")[1:])
                f.close()
            except FileNotFoundError:
                logging.log(logging.INFO, f"Policy file for user {uuid} not found. Skipping.")

    @property
    def actions(self):
        return self._actions

    def _write_user_policies(self, user_uuid: str):
        """
        Write user policies to a file.
        """

        user_uuid = user_uuid.__str__()
        user_policy_file = Path(self.user_policies_folder) / (user_uuid + '.policies')
        with open(user_policy_file, 'w') as f:
            for policy in self.enforcer.get_filtered_policy(0, user_uuid):
                f.write(f"p, {', '.join(policy)}\n")
        f.close()

    def _write_user_policy(self, user_uuid: str, instance_uuid: str, resource: str, action: str):
        """
        Write a user policy to a file.
        """
        # Retrieve the users policy file
        user_policy_file = Path(self.user_policies_folder) / (user_uuid + '.policies')
        # Write the policy
        with open(user_policy_file, 'a') as f:
            f.write(f"p, {user_uuid}, {instance_uuid}, {resource}, {action}\n")
        f.close()

    def _write_enforcer_policies(self, enforcer: Enforcer):
        """
        Write the policies of an enforcer object to a csv file.

        NOTE: This will overwrite the existing csv file.

        :param enforcer: The enforcer object containing the policies.
        :type enforcer: Enforcer
        """
        for uuid in enforcer.get_all_named_subjects("p"):
            self._write_user_policies(uuid)

    def get_user_policies(self, user_uuid: UUID):
        """
        Get the user policies.

        :return: The filtered user policies.
        :rtype: list[str]
        """
        user_uuid = user_uuid.__str__()
        policies = self.enforcer.get_filtered_policy(0, user_uuid)
        result = []
        for policy in policies:
            result.append(Policy(
                user_uuid=UUID(policy[0]),
                instance_uuid=UUID(policy[1]),
                resource=policy[2],
                action=policy[3]
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
            result.append(Policy(
                user_uuid=UUID(policy[0]),
                instance_uuid=UUID(policy[1]),
                resource=policy[2],
                action=policy[3]
            ))

        return result

    def filter_policies(self, filter_: Policy) -> list[Policy]:
        """
        Get all policies under a user according the given filters.

        """

        def convert_to_str(value):
            return value.__str__() if value is not None else ""

        filter_ = tuple(map(convert_to_str, filter_.dict().values()))

        # Retrieve the policies matching the filter
        policies = self.enforcer.get_filtered_policy(0, *filter_)

        # Sort by access points
        result = []
        for policy in policies:
            user_uuid = UUID(policy[0])
            instance_uuid = UUID(policy[1])
            resource = policy[2]
            action = policy[3]

            result.append(Policy(
                user_uuid=user_uuid,
                instance_uuid=instance_uuid,
                resource=resource,
                action=action
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

        # Check if the policy already exists
        if self.enforcer.has_policy(user_uuid, instance_uuid, resource, action):
            raise ValueError("Policy already exists.")

        result = self.enforcer.add_policy(user_uuid, instance_uuid, resource, action)
        if result:
            self._write_user_policy(user_uuid, instance_uuid, resource, action)
            return True
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
            self._write_user_policies(user_uuid)
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

    def create_user_policy_store(self, user_uuid: UUID) -> bool:
        """
        Creates a policy file for the given unique user identifier.
        """

        # Create a new user policy file
        user_policy_file = Path(self.user_policies_folder) / (user_uuid.__str__() + '.policies')

        # Check if the file exists
        if user_policy_file.exists():
            raise FileExistsError('The user policy file already exists.')

        with open(user_policy_file, 'w') as f:
            f.write("")
        f.close()

        return True

    def remove_user_policy_store(self, user_uuid: UUID) -> bool:
        """
        Removes a policy file for the given unique user identifier.
        """

        # Delete the user policies
        user_policy_file = Path(self.user_policies_folder) / (user_uuid.__str__() + '.policies')
        user_policy_file.unlink()

        # Remove user policies from enforcer
        self.enforcer.remove_filtered_policy(0, user_uuid.__str__())

        return True

    def validate_policy(self, policy: Policy) -> bool:
        """
        Validate user access based on the provided parameters.
        """

        user_uuid = policy.user_uuid.__str__()
        instance_uuid = policy.instance_uuid.__str__()
        resource = policy.resource
        action = policy.action

        return self.enforcer.enforce(user_uuid, instance_uuid, resource, action)

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
