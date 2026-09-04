# Nomad var-file for storage-events-worker.nomad
#
# Fill in required values before running. Do not commit real credentials.

database_url      = "" # postgresql+asyncpg://<user:pass>@<host:port>/<db_name>
registry_password = ""

registry_username = "" # INN-Data-Portal
registry_server   = "" # https://registry.rcg.sfu.ca

object_storage_endpoint_url      = ""
object_storage_access_key_id     = ""
object_storage_secret_access_key = ""
object_storage_region            = "" # default

worker_image = "registry.rcg.sfu.ca/rcg/inn-data-portal/storage-events-worker:latest"
