lint:
	@$(MAKE) lint-ruff
	@$(MAKE) lint-format
	@$(MAKE) lint-mypy

test:
	pytest -n 7

lint-mypy:
	@mypy . > /dev/null

lint-ruff:
	@ruff check .

lint-format:
	@ruff format --check --quiet

fmt:
	@ruff format
	@ruff check --fix

cov:
	coverage run -m pytest .

cov-show:
	coverage report -m

init:
	PYTHONPATH=. python3 tracker/main.py

run:
	PYTHONPATH=. uvicorn tracker.main:app --host 127.0.0.1 --port 9999 --reload --loop uvloop
