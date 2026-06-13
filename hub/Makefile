.PHONY: setup up down status gateway gateway-down llm llm-down gpu gpu-down

setup:
	./setup.sh

## Start every module + the hub gateway.
up:
	docker compose -f ../apps/supoclip/docker-compose.yml up -d
	@if [ -d vendor/flowsint ]; then \
		docker compose -f vendor/flowsint/docker-compose.prod.yml --project-directory vendor/flowsint up -d || \
		(cd vendor/flowsint && make prod); \
	else echo "vendor/flowsint missing — run 'make setup' first"; fi
	@if [ -d vendor/mirofish ]; then \
		docker compose --project-directory vendor/mirofish up -d || \
		echo "MiroFish compose failed — check vendor/mirofish/.env"; \
	else echo "vendor/mirofish missing — run 'make setup' first"; fi
	docker compose -f docker-compose.hub.yml up -d --build
	@echo "Hub running at http://localhost:8090"

down:
	-docker compose -f docker-compose.hub.yml down
	-docker compose --project-directory vendor/mirofish down
	-docker compose -f vendor/flowsint/docker-compose.prod.yml --project-directory vendor/flowsint down
	docker compose -f ../apps/supoclip/docker-compose.yml down

## Just the gateway (useful when modules are managed separately).
gateway:
	docker compose -f docker-compose.hub.yml up -d --build

gateway-down:
	docker compose -f docker-compose.hub.yml down

## Local LLM stack (Ollama + Open WebUI). Pull a model after first start:
##   docker exec hub-ollama ollama pull llama3.2
llm:
	docker compose -f docker-compose.hub.yml --profile llm up -d
	@echo "Open WebUI at http://localhost:3200, Ollama API at :11434"

llm-down:
	docker compose -f docker-compose.hub.yml --profile llm down

## Local video generation (ComfyUI). NVIDIA GPU required. Download Wan/LTX
## weights into hub/comfyui/models/ after first start (see README).
gpu:
	docker compose -f docker-compose.hub.yml --profile gpu up -d
	@echo "ComfyUI at http://localhost:8188 (place model weights in hub/comfyui/models/)"

gpu-down:
	docker compose -f docker-compose.hub.yml --profile gpu down

status:
	@curl -sf http://localhost:8090/api/status | python3 -m json.tool
