/// Рендер дерева редактора в LaTeX вместе с курсором.
///
/// Отдельно от `render/latex.dart`: там узел контракта, здесь — дерево
/// редактора с пустыми слотами и позицией курсора. Курсор вставляется
/// макросом `\cursor{}` из `flutter_math_fork` — он рисует вертикальную
/// черту на месте курсора.
library;

import 'kind.dart';
import 'model.dart';

/// Пустая группа шаблона: слот ещё не заполнен.
const String _empty = r'{}';

/// LaTeX документа редактора с курсором.
String editorToLatex(ENode document, EdCursor cursor) =>
    _renderRow(document, cursor.steps, cursor.offset);

/// Отрисовать ряд. [steps] пуст, если курсор стоит именно в этом ряду.
String _renderRow(ENode row, List<CursorStep> steps, int offset) {
  final cursorHere = steps.isEmpty;
  final parts = <String>[];
  for (var i = 0; i < row.children.length; i++) {
    if (cursorHere && i == offset) parts.add(_cursorMacro);
    final child = row.children[i];
    if (!cursorHere && steps.first.child == i) {
      parts.add(
        _renderTemplate(child, steps.first.slot, steps.sublist(1), offset),
      );
    } else {
      parts.add(_tokenLatex(child));
    }
  }
  if (cursorHere && offset >= row.children.length) parts.add(_cursorMacro);
  final body = parts.join(' ');
  return body;
}

/// Отрисовать шаблон, поставив курсор в слот [cursorSlot].
String _renderTemplate(
  ENode template,
  int cursorSlot,
  List<CursorStep> steps,
  int offset,
) {
  final slots = <String>[];
  for (var j = 0; j < template.children.length; j++) {
    if (j == cursorSlot) {
      slots.add(_renderRow(template.children[j], steps, offset));
    } else {
      slots.add(_tokenLatex(template.children[j]));
    }
  }
  return _templateLatex(template.kind, slots);
}

const String _cursorMacro = r'\cursor{}';

/// LaTeX числовой или символьной константы.
///
/// Цифры идут как есть, а `π`/`∞` — командами: движок формул ждёт LaTeX,
/// а не юникод-символ.
String _constantLatex(String value) {
  switch (value) {
    case 'π':
      return r'\pi';
    case '∞':
      return r'\infty';
    default:
      return value;
  }
}

/// LaTeX одного токена (без курсора).
String _tokenLatex(ENode node) {
  if (node.kind == ENodeKind.row) {
    // Ряд без курсора: offset -1 не совпадёт ни с одним индексом.
    return _renderRow(node, const [], -1);
  }
  switch (node.kind) {
    case ENodeKind.constant:
      return _constantLatex(node.value ?? '');
    case ENodeKind.variable:
      return node.value ?? '';
    case ENodeKind.add:
      return '+';
    case ENodeKind.subtract:
      return '-';
    case ENodeKind.multiply:
      return r'\times';
    case ENodeKind.divide:
      return r'\div';
    case ENodeKind.equals:
      return '=';
    case ENodeKind.notEquals:
      return r'\ne';
    case ENodeKind.lessThan:
      return '<';
    case ENodeKind.lessThanEqual:
      return r'\le';
    case ENodeKind.greaterThan:
      return '>';
    case ENodeKind.greaterThanEqual:
      return r'\ge';
    case ENodeKind.factorial:
      return '!';
    case ENodeKind.percentage:
      return r'\%';
    default:
      if (node.kind.isTemplate) {
        final slots = [
          for (final slot in node.children) _tokenLatex(slot),
        ];
        return _templateLatex(node.kind, slots);
      }
      return '';
  }
}

/// Обёртка шаблона: подставляет слоты в форму.
String _templateLatex(ENodeKind kind, List<String> slots) {
  String slot(int i) => i < slots.length && slots[i].isNotEmpty
      ? slots[i]
      : _empty;
  switch (kind) {
    case ENodeKind.fraction:
      return '\\frac{${slot(0)}}{${slot(1)}}';
    case ENodeKind.power:
      return '{${slot(0)}}^{${slot(1)}}';
    case ENodeKind.root2:
      return '\\sqrt{${slot(0)}}';
    case ENodeKind.rootN:
      return '\\sqrt[${slot(0)}]{${slot(1)}}';
    case ENodeKind.abs:
      return '\\left|${slot(0)}\\right|';
    case ENodeKind.bracket:
      return '\\left(${slot(0)}\\right)';
    case ENodeKind.sin:
      return '\\sin\\left(${slot(0)}\\right)';
    case ENodeKind.cos:
      return '\\cos\\left(${slot(0)}\\right)';
    case ENodeKind.tan:
      return '\\tan\\left(${slot(0)}\\right)';
    case ENodeKind.cot:
      return '\\cot\\left(${slot(0)}\\right)';
    case ENodeKind.sec:
      return '\\sec\\left(${slot(0)}\\right)';
    case ENodeKind.csc:
      return '\\csc\\left(${slot(0)}\\right)';
    case ENodeKind.asin:
      return '\\arcsin\\left(${slot(0)}\\right)';
    case ENodeKind.acos:
      return '\\arccos\\left(${slot(0)}\\right)';
    case ENodeKind.atan:
      return '\\arctan\\left(${slot(0)}\\right)';
    case ENodeKind.acot:
      return '\\mathrm{acot}\\left(${slot(0)}\\right)';
    case ENodeKind.sinh:
      return '\\sinh\\left(${slot(0)}\\right)';
    case ENodeKind.cosh:
      return '\\cosh\\left(${slot(0)}\\right)';
    case ENodeKind.tanh:
      return '\\tanh\\left(${slot(0)}\\right)';
    case ENodeKind.coth:
      return '\\coth\\left(${slot(0)}\\right)';
    case ENodeKind.ln:
      return '\\ln\\left(${slot(0)}\\right)';
    case ENodeKind.log10:
      return '\\log_{10}\\left(${slot(0)}\\right)';
    case ENodeKind.log:
      return '\\log_{${slot(1)}}\\left(${slot(0)}\\right)';
    case ENodeKind.exp:
      return 'e^{${slot(0)}}';
    case ENodeKind.floor:
      return '\\lfloor ${slot(0)} \\rfloor';
    case ENodeKind.sign:
      return '\\mathrm{sign}\\left(${slot(0)}\\right)';
    case ENodeKind.derivative:
      return '\\frac{d}{dx}\\left(${slot(0)}\\right)';
    case ENodeKind.integral:
      return '\\int ${slot(0)}\\,dx';
    case ENodeKind.integralDefinite:
      return '\\int_{${slot(0)}}^{${slot(1)}} ${slot(2)}\\,dx';
    case ENodeKind.limit:
      return '\\lim_{x \\to ${slot(0)}} ${slot(1)}';
    case ENodeKind.sigma:
      return '\\sum_{n=${slot(0)}}^{${slot(1)}} ${slot(2)}';
    case ENodeKind.choose:
      return '\\binom{${slot(0)}}{${slot(1)}}';
    case ENodeKind.permutation:
      return '{}^{${slot(0)}}P_{${slot(1)}}';
    case ENodeKind.variation:
      return '{}^{${slot(0)}}A_{${slot(1)}}';
    default:
      return '';
  }
}
