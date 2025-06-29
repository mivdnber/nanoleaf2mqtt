---
trigger: glob
globs: *.py
---

- use Python 3.10+ type annotations, e.g. dict[str, int] instead of Dict[str, int]
- use modern type union syntax, e.g. int | None instead of Optional[int]
- prefer early returns over nested if blocks
- use match/case when applicable
- the Python interpreter is at .venv/bin/python
- add dependencies in pyproject.toml, never to uv-requirements.txt