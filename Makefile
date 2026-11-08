.DEFAULT_GOAL := help

COMPOSE ?= docker compose
WAIT_TIMEOUT ?= 60

.PHONY: help start up stop down restart build logs status test

help:
	@echo make start   - Build and start the app; wait until healthy
	@echo make stop    - Stop and remove the project containers
	@echo make restart - Stop, rebuild and start the app
	@echo make build   - Build the image without starting it
	@echo make logs    - Follow the backend logs
	@echo make status  - Show container status
	@echo make test    - Run Python and API tests in Docker

start up:
	$(COMPOSE) up --build --wait --wait-timeout $(WAIT_TIMEOUT)

stop down:
	$(COMPOSE) down

restart:
	$(COMPOSE) down
	$(COMPOSE) up --build --wait --wait-timeout $(WAIT_TIMEOUT)

build:
	$(COMPOSE) build

logs:
	$(COMPOSE) logs --follow web

status:
	$(COMPOSE) ps

test:
	docker build --target checks -t weibull-lab-checks .
