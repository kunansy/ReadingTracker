NUMCPU := $(shell nproc 2> /dev/null || sysctl -n hw.ncpu 2> /dev/null)

lint: lint-black
	ruff . && mypy .

lint-flake:
	flake8

test:
	pytest -n 7

lint-black:
	black --check --diff --workers $(NUMCPU) --color .

format:
	black .

cov:
	coverage run -m pytest .

cov-show:
	coverage report -m

run:
	PYTHONPATH=. python3 tracker/main.py
