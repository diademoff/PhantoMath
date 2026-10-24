# Architecture

PhantoMath is two programs that ship as one Android app:

* **`app/`** — a Flutter client: the structural formula editor, the maths keyboard,
  the step-by-step screen, graphs, the notebook and the settings.
* **`backend/`** — `mymath_backend`, a Python solver built on [SymPy](https://www.sympy.org).
  It turns an expression tree into an answer plus a list of explained steps.

On the phone the solver runs **inside the app**: [`serious_python`](https://pub.dev/packages/serious_python)
starts CPython in a background thread, `app/python/main.py` opens a tiny HTTP server on
`127.0.0.1:8770` (`mymath_backend.device`, standard library only) and the Flutter side talks to
it like to any backend. Nothing leaves the device. On a desktop the same solver is served by
FastAPI (`mymath_backend.api`) for development.

```
┌──────────── Flutter (app/lib) ─────────────┐        ┌────────── Python (backend) ──────────┐
│ keyboard → editor tree → CoreNode JSON ──┼──HTTP──▶ │ input.py  → CoreNode                  │
│                                            │        │ solver/*   → steps (keys + args)      │
│ step screen ◀── CoreSolverData JSON ◀─────┼────────│ service.py → texts from the dictionary│
└────────────────────────────────────────────┘        └───────────────────────────────────────┘
```

## Repository layout

| Path | What lives there |
|---|---|
| `app/lib/main.dart` | Input screen, live answer, solution screen, drawer |
| `app/lib/src/editor/` | Structural editor: model, caret, conversion to `CoreNode` |
| `app/lib/src/ui/keyboard/` | Keyboard sheets, keys, long-press variants |
| `app/lib/src/ui/vertical_result.dart` | The step screen: stages, «More detail», «Why?» |
| `app/lib/src/render/` | `CoreNode` → LaTeX, graph view, highlighting |
| `app/lib/src/i18n.dart` | `tr(ru, en)` — the whole UI follows one language switch |
| `backend/mymath_backend/input.py` | Keyboard protocol and AST JSON → `CoreNode` |
| `backend/mymath_backend/solver/` | One module per topic, registered by node type |
| `backend/mymath_backend/teaching*.py` | Authored lessons and offline theory articles |
| `backend/mymath_backend/data/explanations.json` | Step texts in Russian and English |
| `backend/mymath_backend/service.py` | Rendering texts, choosing the default action, graph sampling |
| `backend/tests/` | Unit tests, the hand-written corpus (`corpus/`), sample inputs |
| `tools/fuzz/` | Random checks of the solver against SymPy |
| `tools/audit/` | Every answer formula through the app's real TeX parser |
| `tools/device/` | Drives a phone or emulator over `adb` and takes screenshots |

## The expression tree: `CoreNode`

Every formula — the problem, each intermediate row, the answer — is the same tree:

```json
{"type": "EQUALS", "children": [
  {"type": "ADD", "children": [
    {"type": "MULTIPLY_IMPLICIT", "children": [{"type": "CONSTANT", "value": "2"}, {"type": "VARIABLE", "value": "x"}]},
    {"type": "CONSTANT", "value": "3"}]},
  {"type": "CONSTANT", "value": "7"}]}
```

* `type` is one of 143 node types (`backend/mymath_backend/node_types.py`, mirrored in
  `app/lib/src/model/core_node.dart`).
* `value` is a string on leaves (`"3"`, `"x"`, `"π"`), absent on inner nodes.
* `children` are ordered; an empty list is omitted.
* `color` / `crossed` mark the parts a step changes (`CoreColoredNode`).

## The keyboard protocol

The keyboard sends a compact text form that `input.py` parses into `CoreNode`. Every
argument is wrapped in braces:

| Input | Meaning |
|---|---|
| `{2x+3=7}` or `{=({2x+3},{7})}` | an equation |
| `{frac({1},{x})}` | `1/x` |
| `{x^2}`, `{root2({x})}`, `{root({3},{x})}` | power, square root, n-th root |
| `{log({x},{2})}`, `{log10({x})}`, `{ln({x})}` | logarithms |
| `{system({=({x+y},{3})},{=({x-y},{1})})}` | a system |
| `{mat({mat_row({1},{2})},{mat_row({3},{4})})}` | a matrix; `{det({mat(…)})}` its determinant |
| `{lim({0},{frac({sin({x})},{x})})}` | a limit |
| `{integral({x^2})}`, `{derivation_diff({x},{x^3})}` | integral and derivative |
| `pi`, `inf`, `\i`, `\e` | π, ∞, the imaginary unit, Euler's number |

`backend/tests/inputs.json` lists 144 real inputs across all topics.

## A request

`POST /api/v1/solve`

```json
{"node": { …CoreNode… }, "action": {"command": "factor", "args": []}, "locale": "en"}
```

* `action` is optional: without it the solver picks the default (solve, evaluate, …).
  Commands: `factor`, `expand`, `simplify`, `domain`, `range`, `restrictions`, `intercepts`,
  `inverse_function`, `partial_fractions`, `extrema`, `inflection`, `asymptotes`, `conic`,
  `convergence`, `area`, `to_degrees`, `matrix_rank`, … (see `solver/commands.py`).
* `locale` is `ru` or anything else for English.

Other endpoints: `POST /api/v1/parse` (protocol string → tree), `POST /api/v1/graph`
(points of `y = f(x)`), `GET /api/v1/theory` (offline articles), `GET /api/v1/health`.

## A response: `CoreSolverData`

```
result
├── problem             CoreNode — what was solved
├── solution            CoreNode — the answer shown on top
└── groups[]            one group per way of solving
    └── entries[]
        ├── action      the command that produced it (or null)
        └── result
            ├── solutionNode
            ├── selectMethodText   the method's name in the switcher
            └── steps[]            main steps
                ├── headers[]      CoreRichText — the step title
                └── substeps[]     stages of the step
                    ├── left / right    the formula before and after
                    ├── description     CoreRichText — what happened
                    └── subresult       optional nested solution («More detail»)
```

A `CoreRichText` is a dictionary key plus arguments: `{"type": "rel_move_right_const_eq",
"args": [ … ]}`. With `render=True` the service also attaches the finished text:

```json
"explanation": {
  "key": "rel_move_right_const_eq",
  "text": "Move the constant to the right side, flipping its sign",
  "links": [{"label": "constant", "uuid": "…", "definition": "…"}],
  "theory": {"title": "Equivalent equations", "formula": "…", "example": "…", "mistake": "…"}
}
```

A problem that cannot be solved returns `422` with a translated message, never `500`.

## Explanation texts

`data/explanations.json` holds every step template:

```json
"conics_classify_circle": {
  "arity": 3,
  "templates": {
    "default": "The equation takes the form ARG1: a [circle|b56e7f77-…] with radius ARG2 and center ARG3",
    "ru": "Уравнение приводится к виду ARG1: это окружность радиуса ARG2 с центром ARG3"
  }
}
```

* `ARGn` is replaced by the n-th rendered argument.
* `[label|uuid]` becomes a tappable link to a short definition (`concepts.py`).
* A trailing `[uuid]` names the theory topic of the step.
* `default` is English; a locale without its own template falls back to it.

The teaching packs (`teaching_algebra.py`, `teaching_calculus.py`, `teaching_discrete.py`)
add lesson cards and theory articles in both languages. Every lesson is checked against SymPy
before it is offered.

## Solver modules

`solver/__init__.py` routes a node to the module registered for its type: arithmetic,
fractions, powers and roots, logarithms, trigonometry, absolute value, equations (linear,
quadratic, rational, irrational, exponential, logarithmic, trigonometric), inequalities,
systems, matrices and determinants, derivatives, limits, integrals (indefinite, definite,
improper, area), series and convergence, sequences, combinatorics, complex numbers, vectors,
differential equations, conics and function analysis. A module appends `Step`s to a
`SolveResult`; several ways of solving become several groups.

## Testing

```bash
make test     # backend pytest + flutter test
make lint     # ruff, ruff format, mypy, flutter analyze
make audit    # every answer formula through the app's TeX parser
backend/.venv/bin/python tools/fuzz/matrices.py 1   # random checks vs SymPy
```

`backend/tests/corpus/*.json` is a hand-written corpus: input, expected answer and the expected
order of step keys. Answers are compared structurally, so formatting changes do not break it.
