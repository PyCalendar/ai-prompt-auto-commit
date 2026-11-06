.venv/.installed: pyproject.toml
	python3 -m venv .venv
	.venv/bin/pip install --quiet --upgrade pip
	.venv/bin/pip install --quiet -e .[dev]
	touch .venv/.installed

.PHONY: dev
dev: .venv/.installed
	.venv/bin/pre-commit install
	.venv/bin/prepare-ai-repository

.PHONY: test
test: .venv/.installed
	.venv/bin/tox -e py

.PHONY: clean
clean:
	.venv/bin/pre-commit clean 2>/dev/null || true
	.venv/bin/pre-commit uninstall 2>>/dev/null || true
	rm -rf .venv .pytest_cache __pycache__ *.egg-info ai_prompt_auto_commit.egg-info
