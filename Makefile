lint:
	@$(MAKE) lint-ruff
	@$(MAKE) lint-format
	@$(MAKE) lint-mypy

test:
	pytest -vvvv

test-unit:
	pytest tests/unit

# needs a running Docker daemon: starts throwaway PostgreSQL and Manticore containers
test-integration:
	pytest tests/integration

# calls the real habr.com and YouTube API
test-network:
	pytest tests/network -m network

lint-mypy:
	@mypy .

lint-ruff:
	@ruff check .

lint-format:
	@ruff format --check --quiet

fmt:
	@ruff format
	@ruff check --fix

patch:
	@bumpversion --commit --tag version

build-status:
	@curl -L --silent \
		-H "Accept: application/vnd.github+json" \
		-H "X-GitHub-Api-Version: 2022-11-28" \
		https://api.github.com/repos/kunansy/ReadingTracker/actions/runs \
		| jq '[.workflow_runs | .[] | select(.name == "Build docker image")] | .[0] | .name,.display_title,.status,.conclusion'

CURRENT_TAG := $(shell git describe --tags --abbrev=0)
LAST_TAG := $(shell git describe --tags --abbrev=0 HEAD^)

deploy:
	@echo "${LAST_TAG} -> ${CURRENT_TAG}"
	@ssh tracker "set -e; cd tracker; \
		sed -i -E 's#(image: kunansy/reading_tracker):[0-9]+#\1:${CURRENT_TAG}#' docker-compose.yml; \
		grep -q 'image: kunansy/reading_tracker:${CURRENT_TAG}' docker-compose.yml || { echo 'image tag not updated' >&2; exit 1; }; \
		docker compose up -d --build --force-recreate tracker-app; sleep 2; \
		docker ps --filter name=tracker-app --format json | jq '.Image,.State,.Status'; \
		test \"\$$(docker ps --filter name=tracker-app --format '{{.Image}}')\" = 'kunansy/reading_tracker:${CURRENT_TAG}' || { echo 'wrong image running' >&2; exit 1; }"

cov:
	coverage run -m pytest
	coverage combine
	coverage report

cov-show:
	coverage report -m

init:
	PYTHONPATH=. python3 tracker/main.py

gen-api:
	python3 -m tracker.openapi_dump frontend/openapi.json
	npm --prefix frontend run gen:api

run:
	PYTHONPATH=. gunicorn tracker.main:app --bind 127.0.0.1:9999 --worker-class asgi --asgi-loop uvloop --reload

.PHONY: all
all: lint test test-unit test-integration test-network lint-format lint-mypy lint-ruff fmt patch cov cov-show init run gen-api
