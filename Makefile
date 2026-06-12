# Mission Control — top-level orchestrator.
# The hub is the product; SupoClip is one module under apps/supoclip.
.PHONY: help hub hub-down up down status setup supoclip supoclip-down test

help:
	@echo "Mission Control"
	@echo "  make hub         - start the hub gateway + always-on modules (no keys needed)"
	@echo "  make up          - start the hub + SupoClip + vendored modules"
	@echo "  make down        - stop everything"
	@echo "  make setup       - clone vendored modules (Flowsint, MiroFish, Firecrawl, Perplexica)"
	@echo "  make status      - print live module health JSON"
	@echo "  make supoclip    - start just the SupoClip app"
	@echo "  make test        - run SupoClip's test suite"

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

## SupoClip's own test suite
test:
	$(MAKE) -C apps/supoclip test
