create table if not exists bundle_jobs (
    id varchar(255) primary key,
    status varchar(255) not null check (status in ('pending', 'processing', 'failed', 'complete')),
    folder_name varchar(255),
    compression varchar(255) not null,
    archive_path text,
    result_url text,
    error_message text,
    created_at timestamp with time zone not null,
    updated_at timestamp with time zone not null,
    started_at timestamp with time zone,
    completed_at timestamp with time zone,
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
