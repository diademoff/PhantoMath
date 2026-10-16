/// Контроллер редактора: хранит состояние и выполняет команды клавиатуры.
///
/// Вся логика правки — чистые функции из `model.dart`; контроллер только
/// подменяет состояние и уведомляет слушателей. Так же устроены штатные
/// `TextEditingController`/`ScrollController` во Flutter.
library;

import 'package:flutter/foundation.dart';

import '../model/core_node.dart';
import 'convert.dart' as convert;
import 'kind.dart';
import 'model.dart' as ed;

class EditorController extends ChangeNotifier {
  EditorController({ed.ENode? document, ed.EdCursor? cursor})
    : _state = ed.EditorState(
        document ?? ed.ENode.row(),
        cursor ?? const ed.EdCursor(),
      );

  ed.EditorState _state;

  /// Текущее состояние: документ и курсор.
  ed.EditorState get state => _state;

  /// Документ редактора.
  ed.ENode get document => _state.document;

  /// Курсор.
  ed.EdCursor get cursor => _state.cursor;

  /// Пуст ли документ.
  bool get isEmpty => _state.isEmpty;

  /// Узел контракта для отправки решателю.
  CoreNode toCoreNode() => convert.editorToCoreNode(_state.document);

  void _apply(ed.EditorState next) {
    if (next.document == _state.document && next.cursor == _state.cursor) {
      return;
    }
    _state = next;
    notifyListeners();
  }

  /// Набрать цифру или точку.
  void typeDigit(String value) =>
      _apply(ed.insertTerminal(_state, ENodeKind.constant, value));

  /// Набрать переменную ([value] — её имя, например `x`).
  void typeVariable(String value) =>
      _apply(ed.insertTerminal(_state, ENodeKind.variable, value));

  /// Вставить плоский знак (`+`, `=`, `!`, …).
  void insertOperator(ENodeKind kind) =>
      _apply(ed.insertTerminal(_state, kind, ''));

  /// Вставить шаблон (`fraction`, `sin`, `integral`, …).
  void insertTemplate(ENodeKind kind) =>
      _apply(ed.insertTemplate(_state, kind));

  /// Перевод строки: новая строка для следующего уравнения системы.
  void newLine() => _apply(ed.insertNewline(_state));

  /// Удалить слева.
  void backspace() => _apply(ed.backspace(_state));

  /// Удалить справа.
  void deleteForward() => _apply(ed.deleteForward(_state));

  /// Курсор влево.
  void moveLeft() => _apply(ed.moveLeft(_state));

  /// Курсор вправо.
  void moveRight() => _apply(ed.moveRight(_state));

  /// Курсор вверх (предыдущий слот шаблона).
  void moveUp() => _apply(ed.moveSlot(_state, -1));

  /// Курсор вниз (следующий слот шаблона).
  void moveDown() => _apply(ed.moveSlot(_state, 1));

  /// Очистить документ.
  void clear() => _apply(ed.clearEditor());

  /// Поставить курсор (например, тапом по формуле).
  void focus(ed.EdCursor cursor) => _apply(_state.copyWith(cursor: cursor));
}
