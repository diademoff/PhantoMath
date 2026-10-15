/// Каталог операторов редактора — все 128 значений `editor_operators` из APK.
///
/// Полный перечень взят из `truth/data/enums.json` (`editor_operators`).
/// Каждый оператор сопоставлен действию редактора (`MathKey`) либо помечен
/// недоступным с причиной: наш решатель поддерживает не все узлы оригинала
/// (`FUNCTION`, `ADD_SUBTRACT`, подстрочные индексы, многострочный ввод).
///
/// Каталог — источник истины о покрытии клавиатуры: тест
/// `test/operators_test.dart` проверяет, что перечислены ровно 128 операторов
/// и что у каждого есть либо действие, либо причина недоступности.
library;

import 'keyboard.dart';
import 'kind.dart';

/// Все `editor_operators` APK в исходном порядке.
const List<String> apkEditorOperators = [
  'CONTROL_NEW_LINE',
  'CONTROL_MOVE_LEFT',
  'CONTROL_MOVE_RIGHT',
  'CONTROL_DELETE',
  'CONTROL_EMPTY',
  'DIGIT_ONE',
  'DIGIT_TWO',
  'DIGIT_THREE',
  'DIGIT_FOUR',
  'DIGIT_FIVE',
  'DIGIT_SIX',
  'DIGIT_SEVEN',
  'DIGIT_EIGHT',
  'DIGIT_NINE',
  'DIGIT_ZERO',
  'DIGIT_DOT',
  'BASIC_INFIX_OPERATOR_PLUS',
  'BASIC_INFIX_OPERATOR_MINUS',
  'BASIC_INFIX_OPERATOR_MULTIPLY',
  'BASIC_INFIX_OPERATOR_DIVIDE',
  'BASIC_INFIX_OPERATOR_EQUALS',
  'BASIC_INFIX_OPERATOR_PLUS_MINUS',
  'BASIC_INFIX_OPERATOR_LESS_THAN',
  'BASIC_INFIX_OPERATOR_LESS_THAN_OR_EQUAL',
  'BASIC_INFIX_OPERATOR_GREATER_THAN',
  'BASIC_INFIX_OPERATOR_GREATER_THAN_OR_EQUAL',
  'BASIC_INFIX_OPERATOR_FACTORIAL',
  'BASIC_INFIX_OPERATOR_DEGREE',
  'BASIC_INFIX_OPERATOR_RADIAN',
  'BASIC_INFIX_OPERATOR_PERCENTAGE',
  'OPERATOR_LEFT_BRACKET',
  'OPERATOR_RIGHT_BRACKET',
  'OPERATOR_FRACTION',
  'OPERATOR_FRACTION_MIXED',
  'OPERATOR_POWER',
  'OPERATOR_POWER_TWO',
  'OPERATOR_POWER_THREE',
  'OPERATOR_ROOT',
  'OPERATOR_ROOT_TWO',
  'OPERATOR_ROOT_THREE',
  'OPERATOR_CHOOSE',
  'OPERATOR_CHOOSE_C',
  'OPERATOR_PARTIAL_PERMUTATION',
  'OPERATOR_VARIATION',
  'OPERATOR_FUNCTION',
  'OPERATOR_FUNCTION_F',
  'OPERATOR_FUNCTION_G',
  'OPERATOR_MATRIX',
  'OPERATOR_DETERMINANT',
  'OPERATOR_ABS',
  'OPERATOR_COT',
  'OPERATOR_TAN',
  'OPERATOR_COS',
  'OPERATOR_SIN',
  'OPERATOR_DERIVATIVE',
  'OPERATOR_DERIVATIVE_X',
  'OPERATOR_DERIVATIVE_CUSTOM_DEGREE',
  'OPERATOR_INTEGRAL_INDEFINITE',
  'OPERATOR_INTEGRAL_DEFINITE',
  'OPERATOR_LIMIT',
  'OPERATOR_LIMIT_LEFT_NODE',
  'OPERATOR_LIMIT_RIGHT_NODE',
  'OPERATOR_SIGMA_DEFINITE',
  'OPERATOR_SINH',
  'OPERATOR_COSH',
  'OPERATOR_TANH',
  'OPERATOR_COTH',
  'OPERATOR_EXP',
  'OPERATOR_SIGN',
  'OPERATOR_LN',
  'OPERATOR_LOG10',
  'OPERATOR_LOG2',
  'OPERATOR_LOG',
  'OPERATOR_ACOTH',
  'OPERATOR_ATANH',
  'OPERATOR_ACOSH',
  'OPERATOR_ASINH',
  'OPERATOR_ACOT',
  'OPERATOR_ATAN',
  'OPERATOR_ACOS',
  'OPERATOR_ASIN',
  'OPERATOR_SEC',
  'OPERATOR_CSC',
  'OPERATOR_ASEC',
  'OPERATOR_ACSC',
  'OPERATOR_SECH',
  'OPERATOR_CSCH',
  'OPERATOR_ASECH',
  'OPERATOR_ACSCH',
  'VARIABLE_X_LOW',
  'VARIABLE_Y_LOW',
  'VARIABLE_Z_LOW',
  'CONSTANT_PI',
  'CONSTANT_HALF_PI',
  'CONSTANT_THIRD_PI',
  'CONSTANT_INFINITY',
  'HELPER_XYZ_SHEET',
  'HELPER_SHOW_SECONDARY_SHEET',
  'HELPER_SUBSCRIPT',
  'VARIABLE_A_LOW',
  'VARIABLE_B_LOW',
  'VARIABLE_C_LOW',
  'VARIABLE_D_LOW',
  'CONSTANT_E',
  'VARIABLE_E_LOW',
  'VARIABLE_F_LOW',
  'VARIABLE_G_LOW',
  'VARIABLE_H_LOW',
  'CONSTANT_I',
  'VARIABLE_I_LOW',
  'VARIABLE_J_LOW',
  'VARIABLE_K_LOW',
  'VARIABLE_L_LOW',
  'VARIABLE_M_LOW',
  'VARIABLE_N_LOW',
  'VARIABLE_O_LOW',
  'VARIABLE_P_LOW',
  'VARIABLE_Q_LOW',
  'VARIABLE_R_LOW',
  'VARIABLE_S_LOW',
  'VARIABLE_T_LOW',
  'VARIABLE_U_LOW',
  'VARIABLE_V_LOW',
  'VARIABLE_W_LOW',
  'VARIABLE_ALPHA',
  'VARIABLE_BETA',
  'VARIABLE_THETA',
  'VARIABLE_AN',
];

/// Оператор APK и действие редактора (или причина недоступности).
class OperatorBinding {
  const OperatorBinding(this.name, {this.key, this.reason});

  /// Имя оператора из `editor_operators`.
  final String name;

  /// Действие клавиши; `null`, если оператор не поддержан.
  final MathKey? key;

  /// Причина недоступности (для интерфейса и отчёта о покрытии).
  final String? reason;

  /// Доступен ли оператор в редакторе.
  bool get available => key != null;
}

const Map<String, String> _digits = {
  'DIGIT_ZERO': '0',
  'DIGIT_ONE': '1',
  'DIGIT_TWO': '2',
  'DIGIT_THREE': '3',
  'DIGIT_FOUR': '4',
  'DIGIT_FIVE': '5',
  'DIGIT_SIX': '6',
  'DIGIT_SEVEN': '7',
  'DIGIT_EIGHT': '8',
  'DIGIT_NINE': '9',
  'DIGIT_DOT': '.',
};

const Map<String, String> _variables = {
  'VARIABLE_X_LOW': 'x',
  'VARIABLE_Y_LOW': 'y',
  'VARIABLE_Z_LOW': 'z',
  'VARIABLE_A_LOW': 'a',
  'VARIABLE_B_LOW': 'b',
  'VARIABLE_C_LOW': 'c',
  'VARIABLE_D_LOW': 'd',
  'VARIABLE_E_LOW': 'e',
  'VARIABLE_F_LOW': 'f',
  'VARIABLE_G_LOW': 'g',
  'VARIABLE_H_LOW': 'h',
  'VARIABLE_I_LOW': 'i',
  'VARIABLE_J_LOW': 'j',
  'VARIABLE_K_LOW': 'k',
  'VARIABLE_L_LOW': 'l',
  'VARIABLE_M_LOW': 'm',
  'VARIABLE_N_LOW': 'n',
  'VARIABLE_O_LOW': 'o',
  'VARIABLE_P_LOW': 'p',
  'VARIABLE_Q_LOW': 'q',
  'VARIABLE_R_LOW': 'r',
  'VARIABLE_S_LOW': 's',
  'VARIABLE_T_LOW': 't',
  'VARIABLE_U_LOW': 'u',
  'VARIABLE_V_LOW': 'v',
  'VARIABLE_W_LOW': 'w',
  'VARIABLE_ALPHA': r'\alpha',
  'VARIABLE_BETA': r'\beta',
  'VARIABLE_THETA': r'\theta',
};

const Map<String, String> _constants = {
  'CONSTANT_PI': 'π',
  'CONSTANT_INFINITY': '∞',
  'CONSTANT_E': 'e',
  'CONSTANT_I': 'i',
};

/// Операторы-шаблоны (`OPERATOR_*`) → вид редактора.
final Map<String, ENodeKind> _templates = {
  'OPERATOR_LEFT_BRACKET': ENodeKind.bracket,
  'OPERATOR_RIGHT_BRACKET': ENodeKind.bracket,
  'OPERATOR_FRACTION': ENodeKind.fraction,
  'OPERATOR_FRACTION_MIXED': ENodeKind.mixedFraction,
  'OPERATOR_POWER': ENodeKind.power,
  'OPERATOR_POWER_TWO': ENodeKind.powerTwo,
  'OPERATOR_POWER_THREE': ENodeKind.powerThree,
  'OPERATOR_ROOT': ENodeKind.rootN,
  'OPERATOR_ROOT_TWO': ENodeKind.root2,
  'OPERATOR_ROOT_THREE': ENodeKind.rootThree,
  'OPERATOR_CHOOSE': ENodeKind.choose,
  'OPERATOR_CHOOSE_C': ENodeKind.choose,
  'OPERATOR_PARTIAL_PERMUTATION': ENodeKind.permutation,
  'OPERATOR_VARIATION': ENodeKind.variation,
  'OPERATOR_MATRIX': ENodeKind.matrix2,
  'OPERATOR_DETERMINANT': ENodeKind.determinant2,
  'OPERATOR_ABS': ENodeKind.abs,
  'OPERATOR_COT': ENodeKind.cot,
  'OPERATOR_TAN': ENodeKind.tan,
  'OPERATOR_COS': ENodeKind.cos,
  'OPERATOR_SIN': ENodeKind.sin,
  'OPERATOR_DERIVATIVE': ENodeKind.derivative,
  'OPERATOR_DERIVATIVE_X': ENodeKind.derivative,
  'OPERATOR_DERIVATIVE_CUSTOM_DEGREE': ENodeKind.derivative,
  'OPERATOR_INTEGRAL_INDEFINITE': ENodeKind.integral,
  'OPERATOR_INTEGRAL_DEFINITE': ENodeKind.integralDefinite,
  'OPERATOR_LIMIT': ENodeKind.limit,
  'OPERATOR_LIMIT_LEFT_NODE': ENodeKind.limit,
  'OPERATOR_LIMIT_RIGHT_NODE': ENodeKind.limit,
  'OPERATOR_SIGMA_DEFINITE': ENodeKind.sigma,
  'OPERATOR_SINH': ENodeKind.sinh,
  'OPERATOR_COSH': ENodeKind.cosh,
  'OPERATOR_TANH': ENodeKind.tanh,
  'OPERATOR_COTH': ENodeKind.coth,
  'OPERATOR_EXP': ENodeKind.exp,
  'OPERATOR_SIGN': ENodeKind.sign,
  'OPERATOR_LN': ENodeKind.ln,
  'OPERATOR_LOG10': ENodeKind.log10,
  'OPERATOR_LOG2': ENodeKind.log2,
  'OPERATOR_LOG': ENodeKind.log,
  'OPERATOR_ACOTH': ENodeKind.acoth,
  'OPERATOR_ATANH': ENodeKind.atanh,
  'OPERATOR_ACOSH': ENodeKind.acosh,
  'OPERATOR_ASINH': ENodeKind.asinh,
  'OPERATOR_ACOT': ENodeKind.acot,
  'OPERATOR_ATAN': ENodeKind.atan,
  'OPERATOR_ACOS': ENodeKind.acos,
  'OPERATOR_ASIN': ENodeKind.asin,
  'OPERATOR_SEC': ENodeKind.sec,
  'OPERATOR_CSC': ENodeKind.csc,
  'OPERATOR_ASEC': ENodeKind.asec,
  'OPERATOR_ACSC': ENodeKind.acsc,
  'OPERATOR_SECH': ENodeKind.sech,
  'OPERATOR_CSCH': ENodeKind.csch,
  'OPERATOR_ASECH': ENodeKind.asech,
  'OPERATOR_ACSCH': ENodeKind.acsch,
};

/// Операторы-знаки (`BASIC_INFIX_OPERATOR_*`) → вид редактора.
final Map<String, ENodeKind> _infix = {
  'BASIC_INFIX_OPERATOR_PLUS': ENodeKind.add,
  'BASIC_INFIX_OPERATOR_MINUS': ENodeKind.subtract,
  'BASIC_INFIX_OPERATOR_MULTIPLY': ENodeKind.multiply,
  'BASIC_INFIX_OPERATOR_DIVIDE': ENodeKind.divide,
  'BASIC_INFIX_OPERATOR_EQUALS': ENodeKind.equals,
  'BASIC_INFIX_OPERATOR_LESS_THAN': ENodeKind.lessThan,
  'BASIC_INFIX_OPERATOR_LESS_THAN_OR_EQUAL': ENodeKind.lessThanEqual,
  'BASIC_INFIX_OPERATOR_GREATER_THAN': ENodeKind.greaterThan,
  'BASIC_INFIX_OPERATOR_GREATER_THAN_OR_EQUAL': ENodeKind.greaterThanEqual,
  'BASIC_INFIX_OPERATOR_FACTORIAL': ENodeKind.factorial,
  'BASIC_INFIX_OPERATOR_DEGREE': ENodeKind.degree,
  'BASIC_INFIX_OPERATOR_RADIAN': ENodeKind.radian,
  'BASIC_INFIX_OPERATOR_PERCENTAGE': ENodeKind.percentage,
};

/// Операторы без поддержки в нашем решателе: причина.
const Map<String, String> _unsupported = {
  'CONTROL_NEW_LINE': 'многострочный ввод не поддержан',
  'BASIC_INFIX_OPERATOR_PLUS_MINUS': 'узел ADD_SUBTRACT не реализован',
  'OPERATOR_FUNCTION': 'узел FUNCTION не реализован',
  'OPERATOR_FUNCTION_F': 'узел FUNCTION не реализован',
  'OPERATOR_FUNCTION_G': 'узел FUNCTION не реализован',
  'CONSTANT_HALF_PI': 'нет отдельного узла π/2 (вводится как π⁄2)',
  'CONSTANT_THIRD_PI': 'нет отдельного узла π/3 (вводится как π⁄3)',
  'HELPER_SUBSCRIPT': 'подстрочный индекс не реализован',
  'VARIABLE_AN': 'подстрочный индекс не реализован',
};

/// Сопоставить оператор APK действию редактора или причине недоступности.
OperatorBinding bindOperator(String name) {
  final digit = _digits[name];
  if (digit != null) return OperatorBinding(name, key: MathKey.digit(digit));

  final variable = _variables[name];
  if (variable != null) return OperatorBinding(name, key: MathKey.variable(variable));

  final constant = _constants[name];
  if (constant != null) return OperatorBinding(name, key: MathKey.constant(constant));

  final template = _templates[name];
  if (template != null) return OperatorBinding(name, key: MathKey.template(template));

  final infix = _infix[name];
  if (infix != null) return OperatorBinding(name, key: MathKey.operator(infix));

  switch (name) {
    case 'CONTROL_MOVE_LEFT':
      return OperatorBinding(name, key: const MathKey(MathKeyType.left, label: '◀'));
    case 'CONTROL_MOVE_RIGHT':
      return OperatorBinding(name, key: const MathKey(MathKeyType.right, label: '▶'));
    case 'CONTROL_DELETE':
      return OperatorBinding(name, key: const MathKey(MathKeyType.backspace, label: '⌫'));
    case 'CONTROL_EMPTY':
      return OperatorBinding(name, key: const MathKey(MathKeyType.clear, label: 'C'));
    case 'HELPER_XYZ_SHEET':
      return OperatorBinding(name, key: const MathKey.panel(1, 'f(x)'));
    case 'HELPER_SHOW_SECONDARY_SHEET':
      return OperatorBinding(name, key: const MathKey.panel(4, 'abc'));
  }

  final reason = _unsupported[name];
  if (reason != null) return OperatorBinding(name, reason: reason);
  return OperatorBinding(name, reason: 'не сопоставлен');
}

/// Каталог операторов по порядку `editor_operators`.
List<OperatorBinding> operatorCatalog() =>
    [for (final name in apkEditorOperators) bindOperator(name)];
