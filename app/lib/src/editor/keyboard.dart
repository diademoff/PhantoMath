/// Клавиатура редактора: клавиши, панели и виджет.
///
/// Раскладка повторяет логику Photomath: базовый экран с числами и знаками,
/// плюс дополнительные панели (функции, степени и корни, отношения,
/// переменные, исчисление, комбинаторика). Перечень клавиш соответствует
/// `editor_operators` из `truth/data/enums.json`; берём его по частям.
library;

import 'package:flutter/material.dart';

import 'controller.dart';
import 'kind.dart';

/// Что делает клавиша.
enum MathKeyType {
  digit,
  variable,
  operator,
  template,
  backspace,
  delete,
  left,
  right,
  up,
  down,
  clear,
  panel,
}

/// Описание одной клавиши.
class MathKey {
  const MathKey(
    this.type, {
    this.label = '',
    this.value,
    this.kind,
    this.panel,
    this.flex = 1,
  });

  /// Цифра или точка.
  const MathKey.digit(String digit)
    : this(MathKeyType.digit, label: digit, value: digit);

  /// Символьная константа (`π`, `e`, `∞`).
  const MathKey.constant(String symbol)
    : this(MathKeyType.digit, label: symbol, value: symbol);

  /// Переменная.
  const MathKey.variable(String name)
    : this(MathKeyType.variable, label: name, value: name);

  /// Плоский знак (`+`, `=`, `!`, …).
  MathKey.operator(ENodeKind kind)
    : this(MathKeyType.operator, label: kind.label, kind: kind);

  /// Шаблон (`fraction`, `sin`, `integral`, …).
  MathKey.template(ENodeKind kind)
    : this(MathKeyType.template, label: kind.label, kind: kind);

  /// Переключение панели.
  const MathKey.panel(int panel, String label)
    : this(MathKeyType.panel, label: label, panel: panel);

  final MathKeyType type;
  final String label;
  final String? value;
  final ENodeKind? kind;
  final int? panel;

  /// Во сколько раз клавиша шире обычной.
  final int flex;
}

/// Панель клавиатуры: набор рядов клавиш.
class KeyboardPanel {
  const KeyboardPanel({required this.title, required this.rows});

  /// Подпись на вкладке панели.
  final String title;

  /// Ряды клавиш; ряды могут иметь разную длину.
  final List<List<MathKey>> rows;
}

/// Базовый экран: числа, скобки, базовые знаки.
final KeyboardPanel _basePanel = KeyboardPanel(
  title: '123',
  rows: [
    [
      MathKey.digit('7'),
      MathKey.digit('8'),
      MathKey.digit('9'),
      MathKey.operator(ENodeKind.divide),
      MathKey.template(ENodeKind.bracket),
      MathKey.template(ENodeKind.fraction),
    ],
    [
      MathKey.digit('4'),
      MathKey.digit('5'),
      MathKey.digit('6'),
      MathKey.operator(ENodeKind.multiply),
      MathKey.template(ENodeKind.power),
      MathKey.operator(ENodeKind.subtract),
    ],
    [
      MathKey.digit('1'),
      MathKey.digit('2'),
      MathKey.digit('3'),
      MathKey.operator(ENodeKind.add),
      MathKey.template(ENodeKind.root2),
      MathKey.template(ENodeKind.abs),
    ],
    [
      MathKey.digit('0'),
      MathKey.digit('.'),
      MathKey.variable('x'),
      MathKey.operator(ENodeKind.equals),
      MathKey.constant('π'),
      MathKey.variable('e'),
    ],
  ],
);

/// Функции: прямые, обратные и гиперболические.
final KeyboardPanel _functionPanel = KeyboardPanel(
  title: 'f(x)',
  rows: [
    [
      MathKey.template(ENodeKind.sin),
      MathKey.template(ENodeKind.cos),
      MathKey.template(ENodeKind.tan),
      MathKey.template(ENodeKind.cot),
      MathKey.template(ENodeKind.sec),
      MathKey.template(ENodeKind.csc),
    ],
    [
      MathKey.template(ENodeKind.asin),
      MathKey.template(ENodeKind.acos),
      MathKey.template(ENodeKind.atan),
      MathKey.template(ENodeKind.acot),
      MathKey.template(ENodeKind.asec),
      MathKey.template(ENodeKind.acsc),
    ],
    [
      MathKey.template(ENodeKind.sinh),
      MathKey.template(ENodeKind.cosh),
      MathKey.template(ENodeKind.tanh),
      MathKey.template(ENodeKind.coth),
      MathKey.template(ENodeKind.sech),
      MathKey.template(ENodeKind.csch),
    ],
    [
      MathKey.template(ENodeKind.asinh),
      MathKey.template(ENodeKind.acosh),
      MathKey.template(ENodeKind.atanh),
      MathKey.template(ENodeKind.acoth),
      MathKey.template(ENodeKind.asech),
      MathKey.template(ENodeKind.acsch),
    ],
    [
      MathKey.template(ENodeKind.ln),
      MathKey.template(ENodeKind.log10),
      MathKey.template(ENodeKind.log2),
      MathKey.template(ENodeKind.log),
      MathKey.template(ENodeKind.exp),
      MathKey.template(ENodeKind.floor),
    ],
    [
      MathKey.template(ENodeKind.abs),
      MathKey.template(ENodeKind.sign),
      MathKey.template(ENodeKind.fraction),
      MathKey.template(ENodeKind.mixedFraction),
      MathKey.operator(ENodeKind.degree),
      MathKey.operator(ENodeKind.radian),
    ],
    [
      MathKey.template(ENodeKind.functionF),
      MathKey.template(ENodeKind.functionG),
      MathKey.template(ENodeKind.functionInverseF),
      MathKey.template(ENodeKind.functionInverseG),
    ],
  ],
);

/// Степени, корни, дробь, факториал.
final KeyboardPanel _powerPanel = KeyboardPanel(
  title: 'xⁿ',
  rows: [
    [
      MathKey.template(ENodeKind.power),
      MathKey.template(ENodeKind.fraction),
      MathKey.template(ENodeKind.root2),
      MathKey.template(ENodeKind.rootN),
    ],
    [
      MathKey.template(ENodeKind.powerTwo),
      MathKey.template(ENodeKind.powerThree),
      MathKey.template(ENodeKind.rootThree),
      MathKey.template(ENodeKind.mixedFraction),
    ],
    [
      MathKey.digit('2'),
      MathKey.digit('3'),
      MathKey.operator(ENodeKind.factorial),
      MathKey.operator(ENodeKind.percentage),
    ],
    [
      MathKey.template(ENodeKind.abs),
      MathKey.template(ENodeKind.bracket),
      MathKey.template(ENodeKind.vector),
      MathKey.constant('π'),
      MathKey.constant('e'),
    ],
  ],
);

/// Отношения.
final KeyboardPanel _relationPanel = KeyboardPanel(
  title: ' = <',
  rows: [
    [
      MathKey.operator(ENodeKind.equals),
      MathKey.operator(ENodeKind.notEquals),
      MathKey.operator(ENodeKind.lessThan),
      MathKey.operator(ENodeKind.lessThanEqual),
    ],
    [
      MathKey.operator(ENodeKind.greaterThan),
      MathKey.operator(ENodeKind.greaterThanEqual),
      MathKey.template(ENodeKind.bracket),
      MathKey.template(ENodeKind.abs),
    ],
  ],
);

/// Переменные и константы.
final KeyboardPanel _variablePanel = KeyboardPanel(
  title: 'abc',
  rows: [
    [
      MathKey.variable('x'),
      MathKey.variable('y'),
      MathKey.variable('z'),
      MathKey.variable('a'),
      MathKey.variable('b'),
    ],
    [
      MathKey.variable('c'),
      MathKey.variable('n'),
      MathKey.variable('k'),
      MathKey.variable('m'),
      MathKey.constant('i'),
    ],
    [
      MathKey.variable(r'\alpha'),
      MathKey.variable(r'\beta'),
      MathKey.variable(r'\theta'),
      MathKey.constant('π'),
      MathKey.constant('∞'),
    ],
    [
      MathKey.variable('d'),
      MathKey.variable('f'),
      MathKey.variable('g'),
      MathKey.variable('h'),
      MathKey.constant('e'),
    ],
    [
      MathKey.variable('p'),
      MathKey.variable('q'),
      MathKey.variable('r'),
      MathKey.variable('s'),
      MathKey.variable('t'),
    ],
  ],
);

/// Исчисление.
final KeyboardPanel _calculusPanel = KeyboardPanel(
  title: '∫',
  rows: [
    [
      MathKey.template(ENodeKind.derivative),
      MathKey.template(ENodeKind.integral),
      MathKey.template(ENodeKind.integralDefinite),
    ],
    [
      MathKey.template(ENodeKind.limit),
      MathKey.template(ENodeKind.sigma),
    ],
  ],
);

/// Комбинаторика.
final KeyboardPanel _combinatoricsPanel = KeyboardPanel(
  title: 'nCr',
  rows: [
    [
      MathKey.template(ENodeKind.choose),
      MathKey.template(ENodeKind.permutation),
      MathKey.template(ENodeKind.variation),
      MathKey.operator(ENodeKind.factorial),
    ],
  ],
);

/// Структуры: системы уравнений и определители.
final KeyboardPanel _structurePanel = KeyboardPanel(
  title: '{}',
  rows: [
    [
      MathKey.template(ENodeKind.system2),
      MathKey.template(ENodeKind.determinant2),
      MathKey.template(ENodeKind.determinant3),
      MathKey.template(ENodeKind.vector),
    ],
    [
      MathKey.template(ENodeKind.matrix2),
      MathKey.template(ENodeKind.matrix3),
    ],
  ],
);

/// Все панели в порядке вкладок.
final List<KeyboardPanel> keyboardPanels = [
  _basePanel,
  _functionPanel,
  _powerPanel,
  _relationPanel,
  _variablePanel,
  _calculusPanel,
  _structurePanel,
  _combinatoricsPanel,
];

/// Клавиатура: вкладки панелей, клавиша навигации и клавиши панели.
class MathKeyboard extends StatefulWidget {
  const MathKeyboard({super.key, required this.controller});

  final EditorController controller;

  @override
  State<MathKeyboard> createState() => _MathKeyboardState();
}

class _MathKeyboardState extends State<MathKeyboard> {
  int _panel = 0;

  void _press(MathKey key) {
    final controller = widget.controller;
    switch (key.type) {
      case MathKeyType.digit:
        controller.typeDigit(key.value!);
      case MathKeyType.variable:
        controller.typeVariable(key.value!);
      case MathKeyType.operator:
        controller.insertOperator(key.kind!);
      case MathKeyType.template:
        controller.insertTemplate(key.kind!);
      case MathKeyType.backspace:
        controller.backspace();
      case MathKeyType.delete:
        controller.deleteForward();
      case MathKeyType.left:
        controller.moveLeft();
      case MathKeyType.right:
        controller.moveRight();
      case MathKeyType.up:
        controller.moveUp();
      case MathKeyType.down:
        controller.moveDown();
      case MathKeyType.clear:
        controller.clear();
      case MathKeyType.panel:
        setState(() => _panel = key.panel!);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Container(
      color: theme.colorScheme.surfaceContainerHighest,
      padding: const EdgeInsets.fromLTRB(4, 4, 4, 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _tabs(theme),
          const SizedBox(height: 4),
          _navRow(),
          const SizedBox(height: 4),
          for (final row in keyboardPanels[_panel].rows) ...[
            _keyRow(row),
            const SizedBox(height: 4),
          ],
        ],
      ),
    );
  }

  /// Вкладки панелей: горизонтальная прокрутка, чтобы не сжимать подписи.
  Widget _tabs(ThemeData theme) {
    return SizedBox(
      height: 36,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: [
            for (var i = 0; i < keyboardPanels.length; i++)
              Padding(
                padding: const EdgeInsets.only(right: 4),
                child: ChoiceChip(
                  label: Text(keyboardPanels[i].title),
                  selected: _panel == i,
                  onSelected: (_) => setState(() => _panel = i),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _navRow() {
    return _keyRow(const [
      MathKey(MathKeyType.left, label: '◀', flex: 1),
      MathKey(MathKeyType.up, label: '▲', flex: 1),
      MathKey(MathKeyType.down, label: '▼', flex: 1),
      MathKey(MathKeyType.right, label: '▶', flex: 1),
      MathKey(MathKeyType.backspace, label: '⌫', flex: 1),
      MathKey(MathKeyType.clear, label: 'C', flex: 1),
    ]);
  }

  Widget _keyRow(List<MathKey> keys) {
    return Row(
      children: [
        for (final key in keys)
          Expanded(
            flex: key.flex,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 2),
              child: _KeyButton(
                key: ValueKey('key:${key.label}'),
                mathKey: key,
                onPressed: () => _press(key),
              ),
            ),
          ),
      ],
    );
  }
}

/// Кнопка одной клавиши.
class _KeyButton extends StatelessWidget {
  const _KeyButton({super.key, required this.mathKey, required this.onPressed});

  final MathKey mathKey;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    final isAction = switch (mathKey.type) {
      MathKeyType.backspace ||
      MathKeyType.delete ||
      MathKeyType.left ||
      MathKeyType.right ||
      MathKeyType.up ||
      MathKeyType.down ||
      MathKeyType.clear => true,
      _ => false,
    };
    // Подпись словами: символьные клавиши (`⁄`, `xⁿ`, `|x|`) иначе читаются
    // непонятно — и как подсказка, и в screen reader.
    final described = mathKey.kind?.description ?? mathKey.label;
    final child = SizedBox(
      height: 48,
      child: isAction
          ? OutlinedButton(
              onPressed: onPressed,
              style: OutlinedButton.styleFrom(
                padding: EdgeInsets.zero,
                minimumSize: const Size(0, 48),
              ),
              child: Text(mathKey.label, style: const TextStyle(fontSize: 18)),
            )
          : FilledButton.tonal(
              onPressed: onPressed,
              style: FilledButton.styleFrom(
                padding: EdgeInsets.zero,
                minimumSize: const Size(0, 48),
              ),
              child: Text(
                mathKey.label,
                style: const TextStyle(fontSize: 18),
              ),
            ),
    );
    return Semantics(
      button: true,
      label: described,
      child: Tooltip(message: described, child: child),
    );
  }
}
