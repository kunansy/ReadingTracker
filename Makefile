lint: lint-black
	ruff . && mypy .

lint-flake:
	flake8

test:
	pytest -n 7

lint-black:
	black --check --diff --color .

format:
	black .

cov:
	coverage run -m pytest .

cov-show:
	coverage report -m

run:
	PYTHONPATH=. python3 tracker/main.py
