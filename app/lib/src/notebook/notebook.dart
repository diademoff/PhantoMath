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

/// Одна запись блокнота.
@immutable
class NotebookEntry {
  const NotebookEntry({
    required this.problem,
    this.solution,
    required this.savedAt,
  });

  /// Условие задачи.
  final CoreNode problem;

  /// Ответ, если решатель его дал (тождество/противоречие — без ответа).
  final CoreNode? solution;

  final DateTime savedAt;

  Map<String, dynamic> toJson() => {
    'problem': problem.toJson(),
    if (solution != null) 'solution': solution!.toJson(),
    'savedAt': savedAt.toIso8601String(),
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

  /// Очистить историю.
  Future<void> clear() async {
    _entries.clear();
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
