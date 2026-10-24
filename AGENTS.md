# PhantoMath — rules for coding agents

Flutter app (`app/`) with an embedded Python solver (`backend/mymath_backend`, sympy). UI and
explanations: Russian (ru) and English. Overview: `docs/ARCHITECTURE.md`.

## Commands
- Python: always `backend/.venv/bin/python` (never system python). Solve one input:
  `from mymath_backend import service; from mymath_backend.input import parse_protocol;
  service.solve_request(parse_protocol(PROTO).to_contract(), render=True, locale="ru")`
- Input protocol: `docs/ARCHITECTURE.md`; real examples in `backend/tests/inputs.json` (`proto`)
  and `tools/fuzz/*.py`. Matrix: `{mat({mat_row({1},{2})},{mat_row({3},{4})})}`,
  determinant: `{det({mat(...)})}`, inverse `{M^(-1)}`.
- Tests: `cd backend && uv run pytest -q`; `cd app && flutter test`; formulas through the real TeX parser: `make audit`.
- Lint: `make lint`. Random checks vs sympy: `backend/.venv/bin/python tools/fuzz/matrices.py SEED`.
- APK: `make apk` (first `rm -rf app/build/serious_python_android`, else the APK keeps the old solver);
  install: `adb install -r app/build/app/outputs/flutter-apk/app-release.apk`.

## Explanation texts
- Step templates: `backend/mymath_backend/data/explanations.json`, keys with `default` (English) and `ru`.
  Keep `ARGn` and `[label|uuid]` the same in both languages. Lessons and theory: `teaching*.py`.
- UI strings: `tr('Русский', 'English')` from `app/lib/src/i18n.dart`.

## Device (Pixel 4a over adb, emulator AVD `mymath_api36`)
- `tools/device/drive.py` drives the app over adb (see `tools/device/README.md`).
- `uiautomator dump` must be non-compressed; formulas are custom-drawn and NOT in the dump — only screenshots
  (`adb exec-out screencap -p > file.png`) show them. First keystrokes after opening the app can be lost: wait ~1 s.
- `flutter test integration_test` uninstalls our APK — reinstall the release APK afterwards.

## Code rules
- Smallest complete change; match surrounding style; no new dependencies.
- Fix the root cause in shared code; every behaviour fix gets a small test in `backend/tests/`.
- Do NOT commit — the operator reviews and commits.
- Temporary files go to `build/` (git-ignored), not the repo tree.
