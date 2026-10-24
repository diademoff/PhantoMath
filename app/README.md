# PhantoMath app

Flutter client for Android: structural formula editor, maths keyboard, live answer, step screen,
graphs, notebook and settings. The Python solver is embedded and answers on `127.0.0.1:8770`.
See [`../docs/ARCHITECTURE.md`](../docs/ARCHITECTURE.md).

```bash
flutter pub get
flutter analyze
flutter test
```

Build from the repository root: `make apk` (packs the solver with SymPy into the APK).

During development the app can talk to a desktop solver instead of the embedded one:

```bash
make backend   # in another terminal
flutter run --dart-define=MYMATH_API=http://10.0.2.2:8000   # emulator → host
```

Integration tests on a USB device: `flutter test integration_test -d <device-id>` (they uninstall
the release APK — reinstall it afterwards). Keep the phone unlocked during the run.
