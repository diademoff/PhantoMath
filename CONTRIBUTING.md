# Contributing to PhantoMath

Thanks for helping! Bug reports, wrong or unclear steps, new topics and translations are all welcome.

## Reporting a problem

Open an issue with:

- the problem exactly as you typed it (or a screenshot of the input);
- what the app showed and what you expected;
- the app language (English or Russian).

A wrong step is a bug even when the final answer is right.

## Setting up

```bash
cd backend && uv sync --python 3.12 --extra api
cd ../app && flutter pub get
```

Requirements: Flutter 3.x, Android SDK (platform 36), JDK 17+, Python 3.12, [uv](https://docs.astral.sh/uv/).

## Before you open a pull request

```bash
make lint    # ruff, ruff format, mypy, flutter analyze
make test    # backend pytest + flutter test
```

- Keep changes small and focused; match the style of the surrounding code.
- Every behaviour fix gets a small test in `backend/tests/` (or `app/test/` for the UI).
- A new explanation text goes to `backend/mymath_backend/data/explanations.json` in **both**
  `default` (English) and `ru`; keep `ARGn` placeholders and `[label|uuid]` links consistent.
- UI strings go through `tr('Русский', 'English')` from `app/lib/src/i18n.dart`.
- No new dependencies without a good reason — the solver must stay pure Python + SymPy so it
  fits into the APK.

## Where things live

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the layout, the request/response format and
how steps get their texts.

By contributing you agree that your work is licensed under [GPL-3.0-or-later](LICENSE).
