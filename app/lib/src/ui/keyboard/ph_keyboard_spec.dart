/// Клавиатура: ключи, экраны и раскладка.
///
/// * **тип ключа** задаёт заливку клавиши: цифры, константы, переменные,
///   плоские знаки и вспомогательные — белые, функции — `#E0E0E0`, служебные —
///   `#F0F0F0`, клавиша возврата — `#CBCCCD`;
/// * **раскладка** — четыре экрана (служебный ряд 1×6, базовый 4×6, функции
///   4×6, буквы 4×8), ключи идут построчно (`child = cols * row + col`);
/// * **долгое нажатие** — у `π` выпадают `π/2` и `π/3`, у `x` — `y` и `z`,
///   у `√` — `∛` и `ⁿ√`, у `x²` — `x³` и `xⁿ`, у `ln` — `log₂` и `logₓ`,
///   у `d/dx` — производная произвольного порядка и т. д.;
/// * **подписи** — математические символы, нарисованные тем же наборщиком
///   формул, что и результат; длинные имена в выпадающих списках
///   сокращаются (`asin` вместо `arcsin`).
library;

import 'package:flutter/material.dart';

import '../../editor/keyboard.dart';
import '../../editor/operators.dart';
import '../../theme/palette.dart';
import '../../i18n.dart';

/// Тип ключа: от него зависит заливка клавиши.
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

  /// `GRID` — зарезервированный тип.
  grid,
}

/// Экран клавиатуры.
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

/// Один ключ.
@immutable
class PhKey {
  const PhKey(this.code, this.type, this.glyph, {this.description = ''});

  /// Код оператора редактора (`OPERATOR_*`, `DIGIT_*`, …).
  ///
  /// По нему же `operators.dart` находит действие редактора, поэтому
  /// клавиатура и каталог операторов не расходятся.
  final String code;

  /// Тип ключа — определяет заливку.
  final PhKeyType type;

  /// Подпись в LaTeX без `$…$`.
  final String glyph;

  /// Словесная подпись для подсказки и для экранного диктора.
  final String description;

  /// Действие клавиши; `null`, если оператор не поддержан
  /// решателем (см. `_unsupported` в `operators.dart`).
  MathKey? get action => bindOperator(code).key;
}

/// Ряд ключей.
@immutable
class PhRow {
  const PhRow(this.keys);

  final List<PhKey> keys;
}

/// Экран ключей: `a` — число рядов, `b` — ключей в ряду.
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
  items: [
    PhRow([
      PhKey(
        'HELPER_SHOW_SECONDARY_SHEET',
        PhKeyType.control,
        r'f\ \int\ <\ >',
        description: tr('Расширенная панель', 'More functions'),
      ),
      PhKey(
        'HELPER_XYZ_SHEET',
        PhKeyType.control,
        'abc',
        description: tr('Буквы', 'Letters'),
      ),
      PhKey(
        'CONTROL_MOVE_LEFT',
        PhKeyType.control,
        '',
        description: tr('Курсор влево', 'Cursor left'),
      ),
      PhKey(
        'CONTROL_MOVE_RIGHT',
        PhKeyType.control,
        '',
        description: tr('Курсор вправо', 'Cursor right'),
      ),
      PhKey(
        'CONTROL_NEW_LINE',
        PhKeyType.control,
        '',
        description: tr('Новая строка', 'New line'),
      ),
      PhKey(
        'CONTROL_DELETE',
        PhKeyType.control,
        '',
        description: tr('Удалить', 'Delete'),
      ),
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
        tr('Открывающая скобка', 'Opening bracket'),
      ),
      _k(
        'OPERATOR_RIGHT_BRACKET',
        PhKeyType.function,
        r')',
        tr('Закрывающая скобка', 'Closing bracket'),
      ),
      _k('DIGIT_SEVEN', PhKeyType.digit, '7', '7'),
      _k('DIGIT_EIGHT', PhKeyType.digit, '8', '8'),
      _k('DIGIT_NINE', PhKeyType.digit, '9', '9'),
      _k(
        'BASIC_INFIX_OPERATOR_DIVIDE',
        PhKeyType.infix,
        r'\div',
        tr('Разделить', 'Divide'),
      ),
    ]),
    PhRow([
      _k(
        'OPERATOR_FRACTION',
        PhKeyType.function,
        r'\frac{\square}{\square}',
        tr('Дробь', 'Fraction'),
      ),
      _k(
        'OPERATOR_ROOT_TWO',
        PhKeyType.function,
        r'\sqrt{\square}',
        tr('Корень', 'Square root'),
      ),
      _k('DIGIT_FOUR', PhKeyType.digit, '4', '4'),
      _k('DIGIT_FIVE', PhKeyType.digit, '5', '5'),
      _k('DIGIT_SIX', PhKeyType.digit, '6', '6'),
      _k(
        'BASIC_INFIX_OPERATOR_MULTIPLY',
        PhKeyType.infix,
        r'\times',
        tr('Умножить', 'Multiply'),
      ),
    ]),
    PhRow([
      _k(
        'OPERATOR_POWER_TWO',
        PhKeyType.function,
        r'\square^2',
        tr('Квадрат', 'Square'),
      ),
      _k('VARIABLE_X_LOW', PhKeyType.variable, 'x', 'x'),
      _k('DIGIT_ONE', PhKeyType.digit, '1', '1'),
      _k('DIGIT_TWO', PhKeyType.digit, '2', '2'),
      _k('DIGIT_THREE', PhKeyType.digit, '3', '3'),
      _k(
        'BASIC_INFIX_OPERATOR_MINUS',
        PhKeyType.infix,
        '-',
        tr('Вычесть', 'Subtract'),
      ),
    ]),
    PhRow([
      _k(
        'BASIC_INFIX_OPERATOR_PERCENTAGE',
        PhKeyType.infix,
        r'\%',
        tr('Процент', 'Percent'),
      ),
      _k('CONSTANT_PI', PhKeyType.constant, r'\pi', tr('Пи', 'Pi')),
      _k('DIGIT_ZERO', PhKeyType.digit, '0', '0'),
      _k(
        'DIGIT_DOT',
        PhKeyType.digit,
        '.',
        tr('Десятичный разделитель', 'Decimal separator'),
      ),
      _k(
        'BASIC_INFIX_OPERATOR_EQUALS',
        PhKeyType.infix,
        '=',
        tr('Равно', 'Equals'),
      ),
      _k(
        'BASIC_INFIX_OPERATOR_PLUS',
        PhKeyType.infix,
        '+',
        tr('Сложить', 'Add'),
      ),
    ]),
  ],
);

/// Расширенный экран: 4 × 6, порядок `hVar` конструктора `g`.
///
/// ```
/// <     >     f(x)   Σ      [ ]    |…|   log₁₀
/// ∫    d/dx  y′    ∞      i      sin     cos
/// |x|  nPk   e      °      tan    cot
/// lim  aₙ    !      sign   sec    csc
/// ```
///
/// Клавиша «Определитель» стоит сразу за «Матрицей» и открывает тот же диалог
/// размера, но квадратный (2…5). «Штрих» (`y′`) нужен решателю для `y′`/`y″`
/// и стоит рядом с «Производной». Сетка телефона переносит ряды сама (`GridView`),
/// поэтому лишняя клавиша никого не сдвигает.
PhSheetSpec secondarySheet() => PhSheetSpec(
  sheet: PhSheet.secondary,
  rowCount: 4,
  columnCount: 6,
  ofFullHeight: 0.33,
  items: [
    PhRow([
      _k(
        'BASIC_INFIX_OPERATOR_LESS_THAN',
        PhKeyType.infix,
        '<',
        tr('Меньше', 'Less than'),
      ),
      _k(
        'BASIC_INFIX_OPERATOR_GREATER_THAN',
        PhKeyType.infix,
        '>',
        tr('Больше', 'Greater than'),
      ),
      _k(
        'OPERATOR_FUNCTION_F',
        PhKeyType.function,
        'f(x)',
        tr('Функция f(x)', 'Function f(x)'),
      ),
      _k(
        'OPERATOR_SIGMA_DEFINITE',
        PhKeyType.function,
        r'\sum_{x=\square}^{\square}\square',
        tr(
          'Сумма: начало, конец, слагаемое',
          'Sum: lower bound, upper bound, term',
        ),
      ),
      _k(
        'OPERATOR_MATRIX',
        PhKeyType.intermediate,
        r'\begin{bmatrix}\square&\square\\\square&\square\end{bmatrix}',
        tr('Матрица', 'Matrix'),
      ),
      _k(
        'OPERATOR_DETERMINANT',
        PhKeyType.intermediate,
        r'\begin{vmatrix}\square&\square\\\square&\square\end{vmatrix}',
        tr('Определитель', 'Determinant'),
      ),
      _k(
        'OPERATOR_LOG10',
        PhKeyType.function,
        r'\log_{10}',
        tr('Логарифм', 'Logarithm'),
      ),
    ]),
    PhRow([
      _k(
        'OPERATOR_INTEGRAL_INDEFINITE',
        PhKeyType.function,
        r'\int',
        tr('Интеграл', 'Integral'),
      ),
      _k(
        'OPERATOR_DERIVATIVE_X',
        PhKeyType.function,
        r'\frac{d}{dx}',
        tr('Производная', 'Derivative'),
      ),
      // Tooltip: «Штрих» (ru) / «Prime» (en); на экране — □′.
      _k(
        'OPERATOR_PRIME',
        PhKeyType.function,
        r"\square'",
        tr('Штрих', 'Prime'),
      ),
      _k(
        'CONSTANT_INFINITY',
        PhKeyType.constant,
        r'\infty',
        tr('Бесконечность', 'Infinity'),
      ),
      _k(
        'CONSTANT_I',
        PhKeyType.constant,
        'i',
        tr('Мнимая единица', 'Imaginary unit'),
      ),
      _k('OPERATOR_SIN', PhKeyType.function, r'\sin', tr('Синус', 'Sine')),
      _k('OPERATOR_COS', PhKeyType.function, r'\cos', tr('Косинус', 'Cosine')),
    ]),
    PhRow([
      _k(
        'OPERATOR_ABS',
        PhKeyType.function,
        r'|\square|',
        tr('Модуль', 'Absolute value'),
      ),
      _k(
        'OPERATOR_PARTIAL_PERMUTATION',
        PhKeyType.function,
        r'\binom{\square}{\square}',
        tr('Размещений', 'Permutations'),
      ),
      _k(
        'CONSTANT_E',
        PhKeyType.constant,
        'e',
        tr('Число Эйлера', 'Euler\'s number'),
      ),
      _k(
        'BASIC_INFIX_OPERATOR_DEGREE',
        PhKeyType.infix,
        r'^{\circ}',
        tr('Градусы', 'Degrees'),
      ),
      _k('OPERATOR_TAN', PhKeyType.function, r'\tan', tr('Тангенс', 'Tangent')),
      _k(
        'OPERATOR_COT',
        PhKeyType.function,
        r'\cot',
        tr('Котангенс', 'Cotangent'),
      ),
    ]),
    PhRow([
      _k('OPERATOR_LIMIT', PhKeyType.function, r'\lim', tr('Предел', 'Limit')),
      _k(
        'VARIABLE_AN',
        PhKeyType.function,
        r'a_{\square}',
        tr('Члены последовательности', 'Sequence terms'),
      ),
      _k(
        'BASIC_INFIX_OPERATOR_FACTORIAL',
        PhKeyType.infix,
        '!',
        tr('Факториал', 'Factorial'),
      ),
      _k(
        'OPERATOR_SIGN',
        PhKeyType.function,
        r'\operatorname{sign}',
        tr('Знак', 'Sign'),
      ),
      _k('OPERATOR_SEC', PhKeyType.function, r'\sec', tr('Секанс', 'Secant')),
      _k(
        'OPERATOR_CSC',
        PhKeyType.function,
        r'\csc',
        tr('Косеканс', 'Cosecant'),
      ),
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

/// Все экраны по порядку.
List<PhSheetSpec> get sheets => [
  controlSheet(),
  primarySheet(),
  secondarySheet(),
  alphabetSheet(),
];

PhSheetSpec sheetOf(PhSheet sheet) =>
    sheets.firstWhere((spec) => spec.sheet == sheet);

/// Ключи всех экранов по коду оператора — поиск для выпадающих списков.
Map<String, PhKey> get _byCode => {
  for (final spec in sheets)
    for (final key in spec.keys)
      if (key.code.isNotEmpty) key.code: key,
};

PhKey? keyByCode(String code) => _byCode[code];

/// Долгое нажатие: ключ — код оператора, значение — коды клавиш, которые
/// выпадают под ним, по порядку.
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
Map<String, PhKeySpec> get extensionKeys => {
  'CONSTANT_HALF_PI': PhKeySpec(
    r'\frac{\pi}{2}',
    PhKeyType.infix,
    tr('Пи пополам', 'Half pi'),
  ),
  'CONSTANT_THIRD_PI': PhKeySpec(
    r'\frac{\pi}{3}',
    PhKeyType.infix,
    tr('Пи на три', 'Pi over 3'),
  ),
  'BASIC_INFIX_OPERATOR_LESS_THAN_OR_EQUAL': PhKeySpec(
    r'\leq',
    PhKeyType.infix,
    tr('Меньше или равно', 'Less than or equal'),
  ),
  'BASIC_INFIX_OPERATOR_GREATER_THAN_OR_EQUAL': PhKeySpec(
    r'\geq',
    PhKeyType.infix,
    tr('Больше или равно', 'Greater than or equal'),
  ),
  'BASIC_INFIX_OPERATOR_RADIAN': PhKeySpec(
    'rad',
    PhKeyType.infix,
    tr('Радианы', 'Radians'),
  ),
  'BASIC_INFIX_OPERATOR_PLUS_MINUS': PhKeySpec(
    r'\pm',
    PhKeyType.infix,
    tr('Плюс-минус', 'Plus-minus'),
  ),
  'OPERATOR_EXP': PhKeySpec(
    r'\exp',
    PhKeyType.function,
    tr('Экспонента', 'Exponential'),
  ),
  'OPERATOR_INTEGRAL_DEFINITE': PhKeySpec(
    r'\int\limits_{\square}^{\square}',
    PhKeyType.function,
    tr('Определённый интеграл', 'Definite integral'),
  ),
  'OPERATOR_DERIVATIVE_CUSTOM': PhKeySpec(
    r'\frac{d}{dx}',
    PhKeyType.function,
    tr('Производная', 'Derivative'),
  ),
  'OPERATOR_DERIVATIVE_CUSTOM_DEGREE': PhKeySpec(
    r'\frac{d^{\square}}{d\square^{\square}}',
    PhKeyType.function,
    tr('Производная n-го порядка', 'Nth derivative'),
  ),
  'OPERATOR_LN': PhKeySpec(
    r'\ln',
    PhKeyType.function,
    tr('Натуральный логарифм', 'Natural logarithm'),
  ),
  'OPERATOR_LOG2': PhKeySpec(
    r'\log_2',
    PhKeyType.function,
    tr('Логарифм по 2', 'Logarithm base 2'),
  ),
  'OPERATOR_LOG': PhKeySpec(
    r'\log_{\square}',
    PhKeyType.function,
    tr('Логарифм по x', 'Logarithm base x'),
  ),
  'OPERATOR_ASIN': PhKeySpec(
    r'\arcsin',
    PhKeyType.function,
    tr('Арксинус', 'Arcsine'),
  ),
  'OPERATOR_ASINH': PhKeySpec(
    r'\operatorname{arsinh}',
    PhKeyType.function,
    tr('Арсинус гиперболический', 'Inverse hyperbolic sine'),
  ),
  'OPERATOR_ACOS': PhKeySpec(
    r'\arccos',
    PhKeyType.function,
    tr('Арккосинус', 'Arccosine'),
  ),
  'OPERATOR_ACOSH': PhKeySpec(
    r'\operatorname{arcosh}',
    PhKeyType.function,
    tr('Арккосинус гиперболический', 'Inverse hyperbolic cosine'),
  ),
  'OPERATOR_ATAN': PhKeySpec(
    r'\arctan',
    PhKeyType.function,
    tr('Арктангенс', 'Arctangent'),
  ),
  'OPERATOR_ATANH': PhKeySpec(
    r'\operatorname{artanh}',
    PhKeyType.function,
    tr('Арктангенс гиперболический', 'Inverse hyperbolic tangent'),
  ),
  'OPERATOR_ACOT': PhKeySpec(
    r'\operatorname{arccot}',
    PhKeyType.function,
    tr('Арккотангенс', 'Arccotangent'),
  ),
  'OPERATOR_ACOTH': PhKeySpec(
    r'\operatorname{arcoth}',
    PhKeyType.function,
    tr('Арккотангенс гиперболический', 'Inverse hyperbolic cotangent'),
  ),
  'OPERATOR_ASEC': PhKeySpec(
    r'\operatorname{arcsec}',
    PhKeyType.function,
    tr('Арксеканс', 'Arcsecant'),
  ),
  'OPERATOR_ASECH': PhKeySpec(
    r'\operatorname{arsech}',
    PhKeyType.function,
    tr('Арксеканс гиперболический', 'Inverse hyperbolic secant'),
  ),
  'OPERATOR_ACSC': PhKeySpec(
    r'\operatorname{arccsc}',
    PhKeyType.function,
    tr('Арккосеканс', 'Arccosecant'),
  ),
  'OPERATOR_ACSCH': PhKeySpec(
    r'\operatorname{arcsch}',
    PhKeyType.function,
    tr('Арккосеканс гиперболический', 'Inverse hyperbolic cosecant'),
  ),
  'OPERATOR_SINH': PhKeySpec(
    r'\sinh',
    PhKeyType.function,
    tr('Гиперболический синус', 'Hyperbolic sine'),
  ),
  'OPERATOR_COSH': PhKeySpec(
    r'\cosh',
    PhKeyType.function,
    tr('Гиперболический косинус', 'Hyperbolic cosine'),
  ),
  'OPERATOR_TANH': PhKeySpec(
    r'\tanh',
    PhKeyType.function,
    tr('Гиперболический тангенс', 'Hyperbolic tangent'),
  ),
  'OPERATOR_COTH': PhKeySpec(
    r'\coth',
    PhKeyType.function,
    tr('Гиперболический котангенс', 'Hyperbolic cotangent'),
  ),
  'OPERATOR_SECH': PhKeySpec(
    r'\operatorname{sech}',
    PhKeyType.function,
    tr('Гиперболический секанс', 'Hyperbolic secant'),
  ),
  'OPERATOR_CSCH': PhKeySpec(
    r'\operatorname{csch}',
    PhKeyType.function,
    tr('Гиперболический косеканс', 'Hyperbolic cosecant'),
  ),
  'OPERATOR_FUNCTION_G': PhKeySpec(
    'g(x)',
    PhKeyType.function,
    tr('Функция g(x)', 'Function g(x)'),
  ),
  'OPERATOR_FUNCTION': PhKeySpec(
    'f(x)',
    PhKeyType.function,
    tr('Функция f(x)', 'Function f(x)'),
  ),
  'OPERATOR_CHOOSE_C': PhKeySpec(
    r'\binom{\square}{\square}',
    PhKeyType.function,
    tr('Сочетаний', 'Combinations'),
  ),
  'OPERATOR_CHOOSE': PhKeySpec(
    r'\frac{\square!}{(\square-\square)!}',
    PhKeyType.function,
    tr('Размещений', 'Permutations'),
  ),
  'OPERATOR_VARIATION': PhKeySpec(
    r'A_{\square}^{\square}',
    PhKeyType.function,
    tr('Размещений без повторов', 'Permutations without repetition'),
  ),
  'OPERATOR_MIXED_FRACTION': PhKeySpec(
    r'\square\frac{\square}{\square}',
    PhKeyType.function,
    tr('Смешанная дробь', 'Mixed fraction'),
  ),
  'OPERATOR_FRACTION_MIXED': PhKeySpec(
    r'\square\frac{\square}{\square}',
    PhKeyType.function,
    tr('Смешанная дробь', 'Mixed fraction'),
  ),
  'OPERATOR_ROOT_THREE': PhKeySpec(
    r'\sqrt[3]{\square}',
    PhKeyType.function,
    tr('Кубический корень', 'Cube root'),
  ),
  'OPERATOR_ROOT': PhKeySpec(
    r'\sqrt[\square]{\square}',
    PhKeyType.function,
    tr('Корень n-й степени', 'Nth root'),
  ),
  'OPERATOR_POWER_THREE': PhKeySpec(
    r'\square^3',
    PhKeyType.function,
    tr('Куб', 'Cube'),
  ),
  'OPERATOR_POWER': PhKeySpec(
    r'\square^{\square}',
    PhKeyType.function,
    tr('Степень', 'Power'),
  ),
  'HELPER_SUBSCRIPT': PhKeySpec(
    r'\square_{\square}',
    PhKeyType.function,
    tr('Подстрочный индекс', 'Subscript'),
  ),
  'OPERATOR_LIMIT_LEFT_NODE': PhKeySpec(
    r'\lim^-',
    PhKeyType.function,
    tr('Предел слева', 'Left-hand limit'),
  ),
  'OPERATOR_LIMIT_RIGHT_NODE': PhKeySpec(
    r'\lim^+',
    PhKeyType.function,
    tr('Предел справа', 'Right-hand limit'),
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
/// Длинные имена берутся короткими: в шестиколоночной сетке `arcsin` не
/// помещается, поэтому там написано `asin`.
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

/// Заливка клавиши по типу; сама клавиша — прямоугольник со скруглением 2dp.
Color keyBackground(PhKeyType type) => switch (type) {
  PhKeyType.control => PhColor.keyboardBackground,
  PhKeyType.function => PhColor.keyboardFunction,
  PhKeyType.returnHelper => PhColor.keyboardReturnHelper,
  _ => PhColor.keyboardNumeric,
};
