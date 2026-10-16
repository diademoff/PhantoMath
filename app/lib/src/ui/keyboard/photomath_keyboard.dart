/// Клавиатура Photomath — виджет с геометрией оригинала.
///
/// Раскладка повторяет `res/layout/view_editor_keyboard.xml` и расчёт
/// `com.microblink.photomath.editor.keyboard.view.GridLayout.onMeasure`:
///
/// * высота экрана = доля высоты окна (`ofFullHeight`: 8% для служебного
///   ряда, 33% для сетки клавиш);
/// * ячейка = (высота − (рядов + 1) × `rowPadding`) / рядов по вертикали и
///   (ширина − (столбцов + 1) × `columnPadding`) / столбцов по горизонтали;
/// * отступ 2dip (`keyboard_column_padding` / `keyboard_row_padding`) стоит
///   и между ячейками, и по краям — как в `onLayout`, где координата
///   считается от единицы, а не от нуля;
/// * клавиша — прямоугольник со скруглением 2dip поверх однотонной заливки
///   (`drawable/keyboard_button_background`), подпись `#4C4F54`.
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import '../../editor/controller.dart';
import '../../editor/keyboard.dart';
import '../../theme/photomath_theme.dart';
import 'ph_keyboard_spec.dart';

/// Клавиатура Photomath: служебный ряд + сетка клавиш выбранного экрана.
class PhotomathKeyboard extends StatefulWidget {
  const PhotomathKeyboard({
    super.key,
    required this.controller,
    this.decimalSeparator = '.',
  });

  final EditorController controller;

  /// Разделитель из профиля (`DecimalSeparator` оригинала) — на нём
  /// перерисовывается клавиша `DIGIT_DOT`.
  final String decimalSeparator;

  @override
  State<PhotomathKeyboard> createState() => _PhotomathKeyboardState();
}

class _PhotomathKeyboardState extends State<PhotomathKeyboard> {
  PhSheet _sheet = PhSheet.primary;

  /// Код клавиши, у которой сейчас показано выпадающее меню.
  String? _extended;

  /// Позиция ячейки внутри текущего экрана — по ней открывается меню.
  (int, int)? _anchor;

  EditorController get _editor => widget.controller;

  PhSheetSpec get _grid => sheetOf(_sheet);

  @override
  void dispose() {
    _closeExtensions();
    super.dispose();
  }

  void _closeExtensions() {
    if (_extended == null) return;
    _extended = null;
    _anchor = null;
  }

  /// Переключение экрана: `HELPER_XYZ_SHEET` и `HELPER_SHOW_SECONDARY_SHEET`
  /// оригинала открывают `ALPHABET_SHEET` и `SECONDARY_SHEET`.
  void _openSheet(PhSheet sheet) => setState(() => _sheet = sheet);

  /// Нажатие клавиши: `KeyboardView$h$a` оригинала.
  ///
  /// Оригинал (`KeyboardView.a`, jadx) после любой обычной клавиши
  /// возвращает сетку на `PRIMARY_SHEET`: цифры всегда под рукой, а за
  /// функциями ходят тогглом `f ∫ <>` / `abc`.
  void _press(PhKey key) {
    _closeExtensions();
    final action = key.action;
    if (action == null) return;
    _apply(action);
    if (_sheet != PhSheet.primary) {
      setState(() => _sheet = PhSheet.primary);
    }
  }

  /// Раздать действие редактору (`MathKey` → `EditorController`).
  void _apply(MathKey action) {
    switch (action.type) {
      case MathKeyType.digit:
        _editor.typeDigit(action.value!);
      case MathKeyType.variable:
        _editor.typeVariable(action.value!);
      case MathKeyType.operator:
        _editor.insertOperator(action.kind!);
      case MathKeyType.template:
        _editor.insertTemplate(action.kind!);
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
        // Панели `operators.dart` указывают номера старой раскладки; здесь
        // экраны Photomath, поэтому маршрутизируем по самой клавише.
        break;
    }
  }

  /// Служебная клавиша: переключение экрана либо действие редактора.
  ///
  /// Тогглы повторяют `KeyboardView.a` оригинала (jadx): повторное нажатие
  /// `HELPER_XYZ_SHEET` / `HELPER_SHOW_SECONDARY_SHEET` на своём экране
  /// возвращает `PRIMARY_SHEET`; любая другая служебная клавиша тоже
  /// возвращает сетку на primary (`else`-ветка `a`: `this.i = PRIMARY`).
  void _pressControl(PhKey key) {
    switch (key.code) {
      case 'HELPER_XYZ_SHEET':
        _openSheet(
          _sheet == PhSheet.alphabet ? PhSheet.primary : PhSheet.alphabet,
        );
        return;
      case 'HELPER_SHOW_SECONDARY_SHEET':
        _openSheet(
          _sheet == PhSheet.secondary ? PhSheet.primary : PhSheet.secondary,
        );
        return;
      case 'CONTROL_MOVE_LEFT':
        _editor.moveLeft();
      case 'CONTROL_MOVE_RIGHT':
        _editor.moveRight();
      case 'CONTROL_DELETE':
        _editor.backspace();
      case 'CONTROL_NEW_LINE':
        // Новая строка системы: строки документа решаются совместно.
        _editor.newLine();
        break;
    }
    if (_sheet != PhSheet.primary) {
      setState(() => _sheet = PhSheet.primary);
    }
  }

  /// Меню долгого нажатия (`f286c` оригинала).
  ///
  /// Открывается только если у клавиши есть расширение
  /// (`KeyboardKeyView.g`: `z2 && extensions != null && length > 0`).
  void _showExtensions(PhKey key, int row, int column) {
    final items = extensionsOf(key.code);
    if (items.isEmpty) return;
    setState(() {
      _extended = key.code;
      _anchor = (row, column);
    });
  }

  @override
  Widget build(BuildContext context) {
    final screenHeight = MediaQuery.sizeOf(context).height;
    return Material(
      color: PhColor.keyboardBackground,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildSheet(controlSheet(), screenHeight, isControl: true),
          _buildSheet(_grid, screenHeight, isControl: false),
        ],
      ),
    );
  }

  /// Один экран: сетка `rows × columns` высотой `ofFullHeight` окна.
  Widget _buildSheet(
    PhSheetSpec spec,
    double screenHeight, {
    required bool isControl,
  }) {
    final height = screenHeight * spec.ofFullHeight;
    // Меню долгого нажатия живёт только в сетке клавиш: служебный ряд
    // (`ofFullHeight=8%`) слишком низок для всплывающего окна, а долгое
    // нажатие там всё равно ничего не открывает (`onLongPress=null`).
    final showMenu = !isControl && _extended != null && _anchor != null;
    return SizedBox(
      height: height,
      child: Stack(
        clipBehavior: Clip.none,
        children: [
          Positioned.fill(
            child: Padding(
              padding: const EdgeInsets.all(PhSize.keyPadding),
              child: _Grid(
                spec: spec,
                keys: _keysOf(spec).take(spec.cellCount).toList(),
                onPress: isControl ? _pressControl : _press,
                onLongPress: isControl ? null : _showExtensions,
              ),
            ),
          ),
          if (showMenu)
            _ExtensionMenu(
              anchor: _anchor!,
              code: _extended!,
              onDismiss: _closeExtensions,
              onPick: (key) {
                _closeExtensions();
                _press(key);
              },
            ),
        ],
      ),
    );
  }

  /// Разделитель из профиля подставляется в клавишу `DIGIT_DOT`.
  ///
  /// Оригинал делает это в конструкторе `g`: `new f(DIGIT_DOT,
  /// decimalSeparator.g)`, то есть точка или запятая берётся из настроек
  /// профиля, а не из локали.
  List<PhKey> _keysOf(PhSheetSpec spec) => [
    for (final key in spec.keys)
      if (key.code == 'DIGIT_DOT')
        PhKey(
          key.code,
          key.type,
          widget.decimalSeparator,
          description: key.description,
        )
      else
        key,
  ];
}

/// Сетка клавиш: равные ячейки с отступом 2dip, как в `GridLayout.onLayout`.
class _Grid extends StatelessWidget {
  const _Grid({
    required this.spec,
    required this.keys,
    required this.onPress,
    required this.onLongPress,
  });

  final PhSheetSpec spec;
  final List<PhKey> keys;
  final void Function(PhKey key) onPress;

  /// `null` на служебном ряду: там долгое нажатие ничего не открывает.
  final void Function(PhKey key, int row, int column)? onLongPress;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Ширина и высота ячейки считаются той же формулой, что и в
        // `GridLayout.onMeasure`: из доступного места вычитаются все
        // промежутки, включая крайние.
        final cellWidth =
            (constraints.maxWidth -
                (spec.columnCount + 1) * PhSize.keyPadding) /
            spec.columnCount;
        final cellHeight =
            (constraints.maxHeight - (spec.rowCount + 1) * PhSize.keyPadding) /
            spec.rowCount;
        return Column(
          children: [
            for (var row = 0; row < spec.rowCount; row++)
              SizedBox(
                height: cellHeight + PhSize.keyPadding,
                child: Row(
                  children: [
                    for (var column = 0; column < spec.columnCount; column++)
                      Builder(
                        builder: (context) {
                          final key = _at(row, column);
                          return SizedBox(
                            width: cellWidth + PhSize.keyPadding,
                            child: Padding(
                              padding: const EdgeInsets.all(
                                PhSize.keyPadding / 2,
                              ),
                              child: _KeyButton(
                                // Ключ виджета — код оператора оригинала:
                                // он не меняется при смене экрана и не
                                // зависит от того, как нарисован глиф.
                                key: ValueKey(
                                  key.code.isEmpty
                                      ? '${spec.sheet.name}:$row:$column'
                                      : 'key:${key.code}',
                                ),
                                width: cellWidth,
                                height: cellHeight,
                                phKey: key,
                                onPressed: onPress,
                                onLongPressed: onLongPress == null
                                    ? null
                                    : (pressed) =>
                                          onLongPress!(pressed, row, column),
                              ),
                            ),
                          );
                        },
                      ),
                  ],
                ),
              ),
          ],
        );
      },
    );
  }

  PhKey _at(int row, int column) {
    final index = spec.columnCount * row + column;
    if (index < keys.length) return keys[index];
    return const PhKey('', PhKeyType.grid, '');
  }
}

/// Клавиша: скруглённый прямоугольник с заливкой по типу и глифом.
class _KeyButton extends StatelessWidget {
  const _KeyButton({
    super.key,
    required this.width,
    required this.height,
    required this.phKey,
    required this.onPressed,
    this.onLongPressed,
  });

  final double width;
  final double height;
  final PhKey phKey;
  final void Function(PhKey key) onPressed;
  final void Function(PhKey key)? onLongPressed;

  bool get _isSpacer => phKey.code.isEmpty;

  @override
  Widget build(BuildContext context) {
    if (_isSpacer) return const SizedBox.shrink();
    final enabled = phKey.action != null;
    return Semantics(
      button: true,
      enabled: enabled,
      label: phKey.description,
      child: SizedBox(
        width: width,
        height: height,
        // Неподдержанные решателем клавиши (`_unsupported` в `operators.dart`:
        // `aₙ`, перевод строки) видны, но приглушены — иначе они выглядят
        // рабочими и молча глотают нажатие.
        child: Opacity(
          opacity: enabled ? 1.0 : 0.35,
          child: Material(
            color: keyBackground(phKey.type),
            borderRadius: BorderRadius.circular(PhSize.keyRadius),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: enabled ? () => onPressed(phKey) : null,
              onLongPress: onLongPressed == null
                  ? null
                  : () => onLongPressed!(phKey),
              splashColor: PhColor.gray30,
              highlightColor: PhColor.gray30,
              child: Center(child: _glyph(context)),
            ),
          ),
        ),
      ),
    );
  }

  /// Глиф клавиши.
  ///
  /// Оригинал рисует математические подписи движком (`MathTextView` с
  /// кеглем `keyViewTextSize × 0.85`), а иконки — векторными картинками
  /// 58×52dip: подпись всегда занимает одну ячейку и не выходит за неё.
  /// Здесь то же самое делает [FittedBox]: широкая формула вроде `a/b`
  /// ужимается до ширины клавиши, узкая остаётся натурального размера.
  Widget _glyph(BuildContext context) {
    final color = PhColor.keyboardText;
    if (_isControlGlyph) {
      return Icon(_controlIcon, size: PhSize.keyTextSize * 1.4, color: color);
    }
    final glyph = phKey.glyph;
    if (glyph.isEmpty) return const SizedBox.shrink();
    final style = TextStyle(
      fontSize: PhSize.keyTextSize * PhSize.keyGlyphScale,
      color: color,
    );
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: FittedBox(
        fit: BoxFit.scaleDown,
        child: Math.tex(
          glyph,
          mathStyle: MathStyle.display,
          textStyle: style,
          onErrorFallback: (error) => Text(phKey.description, style: style),
        ),
      ),
    );
  }

  bool get _isControlGlyph =>
      phKey.type == PhKeyType.control &&
      const {
        'CONTROL_MOVE_LEFT',
        'CONTROL_MOVE_RIGHT',
        'CONTROL_NEW_LINE',
        'CONTROL_DELETE',
      }.contains(phKey.code);

  IconData get _controlIcon => switch (phKey.code) {
    'CONTROL_MOVE_LEFT' => Icons.arrow_left,
    'CONTROL_MOVE_RIGHT' => Icons.arrow_right,
    'CONTROL_NEW_LINE' => Icons.keyboard_return,
    'CONTROL_DELETE' => Icons.backspace_outlined,
    _ => Icons.circle,
  };
}

/// Выпадающее меню долгого нажатия — аналог `f286c` оригинала.
class _ExtensionMenu extends StatelessWidget {
  const _ExtensionMenu({
    required this.anchor,
    required this.code,
    required this.onDismiss,
    required this.onPick,
  });

  /// Строка и столбец ячейки, у которой открыто меню.
  final (int, int) anchor;

  /// Код клавиши, у которой открыто меню.
  final String code;

  /// Закрыть меню тапом мимо.
  final VoidCallback onDismiss;

  final void Function(PhKey key) onPick;

  @override
  Widget build(BuildContext context) {
    final items = extensionsOf(code);
    if (items.isEmpty) return const SizedBox.shrink();
    // Меню выскакивает над клавишей и прижато к краю экрана, если клавиша
    /// у края — как всплывающее окно оригинала (`keyboard_selected_extension`
    /// рисуется отдельным слоем поверх сетки).
    final column = anchor.$2;
    final alignment = Alignment(
      ((column + 0.5) / 6 * 2 - 1).clamp(-0.95, 0.95),
      0.55,
    );
    return Positioned.fill(
      child: GestureDetector(
        onTap: onDismiss,
        child: Align(
          alignment: alignment,
          child: Material(
            color: PhColor.white,
            elevation: 4,
            borderRadius: BorderRadius.circular(PhSize.keyRadius),
            clipBehavior: Clip.antiAlias,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                for (final key in items)
                  InkWell(
                    // Ключ — код оператора оригинала, как у клавиш сетки:
                    // тесты и скринридер находят пункт по тому же ключу.
                    key: ValueKey('key:${key.code}'),
                    onTap: () => onPick(key),
                    child: Container(
                      height: 44,
                      alignment: Alignment.center,
                      color: keyBackground(key.type),
                      child: Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 8),
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          child: Math.tex(
                            key.glyph,
                            mathStyle: MathStyle.display,
                            textStyle: const TextStyle(
                              fontSize: 17,
                              color: PhColor.keyboardText,
                            ),
                            onErrorFallback: (error) => Text(
                              key.description,
                              style: const TextStyle(
                                fontSize: 14,
                                color: PhColor.keyboardText,
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
