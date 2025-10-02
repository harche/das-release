.PHONY: help test test-unit test-e2e check-deps clean install

help:
	@echo "InstaSlice Operator Release Automation"
	@echo ""
	@echo "Available targets:"
	@echo "  make help        - Show this help message"
	@echo "  make check-deps  - Check required system dependencies"
	@echo "  make test        - Run all tests (unit + e2e)"
	@echo "  make test-unit   - Run unit tests only"
	@echo "  make test-e2e    - Run end-to-end tests (requires real repos)"
	@echo "  make clean       - Remove temporary files"
	@echo "  make install     - Make release.sh executable"
	@echo ""
	@echo "Usage:"
	@echo "  ./release.sh              - Run release automation"
	@echo "  ./release.sh --dry-run    - Run without committing"
	@echo "  ./release.sh --check-deps - Check dependencies only"
	@echo "  ./release.sh --help       - Show detailed help"

install:
	chmod +x release.sh
	chmod +x src/release_manager.py

check-deps:
	@./release.sh --check-deps

test: test-unit test-e2e

test-unit:
	@echo "Running unit tests..."
	@cd $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST)))) && python3 -m unittest discover -s tests/unit -p 'test_*.py' -v

test-e2e:
	@echo "Running end-to-end tests..."
	@echo "Note: E2E tests require real repositories and network access"
	@cd $(shell dirname $(realpath $(firstword $(MAKEFILE_LIST)))) && python3 -m unittest discover -s tests/e2e -p 'test_*.py' -v

clean:
	find . -type f -name '*.pyc' -delete
	find . -type d -name '__pycache__' -delete
	find . -type d -name '*.egg-info' -exec rm -rf {} + 2>/dev/null || true
