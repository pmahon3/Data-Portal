create table if not exists bundle_jobs (
    id varchar(255) primary key,
    status varchar(255) not null check (status in ('pending', 'processing', 'failed', 'complete')),
    folder_name varchar(255),
    compression varchar(255) not null,
    archive_path text,
    result_object_key text,
    error_message text,
    created_at timestamp with time zone not null,
    updated_at timestamp with time zone not null,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
    archive_started_at timestamp with time zone,
    archive_completed_at timestamp with time zone,
    upload_started_at timestamp with time zone,
    upload_completed_at timestamp with time zone,
    archive_duration_millis bigint,
    upload_duration_millis bigint,
    total_duration_millis bigint,
    locked_by varchar(255),
    lock_expires_at timestamp with time zone,
    attempt_count integer not null default 0,
    bundle_fingerprint varchar(255),
    fingerprint_algorithm varchar(255)
);

create table if not exists bundle_job_files (
    bundle_job_id varchar(255) not null,
    file_order integer not null,
    url text,
    relative_path text,
    primary key (bundle_job_id, file_order),
    constraint fk_bundle_job_files_job
        foreign key (bundle_job_id)
        references bundle_jobs (id)
        on delete cascade
);

create index if not exists idx_bundle_jobs_claim_scan
    on bundle_jobs (status, created_at, lock_expires_at);

create index if not exists idx_bundle_jobs_retention_scan
    on bundle_jobs (status, completed_at);

create index if not exists idx_bundle_job_files_job
    on bundle_job_files (bundle_job_id);

alter table if exists bundle_jobs
    add column if not exists result_object_key text;

alter table if exists bundle_jobs
    alter column archive_path type text;

alter table if exists bundle_jobs
    drop column if exists result_url;

alter table if exists bundle_jobs
    alter column result_object_key type text;

alter table if exists bundle_jobs
    alter column error_message type text;

alter table if exists bundle_jobs
    add column if not exists archive_started_at timestamp with time zone;

alter table if exists bundle_jobs
    add column if not exists archive_completed_at timestamp with time zone;

alter table if exists bundle_jobs
    add column if not exists upload_started_at timestamp with time zone;

alter table if exists bundle_jobs
    add column if not exists upload_completed_at timestamp with time zone;

alter table if exists bundle_jobs
    add column if not exists archive_duration_millis bigint;

alter table if exists bundle_jobs
    add column if not exists upload_duration_millis bigint;

alter table if exists bundle_jobs
    add column if not exists total_duration_millis bigint;
