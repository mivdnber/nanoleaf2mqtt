all: .venv/installed
.PHONY: check format

uvenv/.installed: uv-requirements.txt
	python3 -m venv uvenv
	uvenv/bin/pip install -r uv-requirements.txt --disable-pip-version-check
	touch uvenv/.installed

uv.lock: pyproject.toml
	./uv lock

.venv/installed: uvenv/.installed uv.lock
	./uv sync
	touch .venv/.installed

format:
	./uv run ruff format .

check:
	./uv run ruff check .

