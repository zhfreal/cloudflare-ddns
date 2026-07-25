PYTHON ?= $(shell [ -f .venv/bin/python ] && echo .venv/bin/python || echo python3)

.PHONY: help install install-dev clean format lint test test-cov build wheel upload

help:
	@echo "Available commands:"
	@echo "  make install      - Install the package"
	@echo "  make install-dev  - Install package with development dependencies"
	@echo "  make clean        - Remove build artifacts and cache files"
	@echo "  make format       - Format code with black and isort"
	@echo "  make lint         - Run linters (flake8, pylint)"
	@echo "  make test         - Run tests with pytest"
	@echo "  make test-cov     - Run tests with coverage report"
	@echo "  make build        - Build distribution packages (sdist and wheel)"
	@echo "  make wheel        - Build only the wheel package"
	@echo "  make upload       - Upload package to PyPI (requires credentials)"

install:
	$(PYTHON) -m pip install -e .

install-dev:
	$(PYTHON) -m pip install -e ".[dev]"
	$(PYTHON) -m pip install -r requirements-dev.txt

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache/
	rm -rf .mypy_cache/
	rm -rf .tox/
	rm -rf htmlcov/
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete
	find . -type f -name "*.pyd" -delete

format:
	$(PYTHON) -m black .
	$(PYTHON) -m isort .

lint:
	$(PYTHON) -m flake8 .
	$(PYTHON) -m pylint src

type-check:
	$(PYTHON) -m mypy src

test:
	-$(PYTHON) -m pytest

test-cov:
	-$(PYTHON) -m pytest --cov=. --cov-report=html --cov-report=term

build: clean
	@if $(PYTHON) -c "import build" >/dev/null 2>&1; then \
		$(PYTHON) -m build; \
	elif $(PYTHON) -m pip install build >/dev/null 2>&1; then \
		$(PYTHON) -m build; \
	else \
		$(PYTHON) setup.py sdist bdist_wheel; \
	fi

wheel: clean
	@if $(PYTHON) -c "import build" >/dev/null 2>&1; then \
		$(PYTHON) -m build --wheel; \
	elif $(PYTHON) -m pip install build >/dev/null 2>&1; then \
		$(PYTHON) -m build --wheel; \
	else \
		$(PYTHON) setup.py bdist_wheel; \
	fi

upload: build
	$(PYTHON) -m twine upload dist/*

check: format lint type-check test
	@echo "All checks passed!"
