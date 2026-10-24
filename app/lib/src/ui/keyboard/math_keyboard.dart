import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'dart:math' as math;

import 'package:flutter_math_fork/flutter_math.dart';

import '../../editor/controller.dart';
import '../../editor/kind.dart';
import '../../editor/model.dart' as ed;
import '../../editor/keyboard.dart';
import '../../i18n.dart';
import 'ph_keyboard_spec.dart';

/// Stable numeric block, minimum 48dp keys, persistent alphabet and an explicit
/// catalog for variants (long press is a shortcut, never the only way).
class MathKeyboard extends StatefulWidget {
  const MathKeyboard({
    super.key,
    required this.controller,
    this.decimalSeparator = '.',
    this.maxHeight,
  });
  final EditorController controller;
  final String decimalSeparator;
  final double? maxHeight;
  @override
  State<MathKeyboard> createState() => _MathKeyboardState();
}

class _MathKeyboardState extends State<MathKeyboard> {
  PhSheet _sheet = PhSheet.primary;
  final Map<String, int> _interactionEpoch = {};
  EditorController get _editor => widget.controller;

  void _apply(PhKey key) {
    final action = key.action;
    if (action == null) return;
    switch (action.type) {
      case MathKeyType.digit:
        _editor.typeDigit(action.value!);
      case MathKeyType.variable:
        _editor.typeVariable(action.value!);
      case MathKeyType.operator:
        _editor.insertOperator(action.kind!);
      case MathKeyType.template:
        switch (action.kind!) {
          case ENodeKind.matrix2 || ENodeKind.matrix3:
            _matrixSize();
          case ENodeKind.determinant2 || ENodeKind.determinant3:
            _determinantSize();
          case ENodeKind.bracket when key.code == 'OPERATOR_RIGHT_BRACKET':
            _editor.closeBracket();
          default:
            _editor.insertTemplate(action.kind!);
        }
      case MathKeyType.newline:
        _editor.newLine();
      case MathKeyType.backspace:
        _editor.backspace();
      case MathKeyType.delete:
        _editor.deleteForward();
      case MathKeyType.left:
        _editor.moveLeft();
      case MathKeyType.right:
        _editor.moveRight();
      case MathKeyType.up:
        _editor.moveUp();
      case MathKeyType.down:
        _editor.moveDown();
      case MathKeyType.clear:
        _editor.clear();
      case MathKeyType.panel:
        break;
    }
    if (_sheet == PhSheet.secondary &&
        action.type != MathKeyType.left &&
        action.type != MathKeyType.right) {
      setState(() => _sheet = PhSheet.primary);
    }
  }

  void _toggle(PhSheet sheet) =>
      setState(() => _sheet = _sheet == sheet ? PhSheet.primary : sheet);

  List<PhKey> get _primary {
    final byCode = {for (final k in primarySheet().keys) k.code: k};
    return [
      for (final code in const [
        'OPERATOR_LEFT_BRACKET',
        'OPERATOR_RIGHT_BRACKET',
        'OPERATOR_ROOT_TWO',
        'OPERATOR_POWER_TWO',
        'OPERATOR_FRACTION',
        'VARIABLE_X_LOW',
        'DIGIT_SEVEN',
        'DIGIT_EIGHT',
        'DIGIT_NINE',
        'BASIC_INFIX_OPERATOR_DIVIDE',
        'CONSTANT_PI',
        'DIGIT_FOUR',
        'DIGIT_FIVE',
        'DIGIT_SIX',
        'BASIC_INFIX_OPERATOR_MULTIPLY',
        'BASIC_INFIX_OPERATOR_PERCENTAGE',
        'DIGIT_ONE',
        'DIGIT_TWO',
        'DIGIT_THREE',
        'BASIC_INFIX_OPERATOR_MINUS',
        'BASIC_INFIX_OPERATOR_EQUALS',
        'DIGIT_ZERO',
        'DIGIT_DOT',
        'CONTROL_DELETE',
        'BASIC_INFIX_OPERATOR_PLUS',
      ])
        code == 'CONTROL_DELETE' ? controlSheet().keys.last : byCode[code]!,
    ];
  }

  Future<void> _variants(PhKey key) async {
    final variants = extensionsOf(key.code);
    if (variants.isEmpty) return;
    final selected = await showModalBottomSheet<PhKey>(
      context: context,
      builder: (context) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          padding: const EdgeInsets.fromLTRB(16, 0, 16, 24),
          children: [
            Text(
              key.description,
              style: Theme.of(context).textTheme.titleLarge,
            ),
            for (final k in variants)
              ListTile(
                key: ValueKey('key:${k.code}'),
                minTileHeight: 56,
                title: Text(k.description),
                trailing: SizedBox(width: 64, child: _glyph(k)),
                onTap: k.action == null
                    ? null
                    : () => Navigator.pop(context, k),
              ),
          ],
        ),
      ),
    );
    if (!mounted) return;
    // A modal takes the active long-press pointer away from InkResponse. Reset
    // that key's interaction state, not the editor, layout or scroll position.
    setState(
      () =>
          _interactionEpoch[key.code] = (_interactionEpoch[key.code] ?? 0) + 1,
    );
    if (selected != null) _apply(selected);
  }

  /// Ряд «минус · значение · плюс» диалога размера.
  Widget _dimension(
    StateSetter update,
    String label,
    int value,
    int min,
    int max,
    void Function(int) change,
  ) => Row(
    children: [
      Expanded(child: Text(label)),
      IconButton(
        tooltip: tr('Уменьшить $label', 'Decrease $label'),
        onPressed: value > min ? () => update(() => change(value - 1)) : null,
        icon: const Icon(Icons.remove),
      ),
      Text('$value'),
      IconButton(
        tooltip: tr('Увеличить $label', 'Increase $label'),
        onPressed: value < max ? () => update(() => change(value + 1)) : null,
        icon: const Icon(Icons.add),
      ),
    ],
  );

  /// Диалог размера — общий для «Матрицы» и «Определителя».
  ///
  /// У матрицы независимые строки и столбцы (1…8), у определителя размер один:
  /// он квадратный (2…5), поэтому там показывается одна строка «Размер».
  Future<(int, int)?> _sizeDialog({
    required String title,
    required String hint,
    required int minRows,
    required int maxRows,
    required int minColumns,
    required int maxColumns,
    bool square = false,
  }) async {
    var rows = square ? minRows : 2;
    var columns = square ? minRows : 2;
    return showDialog<(int, int)>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, update) => AlertDialog(
          title: Text(title),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _dimension(
                update,
                square ? tr('Размер', 'Size') : tr('Строки', 'Rows'),
                rows,
                minRows,
                maxRows,
                (v) {
                  rows = v;
                  if (square) columns = v;
                },
              ),
              if (!square)
                _dimension(
                  update,
                  tr('Столбцы', 'Columns'),
                  columns,
                  minColumns,
                  maxColumns,
                  (v) => columns = v,
                ),
              Text(hint),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text(tr('Отмена', 'Cancel')),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(context, (rows, columns)),
              child: Text(tr('Вставить', 'Insert')),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _matrixSize() async {
    final size = await _sizeDialog(
      title: tr('Размер матрицы', 'Matrix size'),
      hint: tr(
        'От 1 до 8. «Далее» переходит к следующей ячейке.',
        '1 to 8. Next moves to the next cell.',
      ),
      minRows: 1,
      maxRows: 8,
      minColumns: 1,
      maxColumns: 8,
    );
    if (mounted && size != null) _editor.insertMatrix(size.$1, size.$2);
  }

  /// Определитель — тот же диалог, но квадратный: 2…5.
  Future<void> _determinantSize() async {
    final size = await _sizeDialog(
      title: tr('Размер определителя', 'Determinant size'),
      hint: tr(
        'От 2 до 5. Определитель квадратный.',
        '2 to 5. Determinant is square.',
      ),
      minRows: 2,
      maxRows: 5,
      minColumns: 2,
      maxColumns: 5,
      square: true,
    );
    if (mounted && size != null) {
      _editor.insertTemplate(_determinantKind(size.$1));
    }
  }

  /// Вид узла редактора по размеру определителя.
  static ENodeKind _determinantKind(int size) => switch (size) {
    2 => ENodeKind.determinant2,
    3 => ENodeKind.determinant3,
    4 => ENodeKind.determinant4,
    _ => ENodeKind.determinant5,
  };

  String? get _slotHint {
    final steps = _editor.cursor.steps;
    if (steps.isEmpty) return null;
    final step = steps.last;
    final parent = ed.rowAt(
      _editor.document,
      steps.sublist(0, steps.length - 1),
    );
    final node = parent.children[step.child];
    return switch (node.kind) {
      ENodeKind.fraction =>
        step.slot == 0
            ? tr('Числитель', 'Numerator')
            : tr('Знаменатель', 'Denominator'),
      ENodeKind.power =>
        step.slot == 0
            ? tr('Основание степени', 'Base')
            : tr('Показатель степени', 'Exponent'),
      ENodeKind.log =>
        step.slot == 1
            ? tr('Основание логарифма', 'Logarithm base')
            : tr('Аргумент логарифма', 'Argument'),
      ENodeKind.sigma =>
        (node.children.length == 4
            ? [
                tr('Переменная суммирования', 'Summation variable'),
                tr('Нижняя граница', 'Lower bound'),
                tr('Верхняя граница', 'Upper bound'),
                tr('Слагаемое', 'Term'),
              ]
            : [
                tr('Нижняя граница (индекс n)', 'Lower bound (index n)'),
                tr('Верхняя граница', 'Upper bound'),
                tr('Слагаемое', 'Term'),
              ])[step.slot],
      ENodeKind.matrix2 ||
      ENodeKind.matrix3 ||
      ENodeKind.determinant2 ||
      ENodeKind.determinant3 ||
      ENodeKind.determinant4 ||
      ENodeKind.determinant5 => tr(
        'Строка ${step.slot ~/ node.matrixColumns + 1}, столбец ${step.slot % node.matrixColumns + 1}',
        'Row ${step.slot ~/ node.matrixColumns + 1}, column ${step.slot % node.matrixColumns + 1}',
      ),
      _ => null,
    };
  }

  Widget _control(
    String code,
    String label,
    IconData icon,
    VoidCallback onTap,
  ) => IconButton(
    key: ValueKey('key:$code'),
    tooltip: label,
    onPressed: onTap,
    icon: Icon(icon, size: 22),
  );

  Widget _glyph(PhKey key) {
    if (key.code == 'CONTROL_DELETE') {
      return const Icon(Icons.backspace_outlined, size: 22);
    }
    final glyph = key.code == 'DIGIT_DOT' ? widget.decimalSeparator : key.glyph;
    if (key.type == PhKeyType.digit) {
      return Text(
        glyph,
        style: const TextStyle(fontSize: 24, fontWeight: FontWeight.w500),
      );
    }
    return FittedBox(
      fit: BoxFit.scaleDown,
      child: Math.tex(
        glyph,
        textStyle: TextStyle(
          fontSize: 21,
          color: Theme.of(context).colorScheme.onSurface,
        ),
        onErrorFallback: (_) =>
            Text(key.description, style: const TextStyle(fontSize: 16)),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Material(
      color: colors.surfaceContainerLow,
      child: ListenableBuilder(
        listenable: _editor,
        builder: (context, _) => Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _control(
                    'HELPER_SHOW_SECONDARY_SHEET',
                    tr('Функции', 'Functions'),
                    Icons.functions,
                    () => _toggle(PhSheet.secondary),
                  ),
                  _control(
                    'HELPER_XYZ_SHEET',
                    tr('Буквы', 'Letters'),
                    Icons.abc,
                    () => _toggle(PhSheet.alphabet),
                  ),
                  _control(
                    'CONTROL_MOVE_LEFT',
                    tr('Курсор влево', 'Cursor left'),
                    Icons.chevron_left,
                    _editor.moveLeft,
                  ),
                  _control(
                    'CONTROL_MOVE_RIGHT',
                    tr('Курсор вправо', 'Cursor right'),
                    Icons.chevron_right,
                    _editor.moveRight,
                  ),
                  _control(
                    'CONTROL_NEW_LINE',
                    tr('Новая строка', 'New line'),
                    Icons.keyboard_return,
                    _editor.newLine,
                  ),
                  if (_sheet != PhSheet.primary)
                    _control(
                      'CONTROL_DELETE',
                      tr('Удалить', 'Delete'),
                      Icons.backspace_outlined,
                      _editor.backspace,
                    ),
                  if (_editor.cursor.steps.isNotEmpty)
                    TextButton(
                      onPressed: _editor.nextSlot,
                      child: Text(tr('Далее', 'Next')),
                    ),
                ],
              ),
            ),
            // The hint line is always reserved, so the keyboard keeps its
            // height and the arrow keys do not move when a slot gets focus.
            SizedBox(
              height: 24 * MediaQuery.textScalerOf(context).scale(1),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Text(
                  _slotHint ?? '',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: Theme.of(context).textTheme.labelSmall,
                ),
              ),
            ),
            LayoutBuilder(
              builder: (context, constraints) {
                final keys = switch (_sheet) {
                  PhSheet.primary => _primary,
                  PhSheet.alphabet =>
                    alphabetSheet().keys
                        .where((k) => k.code.isNotEmpty)
                        .toList(),
                  _ => secondarySheet().keys,
                };
                final columns = ((constraints.maxWidth - 16) / 52)
                    .floor()
                    .clamp(1, 5);
                final textScale = MediaQuery.textScalerOf(context).scale(1);
                final height = (48 * textScale).clamp(48.0, 80.0);
                final gridHeight = math.max(
                  height + 16,
                  math.min(
                    height * 5 + 32,
                    (widget.maxHeight ?? (height * 5 + 128)) -
                        48 -
                        24 * textScale -
                        (_sheet == PhSheet.primary ? 0 : 48),
                  ),
                );
                return SizedBox(
                  height: gridHeight,
                  child: GridView.builder(
                    key: ValueKey(_sheet),
                    padding: const EdgeInsets.fromLTRB(8, 4, 8, 12),
                    gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                      crossAxisCount: columns,
                      mainAxisExtent: height,
                      crossAxisSpacing: 4,
                      mainAxisSpacing: 4,
                    ),
                    itemCount: keys.length,
                    itemBuilder: (context, index) {
                      final key = keys[index];
                      final enabled = key.action != null;
                      return Semantics(
                        button: true,
                        enabled: enabled,
                        label: key.description,
                        child: Opacity(
                          opacity: enabled ? 1 : .35,
                          child: _PressScale(
                            enabled: enabled,
                            child: Material(
                              key: ValueKey(
                                '${key.code}:${_interactionEpoch[key.code] ?? 0}',
                              ),
                              color: key.type == PhKeyType.digit
                                  ? colors.surface
                                  : colors.surfaceContainerHighest,
                              borderRadius: BorderRadius.circular(10),
                              clipBehavior: Clip.antiAlias,
                              child: InkWell(
                                key: ValueKey('key:${key.code}'),
                                onTap: enabled
                                    ? () {
                                        HapticFeedback.selectionClick();
                                        _apply(key);
                                      }
                                    : null,
                                onLongPress: extensionsOf(key.code).isEmpty
                                    ? null
                                    : () => _variants(key),
                                child: Stack(
                                  children: [
                                    Center(
                                      child: Padding(
                                        padding: const EdgeInsets.all(8),
                                        child: _glyph(key),
                                      ),
                                    ),
                                    if (extensionsOf(key.code).isNotEmpty)
                                      Positioned(
                                        right: 5,
                                        bottom: 3,
                                        child: Icon(
                                          Icons.more_horiz,
                                          size: 12,
                                          color: colors.onSurfaceVariant,
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                        ),
                      );
                    },
                  ),
                );
              },
            ),
            if (_sheet != PhSheet.primary)
              TextButton(
                onPressed: () => _toggle(_sheet),
                child: Text(tr('123 · Цифры', '123 · Digits')),
              ),
          ],
        ),
      ),
    );
  }
}

/// Keys sink slightly while pressed, which reads as a physical button.
class _PressScale extends StatefulWidget {
  const _PressScale({required this.enabled, required this.child});
  final bool enabled;
  final Widget child;
  @override
  State<_PressScale> createState() => _PressScaleState();
}

class _PressScaleState extends State<_PressScale> {
  bool _down = false;
  void _set(bool value) {
    if (_down != value && widget.enabled) setState(() => _down = value);
  }

  @override
  Widget build(BuildContext context) => Listener(
    onPointerDown: (_) => _set(true),
    onPointerUp: (_) => _set(false),
    onPointerCancel: (_) => _set(false),
    child: AnimatedScale(
      scale: _down ? .93 : 1,
      duration: MediaQuery.disableAnimationsOf(context)
          ? Duration.zero
          : const Duration(milliseconds: 90),
      curve: Curves.easeOut,
      child: widget.child,
    ),
  );
}
