lint:
	@$(MAKE) lint-ruff
	@$(MAKE) lint-format
	@$(MAKE) lint-mypy

test:
	pytest -vvv -n 7

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
	@curl -L \
		-H "Accept: application/vnd.github+json" \
		-H "X-GitHub-Api-Version: 2022-11-28" \
		https://api.github.com/repos/kunansy/ReadingTracker/actions/runs \
		| jq '.workflow_runs | .[0] | .display_title,.status,.conclusion'

CURRENT_TAG := $(shell git describe --tags --abbrev=0)
LAST_TAG := $(shell git describe --tags --abbrev=0 HEAD^)
IMAGE_LINE := $(shell cat docker-compose.yml | grep -n "image: kunansy/reading_tracker" | cut -f1 -d:)

deploy:
	@echo "${LAST_TAG} -> ${CURRENT_TAG}"
	@ssh tracker "cd tracker; sed -i '${IMAGE_LINE} s/${LAST_TAG}/${CURRENT_TAG}/' docker-compose.yml; docker-compose up -d --build --force-recreate tracker-app; sleep 2; docker ps --filter name=tracker-app --format json | jq '.Image,.State,.Status'"

cov:
	coverage run -m pytest .

cov-show:
	coverage report -m

init:
	PYTHONPATH=. python3 tracker/main.py

run:
	PYTHONPATH=. uvicorn tracker.main:app --host 127.0.0.1 --port 9999 --reload --loop uvloop

.PHONY: all
all: lint test lint-format lint-mypy lint-ruff fmt patch cov cov-show init run
