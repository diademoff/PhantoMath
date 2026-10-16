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
  const EdCursor({
    this.steps = const <CursorStep>[],
    this.offset = 0,
    this.textOffset,
    this.templateSelected = false,
  });

  final List<CursorStep> steps;
  final int offset;

  /// Interior position in a numeric token; null means a token boundary.
  final int? textOffset;
  final bool templateSelected;

  EdCursor copyWith({List<CursorStep>? steps, int? offset, int? textOffset}) =>
      EdCursor(
        steps: steps ?? this.steps,
        offset: offset ?? this.offset,
        textOffset: textOffset,
      );

  @override
  bool operator ==(Object other) =>
      other is EdCursor &&
      other.offset == offset &&
      other.textOffset == textOffset &&
      other.templateSelected == templateSelected &&
      listEquals(other.steps, steps);

  @override
  int get hashCode =>
      Object.hash(Object.hashAll(steps), offset, textOffset, templateSelected);

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

  /// Документ пуст (ни одного токена в корне, либо одни переводы строк).
  bool get isEmpty =>
      document.children.isEmpty ||
      document.children.every((token) => token.kind == ENodeKind.newline);

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
  final inside = state.cursor.textOffset;
  if (inside != null &&
      kind == ENodeKind.constant &&
      _numeric.hasMatch(value)) {
    final cursor = state.cursor;
    final token = rowAt(state.document, cursor.steps).children[cursor.offset];
    if (value == '.' && token.value!.contains('.')) return state;
    final text = token.value!.replaceRange(inside, inside, value);
    final document = _updateLeafRow(state.document, cursor.steps, (row) {
      final children = List<ENode>.of(row.children);
      children[cursor.offset] = ENode.terminal(kind, text);
      return ENode.row(children);
    });
    return EditorState(
      document,
      cursor.copyWith(textOffset: inside + value.length),
    );
  }
  state = _splitNumber(state);
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

/// Вставить перевод строки (клавиша ⏎).
///
/// В корне — разделитель в позиции курсора: документ делится на строки,
/// каждая строка — отдельное уравнение системы. Внутри шаблона разорвать
/// строку нельзя (иначе распадётся дробь или корень), поэтому перевод
/// дописывается в конец документа, а курсор выходит в новую строку.
EditorState insertNewline(EditorState state) {
  if (state.cursor.steps.isEmpty) {
    final at = state.cursor.offset;
    final document = _updateLeafRow(state.document, state.cursor.steps, (row) {
      final children = List<ENode>.of(row.children);
      children.insert(at, const ENode(ENodeKind.newline));
      return ENode.row(children);
    });
    return EditorState(document, state.cursor.copyWith(offset: at + 1));
  }
  final children = List<ENode>.of(state.document.children)
    ..add(const ENode(ENodeKind.newline));
  return EditorState(
    ENode.row(children),
    EdCursor(steps: const [], offset: children.length),
  );
}

/// Вставить шаблон.
///
/// Если [ENodeKind.absorbsPrevious] и слева есть операнд, он переезжает в
/// первый слот шаблона; курсор встаёт в [ENodeKind.cursorSlot].
EditorState insertTemplate(EditorState state, ENodeKind kind) {
  state = _splitNumber(state);
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
  final inside = cursor.textOffset;
  if (inside != null) {
    final document = _updateLeafRow(state.document, cursor.steps, (row) {
      final children = List<ENode>.of(row.children);
      final token = children[cursor.offset];
      children[cursor.offset] = token.copyWith(
        value: token.value!.replaceRange(inside - 1, inside, ''),
      );
      return ENode.row(children);
    });
    return EditorState(
      document,
      cursor.copyWith(textOffset: inside == 1 ? null : inside - 1),
    );
  }
  if (cursor.offset > 0) {
    final prev = rowAt(
      state.document,
      cursor.steps,
    ).children[cursor.offset - 1];
    if (!cursor.templateSelected &&
        prev.kind.isTemplate &&
        prev.children.any((slot) => !slot.isEmptyRow)) {
      return state.copyWith(
        cursor: _edgeCursor(prev, cursor.steps, cursor.offset - 1, end: true),
      );
    }
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
        templateSelected: true,
      ),
    );
  }
  return state;
}

/// Удалить символ справа от курсора.
EditorState deleteForward(EditorState state) {
  final cursor = state.cursor;
  if (cursor.textOffset case final inside?) {
    final document = _updateLeafRow(state.document, cursor.steps, (row) {
      final children = List<ENode>.of(row.children);
      final token = children[cursor.offset];
      children[cursor.offset] = token.copyWith(
        value: token.value!.replaceRange(inside, inside + 1, ''),
      );
      return ENode.row(children);
    });
    final length = rowAt(
      document,
      cursor.steps,
    ).children[cursor.offset].value!.length;
    return EditorState(
      document,
      inside == length ? cursor.copyWith(offset: cursor.offset + 1) : cursor,
    );
  }
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
  if (cursor.textOffset case final inside?) {
    return state.copyWith(
      cursor: cursor.copyWith(textOffset: inside == 1 ? null : inside - 1),
    );
  }
  if (cursor.offset > 0) {
    final prev = rowAt(
      state.document,
      cursor.steps,
    ).children[cursor.offset - 1];
    if (prev.kind.isTemplate) {
      return state.copyWith(
        cursor: _edgeCursor(prev, cursor.steps, cursor.offset - 1, end: true),
      );
    }
    if (prev.kind == ENodeKind.constant &&
        _numeric.hasMatch(prev.value ?? '') &&
        prev.value!.length > 1) {
      return state.copyWith(
        cursor: cursor.copyWith(
          offset: cursor.offset - 1,
          textOffset: prev.value!.length - 1,
        ),
      );
    }
    return state.copyWith(cursor: cursor.copyWith(offset: cursor.offset - 1));
  }
  if (cursor.steps.isNotEmpty) {
    final step = cursor.steps.last;
    if (step.slot > 0) {
      final parent = cursor.steps.sublist(0, cursor.steps.length - 1);
      final template = rowAt(state.document, parent).children[step.child];
      return state.copyWith(
        cursor: EdCursor(
          steps: [...parent, CursorStep(step.child, step.slot - 1)],
          offset: template.children[step.slot - 1].children.length,
        ),
      );
    }
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
  if (cursor.textOffset case final inside?) {
    final length = leaf.children[cursor.offset].value!.length;
    return state.copyWith(
      cursor: inside + 1 == length
          ? cursor.copyWith(offset: cursor.offset + 1)
          : cursor.copyWith(textOffset: inside + 1),
    );
  }
  if (cursor.offset < leaf.children.length) {
    final next = leaf.children[cursor.offset];
    if (next.kind.isTemplate) {
      return state.copyWith(
        cursor: _edgeCursor(next, cursor.steps, cursor.offset, end: false),
      );
    }
    if (next.kind == ENodeKind.constant &&
        _numeric.hasMatch(next.value ?? '') &&
        next.value!.length > 1) {
      return state.copyWith(cursor: cursor.copyWith(textOffset: 1));
    }
    return state.copyWith(cursor: cursor.copyWith(offset: cursor.offset + 1));
  }
  if (cursor.steps.isNotEmpty) {
    final step = cursor.steps.last;
    final parent = cursor.steps.sublist(0, cursor.steps.length - 1);
    final template = rowAt(state.document, parent).children[step.child];
    if (step.slot + 1 < template.children.length) {
      return state.copyWith(
        cursor: EdCursor(
          steps: [...parent, CursorStep(step.child, step.slot + 1)],
        ),
      );
    }
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
      offset: cursor.offset.clamp(0, template.children[target].children.length),
    ),
  );
}

/// Очистить документ.
EditorState clearEditor() => EditorState(ENode.row(), const EdCursor());

EditorState nextSlot(EditorState state) {
  final cursor = state.cursor;
  if (cursor.steps.isEmpty) return state;
  final step = cursor.steps.last;
  final parent = cursor.steps.sublist(0, cursor.steps.length - 1);
  final template = rowAt(state.document, parent).children[step.child];
  return state.copyWith(
    cursor: step.slot + 1 < template.children.length
        ? EdCursor(steps: [...parent, CursorStep(step.child, step.slot + 1)])
        : EdCursor(steps: parent, offset: step.child + 1),
  );
}

EdCursor _edgeCursor(
  ENode template,
  List<CursorStep> steps,
  int index, {
  required bool end,
}) {
  final slot = end ? template.children.length - 1 : 0;
  final row = template.children[slot];
  return EdCursor(
    steps: [...steps, CursorStep(index, slot)],
    offset: end ? row.children.length : 0,
  );
}

EditorState _splitNumber(EditorState state) {
  final cursor = state.cursor;
  final inside = cursor.textOffset;
  if (inside == null) return state;
  final document = _updateLeafRow(state.document, cursor.steps, (row) {
    final children = List<ENode>.of(row.children);
    final token = children.removeAt(cursor.offset);
    children.insertAll(cursor.offset, [
      token.copyWith(value: token.value!.substring(0, inside)),
      token.copyWith(value: token.value!.substring(inside)),
    ]);
    return ENode.row(children);
  });
  return EditorState(document, cursor.copyWith(offset: cursor.offset + 1));
}
