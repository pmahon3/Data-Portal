# Class Service Diagrams

**Last updated:** 2026-08-11

## Storage Agent Architecture

Pluggable storage backends are created by the storage-agent factory. Agents own
backend-specific connections and operations; file-tree metadata is no longer
cached by the agents.

```mermaid
classDiagram
    class AbstractStorageAgent {
        <<abstract>>
        +FLAVOUR: str
        +CONFIG: dict
        +instance_url: str
        +generate_access_link(resource, method, ttl) Tuple
        +generate_access_links(resources, method, ttl) Tuple
        +delete_object(resource)
        +delete_objects(resources)
        +get_object_metadata(resource) dict
        +config(secrets) dict
        +secrets() set~str~
        +clear_secrets()
        +connect() *
        +close() *
    }

    class S3StorageAgent {
        +FLAVOUR: str = "s3"
        -s3_client: boto3.Client
        -aws_access_key_id: str
        -aws_secret_access_key: str
        -region_name: str
        +connect()
        +fetch_all_buckets() list~str~
        +generate_access_link(resource, method, ttl) Tuple
        +generate_access_links(resources, method, ttl) Tuple
        +delete_object(resource)
        +delete_objects(resources)
        +get_object_metadata(resource) dict
        +config(secrets) dict
        +secrets() set~str~
        +close()
    }

    class DummyStorageAgent {
        +FLAVOUR: str = "dummy"
        +get_object(object_name)
        +put_object(object_name, data)
        +delete_object(object_name)
        +list_objects(prefix) list
        +connect()
        +close()
    }

    class AgentFactory {
        <<module>>
        +AVAILABLE_FLAVOURS: dict
        +agent_factory(config) AbstractStorageAgent
    }

    AbstractStorageAgent <|-- S3StorageAgent
    AbstractStorageAgent <|-- DummyStorageAgent
    AgentFactory ..> S3StorageAgent : creates
```

## Instance Manager Architecture

The instance manager persists configuration in MongoDB and keeps connected
agents in memory. Secret fields declared by an agent are encrypted before
persistence and cleared from memory after connection. Bucket names already
represented in PostgreSQL are used to reject conflicting storage instances.

```mermaid
classDiagram
    class AbstractInstanceManager {
        <<abstract>>
        +instances: list~Instance~
        +get_instances(instance_names) dict
        +save_instance(config, session) UUID
        +update_instance(instance_id, new_name) bool
        +get_instances_by_uuid(uuids) list~Instance~
        +get_instance_uuid(instance_name) UUID
        +get_instance_by_uuid(uuid) Instance
        +get_instance_by_name(instance_name) Instance
        +delete_instance(instance_uuid) bool
    }

    class InstanceManager {
        -_collection: MongoCollection
        -_encryption_key: str
        -_agents: dict
        +get_existing_bucket_names(session) set~str~
        -_validate_unique_bucket_names(agent, existing_buckets)
        +save_instance(config, session) UUID
        +update_instance(instance_id, new_name) bool
        +delete_instance(instance_uuid) bool
        +teardown()
    }

    class Instance {
        <<Pydantic BaseModel>>
        +uuid: UUID
        +name: str
        +flavour: str
        +agent: AbstractStorageAgent
        +config(secrets) dict
        +close()
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
        +get_allowed_actions(user_uuid, instance_uuid, resource, actions) list~str~
        +create_agreement(agreement) bool
        +remove_agreement(agreement) bool
    }

    class Policy {
        +user_uuid: UUID | None
        +instance_uuid: UUID | None
        +resource: str | None
        +action: str | None
    }

    class Agreement {
        <<not implemented>>
        +uuid: UUID
        +policies: list~Policy~
        +lifespan: timedelta
        +version: float
    }

    class Enforcer {
        <<external casbin>>
    }

    class MongoAdapter {
        <<external casbin-pymongo-adapter>>
    }

    CasbinPolicyManager o-- Enforcer : evaluates policies with
    Enforcer o-- MongoAdapter : persists through
    CasbinPolicyManager ..> Policy : manages
    Agreement *-- Policy : contains
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
