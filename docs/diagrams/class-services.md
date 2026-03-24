  # Class Services Diagrams

## Storage Agent Architecture

Pluggable storage backend system using the Abstract Factory pattern.

```mermaid
classDiagram
    class AbstractStorageAgent {
        <<abstract>>
        +FLAVOUR: str
        +config(secrets) dict
        +load_file_tree() FileTree
        +generate_access_link() URL
        +generate_upload_link() URL
    }

    class S3StorageAgent {
        +FLAVOUR = "s3"
        -s3_client: boto3.Client
        -bucket_name: str
        +load_file_tree() FileTree
        +generate_access_link() URL
        +generate_upload_link() URL
    }

    class DummyStorageAgent {
        +FLAVOUR = "dummy"
        -mock_data: dict
        +load_file_tree() FileTree
        +generate_access_link() URL
        +generate_upload_link() URL
    }

    class AgentFactory {
        +agent_factory(config, flavour) AbstractStorageAgent
        +available_flavours: dict
    }

    AbstractStorageAgent <|-- S3StorageAgent
    AbstractStorageAgent <|-- DummyStorageAgent
    AgentFactory ..> AbstractStorageAgent : creates
```

## Instance Manager Architecture

This service orchestrates the lifecycle of storage instances. 
It initializes connections via specialized agents during startup and provides a unified interface for CRUD operations.
Additionally, it maintains a registry of agents which handle instance-specific tasks, such as generating pre-signed URLs.

```mermaid
classDiagram
    class AbstractInstanceManager {
        <<abstract>>
        +instances: list~Instance~
        +get_instances(instance_names: set) dict
        +save_instance(config) UUID
        +get_instances_by_uuid(uuids: list) list
        +get_instance_uuid(instance_name: str) UUID
        +get_instance_by_uuid(uuid: UUID) Instance
        +delete_instance(instance_uuid: UUID) bool
    }

    class InstanceManager {
        -_collection
        -_agents: dict
        +teardown()
    }

    class Instance {
        <<Pydantic BaseModel>>
        +uuid: UUID
        +name: str
        +flavour: str
        +agent: AbstractStorageAgent
        +config(secrets: bool)
    }

    class AbstractStorageAgent {
        <<abstract>>
        +FLAVOUR$
        +CONFIG$
    }

    class S3StorageAgent {
        +FLAVOUR$ : string = "s3"
        -_cors_enabled: bool
    }

    class DummyStorageAgent {
        +FLAVOUR$ : string = "dummy"
    }

    class AgentFactory {
        <<Factory>>
        +agent_factory(config: dict) AbstractStorageAgent
    }

    %% Inheritance
    AbstractInstanceManager <|-- InstanceManager
    AbstractStorageAgent <|-- S3StorageAgent
    AbstractStorageAgent <|-- DummyStorageAgent

    %% Aggregation & Composition
    InstanceManager "1" o-- "*" Instance : manages
    Instance "1" o-- "1" AbstractStorageAgent : composed of
    
    %% Dependency
    InstanceManager ..> AgentFactory : uses
    AgentFactory ..> AbstractStorageAgent : creates
```

## User Manager Architecture

Provides a service layer for the CRUD lifecycle of users. 

```mermaid
classDiagram
    class AbstractUserManager {
        <<abstract>>
        +create_user(user_details) User
        +get_user(uuid) User
        +delete_user(uuid) bool
        +get_all_users() list~User~
        +user_exists(user_slug) bool
        +get_user_slug(uuid) str
        +get_user_roles(uuid) list~str~
        +get_user_uuid(user_slug) UUID
        +get_user_uuids() list~UUID~
    }

    class KeycloakUserManager {
        -identity_manager: KeycloakAdmin
    }

    class User {
        +username: str
        +uuid: UUID
        +email: str
        +roles: list~str~
    }

    class UserCreate {
        +username: str
        +email: str
        +roles: list~str~
    }

    class KeycloakAdmin {
        <<external_python_keycloak>>
    }

    AbstractUserManager <|-- KeycloakUserManager : implements
    KeycloakUserManager o-- KeycloakAdmin : contains (identity_manager)
    KeycloakUserManager -- User : returns
    KeycloakUserManager -- UserCreate : accepts
```

## Policy Manager Architecture

Provides a service layer for the CRUD lifecycle of policies and agreements. 
Persistence is managed via a MongoDB Casbin adapter.
Note: Agreement functionality is currently defined but not yet implemented.

```mermaid
classDiagram
    class CasbinPolicyManager {
        -enforcer: casbin.Enforcer
        -_actions: list
        +actions : list
        +get_user_policies(user_uuid) list~Policy~
        +get_instance_policies(instance_uuid) list~Policy~
        +filter_policies(filter_) list~Policy~
        +add_policy(policy) bool
        +add_policies(policies) bool
        +remove_policy(policy) bool
        +remove_policies(policies) bool
        +remove_user_policy_store(user_uuid) bool
        +validate_policy(policy) bool
        +create_agreement(agreement) bool
        +remove_agreement(agreement) bool
    }

    class Policy {
        +user_uuid: UUID | None
        +instance_uuid: UUID | None
        +resource: str | None
        +action: str | None
    }

    class Agreement:::grayedOut {
        <<Not Implemented>>
        +uuid: UUID
        +policies: list~Policy~
        +lifespan: timedelta
        +version: float
    }

    class Enforcer {
        <<external_casbin>>
    }

    class Adapter {
        <<external_casbin_pymongo_adapter>>
    }

    CasbinPolicyManager o-- Enforcer : Uses
    Enforcer o-- Adapter : uses for db persistence
    Enforcer ..> Policy : handles
    Agreement *-- Policy : contains collection
```

## Tree Service Architecture

```mermaid
classDiagram
    namespace Service_Layer {
        class FileService {
            +AsyncSession session
            +create_file_row(bucket, folder_id, name, key) File
            +get_file(file_id) File
            +update_from_head(file, head) void
            +delete_file_row(file) void
        }

        class TreeService {
            +AsyncSession session
            +get_root(bucket) Folder
            +list_children(bucket, folder_id) List_Pair
            +create_folder(bucket, parent_id, name) Folder
            +delete_folder_subtree(bucket, folder_id) void
            +build_key(bucket, folder_id, filename) Folder_Key_Pair
        }
    }

    namespace Data_Models {
        class File {
            +BigInteger id
            +Text bucket
            +BigInteger folder_id
            +String name
            +Text key
            +BigInteger size
            +Text etag
            +DateTime last_modified
            +Text content_type
        }

        class Folder {
            +BigInteger id
            +Text bucket
            +BigInteger parent_id
            +String name
            +Ltree path
            +Text full_path
            +String marker_key
        }
    }

    %% Relationships
    FileService ..> File : CRUD Operations
    TreeService ..> Folder : Handles Tree Logic
    TreeService ..> File : Lists/Deletes
    
    File "*" --> "1" Folder : belongs to folder_id
    Folder "1" -- "*" Folder : parent/children relationship
```