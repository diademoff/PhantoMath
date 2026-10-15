/// Блокнот: локальная история решённых задач.
///
/// Каждая запись — условие и ответ (если он есть). Хранится в файле
/// `notebook.json` в каталоге приложения. Если файловая система недоступна
/// (например, в тестах), блокнот работает в памяти — без падений.
library;

import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:path_provider/path_provider.dart';

import '../model/core_node.dart';

/// Одна запись блокнота: условие, ответ и метаданные задачи.
///
/// Метаданные повторяют `ResultItemMetadata` из APK: идентификатор записи
/// (`uuid`), версия формата (`version`), время (`timestamp` = `savedAt`) и
/// вид результата (`source`, как `PhotoMathResultMetadataType`: `core`).
/// Дополнительно храним действие и язык — они описывают, чем именно решали.
@immutable
class NotebookEntry {
  const NotebookEntry({
    required this.problem,
    this.solution,
    required this.savedAt,
    this.uuid = '',
    this.version = 1,
    this.source = 'core',
    this.command,
    this.locale = 'ru',
    this.methodIndex = 0,
  });

  /// Условие задачи.
  final CoreNode problem;

  /// Ответ, если решатель его дал (тождество/противоречие — без ответа).
  final CoreNode? solution;

  final DateTime savedAt;

  /// Идентификатор записи.
  final String uuid;

  /// Версия формата записи.
  final int version;

  /// Вид результата (`core` — обычное решение).
  final String source;

  /// Действие над выражением (`factor`/`expand`/…), если было.
  final String? command;

  /// Язык пояснений.
  final String locale;

  /// Выбранный способ решения (индекс в вертикальной ветке).
  final int methodIndex;

  Map<String, dynamic> toJson() => {
    'problem': problem.toJson(),
    if (solution != null) 'solution': solution!.toJson(),
    'savedAt': savedAt.toIso8601String(),
    'uuid': uuid,
    'version': version,
    'source': source,
    if (command != null) 'command': command,
    'locale': locale,
    'methodIndex': methodIndex,
  };

  factory NotebookEntry.fromJson(Map<String, dynamic> json) {
    final solution = json['solution'];
    return NotebookEntry(
      problem: CoreNode.fromJson(json['problem'] as Map<String, dynamic>),
      solution: solution is Map<String, dynamic>
          ? CoreNode.fromJson(solution)
          : null,
      savedAt: DateTime.tryParse(json['savedAt'] as String? ?? '') ??
          DateTime.now(),
      uuid: json['uuid'] as String? ?? '',
      version: json['version'] as int? ?? 1,
      source: json['source'] as String? ?? 'core',
      command: json['command'] as String?,
      locale: json['locale'] as String? ?? 'ru',
      methodIndex: json['methodIndex'] as int? ?? 0,
    );
  }
}

/// История решённых задач.
class Notebook extends ChangeNotifier {
  Notebook({this.maxEntries = 50});

  final int maxEntries;

  final List<NotebookEntry> _entries = [];

  List<NotebookEntry> get entries => List.unmodifiable(_entries);

  bool get isEmpty => _entries.isEmpty;

  /// Прочитать историю с диска (если он доступен).
  Future<void> load() async {
    try {
      final file = await _file();
      if (!await file.exists()) return;
      final raw = jsonDecode(await file.readAsString());
      if (raw is! List) return;
      _entries
        ..clear()
        ..addAll([
          for (final item in raw)
            if (item is Map<String, dynamic>) NotebookEntry.fromJson(item),
        ]);
      notifyListeners();
    } on Object {
      // Диска нет (тесты, окружение без плагина) — работаем в памяти.
    }
  }

  /// Добавить запись (свежие — сверху).
  Future<void> add(NotebookEntry entry) async {
    _entries.insert(0, entry);
    if (_entries.length > maxEntries) {
      _entries.removeRange(maxEntries, _entries.length);
    }
    notifyListeners();
    await _save();
  }

  /// Очистить историю и вернуть удалённые записи (для отмены).
  ///
  /// Возврат списка позволяет интерфейсу показать «История очищена» с кнопкой
  /// «Отменить» и восстановить записи через [restore] (`clear_history_undo`
  /// в оригинале).
  Future<List<NotebookEntry>> clear() async {
    final removed = List<NotebookEntry>.of(_entries);
    _entries.clear();
    notifyListeners();
    await _save();
    return removed;
  }

  /// Восстановить ранее удалённые записи (отмена очистки).
  Future<void> restore(List<NotebookEntry> entries) async {
    _entries
      ..clear()
      ..addAll(entries);
    notifyListeners();
    await _save();
  }

  Future<File> _file() async {
    final directory = await getApplicationSupportDirectory();
    return File('${directory.path}/notebook.json');
  }

  Future<void> _save() async {
    try {
      final file = await _file();
      await file.writeAsString(
        jsonEncode([for (final entry in _entries) entry.toJson()]),
      );
    } on Object {
      // Нет диска — запись остаётся только в памяти текущего запуска.
    }
  }
}
