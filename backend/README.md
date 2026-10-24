# mymath_backend

The PhantoMath solver: Python 3.12 + SymPy. It takes an expression tree (`CoreNode`) and returns
the answer with explained steps. See [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

```bash
uv sync --python 3.12                 # solver only: sympy
uv sync --python 3.12 --extra api     # + FastAPI/pydantic for the HTTP layer and the tests
uv run uvicorn mymath_backend.api:app --reload   # OpenAPI docs at http://127.0.0.1:8000/docs

uv run pytest
uv run ruff check . && uv run ruff format --check . && uv run mypy mymath_backend
```

| Module | What it does |
|---|---|
| `input.py` | keyboard protocol and AST JSON → `CoreNode` |
| `solver/` | one module per topic, registered by node type |
| `teaching*.py` | authored lessons and offline theory |
| `data/explanations.json` | step templates in English (`default`) and Russian |
| `explanations.py` | template rendering: `ARGn`, concept links, locale fallback |
| `service.py` | the framework-free service: solve, parse, graph, theory |
| `api.py` / `device.py` | FastAPI for development / stdlib HTTP server on the phone |

`MYMATH_EXPLANATIONS` overrides the path to the dictionary. A problem the solver cannot handle
returns `422` with a translated message:

```json
{"detail": {"message": "Division by zero", "explanation": "div_with_zero"}}
```

`tests/corpus/*.json` is a hand-written corpus: input, expected answer and expected order of step
keys for each topic.
