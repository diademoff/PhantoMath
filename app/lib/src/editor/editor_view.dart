/// Ввод: формула с курсором.
///
/// Редактор собран как дерево виджетов: терминалы (числа и переменные) —
/// `Text`, а конструкции (дробь, корень, степень, функции) — небольшие
/// композиции из `Row`/`Column`. Так у каждого элемента есть свой адресат
/// нажатия, и тап по формуле переносит курсор в нужный слот. Отрисовка
/// формул в шагах решения по-прежнему идёт через `flutter_math`
/// (`render/latex.dart`) — здесь другой задачи: редактируемая поверхность.
library;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../settings/settings.dart';
import 'controller.dart';
import 'kind.dart';
import 'model.dart' as ed;

/// Формула ввода с курсором и тапом по элементам.
class EditorView extends StatefulWidget {
  const EditorView({
    super.key,
    required this.controller,
    this.fontSize = 30,
    this.decimalSeparator = DecimalSeparator.point,
  });

  final EditorController controller;

  /// Размер формулы ввода.
  final double fontSize;

  /// Десятичный разделитель из настроек — для показа чисел.
  final DecimalSeparator decimalSeparator;

  @override
  State<EditorView> createState() => _EditorViewState();
}

class _EditorViewState extends State<EditorView> {
  final _caretAnchor = GlobalKey();
  ed.ENode get _document => widget.controller.document;
  ed.EdCursor get _cursor => widget.controller.cursor;
  double get _fs => widget.fontSize;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return AnimatedBuilder(
      animation: widget.controller,
      builder: (context, _) {
        WidgetsBinding.instance.addPostFrameCallback((_) {
          final anchor = _caretAnchor.currentContext;
          if (mounted && anchor != null) Scrollable.ensureVisible(anchor, alignment: .6);
        });
        return Semantics(
          label: 'Поле ввода математического выражения',
          child: Container(
            width: double.infinity,
            constraints: const BoxConstraints(minHeight: 72),
            alignment: Alignment.centerLeft,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: DefaultTextStyle.merge(
                style: TextStyle(
                  fontSize: _fs,
                  height: 1.25,
                  color: theme.colorScheme.onSurface,
                ),
                child: _row(_document, const []),
              ),
            ),
          ),
        );
      },
    );
  }

  // ── построение дерева ─────────────────────────────────────────────

  /// Ряд токенов; [steps] — путь до него (пустой у корня).
  Widget _row(ed.ENode row, List<ed.CursorStep> steps) {
    final cursorHere = listEquals(_cursor.steps, steps) || row.children.isEmpty;
    if (row.children.isEmpty) {
      // Пустой слот: показываем курсор, если он здесь, иначе — рамку-слот.
      final isFocused = listEquals(_cursor.steps, steps);
      return GestureDetector(
        key: ValueKey('slot:${_pathKey(steps)}'),
        behavior: HitTestBehavior.opaque,
        onTap: () => _focus(ed.EdCursor(steps: steps, offset: 0)),
        child: SizedBox(
          height: _fs * 0.9,
          child: isFocused ? _cursorBar() : _emptySlot(),
        ),
      );
    }
    final spans = <InlineSpan>[];
    for (var i = 0; i < row.children.length; i++) {
      if (cursorHere && i == _cursor.offset && _cursor.textOffset == null) spans.add(_cursorSpan());
      if (row.children[i].kind == ENodeKind.newline) {
        // Перевод строки: разрыв линии, курсор встаёт до/после него
        // общей логикой смещений.
        spans.add(const TextSpan(text: '\n'));
        continue;
      }
      spans.add(
        WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: _token(row.children[i], steps, i),
        ),
      );
    }
    if (cursorHere && _cursor.offset >= row.children.length) {
      spans.add(_cursorSpan());
    }
    final content = Text.rich(TextSpan(children: spans));
    if (!cursorHere || steps.isEmpty) return content;
    return DecoratedBox(decoration: BoxDecoration(
      color: Theme.of(context).colorScheme.primary.withValues(alpha: .07),
      borderRadius: BorderRadius.circular(4)), child: content);
  }

  /// Один токен ряда: терминал, шаблон или вложенный ряд.
  Widget _token(ed.ENode node, List<ed.CursorStep> steps, int index) {
    if (node.kind == ENodeKind.row) return _row(node, steps);
    if (node.kind.isTemplate) return _template(node, steps, index);
    return _terminal(node, steps, index);
  }

  /// Терминал: тап ставит курсор сразу за ним.
  Widget _terminal(ed.ENode node, List<ed.CursorStep> steps, int index) {
    final text = _display(node);
    final numeric = node.kind == ENodeKind.constant && RegExp(r'^[0-9.,]+$').hasMatch(text);
    final inside = listEquals(_cursor.steps, steps) && _cursor.offset == index ? _cursor.textOffset : null;
    return Builder(builder: (tokenContext) => GestureDetector(
      key: ValueKey('tok:${_pathKey(steps)}:$index'),
      behavior: HitTestBehavior.opaque,
      onTapUp: (details) {
        final box = tokenContext.findRenderObject() as RenderBox;
        final at = (details.localPosition.dx / box.size.width * text.length).round().clamp(0, text.length);
        if (numeric && at > 0 && at < text.length) {
          _focus(ed.EdCursor(steps: steps, offset: index, textOffset: at));
        } else {
          _focus(ed.EdCursor(steps: steps, offset: at == 0 ? index : index + 1));
        }
      },
      child: inside == null ? Text(text, style: _terminalStyle(node.kind)) : Row(mainAxisSize: MainAxisSize.min, children: [
        Text(text.substring(0, inside), style: _terminalStyle(node.kind)),
        _cursorBar(),
        Text(text.substring(inside), style: _terminalStyle(node.kind)),
      ]),
    ));
  }

  /// Шаблон: тап по декору ставит курсор в его основной слот.
  Widget _template(ed.ENode node, List<ed.CursorStep> steps, int index) {
    final slots = <Widget>[
      for (var j = 0; j < node.children.length; j++)
        _row(node.children[j], [...steps, ed.CursorStep(index, j)]),
    ];
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: () => _focus(
        ed.EdCursor(
          steps: [...steps, ed.CursorStep(index, node.kind.cursorSlot)],
          offset: 0,
        ),
      ),
      child: _compose(node.kind, slots),
    );
  }

  void _focus(ed.EdCursor cursor) => widget.controller.focus(cursor);

  // ── сборка конструкций ────────────────────────────────────────────

  Widget _compose(ENodeKind kind, List<Widget> slots) {
    switch (kind) {
      case ENodeKind.fraction:
        return _fraction(slots[0], slots[1]);
      case ENodeKind.power:
        return _rowOf([slots[0], _sup(slots[1])]);
      case ENodeKind.root2:
        return _radical(null, slots[0]);
      case ENodeKind.rootN:
        return _radical(slots[0], slots[1]);
      case ENodeKind.abs:
        return _delimited('[', slots[0], ']', bars: true);
      case ENodeKind.bracket:
        return _delimited('(', slots[0], ')');
      case ENodeKind.vector:
        return _rowOf([
          Text('(', style: TextStyle(fontSize: _fs, height: 1)),
          slots[0],
          const Text(', '),
          slots[1],
          Text(')', style: TextStyle(fontSize: _fs, height: 1)),
        ]);
      case ENodeKind.system2:
        return _rowOf([
          Text('{', style: TextStyle(fontSize: _fs * 2.2, height: 1)),
          Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: slots,
          ),
        ]);
      case ENodeKind.determinant2:
        return _matrixView(2, slots);
      case ENodeKind.determinant3:
        return _matrixView(3, slots);
      case ENodeKind.matrix2:
        return _matrixView(2, slots, left: '[', right: ']');
      case ENodeKind.matrix3:
        return _matrixView(3, slots, left: '[', right: ']');
      case ENodeKind.sin:
        return _function('sin', slots[0]);
      case ENodeKind.cos:
        return _function('cos', slots[0]);
      case ENodeKind.tan:
        return _function('tan', slots[0]);
      case ENodeKind.cot:
        return _function('cot', slots[0]);
      case ENodeKind.sec:
        return _function('sec', slots[0]);
      case ENodeKind.csc:
        return _function('csc', slots[0]);
      case ENodeKind.asin:
        return _function('asin', slots[0]);
      case ENodeKind.acos:
        return _function('acos', slots[0]);
      case ENodeKind.atan:
        return _function('atan', slots[0]);
      case ENodeKind.acot:
        return _function('acot', slots[0]);
      case ENodeKind.asec:
        return _function('asec', slots[0]);
      case ENodeKind.acsc:
        return _function('acsc', slots[0]);
      case ENodeKind.sinh:
        return _function('sinh', slots[0]);
      case ENodeKind.cosh:
        return _function('cosh', slots[0]);
      case ENodeKind.tanh:
        return _function('tanh', slots[0]);
      case ENodeKind.coth:
        return _function('coth', slots[0]);
      case ENodeKind.sech:
        return _function('sech', slots[0]);
      case ENodeKind.csch:
        return _function('csch', slots[0]);
      case ENodeKind.asinh:
        return _function('asinh', slots[0]);
      case ENodeKind.acosh:
        return _function('acosh', slots[0]);
      case ENodeKind.atanh:
        return _function('atanh', slots[0]);
      case ENodeKind.acoth:
        return _function('acoth', slots[0]);
      case ENodeKind.asech:
        return _function('asech', slots[0]);
      case ENodeKind.acsch:
        return _function('acsch', slots[0]);
      case ENodeKind.ln:
        return _function('ln', slots[0]);
      case ENodeKind.log10:
        return _rowOf([
          const Text('log'),
          _sub(const Text('10')),
          _functionTail(slots[0]),
        ]);
      case ENodeKind.log:
        return _rowOf([
          const Text('log'),
          _sub(slots[1]),
          _functionTail(slots[0]),
        ]);
      case ENodeKind.exp:
        return _rowOf([const Text('e'), _sup(slots[0])]);
      case ENodeKind.floor:
        return _delimited('⌊', slots[0], '⌋');
      case ENodeKind.sign:
        return _function('sgn', slots[0]);
      case ENodeKind.derivative:
        return _rowOf([const Text('d/dx'), _functionTail(slots[0])]);
      case ENodeKind.integral:
        return _rowOf([const Text('∫'), slots[0], const Text(' dx')]);
      case ENodeKind.integralDefinite:
        return _rowOf([
          const Text('∫'),
          _scripts(slots[0], slots[1]),
          slots[2],
          const Text(' dx'),
        ]);
      case ENodeKind.limit:
        return _rowOf([
          const Text('lim'),
          _sub(_rowOf([const Text('x→'), slots[0]])),
          slots[1],
        ]);
      case ENodeKind.sigma:
        return _rowOf([
          const Text('Σ'),
          _scripts(slots[0], slots[1]),
          slots[2],
        ]);
      case ENodeKind.choose:
        return _binomial(slots[0], slots[1]);
      case ENodeKind.permutation:
        return _rowOf([_sup(slots[0]), const Text('P'), _sub(slots[1])]);
      case ENodeKind.variation:
        return _rowOf([_sup(slots[0]), const Text('A'), _sub(slots[1])]);
      case ENodeKind.mixedFraction:
        return _rowOf([slots[0], _fraction(slots[1], slots[2])]);
      case ENodeKind.powerTwo:
        return _rowOf([slots[0], _sup(const Text('2'))]);
      case ENodeKind.powerThree:
        return _rowOf([slots[0], _sup(const Text('3'))]);
      case ENodeKind.rootThree:
        return _radical(const Text('3'), slots[0]);
      case ENodeKind.log2:
        return _rowOf([
          const Text('log'),
          _sub(const Text('2')),
          _functionTail(slots[0]),
        ]);
      case ENodeKind.functionF:
        return _function('f', slots[0]);
      case ENodeKind.functionG:
        return _function('g', slots[0]);
      case ENodeKind.functionInverseF:
        return _inverseFunction('f', slots[0]);
      case ENodeKind.functionInverseG:
        return _inverseFunction('g', slots[0]);
      case ENodeKind.segment:
        return _overline(slots);
      case ENodeKind.segmentLength:
        return _lengthBars(slots);
      default:
        return _rowOf(slots);
    }
  }

  // ── мелкие виджеты ─────────────────────────────────────────────────

  /// Ряд без переносов, выравнивание по центру.
  Widget _rowOf(List<Widget> children) => Row(
    mainAxisSize: MainAxisSize.min,
    crossAxisAlignment: CrossAxisAlignment.center,
    children: children,
  );

  /// Дробь: числитель, черта, знаменатель.
  Widget _fraction(Widget numerator, Widget denominator) {
    final color = Theme.of(context).colorScheme.onSurface;
    return IntrinsicWidth(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Center(child: numerator),
          Container(
            height: 1.4,
            margin: const EdgeInsets.symmetric(vertical: 3),
            color: color,
          ),
          Center(child: denominator),
        ],
      ),
    );
  }

  /// Корень: знак, необязательная степень и подкоренное с чертой сверху.
  Widget _radical(Widget? degree, Widget radicand) {
    final color = Theme.of(context).colorScheme.onSurface;
    return Row(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        if (degree != null)
          Transform.translate(
            offset: const Offset(2, -4),
            child: _small(degree),
          ),
        Text('√', style: TextStyle(fontSize: _fs * 1.1, height: 1)),
        Container(
          padding: const EdgeInsets.only(left: 2, top: 2),
          decoration: BoxDecoration(
            border: Border(top: BorderSide(color: color, width: 1.2)),
          ),
          child: radicand,
        ),
      ],
    );
  }

  /// Матрица `size×size` между ограничителями (по умолчанию — как определитель).
  Widget _matrixView(
    int size,
    List<Widget> slots, {
    String left = '|',
    String right = '|',
  }) {
    final rows = <Widget>[];
    for (var row = 0; row < size; row++) {
      final cells = <Widget>[];
      for (var column = 0; column < size; column++) {
        if (column > 0) cells.add(const Text('  '));
        cells.add(slots[row * size + column]);
      }
      rows.add(Row(mainAxisSize: MainAxisSize.min, children: cells));
    }
    final bar = TextStyle(fontSize: _fs * size, height: 1);
    return _rowOf([
      Text(left, style: bar),
      Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: rows,
      ),
      Text(right, style: bar),
    ]);
  }

  /// Ограничители: скобки, модуль, пол.
  Widget _delimited(
    String left,
    Widget content,
    String right, {
    bool bars = false,
  }) {
    final style = TextStyle(fontSize: _fs * (bars ? 1.3 : 1.2), height: 1);
    return _rowOf([
      Text(bars ? '|' : left, style: style),
      content,
      Text(bars ? '|' : right, style: style),
    ]);
  }

  /// Функция: имя и её аргумент в скобках.
  Widget _function(String name, Widget argument) =>
      _rowOf([Text(name), _functionTail(argument)]);

  /// Обратная функция: имя с верхним индексом −1 и аргумент в скобках.
  Widget _inverseFunction(String name, Widget argument) =>
      _rowOf([Text(name), _sup(const Text('−1')), _functionTail(argument)]);

  /// Отрезок: черта над концами (``AB``).
  Widget _overline(List<Widget> slots) {
    final color = Theme.of(context).colorScheme.onSurface;
    return Container(
      padding: const EdgeInsets.only(top: 2),
      decoration: BoxDecoration(
        border: Border(top: BorderSide(color: color, width: 1.2)),
      ),
      child: _rowOf(slots),
    );
  }

  /// Длина отрезка: вертикальные черты по бокам (``|AB|``).
  Widget _lengthBars(List<Widget> slots) {
    final style = TextStyle(fontSize: _fs * 1.2, height: 1);
    return _rowOf([Text('|', style: style), ...slots, Text('|', style: style)]);
  }

  /// Хвост функции: `( аргумент )`.
  Widget _functionTail(Widget argument) {
    final style = TextStyle(fontSize: _fs * 1.1, height: 1);
    return _rowOf([Text('(', style: style), argument, Text(')', style: style)]);
  }

  /// Биномиальный коэффициент.
  Widget _binomial(Widget top, Widget bottom) {
    final color = Theme.of(context).colorScheme.onSurface;
    final style = TextStyle(fontSize: _fs * 1.2, height: 1);
    return _rowOf([
      Text('(', style: style),
      Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          top,
          Container(height: 1, width: _fs, color: color),
          bottom,
        ],
      ),
      Text(')', style: style),
    ]);
  }

  /// Верхний и нижний индексы рядом (для интеграла, суммы).
  Widget _scripts(Widget lower, Widget upper) => Column(
    mainAxisSize: MainAxisSize.min,
    children: [_small(upper), _small(lower)],
  );

  Widget _sup(Widget child) =>
      Transform.translate(offset: const Offset(0, -6), child: _small(child));

  Widget _sub(Widget child) =>
      Transform.translate(offset: const Offset(0, 6), child: _small(child));

  Widget _small(Widget child) => DefaultTextStyle.merge(
    style: TextStyle(fontSize: _fs * 0.62, height: 1.1),
    child: child,
  );

  /// Курсор в виде вертикальной черты.
  Widget _cursorBar() => SizedBox(key: _caretAnchor,
      child: _BlinkingCursor(key: const ValueKey('cursor'), height: _fs * 1.15));

  InlineSpan _cursorSpan() =>
      WidgetSpan(alignment: PlaceholderAlignment.middle, child: _cursorBar());

  /// Рамка пустого слота.
  Widget _emptySlot() {
    final color = Theme.of(context).colorScheme.outlineVariant;
    return Container(
      width: _fs * 0.45,
      decoration: BoxDecoration(
        border: Border.all(color: color),
        borderRadius: BorderRadius.circular(2),
      ),
    );
  }

  TextStyle _terminalStyle(ENodeKind kind) => kind == ENodeKind.variable
      ? const TextStyle(fontStyle: FontStyle.italic)
      : const TextStyle();

  /// Текст терминала для показа: знаки — символами, греческие команды — буквами.
  String _display(ed.ENode node) {
    switch (node.kind) {
      case ENodeKind.add:
        return '+';
      case ENodeKind.subtract:
        return '−';
      case ENodeKind.multiply:
        return '×';
      case ENodeKind.divide:
        return '÷';
      case ENodeKind.equals:
        return '=';
      case ENodeKind.notEquals:
        return '≠';
      case ENodeKind.lessThan:
        return '<';
      case ENodeKind.lessThanEqual:
        return '≤';
      case ENodeKind.greaterThan:
        return '>';
      case ENodeKind.greaterThanEqual:
        return '≥';
      case ENodeKind.factorial:
        return '!';
      case ENodeKind.percentage:
        return '%';
      case ENodeKind.degree:
        return '°';
      case ENodeKind.radian:
        return 'rad';
      default:
        break;
    }
    final value = node.value ?? '';
    if (node.kind == ENodeKind.variable) {
      switch (value) {
        case r'\alpha':
          return 'α';
        case r'\beta':
          return 'β';
        case r'\theta':
          return 'θ';
      }
    }
    if (node.kind == ENodeKind.constant &&
        widget.decimalSeparator == DecimalSeparator.comma) {
      return value.replaceAll('.', ',');
    }
    return value;
  }

  String _pathKey(List<ed.CursorStep> steps) =>
      steps.map((s) => '${s.child}.${s.slot}').join('/');
}

/// Мигающий курсор.
class _BlinkingCursor extends StatefulWidget {
  const _BlinkingCursor({super.key, required this.height});

  final double height;

  @override
  State<_BlinkingCursor> createState() => _BlinkingCursorState();
}

class _BlinkingCursorState extends State<_BlinkingCursor>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 500),
  );

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.disableAnimationsOf(context)) {
      _controller.stop();
    } else {
      _controller.repeat(reverse: true);
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (MediaQuery.disableAnimationsOf(context)) {
      return Container(width: 2, height: widget.height, color: Theme.of(context).colorScheme.primary);
    }
    return FadeTransition(
      opacity: _controller.drive(Tween<double>(begin: 0.15, end: 1)),
      child: Container(
        width: 2,
        height: widget.height,
        color: Theme.of(context).colorScheme.primary,
      ),
    );
  }
}
