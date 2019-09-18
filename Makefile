.DEFAULT_GOAL := all

poetry_bootstrap_file = .poetry_up_to_date


.PHONY: all
all: install

.PHONY: install-python
install-python: $(poetry_bootstrap_file)
$(poetry_bootstrap_file): poetry.lock
	touch $(poetry_bootstrap_file).notyet
	poetry install
	poetry install --extras=code_coverage
	mv $(poetry_bootstrap_file).notyet $(poetry_bootstrap_file)

.PHONY: install
install: install-python

.PHONY: check
check: lint test

# Run automatic code formatters/linters that don't require human input
# (might fix a broken `make check`)
.PHONY: fix
fix: install
	black ws
	isort --recursive ws

.PHONY: lint
lint: install
	black --fast --check ws
	isort --recursive --check ws
	pylint --jobs 0 ws  # '0' tells pylint to auto-detect available processors

.PHONY: test
test: install
	WS_DJANGO_TEST=1 coverage run manage.py test

.PHONY: run
run: install
	./manage.py runserver

.PHONY: clean
clean:
	rm -f $(poetry_bootstrap_file)
	find . -name '*.pyc' -delete
