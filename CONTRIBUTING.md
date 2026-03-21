# Contributing to qfl

## Setup

```bash
git clone https://github.com/Aliipou/qfl.git
cd qfl
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Running Tests

```bash
pytest tests/ -v --cov=qfl
```

Financial calculations must be deterministic and testable. If you add a new calculation, include numerical tests with known expected values.

## Code Style

- Python 3.10+, type hints required
- `ruff` for linting, `black` for formatting
- Docstrings with parameter types and return values

## Commit Messages

`feat:`, `fix:`, `docs:`, `test:`, `perf:`, `chore:`
