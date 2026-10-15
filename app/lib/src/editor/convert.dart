/// Преобразование дерева редактора в `CoreNode`.
///
/// Это и есть вход решателя: результат уходит в `POST /api/v1/solve` как
/// AST-JSON. Ряд редактора — плоская запись, поэтому здесь работает разбор
/// по приоритетам: `2+3*4` → `ADD(2, MULTIPLY(3,4))`. Два операнда подряд
/// без знака дают `MULTIPLY_IMPLICIT` (`2x` → `2·x`).
///
/// Таблица приоритетов повторяет бэкенд (`mymath_backend/input.py`), чтобы
/// один и тот же ввод разбирался одинаково.
library;

import '../model/core_node.dart';
import 'kind.dart';
import 'model.dart';

/// Преобразовать документ редактора в узел контракта.
///
/// Пустой документ даёт `EMPTY` — вызывающий решает, что с этим делать
/// (обычно просто не отправляет запрос).
CoreNode editorToCoreNode(ENode document) => _rowToCore(document);

CoreNode _rowToCore(ENode row) {
  if (row.children.isEmpty) {
    return const CoreNode(type: CoreNodeType.empty);
  }
  return _parseSequence(row.children);
}

/// Разбор ряда по приоритетам операций.
CoreNode _parseSequence(List<ENode> items) {
  var pos = 0;

  CoreNode operand() {
    if (pos >= items.length) {
      return const CoreNode(type: CoreNodeType.empty);
    }
    final token = items[pos];
    // Унарный плюс и минус: `+`/`−` перед операндом, а не между двумя.
    if (token.kind == ENodeKind.subtract || token.kind == ENodeKind.add) {
      pos++;
      final inner = operand();
      return CoreNode(
        type: token.kind == ENodeKind.subtract
            ? CoreNodeType.negative
            : CoreNodeType.positive,
        children: [inner],
      );
    }
    if (token.kind.isInfix) {
      // Ведущий бинарный знак без операнда слева — не разбираем, но и не
      // зацикливаемся: отдаём заглушку.
      pos++;
      return const CoreNode(type: CoreNodeType.empty);
    }
    var node = _atom(token);
    pos++;
    while (pos < items.length && items[pos].kind.isPostfix) {
      node = CoreNode(
        type: items[pos].kind.coreType,
        children: [node],
      );
      pos++;
    }
    return node;
  }

  CoreNode parse(int minPrecedence) {
    var left = operand();
    while (pos < items.length) {
      final token = items[pos];
      final bool infix = token.kind.isInfix;
      // Два операнда подряд — неявное умножение; знак не сдвигаем: второй
      // операнд разберётся рекурсивным вызовом.
      final int precedence = infix ? _precedence(token.kind) : 4;
      if (precedence < minPrecedence) break;
      final CoreNodeType? operator = infix ? token.kind.coreType : null;
      if (infix) pos++;
      final right = parse(precedence + 1);
      left = operator == null
          ? CoreNode(
              type: CoreNodeType.multiplyImplicit,
              children: [left, right],
            )
          : CoreNode(type: operator, children: [left, right]);
    }
    return left;
  }

  return parse(1);
}

/// Приоритет инфиксного знака (чем больше — тем крепче связывает).
int _precedence(ENodeKind kind) {
  switch (kind) {
    case ENodeKind.equals:
    case ENodeKind.notEquals:
    case ENodeKind.lessThan:
    case ENodeKind.lessThanEqual:
    case ENodeKind.greaterThan:
    case ENodeKind.greaterThanEqual:
      return 1;
    case ENodeKind.add:
    case ENodeKind.subtract:
      return 2;
    case ENodeKind.multiply:
    case ENodeKind.divide:
      return 3;
    default:
      return 3;
  }
}

/// Превратить один токен ряда в узел.
CoreNode _atom(ENode token) {
  switch (token.kind) {
    case ENodeKind.constant:
    case ENodeKind.variable:
      return CoreNode(type: token.kind.coreType, value: token.value);
    case ENodeKind.row:
      return _rowToCore(token);
    default:
      if (token.kind.isTemplate) {
        return _templateToCore(token);
      }
      return const CoreNode(type: CoreNodeType.empty);
  }
}

/// Шаблон: слоты-ряды становятся детьми узла в том же порядке.
CoreNode _templateToCore(ENode template) {
  final children = [
    for (final slot in template.children)
      slot.kind == ENodeKind.row ? _rowToCore(slot) : _atom(slot),
  ];
  return CoreNode(type: template.kind.coreType, children: children);
}
