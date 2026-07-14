# Included by ../Makefile only. Behavior and keys: ../README_reference.md
# ("openapitools.json and defaults", "Makefile requirements").

# APP_DIR: bundler/ tree root (parent of this directory); default openapitools.json is anchored here so
# `make -f bundler/Makefile` works when the shell cwd is not `bundler/`.
APP_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)

# Required: path to business logic package (relative to bundler/ or absolute).
# Example: make all APP_CORE_DIR=../bundler_core
APP_CORE_DIR ?=

ifndef APP_CORE_DIR
$(error Missing required variable: APP_CORE_DIR. Usage: make <target> APP_CORE_DIR=../bundler_core)
endif
ifeq ($(wildcard $(APP_CORE_DIR)),)
$(error APP_CORE_DIR does not exist or is not a directory: $(APP_CORE_DIR))
endif

APP_CORE_NAME := $(notdir $(patsubst %/,%,$(APP_CORE_DIR)))

REQUIRED_TOOLS := uv uvx npx jq sed ed cut

OPENAPI_NPX := npx -y @openapitools/openapi-generator-cli
OPENAPI_GENERATOR_KEY ?= bundler-server-fastapi
OPENAPI_TOOLS_CONFIG ?= $(APP_DIR)/openapitools.json

# stay aligned—unlike ``$(word …)`` on whitespace. ``//`` only applies for null / false / missing, not JSON ``""``.
# 1. Let jq join the values into a single line separated by '|'
OPENAPI_LINES := $(shell jq -r '.["generator-cli"].generators["$(OPENAPI_GENERATOR_KEY)"] | [ (.output // "$(APP_CORE_NAME)_server_gen"), (.additionalProperties.sourceFolder // "."), (.additionalProperties.packageName // ""), (.additionalProperties.fastapiImplementationPackage // "") ] | join("|")' "$(OPENAPI_TOOLS_CONFIG)")

# 2. Extract fields safely using cut with the '|' delimiter (No syntax issues, handles empty values perfectly)
OPENAPI_OUTPUT_FOLDER_RAW := $(shell echo "$(OPENAPI_LINES)" | cut -d'|' -f1)
OPENAPI_SRC_FOLDER        := $(shell echo "$(OPENAPI_LINES)" | cut -d'|' -f2)
OPENAPI_PACKAGE_NAME      := $(shell echo "$(OPENAPI_LINES)" | cut -d'|' -f3)
OPENAPI_IMPL_PACKAGE      := $(shell echo "$(OPENAPI_LINES)" | cut -d'|' -f4)

# FIX: If sourceFolder was explicitly set to "" in JSON, fall back to "." 
# so it constructs a clean relative path (./bundler_server/core)
ifeq ($(strip $(OPENAPI_SRC_FOLDER)),)
OPENAPI_SRC_FOLDER := .
endif

# 3. Enforce non-empty rules for downstream targets (e.g. coverage path).
$(if $(strip $(OPENAPI_PACKAGE_NAME)),,$(error OPENAPI_PACKAGE_NAME is empty. Set additionalProperties.packageName in $(OPENAPI_TOOLS_CONFIG)))
$(if $(strip $(OPENAPI_IMPL_PACKAGE)),,$(error OPENAPI_IMPL_PACKAGE is empty. Set additionalProperties.fastapiImplementationPackage in $(OPENAPI_TOOLS_CONFIG)))

# 4. Expand "#{cwd}" and enforce stable relative root "." if paths match
OPENAPI_OUTPUT_FOLDER := $(subst \#{cwd},$(CURDIR),$(OPENAPI_OUTPUT_FOLDER_RAW))
ifeq ($(abspath $(OPENAPI_OUTPUT_FOLDER)),$(abspath $(CURDIR)))
OPENAPI_OUTPUT_FOLDER := .
endif

# "#{cwd}" in JSON is expanded here to $(CURDIR) for Make / uv / realpath (see README_reference.md).
OPENAPI_OUTPUT_FOLDER := $(subst \#{cwd},$(CURDIR),$(OPENAPI_OUTPUT_FOLDER_RAW))
# When output is the Makefile cwd, use "." so uv/realpath get a stable relative project root.
ifeq ($(abspath $(OPENAPI_OUTPUT_FOLDER)),$(abspath $(CURDIR)))
OPENAPI_OUTPUT_FOLDER := .
endif

OPENAPI_IMPL_COV_PATH ?= $(OPENAPI_SRC_FOLDER)/$(OPENAPI_PACKAGE_NAME)/$(OPENAPI_IMPL_PACKAGE)

# this is a workaround for the fact that `realpath --relative-to` is not available on macOS
# Linux: `realpath --relative-to` ; macOS: `grealpath --relative-to` (Homebrew coreutils).
UNAME_S := $(shell uname -s)
ifeq ($(UNAME_S),Darwin)
REALPATH_BIN := grealpath
else
REALPATH_BIN := realpath
endif
define relpath_from_output
$(shell $(REALPATH_BIN) --relative-to="$(OPENAPI_OUTPUT_FOLDER)" "$(APP_CORE_DIR)" 2>/dev/null)
endef
# Path from OPENAPI_OUTPUT_FOLDER back to APP_CORE_DIR.
CORE_SOURCE_PATH := "./$(or $(call relpath_from_output),$(APP_CORE_NAME))"

$(info )
$(info Resolved:)
$(info APP_DIR=$(APP_DIR))
$(info APP_CORE_NAME=$(APP_CORE_NAME))
$(info CORE_SOURCE_PATH=$(CORE_SOURCE_PATH))
$(info OPENAPI_OUTPUT_FOLDER=$(OPENAPI_OUTPUT_FOLDER))
$(info OPENAPI_SRC_FOLDER=$(OPENAPI_SRC_FOLDER))
$(info OPENAPI_PACKAGE_NAME=$(OPENAPI_PACKAGE_NAME))
$(info OPENAPI_IMPL_PACKAGE=$(OPENAPI_IMPL_PACKAGE))
$(info OPENAPI_IMPL_COV_PATH=$(OPENAPI_IMPL_COV_PATH))
$(info )

SKIP_GENERATE ?= 0
SKIP_DOCKER_PATCH ?= 1
