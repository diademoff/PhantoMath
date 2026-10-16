import 'package:flutter/foundation.dart';

enum SolverStatus { starting, ready, failed }

/// UI lifecycle only; the solver and its wire protocol are unchanged.
class SolverStartup extends ChangeNotifier {
  SolverStartup(this._start);
  final Future<void> Function() _start;
  SolverStatus status = SolverStatus.starting;
  Future<void>? _pending;
  bool _disposed = false;

  Future<void> ensureReady() {
    if (status == SolverStatus.ready) return Future.value();
    return _pending ??= _run();
  }

  Future<void> _run() async {
    status = SolverStatus.starting;
    if (!_disposed) notifyListeners();
    try {
      await Future<void>.sync(_start);
      status = SolverStatus.ready;
    } catch (_) {
      status = SolverStatus.failed;
      rethrow;
    } finally {
      _pending = null;
      if (!_disposed) notifyListeners();
    }
  }

  @override
  void dispose() {
    _disposed = true;
    super.dispose();
  }
}
