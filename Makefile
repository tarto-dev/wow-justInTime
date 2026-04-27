# JustInTime — repo-level Makefile
# Wraps the most common dev / release operations. All Python work happens
# inside scripts/ via uv; the addon Lua side is just files + a zip.

SHELL          := /bin/bash
SCRIPTS_DIR    := scripts
ADDON_DIR      := addon
ADDON_NAME     := JustInTime
ADDON_SRC_DIR  := $(ADDON_DIR)/$(ADDON_NAME)
TOC_FILE       := $(ADDON_SRC_DIR)/$(ADDON_NAME).toc
DATA_LUA       := $(ADDON_SRC_DIR)/Data.lua
ADDON_VERSION  := $(shell awk '/^## Version:/ {print $$3}' $(TOC_FILE))
ADDON_ZIP      := $(ADDON_DIR)/$(ADDON_NAME)-v$(ADDON_VERSION).zip

UV             := uv

.DEFAULT_GOAL  := help

# ─── Help ──────────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@awk 'BEGIN {FS = ":.*##"; printf "\nUsage:\n  make \033[36m<target>\033[0m\n\nTargets:\n"} \
	      /^[a-zA-Z_-]+:.*?##/ { printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

# ─── Data pipeline (Raider.IO → Data.lua) ──────────────────────────────────

.PHONY: data
data: ## Rebuild reference timers (writes addon/JustInTime/Data.lua)
	cd $(SCRIPTS_DIR) && $(UV) run jit-update

.PHONY: data-dry
data-dry: ## Dry-run: fetch + compute, print stats, do NOT write Data.lua
	cd $(SCRIPTS_DIR) && $(UV) run jit-update --dry-run

.PHONY: data-fresh
data-fresh: ## Bypass HTTP cache then rebuild Data.lua
	cd $(SCRIPTS_DIR) && $(UV) run jit-update --no-cache

# Single-dungeon debug: `make data-only DUNGEON=algethar-academy`
.PHONY: data-only
data-only: ## Rebuild for one dungeon only — pass DUNGEON=<slug>
	@if [ -z "$(DUNGEON)" ]; then echo "usage: make data-only DUNGEON=<slug>" >&2; exit 2; fi
	cd $(SCRIPTS_DIR) && $(UV) run jit-update --only $(DUNGEON)

# ─── Python side: setup, tests, lint ───────────────────────────────────────

.PHONY: setup
setup: ## Install Python deps via uv
	cd $(SCRIPTS_DIR) && $(UV) sync

.PHONY: test
test: ## Run pytest (with coverage gate from pyproject.toml)
	cd $(SCRIPTS_DIR) && $(UV) run pytest

.PHONY: lint
lint: ## ruff + mypy
	cd $(SCRIPTS_DIR) && $(UV) run ruff check jit_update tests
	cd $(SCRIPTS_DIR) && $(UV) run mypy jit_update

# ─── Addon packaging ───────────────────────────────────────────────────────

.PHONY: addon-zip
addon-zip: ## Build addon/JustInTime-v<version>.zip from .toc Version
	@cd $(ADDON_DIR) && rm -f $(ADDON_NAME)-v$(ADDON_VERSION).zip
	@cd $(ADDON_DIR) && zip -rq $(ADDON_NAME)-v$(ADDON_VERSION).zip $(ADDON_NAME)/ -x '*.DS_Store' '*/.*'
	@echo "✓ wrote $(ADDON_ZIP) (toc Version: $(ADDON_VERSION))"

.PHONY: addon-version
addon-version: ## Print the addon version read from the .toc
	@echo $(ADDON_VERSION)

# ─── Cleanup ───────────────────────────────────────────────────────────────

.PHONY: clean
clean: ## Remove HTTP cache, coverage artefacts, built zips
	rm -rf $(SCRIPTS_DIR)/.cache $(SCRIPTS_DIR)/htmlcov $(SCRIPTS_DIR)/.coverage $(SCRIPTS_DIR)/.pytest_cache
	rm -f $(ADDON_DIR)/$(ADDON_NAME)-v*.zip
