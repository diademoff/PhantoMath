/// Определения функций, введённые пользователем (`f(x) = …`).
///
/// Определение — это уравнение, у которого слева стоит вызов `FUNCTION`
/// с переменными-параметрами, а справа — тело. Хранится как `CoreNode`, чтобы
/// уйти на бэкенд в поле `definitions` без преобразований; сервер остаётся
/// без состояния — определения живут только в пределах запроса.
library;

import 'package:flutter/foundation.dart';

import '../model/core_node.dart';

/// Одно определение функции.
@immutable
class FunctionDefinition {
  const FunctionDefinition({
    required this.name,
    required this.params,
    required this.equation,
  });

  /// Имя функции (`f`, `g`, …).
  final String name;

  /// Имена параметров (`x`, `t`, …).
  final List<String> params;

  /// Уравнение `FUNCTION(name, параметры…) = тело`.
  final CoreNode equation;

  Map<String, dynamic> toJson() => equation.toJson();
}

/// Хранилище определённых функций (в памяти текущей сессии).
class FunctionStore extends ChangeNotifier {
  final List<FunctionDefinition> _definitions = [];

  List<FunctionDefinition> get definitions => List.unmodifiable(_definitions);

  bool get isEmpty => _definitions.isEmpty;

  /// Распознать определение функции по узлу `EQUALS(FUNCTION(f, x, …), тело)`.
  static FunctionDefinition? parse(CoreNode node) {
    if (node.type != CoreNodeType.equals || node.children.length != 2) {
      return null;
    }
    final head = node.children[0];
    if (head.type != CoreNodeType.function ||
        head.value == null ||
        head.children.isEmpty) {
      return null;
    }
    final params = <String>[];
    for (final child in head.children) {
      if (child.type != CoreNodeType.variable || child.value == null) return null;
      params.add(child.value!);
    }
    return FunctionDefinition(name: head.value!, params: params, equation: node);
  }

  /// Добавить или заменить определение с тем же именем.
  void define(FunctionDefinition definition) {
    _definitions.removeWhere((item) => item.name == definition.name);
    _definitions.add(definition);
    notifyListeners();
  }

  /// Убрать определение по имени.
  void remove(String name) {
    _definitions.removeWhere((item) => item.name == name);
    notifyListeners();
  }

  /// Забыть все определения.
  void clear() {
    _definitions.clear();
    notifyListeners();
  }

  /// Определения в формате поля `definitions` запроса.
  List<CoreNode> contract() => [for (final item in _definitions) item.equation];
}
