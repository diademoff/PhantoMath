import 'package:flutter/material.dart';

import 'dart:math' as math;

import 'package:flutter_math_fork/flutter_math.dart';

import '../../editor/controller.dart';
import '../../editor/keyboard.dart';
import 'ph_keyboard_spec.dart';

/// Stable numeric block, minimum 48dp keys, persistent alphabet and an explicit
/// catalog for variants (long press is a shortcut, never the only way).
class PhotomathKeyboard extends StatefulWidget {
  const PhotomathKeyboard({
    super.key,
    required this.controller,
    this.decimalSeparator = '.',
    this.maxHeight,
  });
  final EditorController controller;
  final String decimalSeparator;
  final double? maxHeight;
  @override
  State<PhotomathKeyboard> createState() => _PhotomathKeyboardState();
}

class _PhotomathKeyboardState extends State<PhotomathKeyboard> {
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
        _editor.insertTemplate(action.kind!);
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

  Future<void> _catalog() async {
    final keys = <String, PhKey>{};
    for (final spec in sheets) {
      for (final k in spec.keys) {
        if (k.code.isNotEmpty &&
            k.type != PhKeyType.control &&
            k.action != null) {
          keys[k.code] = k;
        }
        for (final v in extensionsOf(k.code)) {
          if (v.action != null) keys[v.code] = v;
        }
      }
    }
    final selected = await showModalBottomSheet<PhKey>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: SizedBox(
          height: MediaQuery.sizeOf(context).height * .75,
          child: ListView(
            padding: const EdgeInsets.all(16),
            children: [
              Text(
                'Все символы',
                style: Theme.of(context).textTheme.titleLarge,
              ),
              for (final k in keys.values)
                ListTile(
                  minTileHeight: 56,
                  title: Text(k.description),
                  onTap: () => Navigator.pop(context, k),
                ),
            ],
          ),
        ),
      ),
    );
    if (selected != null && mounted) _apply(selected);
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
                    'Функции',
                    Icons.functions,
                    () => _toggle(PhSheet.secondary),
                  ),
                  _control(
                    'HELPER_XYZ_SHEET',
                    'Буквы',
                    Icons.abc,
                    () => _toggle(PhSheet.alphabet),
                  ),
                  _control(
                    'CONTROL_MOVE_LEFT',
                    'Курсор влево',
                    Icons.chevron_left,
                    _editor.moveLeft,
                  ),
                  _control(
                    'CONTROL_MOVE_RIGHT',
                    'Курсор вправо',
                    Icons.chevron_right,
                    _editor.moveRight,
                  ),
                  _control(
                    'CONTROL_NEW_LINE',
                    'Новая строка',
                    Icons.keyboard_return,
                    _editor.newLine,
                  ),
                  if (_sheet != PhSheet.primary)
                    _control(
                      'CONTROL_DELETE',
                      'Удалить',
                      Icons.backspace_outlined,
                      _editor.backspace,
                    ),
                  IconButton(
                    tooltip: 'Все символы',
                    onPressed: _catalog,
                    icon: const Icon(Icons.more_horiz),
                  ),
                  if (_editor.cursor.steps.isNotEmpty)
                    TextButton(
                      onPressed: _editor.nextSlot,
                      child: const Text('Далее'),
                    ),
                ],
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
                              onTap: enabled ? () => _apply(key) : null,
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
                      );
                    },
                  ),
                );
              },
            ),
            if (_sheet != PhSheet.primary)
              TextButton(
                onPressed: () => _toggle(_sheet),
                child: const Text('123 · Цифры'),
              ),
          ],
        ),
      ),
    );
  }
}
