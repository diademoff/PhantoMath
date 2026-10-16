/// Клавиатура Photomath: ключи, экраны и раскладка — перенесены из APK 1 в 1.
///
/// Источник: конструктор `c.a.a.a.t.a.g` (декомпилирован через REA,
/// `inspect_android_method`), вспомогательные методы `a`/`b`/`c`/`d`/`e`/`f`/
/// `g`/`h`/`i`/`l` того же класса, `com.microblink.photomath.editor.keyboard.
/// view.KeyboardView.onFinishInflate` и `…view.GridLayout.onLayout`.
///
/// Что перенесено без изменений:
///
/// * **тип ключа** (`c.a.a.a.t.a.d`) — им определяется заливка клавиши:
///   `DIGIT`/`CONSTANT`/`VARIABLE`/`BASIC_INFIX_OPERATOR`/`HELPER`/
///   `INTERMEDIATE`/`GRID` → белый, `OPERATOR` → `#E0E0E0`, `CONTROL` →
///   `#F0F0F0`, `RETURN_HELPER` → `#CBCCCD`;
/// * **раскладка** — четыре экрана (`CONTROL_SHEET` 1×6, `PRIMARY_SHEET`
///   4×6, `SECONDARY_SHEET` 4×6, `ALPHABET_SHEET` 4×8), ключи идут построчно,
///   как в `GridLayout.onLayout` (`child = cols * row + col`);
/// * **долгое нажатие** — карта `f286c`: у `π` выпадают `π/2` и `π/3`, у `x` —
///   `y` и `z`, у `√` — `∛` и `ⁿ√`, у `x²` — `x³` и `xⁿ`, у `ln` — `log₂` и
///   `logₓ`, у `d/dx` — производная пользовательского порядка и т. д.;
/// * **подписи** — словарик `g.d` плюс короткие формы `g.e` (`asin` вместо
///   `arcsin`), которыми помечены длинные имена в выпадающих списках.
///
/// Отличия, которых нельзя избежать: векторные иконки оригинала
/// (`calculator_root2.xml` и подобные — это 58×52dip из точек) заменены
/// отрисовкой тех же математических символов, потому что наборщик формул у нас
/// общий с рендером результата; в Android это тот же движок `MathTextView`.
library;

import 'package:flutter/material.dart';

import '../../editor/keyboard.dart';
import '../../editor/operators.dart';
import '../../theme/photomath_theme.dart';

/// Тип ключа — `c.a.a.a.t.a.d` оригинала.
///
/// Имя каждого значения совпадает с константой перечисления в DEX; порядок
/// тоже (`e`, `f`, `g`, … соответствует `e` = DIGIT … `n` = GRID).
enum PhKeyType {
  /// `DIGIT` — цифры и десятичный разделитель.
  digit,

  /// `CONSTANT` — `π`, `e`, `i`, `∞`.
  constant,

  /// `BASIC_INFIX_OPERATOR` — плоские знаки: `+ − × ÷ = % < ≤ > ≥ ° !`.
  infix,

  /// `OPERATOR` — шаблоны и функции: дробь, корень, степень, `sin`, `∫`.
  function,

  /// `CONTROL` — служебный ряд: переключение экранов и курсор.
  control,

  /// `HELPER` — вспомогательные (`abc`, `f ∫ <>`).
  helper,

  /// `RETURN_HELPER` — клавиша возврата решения.
  returnHelper,

  /// `VARIABLE` — буквы и греческие.
  variable,

  /// `INTERMEDIATE` — матрица, определитель.
  intermediate,

  /// `GRID` — зарезервированный тип оригинала.
  grid,
}

/// Экран клавиатуры — `c.a.a.a.t.a.h.a`.
enum PhSheet {
  /// Ряд управления (`CONTROL_SHEET`): 1 ряд × 6 клавиш.
  control,

  /// Базовый экран (`PRIMARY_SHEET`): 4 × 6.
  primary,

  /// Расширенный экран (`SECONDARY_SHEET`): 4 × 6.
  secondary,

  /// Буквы (`ALPHABET_SHEET`): 4 × 8.
  alphabet,
}

/// Один ключ — `c.a.a.a.t.a.f`.
@immutable
class PhKey {
  const PhKey(this.code, this.type, this.glyph, {this.description = ''});

  /// Код оператора из `editor_operators` оригинала.
  ///
  /// По нему же `operators.dart` находит действие редактора, поэтому
  /// клавиатура и каталог операторов не расходятся.
  final String code;

  /// Тип ключа — определяет заливку.
  final PhKeyType type;

  /// Подпись в LaTeX без `$…$` (`MathTextView` оригинала).
  final String glyph;

  /// Словесная подпись для подсказки и для экранного диктора.
  final String description;

  /// Действие клавиши; `null`, если оператор оригинала не поддержан
  /// нашим решателем (см. `_unsupported` в `operators.dart`).
  MathKey? get action => bindOperator(code).key;
}

/// Ряд ключей — `c.a.a.a.t.a.h`.
@immutable
class PhRow {
  const PhRow(this.keys);

  final List<PhKey> keys;
}

/// Экран ключей — `c.a.a.a.t.a.h`.
///
/// Поля повторяют оригинал: `a` — число рядов, `b` — ключей в ряду.
@immutable
class PhSheetSpec {
  const PhSheetSpec({
    required this.sheet,
    required this.rowCount,
    required this.columnCount,
    required this.items,
    required this.ofFullHeight,
  });

  final PhSheet sheet;

  /// `h.a` — число рядов.
  final int rowCount;

  /// `h.b` — ключей в ряду.
  final int columnCount;

  /// Ряды ключей в порядке `onFinishInflate`.
  final List<PhRow> items;

  /// `app:ofFullHeight` — доля высоты экрана (`dimens.xml`).
  final double ofFullHeight;

  /// Ключи построчно, как их перебирает `KeyboardView.onFinishInflate`.
  List<PhKey> get keys => [for (final row in items) ...row.keys];

  /// Сколько ячеек реально рисуется: `GridLayout.onLayout` обходит
  /// `rowCount × columnCount` и не выходит за пределы списка ключей.
  int get cellCount => rowCount * columnCount;
}

/// Короткие подписи `g.e`: в выпадающих списках длинные имена ужимаются.
const Map<String, String> _shortLabels = {
  'OPERATOR_ASIN': 'asin',
  'OPERATOR_ASINH': 'asinh',
  'OPERATOR_ACOS': 'acos',
  'OPERATOR_ACOSH': 'acosh',
  'OPERATOR_ATAN': 'atan',
  'OPERATOR_ATANH': 'atanh',
  'OPERATOR_ACOT': 'acot',
  'OPERATOR_ACOTH': 'acoth',
  'OPERATOR_ASEC': 'asec',
  'OPERATOR_ASECH': 'asech',
  'OPERATOR_ACSC': 'acsc',
  'OPERATOR_ACSCH': 'acsch',
};

PhKey _k(String code, PhKeyType type, String latex, String description) =>
    PhKey(code, type, latex, description: description);

/// Служебный ряд: 1 × 6, порядок `hVar4` конструктора `g`.
///
/// ```
/// f ∫ <>   abc   ←   →   ⏎   ⌫
/// ```
PhSheetSpec controlSheet() => PhSheetSpec(
  sheet: PhSheet.control,
  rowCount: 1,
  columnCount: 6,
  ofFullHeight: 0.08,
  items: const [
    PhRow([
      PhKey(
        'HELPER_SHOW_SECONDARY_SHEET',
        PhKeyType.control,
        r'f\ \int\ <\ >',
        description: 'Расширенная панель',
      ),
      PhKey('HELPER_XYZ_SHEET', PhKeyType.control, 'abc', description: 'Буквы'),
      PhKey(
        'CONTROL_MOVE_LEFT',
        PhKeyType.control,
        '',
        description: 'Курсор влево',
      ),
      PhKey(
        'CONTROL_MOVE_RIGHT',
        PhKeyType.control,
        '',
        description: 'Курсор вправо',
      ),
      PhKey(
        'CONTROL_NEW_LINE',
        PhKeyType.control,
        '',
        description: 'Новая строка',
      ),
      PhKey('CONTROL_DELETE', PhKeyType.control, '', description: 'Удалить'),
    ]),
  ],
);

/// Базовый экран: 4 × 6, порядок `hVar3` конструктора `g`.
///
/// ```
/// (   )   7   8   9   ÷
/// a/b √2   4   5   6   ×
/// x²  x    1   2   3   −
/// %   π    0   .   =   +
/// ```
PhSheetSpec primarySheet() => PhSheetSpec(
  sheet: PhSheet.primary,
  rowCount: 4,
  columnCount: 6,
  ofFullHeight: 0.33,
  items: [
    PhRow([
      _k(
        'OPERATOR_LEFT_BRACKET',
        PhKeyType.function,
        r'(',
        'Открывающая скобка',
      ),
      _k(
        'OPERATOR_RIGHT_BRACKET',
        PhKeyType.function,
        r')',
        'Закрывающая скобка',
      ),
      _k('DIGIT_SEVEN', PhKeyType.digit, '7', '7'),
      _k('DIGIT_EIGHT', PhKeyType.digit, '8', '8'),
      _k('DIGIT_NINE', PhKeyType.digit, '9', '9'),
      _k('BASIC_INFIX_OPERATOR_DIVIDE', PhKeyType.infix, r'\div', 'Разделить'),
    ]),
    PhRow([
      _k('OPERATOR_FRACTION', PhKeyType.function, r'\frac{a}{b}', 'Дробь'),
      _k('OPERATOR_ROOT_TWO', PhKeyType.function, r'\sqrt{2}', 'Корень'),
      _k('DIGIT_FOUR', PhKeyType.digit, '4', '4'),
      _k('DIGIT_FIVE', PhKeyType.digit, '5', '5'),
      _k('DIGIT_SIX', PhKeyType.digit, '6', '6'),
      _k(
        'BASIC_INFIX_OPERATOR_MULTIPLY',
        PhKeyType.infix,
        r'\times',
        'Умножить',
      ),
    ]),
    PhRow([
      _k('OPERATOR_POWER_TWO', PhKeyType.function, 'x^2', 'Квадрат'),
      _k('VARIABLE_X_LOW', PhKeyType.variable, 'x', 'x'),
      _k('DIGIT_ONE', PhKeyType.digit, '1', '1'),
      _k('DIGIT_TWO', PhKeyType.digit, '2', '2'),
      _k('DIGIT_THREE', PhKeyType.digit, '3', '3'),
      _k('BASIC_INFIX_OPERATOR_MINUS', PhKeyType.infix, '-', 'Вычесть'),
    ]),
    PhRow([
      _k('BASIC_INFIX_OPERATOR_PERCENTAGE', PhKeyType.infix, r'\%', 'Процент'),
      _k('CONSTANT_PI', PhKeyType.constant, r'\pi', 'Пи'),
      _k('DIGIT_ZERO', PhKeyType.digit, '0', '0'),
      _k('DIGIT_DOT', PhKeyType.digit, '.', 'Десятичный разделитель'),
      _k('BASIC_INFIX_OPERATOR_EQUALS', PhKeyType.infix, '=', 'Равно'),
      _k('BASIC_INFIX_OPERATOR_PLUS', PhKeyType.infix, '+', 'Сложить'),
    ]),
  ],
);

/// Расширенный экран: 4 × 6, порядок `hVar` конструктора `g`.
///
/// ```
/// <     >     f(x)   Σ      [ ]    log₁₀
/// ∫    d/dx  ∞      i      sin    cos
/// |x|  nPk   e      °      tan    cot
/// lim  aₙ    !      sign   sec    csc
/// ```
PhSheetSpec secondarySheet() => PhSheetSpec(
  sheet: PhSheet.secondary,
  rowCount: 4,
  columnCount: 6,
  ofFullHeight: 0.33,
  items: [
    PhRow([
      _k('BASIC_INFIX_OPERATOR_LESS_THAN', PhKeyType.infix, '<', 'Меньше'),
      _k('BASIC_INFIX_OPERATOR_GREATER_THAN', PhKeyType.infix, '>', 'Больше'),
      _k('OPERATOR_FUNCTION_F', PhKeyType.function, 'f(x)', 'Функция f(x)'),
      _k('OPERATOR_SIGMA_DEFINITE', PhKeyType.function, r'\sum', 'Сумма'),
      _k('OPERATOR_MATRIX', PhKeyType.intermediate, 'matrix', 'Матрица'),
      _k('OPERATOR_LOG10', PhKeyType.function, r'\log_{10}', 'Логарифм'),
    ]),
    PhRow([
      _k(
        'OPERATOR_INTEGRAL_INDEFINITE',
        PhKeyType.function,
        r'\int',
        'Интеграл',
      ),
      _k(
        'OPERATOR_DERIVATIVE_X',
        PhKeyType.function,
        r'\frac{d}{dx}',
        'Производная',
      ),
      _k('CONSTANT_INFINITY', PhKeyType.constant, r'\infty', 'Бесконечность'),
      _k('CONSTANT_I', PhKeyType.constant, 'i', 'Мнимая единица'),
      _k('OPERATOR_SIN', PhKeyType.function, r'\sin', 'Синус'),
      _k('OPERATOR_COS', PhKeyType.function, r'\cos', 'Косинус'),
    ]),
    PhRow([
      _k('OPERATOR_ABS', PhKeyType.function, r'|x|', 'Модуль'),
      _k(
        'OPERATOR_PARTIAL_PERMUTATION',
        PhKeyType.function,
        r'\binom{n}{k}',
        'Размещений',
      ),
      _k('CONSTANT_E', PhKeyType.constant, 'e', 'Число Эйлера'),
      _k(
        'BASIC_INFIX_OPERATOR_DEGREE',
        PhKeyType.infix,
        r'^{\circ}',
        'Градусы',
      ),
      _k('OPERATOR_TAN', PhKeyType.function, r'\tan', 'Тангенс'),
      _k('OPERATOR_COT', PhKeyType.function, r'\cot', 'Котангенс'),
    ]),
    PhRow([
      _k('OPERATOR_LIMIT', PhKeyType.function, r'\lim', 'Предел'),
      _k(
        'VARIABLE_AN',
        PhKeyType.function,
        'a_{n}',
        'Члены последовательности',
      ),
      _k('BASIC_INFIX_OPERATOR_FACTORIAL', PhKeyType.infix, '!', 'Факториал'),
      _k('OPERATOR_SIGN', PhKeyType.function, r'\operatorname{sign}', 'Знак'),
      _k('OPERATOR_SEC', PhKeyType.function, r'\sec', 'Секанс'),
      _k('OPERATOR_CSC', PhKeyType.function, r'\csc', 'Косеканс'),
    ]),
  ],
);

/// Буквы: 4 × 8, порядок `hVar2` конструктора `g`.
///
/// Ключи идут `a…z`, затем `α β θ`, затем пустые — 35 записей, из которых
/// `GridLayout` рисует только первые 32 (`rowCount × columnCount`).
PhSheetSpec alphabetSheet() => PhSheetSpec(
  sheet: PhSheet.alphabet,
  rowCount: 4,
  columnCount: 8,
  ofFullHeight: 0.33,
  items: [
    PhRow([for (final letter in 'abcdefgh'.split('')) _letter(letter)]),
    PhRow([for (final letter in 'ijklmnop'.split('')) _letter(letter)]),
    PhRow([for (final letter in 'qrstuvwx'.split('')) _letter(letter)]),
    PhRow([
      _letter('y'),
      _letter('z'),
      _greek('VARIABLE_ALPHA', r'\alpha'),
      _greek('VARIABLE_BETA', r'\beta'),
      _greek('VARIABLE_THETA', r'\theta'),
      const PhKey('', PhKeyType.grid, ''),
      const PhKey('', PhKeyType.grid, ''),
      const PhKey('', PhKeyType.grid, ''),
    ]),
  ],
);

PhKey _letter(String letter) => PhKey(
  'VARIABLE_${letter.toUpperCase()}_LOW',
  PhKeyType.variable,
  letter,
  description: letter,
);

PhKey _greek(String code, String latex) =>
    PhKey(code, PhKeyType.variable, latex, description: latex);

/// Все экраны в порядке объявления в оригинале.
List<PhSheetSpec> get sheets => [
  controlSheet(),
  primarySheet(),
  secondarySheet(),
  alphabetSheet(),
];

PhSheetSpec sheetOf(PhSheet sheet) =>
    sheets.firstWhere((spec) => spec.sheet == sheet);

/// Ключи всех экранов по коду оператора — поиск для выпадающих списков.
final Map<String, PhKey> _byCode = {
  for (final spec in sheets)
    for (final key in spec.keys)
      if (key.code.isNotEmpty) key.code: key,
};

PhKey? keyByCode(String code) => _byCode[code];

/// Долгое нажатие — карта `f286c` оригинала.
///
/// Ключ — код оператора, значение — коды клавиш, которые выпадают под ним.
/// Порядок в списках совпадает с порядком `f(n)` + `b(…)` в конструкторе.
const Map<String, List<String>> extensions = {
  'CONSTANT_PI': ['CONSTANT_HALF_PI', 'CONSTANT_THIRD_PI'],
  'BASIC_INFIX_OPERATOR_LESS_THAN': ['BASIC_INFIX_OPERATOR_LESS_THAN_OR_EQUAL'],
  'BASIC_INFIX_OPERATOR_GREATER_THAN': [
    'BASIC_INFIX_OPERATOR_GREATER_THAN_OR_EQUAL',
  ],
  'CONSTANT_E': ['OPERATOR_EXP'],
  'BASIC_INFIX_OPERATOR_DEGREE': ['BASIC_INFIX_OPERATOR_RADIAN'],
  'OPERATOR_INTEGRAL_INDEFINITE': ['OPERATOR_INTEGRAL_DEFINITE'],
  'OPERATOR_DERIVATIVE': [
    'OPERATOR_DERIVATIVE_CUSTOM',
    'OPERATOR_DERIVATIVE_CUSTOM_DEGREE',
  ],
  'OPERATOR_DERIVATIVE_X': [
    'OPERATOR_DERIVATIVE_CUSTOM',
    'OPERATOR_DERIVATIVE_CUSTOM_DEGREE',
  ],
  'OPERATOR_LN': ['OPERATOR_LOG2', 'OPERATOR_LOG'],
  'OPERATOR_LOG10': ['OPERATOR_LN', 'OPERATOR_LOG2', 'OPERATOR_LOG'],
  'OPERATOR_SIN': ['OPERATOR_ASIN', 'OPERATOR_SINH', 'OPERATOR_ASINH'],
  'OPERATOR_COS': ['OPERATOR_ACOS', 'OPERATOR_COSH', 'OPERATOR_ACOSH'],
  'OPERATOR_TAN': ['OPERATOR_ATAN', 'OPERATOR_TANH', 'OPERATOR_ATANH'],
  'OPERATOR_COT': ['OPERATOR_ACOT', 'OPERATOR_COTH', 'OPERATOR_ACOTH'],
  'OPERATOR_SEC': ['OPERATOR_ASEC', 'OPERATOR_SECH', 'OPERATOR_ASECH'],
  'OPERATOR_CSC': ['OPERATOR_ACSC', 'OPERATOR_CSCH', 'OPERATOR_ACSCH'],
  'OPERATOR_CHOOSE': ['OPERATOR_CHOOSE_C', 'OPERATOR_VARIATION'],
  'OPERATOR_FUNCTION_F': ['OPERATOR_FUNCTION_G', 'OPERATOR_FUNCTION'],
  'OPERATOR_LIMIT': ['OPERATOR_LIMIT_LEFT_NODE', 'OPERATOR_LIMIT_RIGHT_NODE'],
  'OPERATOR_FRACTION': ['OPERATOR_FRACTION_MIXED'],
  'OPERATOR_ROOT_TWO': ['OPERATOR_ROOT_THREE', 'OPERATOR_ROOT'],
  'OPERATOR_POWER_TWO': ['OPERATOR_POWER_THREE', 'OPERATOR_POWER'],
  'VARIABLE_X_LOW': ['VARIABLE_Y_LOW', 'VARIABLE_Z_LOW'],
};

/// Клавиши, которых нет на экранах, но которые появляются только в выпадающих
/// списках (`f(n)` + `b(…)` без последующего `a(…)` для своей сетки).
const Map<String, PhKeySpec> extensionKeys = {
  'CONSTANT_HALF_PI': PhKeySpec(
    r'\frac{\pi}{2}',
    PhKeyType.infix,
    'Пи пополам',
  ),
  'CONSTANT_THIRD_PI': PhKeySpec(
    r'\frac{\pi}{3}',
    PhKeyType.infix,
    'Пи на три',
  ),
  'BASIC_INFIX_OPERATOR_LESS_THAN_OR_EQUAL': PhKeySpec(
    r'\leq',
    PhKeyType.infix,
    'Меньше или равно',
  ),
  'BASIC_INFIX_OPERATOR_GREATER_THAN_OR_EQUAL': PhKeySpec(
    r'\geq',
    PhKeyType.infix,
    'Больше или равно',
  ),
  'BASIC_INFIX_OPERATOR_RADIAN': PhKeySpec('rad', PhKeyType.infix, 'Радианы'),
  'BASIC_INFIX_OPERATOR_PLUS_MINUS': PhKeySpec(
    r'\pm',
    PhKeyType.infix,
    'Плюс-минус',
  ),
  'OPERATOR_EXP': PhKeySpec(r'\exp', PhKeyType.function, 'Экспонента'),
  'OPERATOR_INTEGRAL_DEFINITE': PhKeySpec(
    r'\int\limits_a^b',
    PhKeyType.function,
    'Определённый интеграл',
  ),
  'OPERATOR_DERIVATIVE_CUSTOM': PhKeySpec(
    r'\frac{d}{dx}',
    PhKeyType.function,
    'Производная',
  ),
  'OPERATOR_DERIVATIVE_CUSTOM_DEGREE': PhKeySpec(
    r'\frac{d}{d^n x}',
    PhKeyType.function,
    'Производная n-го порядка',
  ),
  'OPERATOR_LN': PhKeySpec(r'\ln', PhKeyType.function, 'Натуральный логарифм'),
  'OPERATOR_LOG2': PhKeySpec(r'\log_2', PhKeyType.function, 'Логарифм по 2'),
  'OPERATOR_LOG': PhKeySpec(r'\log_x', PhKeyType.function, 'Логарифм по x'),
  'OPERATOR_ASIN': PhKeySpec(r'\arcsin', PhKeyType.function, 'Арксинус'),
  'OPERATOR_ASINH': PhKeySpec(
    r'\operatorname{arsinh}',
    PhKeyType.function,
    'Арсинус гиперболический',
  ),
  'OPERATOR_ACOS': PhKeySpec(r'\arccos', PhKeyType.function, 'Арккосинус'),
  'OPERATOR_ACOSH': PhKeySpec(
    r'\operatorname{arcosh}',
    PhKeyType.function,
    'Арккосинус гиперболический',
  ),
  'OPERATOR_ATAN': PhKeySpec(r'\arctan', PhKeyType.function, 'Арктангенс'),
  'OPERATOR_ATANH': PhKeySpec(
    r'\operatorname{artanh}',
    PhKeyType.function,
    'Арктангенс гиперболический',
  ),
  'OPERATOR_ACOT': PhKeySpec(
    r'\operatorname{arccot}',
    PhKeyType.function,
    'Арккотангенс',
  ),
  'OPERATOR_ACOTH': PhKeySpec(
    r'\operatorname{arcoth}',
    PhKeyType.function,
    'Арккотангенс гиперболический',
  ),
  'OPERATOR_ASEC': PhKeySpec(
    r'\operatorname{arcsec}',
    PhKeyType.function,
    'Арксеканс',
  ),
  'OPERATOR_ASECH': PhKeySpec(
    r'\operatorname{arsech}',
    PhKeyType.function,
    'Арксеканс гиперболический',
  ),
  'OPERATOR_ACSC': PhKeySpec(
    r'\operatorname{arccsc}',
    PhKeyType.function,
    'Арккосеканс',
  ),
  'OPERATOR_ACSCH': PhKeySpec(
    r'\operatorname{arcsch}',
    PhKeyType.function,
    'Арккосеканс гиперболический',
  ),
  'OPERATOR_SINH': PhKeySpec(
    r'\sinh',
    PhKeyType.function,
    'Гиперболический синус',
  ),
  'OPERATOR_COSH': PhKeySpec(
    r'\cosh',
    PhKeyType.function,
    'Гиперболический косинус',
  ),
  'OPERATOR_TANH': PhKeySpec(
    r'\tanh',
    PhKeyType.function,
    'Гиперболический тангенс',
  ),
  'OPERATOR_COTH': PhKeySpec(
    r'\coth',
    PhKeyType.function,
    'Гиперболический котангенс',
  ),
  'OPERATOR_SECH': PhKeySpec(
    r'\operatorname{sech}',
    PhKeyType.function,
    'Гиперболический секанс',
  ),
  'OPERATOR_CSCH': PhKeySpec(
    r'\operatorname{csch}',
    PhKeyType.function,
    'Гиперболический косеканс',
  ),
  'OPERATOR_FUNCTION_G': PhKeySpec('g(x)', PhKeyType.function, 'Функция g(x)'),
  'OPERATOR_FUNCTION': PhKeySpec('f(x)', PhKeyType.function, 'Функция f(x)'),
  'OPERATOR_CHOOSE_C': PhKeySpec(
    r'\binom{n}{r}',
    PhKeyType.function,
    'Сочетаний',
  ),
  'OPERATOR_CHOOSE': PhKeySpec(
    r'\frac{n!}{(n-r)!}',
    PhKeyType.function,
    'Размещений',
  ),
  'OPERATOR_VARIATION': PhKeySpec(
    r'A_n^r',
    PhKeyType.function,
    'Размещений без повторов',
  ),
  'OPERATOR_MIXED_FRACTION': PhKeySpec(
    r'1\frac{a}{b}',
    PhKeyType.function,
    'Смешанная дробь',
  ),
  'OPERATOR_FRACTION_MIXED': PhKeySpec(
    r'1\frac{a}{b}',
    PhKeyType.function,
    'Смешанная дробь',
  ),
  'OPERATOR_ROOT_THREE': PhKeySpec(
    r'\sqrt[3]{a}',
    PhKeyType.function,
    'Кубический корень',
  ),
  'OPERATOR_ROOT': PhKeySpec(
    r'\sqrt[n]{a}',
    PhKeyType.function,
    'Корень n-й степени',
  ),
  'OPERATOR_POWER_THREE': PhKeySpec('x^3', PhKeyType.function, 'Куб'),
  'OPERATOR_POWER': PhKeySpec('x^n', PhKeyType.function, 'Степень'),
  'HELPER_SUBSCRIPT': PhKeySpec(
    r'a_{12}',
    PhKeyType.function,
    'Подстрочный индекс',
  ),
  'OPERATOR_LIMIT_LEFT_NODE': PhKeySpec(
    r'\lim^-',
    PhKeyType.function,
    'Предел слева',
  ),
  'OPERATOR_LIMIT_RIGHT_NODE': PhKeySpec(
    r'\lim^+',
    PhKeyType.function,
    'Предел справа',
  ),
};

/// Описание ключа, доступного только в выпадающем списке.
@immutable
class PhKeySpec {
  const PhKeySpec(this.glyph, this.type, this.description);

  final String glyph;
  final PhKeyType type;
  final String description;
}

/// Ключ для показа в выпадающем списке: сетка или словарик `extensionKeys`.
///
/// Длинные имена берутся короткими (`g.e`) — в шестиколоночной сетке
/// оригинала `arcsin` не помещается, поэтому там написано `asin`.
PhKey extensionKey(String code) {
  final known = keyByCode(code);
  if (known != null) return known;
  final spec = extensionKeys[code];
  if (spec == null) {
    return PhKey(code, PhKeyType.function, '', description: code);
  }
  return PhKey(
    code,
    spec.type,
    _shortLabels[code] ?? spec.glyph,
    description: spec.description,
  );
}

/// Выпадающий список долгого нажатия для кода оператора.
List<PhKey> extensionsOf(String code) => [
  for (final child in extensions[code] ?? const <String>[]) extensionKey(child),
];

/// Заливка клавиши по типу — `c.a.a.a.t.a.e.a` оригинала.
///
/// В оригинале цвет берётся из `backgroundTint` клавиши, а сама клавиша —
/// это прямоугольник со скруглением 2dip (`drawable/keyboard_button_background`).
Color keyBackground(PhKeyType type) => switch (type) {
  PhKeyType.control => PhColor.keyboardBackground,
  PhKeyType.function => PhColor.keyboardFunction,
  PhKeyType.returnHelper => PhColor.keyboardReturnHelper,
  _ => PhColor.keyboardNumeric,
};
