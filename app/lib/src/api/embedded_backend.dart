/// Встроенный бэкенд: CPython и решатель внутри приложения.
///
/// На Android Python-программа запускается встроенным интерпретатором
/// (`serious_python`) в фоновом потоке и слушает `localhost`. Приложение
/// ходит к ней по HTTP, как к обычному бэкенду, — тот же контракт. Так
/// решатель работает **без сети**: Python и все зависимости лежат в APK.
library;

import 'dart:io';

import 'package:http/http.dart' as http;
import 'package:serious_python/serious_python.dart';

/// Порт локального сервера; совпадает с `mymath_backend.device.DEFAULT_PORT`.
const int embeddedPort = 8770;

/// Базовый адрес встроенного сервера.
const String embeddedBaseUrl = 'http://127.0.0.1:$embeddedPort';

/// Запустить встроенный Python и дождаться готовности решателя.
///
/// Возвращает базовый адрес или `null`, если платформа не поддерживается
/// либо сервер не поднялся (тогда приложение откатывается к внешнему
/// бэкенду из `MYMATH_API`).
Future<String?> startEmbeddedBackend() async {
  if (!Platform.isAndroid) return null;
  try {
    await SeriousPython.run(
      environmentVariables: {'MYMATH_PORT': '$embeddedPort'},
    );
  } on Object {
    return null;
  }
  return await waitForHealth(embeddedBaseUrl) ? embeddedBaseUrl : null;
}

/// Дождаться ответа `GET /api/v1/health` с кодом 200.
///
/// Python стартует в фоне: интерпретатор и импорт sympy занимают время,
/// поэтому адрес готов не сразу.
Future<bool> waitForHealth(
  String baseUrl, {
  Duration timeout = const Duration(seconds: 60),
}) async {
  final deadline = DateTime.now().add(timeout);
  final client = http.Client();
  try {
    while (DateTime.now().isBefore(deadline)) {
      try {
        final response = await client
            .get(Uri.parse('$baseUrl/api/v1/health'))
            .timeout(const Duration(seconds: 3));
        if (response.statusCode == 200) return true;
      } on Object {
        // Сервер ещё поднимается — ждём дальше.
      }
      await Future<void>.delayed(const Duration(milliseconds: 300));
    }
  } finally {
    client.close();
  }
  return false;
}
