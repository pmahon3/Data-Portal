# Nomad var-file for storage-events-cleanup.nomad
#
# Fill in required values before running. Do not commit real credentials.

database_url      = "" # postgresql+asyncpg://<user:pass>@<host:port>/<db_name>
registry_password = ""

registry_username = "" # INN-Data-Portal
registry_server   = "" # https://registry.rcg.sfu.ca

cleanup_image = "registry.rcg.sfu.ca/rcg/inn-data-portal/storage-events-cleanup:latest"
