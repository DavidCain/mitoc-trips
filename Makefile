.DEFAULT_GOAL := all

poetry_dev_bootstrap_file = .poetry_dev_up_to_date
poetry_prod_bootstrap_file = .poetry_prod_up_to_date
npm_bootstrap_file = .node_packages_up_to_date


# Default `make` will give everything's that helpful for local development.
.PHONY: all
all: install-python-dev install-js

# Build everything needed for deployment in production
.PHONY: build
build: install-python-prod build-frontend

.PHONY: install-python-dev
install-python-dev: $(poetry_dev_bootstrap_file)
$(poetry_dev_bootstrap_file): poetry.lock
	touch $(poetry_dev_bootstrap_file).notyet
	poetry install --no-root
	mv $(poetry_dev_bootstrap_file).notyet $(poetry_dev_bootstrap_file)
	@# Remove the prod bootstrap file, since we now have dev deps present.
	rm -f $(poetry_prod_bootstrap_file)

# Note this will actually *remove* any dev dependencies, if present
.PHONY: install-python-prod
install-python-prod: $(poetry_prod_bootstrap_file)
$(poetry_prod_bootstrap_file): poetry.lock
	touch $(poetry_prod_bootstrap_file).notyet
	poetry install --no-root --no-dev
	mv $(poetry_prod_bootstrap_file).notyet $(poetry_prod_bootstrap_file)
	@# Remove the dev bootstrap file, since the `--no-dev` removed any present dev deps
	rm -f $(poetry_dev_bootstrap_file)

.PHONY: install-js
install-js: $(npm_bootstrap_file)
$(npm_bootstrap_file): frontend/package.json frontend/package-lock.json
	touch $(npm_bootstrap_file).notyet
	npm --prefix=frontend/ ci
	mv $(npm_bootstrap_file).notyet $(npm_bootstrap_file)

# Build webpack-stats.json, which Django webpack loader will serve
# (Needed for production as well as tests, which behave like production)
.PHONY: build-frontend
build-frontend: install-js
	npm --prefix=frontend/ run build

.PHONY: check
check: lint test

# Run automatic code formatters/linters that don't require human input
# (might fix a broken `make check`)
.PHONY: fix
fix: install-python-dev
	poetry run black ws
	poetry run ruff --fix .

.PHONY: lint
lint: lint-python typecheck-python lint-js

.PHONY: lint-python
lint-python: install-python-dev
	poetry run black --fast --check ws
	poetry run ruff .
	poetry run pylint --jobs 0 ws  # '0' tells pylint to auto-detect available processors

.PHONY: typecheck-python
typecheck-python: install-python-dev
	poetry run mypy --config-file pyproject.toml ws

.PHONY: lint-js
lint-js: install-js
	npm --prefix=frontend/ run lint

.PHONY: test
test: test-python test-js

.PHONY: test-python
test-python: install-python-dev build-frontend
	WS_DJANGO_TEST=1 poetry run coverage run -m pytest

.PHONY: test-js
test-js: install-js
	npm --prefix=frontend/ run test:unit -- --coverage

# Production webservers won't run this way, so install dev dependencies
.PHONY: run
run: install-python-dev
	poetry run python -Wd manage.py runserver

.PHONY: run-js
run-js: install-js
	NODE_ENV=development npm --prefix=frontend/ run serve

.PHONY: clean
clean:
	rm -f $(poetry_dev_bootstrap_file)
	rm -f $(poetry_prod_bootstrap_file)
	rm -f $(npm_bootstrap_file)
	rm -rf .mypy_cache
	find . -name '*.pyc' -delete
