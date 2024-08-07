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
	@bumpversion --commit --tag patch

minor:
	@bumpversion --commit --tag minor

cov:
	coverage run -m pytest .

cov-show:
	coverage report -m

init:
	PYTHONPATH=. python3 tracker/main.py

run:
	PYTHONPATH=. uvicorn tracker.main:app --host 127.0.0.1 --port 9999 --reload --loop uvloop

.PHONY: all
all: lint test lint-format lint-mypy lint-ruff fmt patch minor cov cov-show init run
