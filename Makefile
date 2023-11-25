lint: lint-black
	ruff . && mypy .

lint-flake:
	flake8 && mypy .

test:
	pytest -n 7

lint-black:
	black --check --diff --color .

format:
	black .

run:
	PYTHONPATH=. python3 tracker/main.py
