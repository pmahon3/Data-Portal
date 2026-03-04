import os
import logging.config
from pathlib import Path

import uvicorn
import yaml


def get_secret(key: str) -> str:
    """The application should also be configured to read secrets from files rather than environment variables.
    Exposure of secrets through environment variables has led to numerous security incidents over the years.

    Here's a pattern we recommend for python. This pattern:
    - Prioritizes reading secrets from files using the _FILE suffix convention
    - Maintains compatibility with environment variables as a fallback
    - Follows conventions used by official images like MySQL and Postgres

    https://phase.dev/blog/docker-compose-secrets/
    """

    # Check for _FILE suffix first
    file_env = f"{key}_FILE"
    if file_env in os.environ:
        # if not file_env:
            # raise RuntimeError("Missing env variable {file_env}")
        if not Path(os.environ[file_env]).exists():
            raise RuntimeError(f"Environment variable {key} file not found: {file_env}")
        
        try:
            with open(os.environ[file_env], 'r') as f:
                logging.info(f"Loaded env variable from file {file_env}")
                return f.read().strip()
            
        except Exception as err:
            logging.warning(f"An error occurred reading file {file_env}. Falling back to environment variable {key}: {err}")
            # Fall back to environment variable
            if not os.environ.get(key):
                logging.warning(f"The variable {key} is empty.")
            return os.environ.get(key)    


if __name__ == "__main__":

    # ---- Required app vars (Compose is source of truth; set safe defaults for local runs)
    os.environ.setdefault("SYSTEM_RESET", "false")
    os.environ.setdefault("AMS_HOST", "0.0.0.0")
    os.environ.setdefault("AMS_PORT", "8000")
    os.environ.setdefault("AMS_RELOAD", "false")
    os.environ.setdefault("API_VERSION", "0_1")

    # ---- Logging
    print("Initializing loggers...")
    os.environ.setdefault("LOG_DIR", str((Path.cwd() / "data" / "logs").resolve()))
    os.environ.setdefault("LOG_LEVEL", "INFO")
    log_config_path = Path(os.getenv("LOG_CONFIG", "./loggers/log_config.yaml")).resolve()
    with open(log_config_path, "r") as f:
        cfg_text = f.read().replace("${LOG_DIR}", os.environ["LOG_DIR"]).replace("${LOG_LEVEL}", os.environ["LOG_LEVEL"])
    logging.config.dictConfig(yaml.safe_load(cfg_text))
    logging.getLogger("app").info("Starting application...")

    # ---- Resolve/absolutize paths (provided by Compose)
    path_envs = ["ENFORCER_MODEL", "INSTANCE_CONFIGS"]
    for k in path_envs:
        v = os.getenv(k)
        if not v:
            raise RuntimeError(f"Missing required env: {k}")
        os.environ[k] = str(Path(v).resolve())
        logging.info(f"{k}={os.environ[k]}")

    # ---- Root dir (informational)
    prefix = Path(__file__).parent.resolve()
    os.environ["ROOT_DIRECTORY"] = str(prefix)

    # ---- Keycloak derived URLs (internal service address). Do NOT touch TOKEN_ISSUER here.
    logging.info("Setting up Keycloak derived URLs...")
    kc_domain = os.getenv("KEYCLOAK_DOMAIN")
    kc_realm = os.getenv("KEYCLOAK_REALM")
    os.environ["KEYCLOAK_WELL_KNOWN_URL"] = f"{kc_domain}/realms/{kc_realm}/.well-known/openid-configuration"
    os.environ["KEYCLOAK_LOGIN_URL"] = (
        f"{kc_domain}/realms/{kc_realm}/protocol/openid-connect/auth"
        f"?client_id={os.getenv('KEYCLOAK_UI_CLIENT_ID')}"
        f"&redirect_uri={os.getenv('KEYCLOAK_REDIRECT_URI')}"
        f"&response_type=code"
    )
    
    # ---- Run server
    host = os.getenv("AMS_HOST", "0.0.0.0")
    port = int(os.getenv("AMS_PORT", "8000"))
    reload = os.getenv("AMS_RELOAD", "false").lower() == "true"
    os.environ["APP_HOST"] = host
    os.environ["APP_PORT"] = str(port)

    # Configure uvicorn to use our log config
    log_config_dict = yaml.safe_load(cfg_text)
    uvicorn.run(
        app="api.v0_1.app:app",
        host=host,
        port=port,
        reload=reload,
        log_config=log_config_dict,  # Pass our logging config to uvicorn
        access_log=True
    )
