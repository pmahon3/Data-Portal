# Optional advanced targets layered on top of `Makefile`.
# Reasoning:
# - Keep `Makefile` minimal and stable for the core flow:
#   `generate-openapi`, `build`, `sync`, `test`.
# - Keep advanced/rare mutation targets in `make/bootstrap.mk` (this file).
#
# Usage (explicit two-file invocation, from `bundler/`):
# - Full patching flow:
#     make -f Makefile -f make/bootstrap.mk patch APP_CORE_DIR=bundler_core
# - Individual patch steps:
#     make -f Makefile -f make/bootstrap.mk patch-pyproject APP_CORE_DIR=bundler_core
# - Export pinned requirements:
#     make -f Makefile -f make/bootstrap.mk export-pinned APP_CORE_DIR=bundler_core

.PHONY: patch patch-for-uv patch-version patch-docker patch-setupcfg patch-requirements patch-pyproject export-pinned

# If PY_VER is not set, read APP_CORE_DIR/.python-version, else 3.10. Requires `APP_CORE_DIR` from `Makefile` (use `make -f Makefile -f make/bootstrap.mk …`).
PY_VER ?= $(shell if [ -n "$(APP_CORE_DIR)" ] && [ -f "$(APP_CORE_DIR)/.python-version" ]; then v=$$(sed -n '1{/./p;}' "$(APP_CORE_DIR)/.python-version" | tr -d '[:space:]'); if [ -n "$$v" ]; then printf "%s" "$$v"; else printf "3.10"; fi; else printf "3.10"; fi)

# Depends on generate-openapi so a failed codegen blocks patching.
patch-for-uv: patch-version patch-pyproject

patch: generate-openapi patch-for-uv add-deps add-dev-deps

# The standard python-fastapi generator in OpenAPI Generator cannot natively produce a server pre-configured with the uv build tool. 
# By default, it scaffolds projects using legacy configuration files, such as requirements.txt or setup.py.
# Either (1) patch the generated server to use uv, or (2) create Custom Mustache Templates for the generator to use.
patch-version: patch-setupcfg patch-requirements
	@echo "Writing .python-version for app directory ..."
	printf "%s\n" "$(PY_VER)" > "$(OPENAPI_OUTPUT_FOLDER)/.python-version"
	@echo

patch-pyproject:
	@echo "Patching pyproject metadata ..."
	SERVER_PYTHON_VERSION=$(PY_VER) \
		uv run --with tomlkit python make/patch_pyproject_toml.py "$(OPENAPI_OUTPUT_FOLDER)/pyproject.toml"
	@echo

patch-setupcfg:
	@echo "Patching setup.cfg Python requirements/classifier ..."
	SERVER_PYTHON_VERSION=$(PY_VER) uv run python make/patch_setup_cfg.py "$(OPENAPI_OUTPUT_FOLDER)/setup.cfg"
	@echo

patch-requirements:
	@echo "Stripping version constraints in requirements.txt ..."
	uv run python make/patch_requirements.py "$(OPENAPI_OUTPUT_FOLDER)/requirements.txt"
	@echo

# Generate a pinned requirements.txt file from uv.lock file
export-pinned: check-tools
	@echo "Exporting pinned requirements snapshot ..."
	@# Generates `requirements-pinned.txt` from `requirements.txt` so builds/CI can use
	@# stable, lockstep pinned versions (via `uv pip compile`).

	@# TODO: There are two approaches to generating pinned requirements: uv pip compile and uv export.
	uv pip compile --directory "$(OPENAPI_OUTPUT_FOLDER)" requirements.txt -o requirements-pinned.txt
	@#uv --directory "$(OPENAPI_OUTPUT_FOLDER)" export --format requirements-txt --group dev > "$(OPENAPI_OUTPUT_FOLDER)/requirements-dev.lock.txt"
	
	@echo

# Patch the python version in the generated Dockerfile and docker-compose.yaml
patch-docker:
	@echo "Docker (uv / extra contexts): use $(OPENAPI_OUTPUT_FOLDER)/Dockerfile.uv and $(OPENAPI_OUTPUT_FOLDER)/docker-compose.uv.yaml ..."
	@echo "Build: cd $(OPENAPI_OUTPUT_FOLDER) && docker compose -f docker-compose.yaml -f docker-compose.uv.yaml build"
	@if [ "$(SKIP_DOCKER_PATCH)" = "1" ]; then \
		echo "Skipping in-tree Dockerfile and docker-compose.yaml patches (SKIP_DOCKER_PATCH=1) in favor of Dockerfile.uv and docker-compose.uv.yaml. If patching is needed, set SKIP_DOCKER_PATCH=0"; \
	else \
		echo "Patching Dockerfile/docker-compose build ARG for Python version ..."; \
		echo "Replacing FROM python:X.Y (any minor) with FROM python:\$${PYTHON_VERSION} ..."; \
		sed -E -i.bak 's|(FROM python:)[0-9]+\.[0-9]+|\1$${PYTHON_VERSION}|g' "$(OPENAPI_OUTPUT_FOLDER)/Dockerfile" && rm -f "$(OPENAPI_OUTPUT_FOLDER)/Dockerfile.bak"; \
		echo "Inserting ARG PYTHON_VERSION=$(PY_VER) before first FROM if it doesn't exist, otherwise do nothing ..."; \
		if ! grep -Eq '^[[:space:]]*ARG[[:space:]]+PYTHON_VERSION(=|[[:space:]]|$$)' "$(OPENAPI_OUTPUT_FOLDER)/Dockerfile"; then \
			from_line=$$(grep -n '^[[:space:]]*FROM[[:space:]]' "$(OPENAPI_OUTPUT_FOLDER)/Dockerfile" | head -n 1 | cut -d: -f1); \
			if [ -n "$$from_line" ]; then \
				{ echo "$$from_line"; echo i; echo "ARG PYTHON_VERSION=$(PY_VER)"; echo .; echo wq; } | ed -s "$(OPENAPI_OUTPUT_FOLDER)/Dockerfile" >/dev/null; \
			fi; \
		fi; \
		echo 'Patching docker-compose.yaml with build arg service.build.args.PYTHON_VERSION and value $${PYTHON_VERSION:-$(PY_VER)} ...'; \
		PYTHON_VERSION_COMPOSE='$${PYTHON_VERSION:-$(PY_VER)}' uvx yq -y -i '.services.service.build.args.PYTHON_VERSION = env.PYTHON_VERSION_COMPOSE' "$(OPENAPI_OUTPUT_FOLDER)/docker-compose.yaml"; \
	fi
	@echo
