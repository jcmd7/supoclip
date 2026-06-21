# Mission Control — top-level orchestrator.
# The hub is the product; SupoClip is one module under apps/supoclip.
.PHONY: help install lite full hub hub-down up down status setup supoclip supoclip-down test supoclip-pull gpu gpu-down

help:
	@echo "Mission Control — desktop setup"
	@echo "  make install      - one-time: .env, clone source modules, pull all images"
	@echo "  make lite         - START the zero-key core (hub + alerts + feeds), no GPU"
	@echo "  make full         - START everything that doesn't need a GPU (+ SupoClip, vendored)"
	@echo "  make gpu          - START GPU tools (ComfyUI; add Ollama with: make -C hub llm)"
	@echo "  make down         - stop everything"
	@echo "  make status       - print live module health JSON"
	@echo "  --- pieces ---"
	@echo "  make hub          - just the hub gateway + always-on modules"
	@echo "  make supoclip     - just the SupoClip app"
	@echo "  make setup        - clone vendored modules only"
	@echo "  make supoclip-pull- pull upstream SupoClip into apps/supoclip"
	@echo "  make test         - run the gateway + SupoClip test suites"

## ─── One-time install: config + source clones + image pulls ──────────────────
install:
	@test -f .env || (cp .env.example .env && echo "created .env — edit it to add keys (all optional for 'make lite')")
	$(MAKE) -C hub setup
	docker compose -f hub/docker-compose.hub.yml pull
	@echo ""
	@echo "Install complete. Start with:  make lite   (or 'make full' for everything non-GPU)"

## ─── Tiers ───────────────────────────────────────────────────────────────────
## Zero-key core: hub gateway + changedetection + RSSHub + ntfy + Uptime Kuma.
lite:
	$(MAKE) -C hub gateway
	@echo "Mission Control at http://localhost:8090"

## Everything that runs on CPU: lite + SupoClip + vendored stacks.
full:
	$(MAKE) -C hub up

## GPU tools (ComfyUI). Add local LLM with: make -C hub llm
gpu:
	$(MAKE) -C hub gpu

gpu-down:
	$(MAKE) -C hub gpu-down

## Hub gateway + always-on modules (changedetection, RSSHub, ntfy, Uptime Kuma)
hub:
	$(MAKE) -C hub gateway

hub-down:
	$(MAKE) -C hub gateway-down

## Everything: hub + SupoClip + vendored module stacks
up:
	$(MAKE) -C hub up

down:
	$(MAKE) -C hub down

setup:
	$(MAKE) -C hub setup

status:
	$(MAKE) -C hub status

## Just the SupoClip app (apps/supoclip)
supoclip:
	docker compose -f apps/supoclip/docker-compose.yml up -d

supoclip-down:
	docker compose -f apps/supoclip/docker-compose.yml down

## Test suites: gateway (pytest) + SupoClip
test:
	cd hub/gateway && python3 -m pytest test_gateway.py -q
	-$(MAKE) -C apps/supoclip test

## Pull upstream SupoClip (FujiwaraChoki/supoclip) into apps/supoclip via subtree.
## Run from a machine with network access (not the scoped cloud sandbox).
## First time, ensure the remote exists:
##   git remote add supoclip-upstream https://github.com/FujiwaraChoki/supoclip.git
supoclip-pull:
	git subtree pull --prefix=apps/supoclip supoclip-upstream main --squash
