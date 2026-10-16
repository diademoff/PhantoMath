/// Дерево редактора, курсор и операции над ними.
///
/// Документ — это `row` (ряд токенов). Слот шаблона — тоже `row`, поэтому
/// любое содержимое слота — снова последовательность токенов. Курсор задаёт
/// путь до ряда (`steps`) и позицию вставки в нём (`offset`).
///
/// Все операции чистые: на входе состояние, на выходе новое состояние.
/// Контроллер (`controller.dart`) только хранит его и уведомляет слушателей.
library;

import 'package:flutter/foundation.dart';

import 'kind.dart';

/// Шаг пути вглубь дерева.
///
/// `child` — номер ребёнка текущего ряда (это шаблон), `slot` — номер его
/// слота. Соответственно, следующий ряд — `children[child].children[slot]`.
@immutable
class CursorStep {
  const CursorStep(this.child, this.slot);

  final int child;
  final int slot;

  @override
  bool operator ==(Object other) =>
      other is CursorStep && other.child == child && other.slot == slot;

  @override
  int get hashCode => Object.hash(child, slot);

  @override
  String toString() => '($child,$slot)';
}

/// Курсор: путь до ряда и позиция вставки в нём.
///
/// Пустой `steps` означает корневой ряд документа.
@immutable
class EdCursor {
  const EdCursor({this.steps = const <CursorStep>[], this.offset = 0});

  final List<CursorStep> steps;
  final int offset;

  EdCursor copyWith({List<CursorStep>? steps, int? offset}) =>
      EdCursor(steps: steps ?? this.steps, offset: offset ?? this.offset);

  @override
  bool operator ==(Object other) =>
      other is EdCursor &&
      other.offset == offset &&
      listEquals(other.steps, steps);

  @override
  int get hashCode => Object.hash(Object.hashAll(steps), offset);

  @override
  String toString() => 'EdCursor(${steps.join('>')} @$offset)';
}

/// Узел редактора: вид, текст терминала и дети/слоты.
@immutable
class ENode {
  const ENode(this.kind, {this.value, this.children = const <ENode>[]});

  /// Вид узла.
  final ENodeKind kind;

  /// Текст терминала (`constant`, `variable`); у остальных — `null`.
  final String? value;

  /// Для `row` — токены ряда; для шаблона — ровно `kind.arity` слотов-рядов.
  final List<ENode> children;

  /// Пустой ряд — содержимое ещё не набрано.
  factory ENode.row([List<ENode> children = const <ENode>[]]) =>
      ENode(ENodeKind.row, children: children);

  /// Терминал с текстом.
  factory ENode.terminal(ENodeKind kind, String value) =>
      ENode(kind, value: value);

  /// Шаблон с пустыми слотами-рядами.
  factory ENode.template(ENodeKind kind) =>
      ENode(kind, children: [for (var i = 0; i < kind.arity; i++) ENode.row()]);

  /// Пуст ли ряд (нет токенов).
  bool get isEmptyRow => kind == ENodeKind.row && children.isEmpty;

  ENode copyWith({String? value, List<ENode>? children}) => ENode(
    kind,
    value: value ?? this.value,
    children: children ?? this.children,
  );

  @override
  bool operator ==(Object other) =>
      other is ENode &&
      other.kind == kind &&
      other.value == value &&
      listEquals(other.children, children);

  @override
  int get hashCode => Object.hash(kind, value, Object.hashAll(children));

  @override
  String toString() => value ?? '${kind.name}(${children.join(', ')})';
}

/// Состояние редактора: документ и курсор.
@immutable
class EditorState {
  const EditorState(this.document, this.cursor);

  final ENode document;
  final EdCursor cursor;

  /// Документ пуст (ни одного токена в корне).
  bool get isEmpty => document.children.isEmpty;

  EditorState copyWith({ENode? document, EdCursor? cursor}) =>
      EditorState(document ?? this.document, cursor ?? this.cursor);
}

/// Ряд, на который указывает путь.
ENode rowAt(ENode root, List<CursorStep> steps) {
  var node = root;
  for (final step in steps) {
    node = node.children[step.child].children[step.slot];
  }
  return node;
}

/// Заменить ряд на пути результатом [transform].
ENode _updateLeafRow(
  ENode node,
  List<CursorStep> steps,
  ENode Function(ENode row) transform,
) {
  if (steps.isEmpty) return transform(node);
  final step = steps.first;
  final children = List<ENode>.of(node.children);
  final target = children[step.child];
  final slots = List<ENode>.of(target.children);
  slots[step.slot] = _updateLeafRow(
    slots[step.slot],
    steps.sublist(1),
    transform,
  );
  children[step.child] = ENode(target.kind, children: slots);
  return ENode(node.kind, value: node.value, children: children);
}

/// Заменить слот шаблона, вернув новый шаблон.
ENode _withSlot(ENode template, int slot, ENode row) {
  final slots = List<ENode>.of(template.children);
  slots[slot] = row;
  return ENode(template.kind, children: slots);
}

/// Число ли текст терминала: только цифры и точка.
///
/// Символьные константы (`π`, `∞`) набираются как `constant`, но числом не
/// являются — цифру к ним дописывать нельзя.
final RegExp _numeric = RegExp(r'^[0-9.]+$');

/// Вставить терминал в позицию курсора.
///
/// Цифры и точка дописываются к соседнему числу слева (`2` + `3` → `23`),
/// пока он остаётся числом; повторная точка начинает новое число.
EditorState insertTerminal(EditorState state, ENodeKind kind, String value) {
  var newOffset = state.cursor.offset;
  final document = _updateLeafRow(state.document, state.cursor.steps, (row) {
    final children = List<ENode>.of(row.children);
    final at = newOffset;
    final prev = at > 0 ? children[at - 1] : null;
    final canMerge =
        kind == ENodeKind.constant &&
        prev != null &&
        prev.kind == ENodeKind.constant &&
        _numeric.hasMatch(prev.value ?? '') &&
        !(value == '.' && (prev.value ?? '').contains('.'));
    if (canMerge) {
      children[at - 1] = ENode.terminal(kind, '${prev.value}$value');
    } else {
      children.insert(at, ENode.terminal(kind, value));
      newOffset = at + 1;
    }
    return ENode.row(children);
  });
  return EditorState(document, state.cursor.copyWith(offset: newOffset));
}

/// Вставить шаблон.
///
/// Если [ENodeKind.absorbsPrevious] и слева есть операнд, он переезжает в
/// первый слот шаблона; курсор встаёт в [ENodeKind.cursorSlot].
EditorState insertTemplate(EditorState state, ENodeKind kind) {
  final steps = state.cursor.steps;
  final at = state.cursor.offset;
  final leaf = rowAt(state.document, steps);
  final absorbs = kind.absorbsPrevious && at > 0;
  final childIndex = absorbs ? at - 1 : at;

  final document = _updateLeafRow(state.document, steps, (row) {
    final children = List<ENode>.of(row.children);
    var template = ENode.template(kind);
    if (absorbs) {
      template = _withSlot(
        template,
        kind.absorbFillSlot,
        ENode.row([leaf.children[at - 1]]),
      );
      children.removeAt(at - 1);
    }
    children.insert(childIndex, template);
    return ENode.row(children);
  });

  final newSteps = [...steps, CursorStep(childIndex, kind.cursorSlot)];
  final offset = absorbs && kind.cursorAtEnd ? 1 : 0;
  return EditorState(document, EdCursor(steps: newSteps, offset: offset));
}

/// Удалить символ слева от курсора.
///
/// В начале слота курсор выходит наружу (к родительскому ряду), не удаляя
/// шаблон: повторное нажатие уже удалит его как единый токен.
EditorState backspace(EditorState state) {
  final cursor = state.cursor;
  if (cursor.offset > 0) {
    final at = cursor.offset;
    // При обрезке последнего символа числа узел остаётся на месте, поэтому
    // курсор не сдвигается; при удалении узла целиком — сдвигается влево.
    var keptOffset = at - 1;
    final document = _updateLeafRow(state.document, cursor.steps, (row) {
      final children = List<ENode>.of(row.children);
      final prev = children[at - 1];
      final text = prev.value;
      if (prev.kind == ENodeKind.constant && text != null && text.length > 1) {
        children[at - 1] = ENode.terminal(
          ENodeKind.constant,
          text.substring(0, text.length - 1),
        );
        keptOffset = at;
      } else {
        children.removeAt(at - 1);
      }
      return ENode.row(children);
    });
    return EditorState(document, cursor.copyWith(offset: keptOffset));
  }
  if (cursor.steps.isNotEmpty) {
    final step = cursor.steps.last;
    return EditorState(
      state.document,
      EdCursor(
        steps: cursor.steps.sublist(0, cursor.steps.length - 1),
        offset: step.child + 1,
      ),
    );
  }
  return state;
}

/// Удалить символ справа от курсора.
EditorState deleteForward(EditorState state) {
  final cursor = state.cursor;
  final leaf = rowAt(state.document, cursor.steps);
  if (cursor.offset < leaf.children.length) {
    final at = cursor.offset;
    final document = _updateLeafRow(state.document, cursor.steps, (row) {
      final children = List<ENode>.of(row.children);
      final next = children[at];
      final text = next.value;
      if (next.kind == ENodeKind.constant && text != null && text.length > 1) {
        children[at] = ENode.terminal(ENodeKind.constant, text.substring(1));
      } else {
        children.removeAt(at);
      }
      return ENode.row(children);
    });
    return EditorState(document, cursor);
  }
  if (cursor.steps.isNotEmpty) {
    final step = cursor.steps.last;
    return EditorState(
      state.document,
      EdCursor(
        steps: cursor.steps.sublist(0, cursor.steps.length - 1),
        offset: step.child,
      ),
    );
  }
  return state;
}

/// Сдвинуть курсор влево.
EditorState moveLeft(EditorState state) {
  final cursor = state.cursor;
  if (cursor.offset > 0) {
    return state.copyWith(cursor: cursor.copyWith(offset: cursor.offset - 1));
  }
  if (cursor.steps.isNotEmpty) {
    final step = cursor.steps.last;
    return EditorState(
      state.document,
      EdCursor(
        steps: cursor.steps.sublist(0, cursor.steps.length - 1),
        offset: step.child,
      ),
    );
  }
  return state;
}

/// Сдвинуть курсор вправо.
EditorState moveRight(EditorState state) {
  final cursor = state.cursor;
  final leaf = rowAt(state.document, cursor.steps);
  if (cursor.offset < leaf.children.length) {
    return state.copyWith(cursor: cursor.copyWith(offset: cursor.offset + 1));
  }
  if (cursor.steps.isNotEmpty) {
    final step = cursor.steps.last;
    return EditorState(
      state.document,
      EdCursor(
        steps: cursor.steps.sublist(0, cursor.steps.length - 1),
        offset: step.child + 1,
      ),
    );
  }
  return state;
}

/// Перейти между слотами шаблона: [delta] = -1 вверх, +1 вниз.
///
/// Так ходят из числителя дроби в знаменатель и по подынтегральным границам.
EditorState moveSlot(EditorState state, int delta) {
  final cursor = state.cursor;
  if (cursor.steps.isEmpty) return state;
  final step = cursor.steps.last;
  final parentSteps = cursor.steps.sublist(0, cursor.steps.length - 1);
  final parentRow = rowAt(state.document, parentSteps);
  final template = parentRow.children[step.child];
  final target = step.slot + delta;
  if (target < 0 || target >= template.children.length) return state;
  return EditorState(
    state.document,
    EdCursor(
      steps: [...parentSteps, CursorStep(step.child, target)],
      offset: 0,
    ),
  );
}

/// Очистить документ.
EditorState clearEditor() => EditorState(ENode.row(), const EdCursor());
