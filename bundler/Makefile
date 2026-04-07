
# If PY_VER is not provided, read APP_DIR/.python-version, else fallback to 3.10.
PY_VER ?= $(shell if [ -n "$(APP_DIR)" ] && [ -f "$(APP_DIR)/.python-version" ]; then v=$$(sed -n '1{/./p;}' "$(APP_DIR)/.python-version" | tr -d '[:space:]'); if [ -n "$$v" ]; then printf "%s" "$$v"; else printf "3.10"; fi; else printf "3.10"; fi)

# Required CLI variable: absolute/relative path to business logic package directory.
# Example: make patch APP_DIR=../bundler_app
APP_DIR ?=

# Extract name from APP_DIR (e.g. ../bundler_app -> bundler_app).
APP_NAME := $(notdir $(patsubst %/,%,$(APP_DIR)))

# Generated OpenAPI server directory name, sibling-style convention.
APP_DIR_GEN := $(APP_NAME)_server_gen

# Package/source key derived from APP_NAME.
BUNDLER_PKG ?= $(subst _,-,$(APP_NAME))

# Relative path from within APP_DIR_GEN back to APP_DIR.
# Prefer realpath --relative-to; fallback to sibling convention on platforms where
# realpath lacks --relative-to (e.g. default macOS realpath).
# if unsupported/empty (like default macOS realpath), falls back to ../$(APP_NAME)
BUNDLER_SOURCE_PATH := $(shell rel=$$(realpath --relative-to="$(APP_DIR_GEN)" "$(APP_DIR)" 2>/dev/null); if [ -n "$$rel" ]; then printf "%s" "$$rel"; else printf "%s" "../$(APP_NAME)"; fi)

REQUIRED_TOOLS := uv uvx npx sed ed # java is optional, but required for generate-openapi

# FIXME: remove this once the `uv` version of the generator is accepted and the java version is no longer needed
OPENAPI_GENERATOR_JAR ?= openapi-generator-cli-7.7.0.jar
OPENAPI_INPUT_PATH ?= openapi.yaml
OPENAPI_GENERATOR_VERSION ?= latest
OPENAPI_GENERATOR_TARGET ?= python-fastapi
OPENAPI_GENERATOR_OPTIONS ?= --type-mappings file=bytes,binary=bytes

# Set to 1 to skip the generate-openapi step in `make all`.
SKIP_GENERATE ?= 0

# Set to 1 to skip sed/yq edits to the generated Dockerfile and docker-compose.yaml.
# The uv-based image and compose overrides live in Dockerfile.uv and docker-compose.uv.yaml instead.
SKIP_DOCKER_PATCH ?= 1

# Run from this directory (paths are relative to here), e.g. `cd bundler && make patch`
# or `make -C bundler patch`.

# patch-version: setup.cfg → requirements.txt → .python-version
# patch-docker: patch Dockerfile/docker-compose with build ARG wiring for Python image version
#   (set SKIP_DOCKER_PATCH=1 to skip those edits; use Dockerfile.uv + docker-compose.uv.yaml to build)
# patch (full): patch-version + patch-docker + patch-pyproject (reads setup.cfg; merges metadata + uv sources) → add-deps (uv add bundler)
# all: patch, then sync / test
.PHONY: check-tools check-config generate-openapi clean patch patch-version patch-docker patch-setupcfg patch-requirements add-deps add-dev-deps patch-pyproject sync test export-pinned all

check-tools:
	@echo
	@missing_tools=""; \
	for tool in $(REQUIRED_TOOLS); do \
		if ! command -v "$$tool" >/dev/null 2>&1; then \
			missing_tools="$$missing_tools $$tool"; \
		fi; \
	done; \
	if [ -n "$$missing_tools" ]; then \
		echo "Missing required tools:$$missing_tools"; \
		echo "Please install them and retry."; \
		exit 1; \
	fi
	@echo "All required tools ( $(REQUIRED_TOOLS)) are installed"
	@echo

check-config:
	@if [ -z "$(APP_DIR)" ]; then \
		echo "Missing required variable: APP_DIR"; \
		echo "Usage: make <target> APP_DIR=../bundler_app"; \
		exit 1; \
	fi
	@if [ ! -d "$(APP_DIR)" ]; then \
		echo "APP_DIR does not exist or is not a directory: $(APP_DIR)"; \
		exit 1; \
	fi
	@echo "Resolved APP_NAME=$(APP_NAME), APP_DIR_GEN=$(APP_DIR_GEN), BUNDLER_SOURCE_PATH=$(BUNDLER_SOURCE_PATH)"
	@echo

generate-openapi: check-tools check-config
	@echo "Running OpenAPI Generator to generate server stub"
	@echo "See https://openapi-generator.tech/docs/installation for more information."
ifeq ($(SKIP_GENERATE),1)
	@echo "(dry-run): Skipping generate-openapi because SKIP_GENERATE=1"
	@echo "java -jar \"$(OPENAPI_GENERATOR_JAR)\" generate -g python-fastapi -i \"$(OPENAPI_INPUT_PATH)\" -o \"$(APP_DIR_GEN)\""
	@echo "npx @openapitools/openapi-generator-cli@$(OPENAPI_GENERATOR_VERSION) generate -g $(OPENAPI_GENERATOR_TARGET) -i \"$(OPENAPI_INPUT_PATH)\" -o \"$(APP_DIR_GEN)\" --additional-properties="
	@echo "Note: This is a dry-run. The server stub will not be generated."
	@echo
else
	@echo "Running generate-openapi because SKIP_GENERATE=0"
	@echo
	npx -y @openapitools/openapi-generator-cli@$(OPENAPI_GENERATOR_VERSION) version
	npx -y @openapitools/openapi-generator-cli@$(OPENAPI_GENERATOR_VERSION) generate -g $(OPENAPI_GENERATOR_TARGET) -i "$(OPENAPI_INPUT_PATH)" -o "$(APP_DIR_GEN)" $(OPENAPI_GENERATOR_OPTIONS) --additional-properties=
	@echo
endif

# Depends on generate-openapi so a failed codegen blocks patching (and so `make -j` cannot run patch in parallel with codegen).
patch: generate-openapi patch-version patch-docker patch-pyproject add-deps add-dev-deps

patch-version: patch-setupcfg patch-requirements
	@echo "Writing .python-version for app directory"
	printf "%s\n" "$(PY_VER)" > "$(APP_DIR_GEN)/.python-version"
	@echo

patch-pyproject:
	@echo "Patching pyproject metadata"
	BUNDLER_SERVER_PYTHON_VERSION=$(PY_VER) \
		uv run --with tomlkit python scripts/patch_pyproject_toml.py "$(APP_DIR_GEN)/pyproject.toml"
	@echo

patch-setupcfg:
	@echo "Patching setup.cfg Python requirements/classifier"
	BUNDLER_SERVER_PYTHON_VERSION=$(PY_VER) uv run python scripts/patch_setup_cfg.py "$(APP_DIR_GEN)/setup.cfg"
	@echo

patch-requirements:
	@echo "Stripping version constraints in requirements.txt"
	uv run python scripts/patch_requirements.py "$(APP_DIR_GEN)/requirements.txt"
	@echo

patch-docker:
	@echo "Docker (uv / extra contexts): use $(APP_DIR_GEN)/Dockerfile.uv and $(APP_DIR_GEN)/docker-compose.uv.yaml"
	@echo "Build: cd $(APP_DIR_GEN) && docker compose -f docker-compose.yaml -f docker-compose.uv.yaml build"
	@if [ "$(SKIP_DOCKER_PATCH)" = "1" ]; then \
		echo "Skipping in-tree Dockerfile and docker-compose.yaml patches (SKIP_DOCKER_PATCH=1) in favor of Dockerfile.uv and docker-compose.uv.yaml. If patching is needed, set SKIP_DOCKER_PATCH=0"; \
	else \
		echo "Patching Dockerfile/docker-compose build ARG for Python version"; \
		echo "Replacing FROM python:X.Y (any minor) with FROM python:\$${PYTHON_VERSION}"; \
		sed -E -i.bak 's|(FROM python:)[0-9]+\.[0-9]+|\1$${PYTHON_VERSION}|g' "$(APP_DIR_GEN)/Dockerfile" && rm -f "$(APP_DIR_GEN)/Dockerfile.bak"; \
		echo "Inserting ARG PYTHON_VERSION=$(PY_VER) before first FROM if it doesn't exist, otherwise do nothing."; \
		if ! grep -Eq '^[[:space:]]*ARG[[:space:]]+PYTHON_VERSION(=|[[:space:]]|$$)' "$(APP_DIR_GEN)/Dockerfile"; then \
			from_line=$$(grep -n '^[[:space:]]*FROM[[:space:]]' "$(APP_DIR_GEN)/Dockerfile" | head -n 1 | cut -d: -f1); \
			if [ -n "$$from_line" ]; then \
				{ echo "$$from_line"; echo i; echo "ARG PYTHON_VERSION=$(PY_VER)"; echo .; echo wq; } | ed -s "$(APP_DIR_GEN)/Dockerfile" >/dev/null; \
			fi; \
		fi; \
		echo 'Patching docker-compose.yaml with build arg service.build.args.PYTHON_VERSION and value $${PYTHON_VERSION:-$(PY_VER)}'; \
		PYTHON_VERSION_COMPOSE='$${PYTHON_VERSION:-$(PY_VER)}' uvx yq -y -i '.services.service.build.args.PYTHON_VERSION = env.PYTHON_VERSION_COMPOSE' "$(APP_DIR_GEN)/docker-compose.yaml"; \
	fi
	@echo

add-deps:
	@echo "Adding bundler runtime dependency to app"
	uv add --directory "$(APP_DIR_GEN)" "$(BUNDLER_PKG) @ $(BUNDLER_SOURCE_PATH)" --no-sync # PEP 508 direct reference: install package name from local path, e.g. `bundler_app @ ../bundler_app`; --no-sync: update dependency metadata/lock, but skip installing until `uv sync`;
	@echo

add-dev-deps:
	@echo "Adding dev dependencies from requirements-dev.txt"
	cp "$(APP_DIR)/requirements-dev.txt" "$(APP_DIR_GEN)/requirements-dev.txt" # FIXME: temporary workaround since the file is not generated by the openapi-generator-cli
	uv add --directory "$(APP_DIR_GEN)" --dev --no-sync -r requirements-dev.txt
	@echo

sync: patch
	@echo "Syncing environment and local dev package, adding external dependency $(BUNDLER_SOURCE_PATH) as a dev dependency"
	uv sync --directory "$(APP_DIR_GEN)"
	uv add --directory "$(APP_DIR_GEN)" --dev $(BUNDLER_SOURCE_PATH)
	@echo

test: sync
	@echo "Running pytest test suite"
	uv run --directory "$(APP_DIR_GEN)" --with pytest pytest tests
	uv run --directory "$(APP_DIR_GEN)" --with pytest --with pytest-cov pytest tests --cov=src/openapi_server/impl
	@#uv run --directory "$(APP_NAME)" --with pytest pytest tests
	@#uv run --directory "$(APP_NAME)" --with pytest --with pytest-cov pytest tests --cov=app
	@echo

export-pinned: check-tools check-config
	@echo "Exporting pinned requirements snapshot"
	@# Generates `requirements-pinned.txt` from `requirements.txt` so builds/CI can use
	@# stable, lockstep pinned versions (via `uv pip compile`).
	
	@# TODO: There are two approaches to generating pinned requirements: uv pip compile and uv export.
	uv pip compile --directory "$(APP_DIR_GEN)" requirements.txt -o requirements-pinned.txt
	@#uv --directory "$(APP_DIR_GEN)" export --format requirements-txt --group dev > "$(APP_DIR_GEN)/requirements-dev.lock.txt"
	
	@echo

# Single leaf prerequisite so the chain is strictly: generate-openapi → patch → sync → test (see prerequisites on those targets).
all: test
	@printf '%*s\n' "$$(tput cols)" '' | tr ' ' '=' # Write line with = $(tput cols) Dynamically determines the width of the current terminal in columns.
	@echo
	@echo "Completed patch, sync, and tests"
	@echo "Reminder: run \`$$ make export-pinned\` to (re)generate requirements-pinned.txt using pinned versions from requirements.txt."
	@echo

clean: check-config
	@echo "clean OpenAPI Generated Server Stub paths listed in $(APP_DIR_GEN)/.openapi-generator/FILES (not the whole tree)"
	@if [ -z "$(APP_DIR_GEN)" ] || [ "$(APP_DIR_GEN)" = "/" ] || [ "$(APP_DIR_GEN)" = "." ]; then \
		echo "Refusing to clean unsafe APP_DIR_GEN='$(APP_DIR_GEN)'"; \
		exit 1; \
	fi
	
	@#if [ ! -d "$(APP_DIR_GEN)" ]; then \
		echo "Nothing to clean: no directory at APP_DIR_GEN='$(APP_DIR_GEN)'"; \
		exit 0; \
	fi
	@#rm -rf "$(APP_DIR_GEN)" # delete the generated server stub

	@# strips carriage returns (\r) from Windows-style line endings before removing the files
	@files_manifest="$(APP_DIR_GEN)/.openapi-generator/FILES"; \
	if [ -f "$$files_manifest" ]; then \
		while IFS= read -r rel || [ -n "$$rel" ]; do \
			rel=$$(printf '%s' "$$rel" | tr -d '\r'); \
			[ -z "$$rel" ] && continue; \
			case "$$rel" in \#*) continue;; esac; \
			target="$(APP_DIR_GEN)/$$rel"; \
			if [ -e "$$target" ]; then rm -rf "$$target"; fi; \
		done < "$$files_manifest"; \
	fi

	git restore "$(APP_DIR_GEN)" # restore the original server stub
	@echo