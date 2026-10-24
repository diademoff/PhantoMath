/// Виды узлов редактора и их свойства.
///
/// Редактор держит собственное дерево (`ENode`), отличное от `CoreNode`:
/// в нём есть ряды-последовательности и пустые слоты шаблонов, которых в
/// `CoreNode` нет. Вид узла (`ENodeKind`) описывает и то, как узел
/// разбирается в `CoreNode`, и то, как он отрисовывается.
///
/// Перечень повторяет операторы редактора (`operators.dart`) по частям:
/// сначала базовые знаки и функции, затем — панели исчисления и
/// комбинаторики.
library;

import '../model/core_node.dart' as core;
import '../i18n.dart';

/// Вид узла редактора.
///
/// `row` — горизонтальный ряд токенов (корень документа и содержимое
/// любого слота шаблона). Остальные виды — либо терминал
/// (`constant`, `variable`), либо плоский знак (`add`, `equals`, …), либо
/// шаблон со слотами (`fraction`, `power`, `sin`, …).
enum ENodeKind {
  row,
  constant,
  variable,

  // ── плоские знаки: инфиксные ────────────────────────────────────────
  add,
  subtract,
  multiply,
  divide,
  equals,
  notEquals,
  lessThan,
  lessThanEqual,
  greaterThan,
  greaterThanEqual,

  // ── плоские знаки: постфиксные ──────────────────────────────────────
  factorial,
  percentage,
  degree,
  radian,

  // ── шаблоны: дробь, степени, корни ──────────────────────────────────
  fraction,
  power,
  rootN,
  root2,
  abs,
  bracket,
  vector,
  system2,
  determinant2,
  determinant3,
  determinant4,
  determinant5,
  matrix2,
  matrix3,

  // ── шаблоны: функции ────────────────────────────────────────────────
  sin,
  cos,
  tan,
  cot,
  sec,
  csc,
  asin,
  acos,
  atan,
  acot,
  asec,
  acsc,
  sinh,
  cosh,
  tanh,
  coth,
  sech,
  csch,
  asinh,
  acosh,
  atanh,
  acoth,
  asech,
  acsch,
  ln,
  log10,
  log,
  exp,
  floor,
  sign,

  // ── шаблоны: исчисление ─────────────────────────────────────────────
  derivative,
  derivative2,
  prime,
  integral,
  integralDefinite,
  limit,
  limitLeft,
  limitRight,
  sigma,

  // ── шаблоны: комбинаторика ──────────────────────────────────────────
  choose,
  permutation,
  variation,

  // ── быстрые клавиши ─────────────────────────────────────────────────
  mixedFraction,
  powerTwo,
  powerThree,
  rootThree,
  log2,
  halfPi,

  // ── функции как объекты (OPERATOR_FUNCTION[_F|_G]) ──────────────────
  functionF,
  functionG,

  // ── обратные функции f⁻¹(x), g⁻¹(x) ─────────────────────────────────
  functionInverseF,
  functionInverseG,

  // ── геометрия: отрезок и его длина ──────────────────────────────────
  segment,
  segmentLength,

  // ── разделитель строк документа (клавиша ⏎) ──────────────────────────
  // Не узел математики: convert разрезает по нему корень на строки, внутрь
  // слотов шаблонов он не попадает как разделитель.
  newline,
}

/// Свойства вида узла: арность, роль в записи и соответствие `CoreNodeType`.
extension ENodeKindSpec on ENodeKind {
  /// Сколько слотов у шаблона. У терминалов, знаков и `row` — ноль.
  int get arity {
    switch (this) {
      case ENodeKind.fraction:
      case ENodeKind.power:
      case ENodeKind.rootN:
      case ENodeKind.log:
      case ENodeKind.limit:
      case ENodeKind.limitLeft:
      case ENodeKind.limitRight:
      case ENodeKind.choose:
      case ENodeKind.permutation:
      case ENodeKind.variation:
        return 2;
      case ENodeKind.vector:
        return 2;
      case ENodeKind.system2:
        return 2;
      case ENodeKind.determinant2:
        return 4;
      case ENodeKind.determinant3:
        return 9;
      case ENodeKind.determinant4:
        return 16;
      case ENodeKind.determinant5:
        return 25;
      case ENodeKind.segment:
      case ENodeKind.segmentLength:
        return 2;
      case ENodeKind.matrix2:
        return 4;
      case ENodeKind.matrix3:
        return 9;
      case ENodeKind.integralDefinite:
        return 3;
      case ENodeKind.sigma:
        return 4;
      case ENodeKind.mixedFraction:
        return 3;
      case ENodeKind.powerTwo:
      case ENodeKind.powerThree:
      case ENodeKind.rootThree:
      case ENodeKind.log2:
      case ENodeKind.functionF:
      case ENodeKind.functionG:
      case ENodeKind.functionInverseF:
      case ENodeKind.functionInverseG:
        return 1;
      case ENodeKind.root2:
      case ENodeKind.abs:
      case ENodeKind.bracket:
      case ENodeKind.sin:
      case ENodeKind.cos:
      case ENodeKind.tan:
      case ENodeKind.cot:
      case ENodeKind.sec:
      case ENodeKind.csc:
      case ENodeKind.asin:
      case ENodeKind.acos:
      case ENodeKind.atan:
      case ENodeKind.acot:
      case ENodeKind.asec:
      case ENodeKind.acsc:
      case ENodeKind.sinh:
      case ENodeKind.cosh:
      case ENodeKind.tanh:
      case ENodeKind.coth:
      case ENodeKind.sech:
      case ENodeKind.csch:
      case ENodeKind.asinh:
      case ENodeKind.acosh:
      case ENodeKind.atanh:
      case ENodeKind.acoth:
      case ENodeKind.asech:
      case ENodeKind.acsch:
      case ENodeKind.ln:
      case ENodeKind.log10:
      case ENodeKind.exp:
      case ENodeKind.floor:
      case ENodeKind.sign:
      case ENodeKind.derivative:
      case ENodeKind.derivative2:
      case ENodeKind.prime:
      case ENodeKind.integral:
        return 1;
      case ENodeKind.row:
      case ENodeKind.constant:
      case ENodeKind.variable:
      case ENodeKind.halfPi:
      case ENodeKind.add:
      case ENodeKind.subtract:
      case ENodeKind.multiply:
      case ENodeKind.divide:
      case ENodeKind.equals:
      case ENodeKind.notEquals:
      case ENodeKind.lessThan:
      case ENodeKind.lessThanEqual:
      case ENodeKind.greaterThan:
      case ENodeKind.greaterThanEqual:
      case ENodeKind.factorial:
      case ENodeKind.percentage:
      case ENodeKind.degree:
      case ENodeKind.radian:
      case ENodeKind.newline:
        return 0;
    }
  }

  /// Терминал ли это (число или переменная). Терминал хранит `value`.
  bool get isTerminal =>
      this == ENodeKind.constant || this == ENodeKind.variable;

  /// Плоский инфиксный знак: `+`, `=`, `×` и т. п.
  bool get isInfix {
    switch (this) {
      case ENodeKind.add:
      case ENodeKind.subtract:
      case ENodeKind.multiply:
      case ENodeKind.divide:
      case ENodeKind.equals:
      case ENodeKind.notEquals:
      case ENodeKind.lessThan:
      case ENodeKind.lessThanEqual:
      case ENodeKind.greaterThan:
      case ENodeKind.greaterThanEqual:
        return true;
      default:
        return false;
    }
  }

  /// Плоский постфиксный знак: `!`, `%`, `°`, `rad`.
  bool get isPostfix =>
      this == ENodeKind.factorial ||
      this == ENodeKind.percentage ||
      this == ENodeKind.degree ||
      this == ENodeKind.radian;

  /// Шаблон со слотами. У матриц число ячеек задаётся при вставке.
  bool get isTemplate => arity > 0;

  /// Поглощает ли шаблон предыдущий операнд при вставке.
  ///
  /// Дробь и степень могут использовать операнд слева. Корни, функции,
  /// модуль и скобки вставляются пустыми: коэффициент слева остаётся снаружи.
  bool get absorbsPrevious {
    switch (this) {
      case ENodeKind.fraction:
      case ENodeKind.power:
      case ENodeKind.mixedFraction:
      case ENodeKind.powerTwo:
      case ENodeKind.powerThree:
      case ENodeKind.prime:
        return true;
      default:
        return false;
    }
  }

  /// В какой слот попадает поглощённый операнд.
  int get absorbFillSlot => 0;

  /// Слот, в который встаёт курсор после вставки шаблона.
  int get cursorSlot {
    switch (this) {
      case ENodeKind.fraction:
      case ENodeKind.power:
        return 1;
      case ENodeKind.rootN:
        return 1;
      case ENodeKind.log:
        return 1;
      case ENodeKind.integralDefinite:
        // Ввод идёт как у предела: сначала нижний предел, «Далее» — верхний,
        // затем подынтегральное выражение.
        return 0;
      case ENodeKind.sigma:
        return 1;
      case ENodeKind.mixedFraction:
        return 1;
      default:
        return 0;
    }
  }

  /// Ставить ли курсор в конец слота (после поглощённого операнда).
  ///
  /// У корня и скобок операнд уже внутри, и курсор логично оставить за ним,
  /// а не возвращать в начало.
  bool get cursorAtEnd {
    switch (this) {
      case ENodeKind.root2:
      case ENodeKind.abs:
      case ENodeKind.bracket:
        return true;
      default:
        return false;
    }
  }

  /// Оставить курсор снаружи шаблона, сразу за ним.
  ///
  /// Штрих — постфиксный знак: `y` → `y′` → курсор за штрихом, чтобы дальше
  /// набирать `(0)` или `=` в том же ряду, а не внутри слота штриха.
  bool get cursorAfterTemplate => this == ENodeKind.prime;

  /// Тип `CoreNode`, в который превращается узел.
  ///
  /// У `row` своего типа нет: ряд — это последовательность, а не узел.
  core.CoreNodeType get coreType {
    switch (this) {
      case ENodeKind.constant:
        return core.CoreNodeType.constant;
      case ENodeKind.variable:
        return core.CoreNodeType.variable;
      case ENodeKind.add:
        return core.CoreNodeType.add;
      case ENodeKind.subtract:
        return core.CoreNodeType.subtract;
      case ENodeKind.multiply:
        return core.CoreNodeType.multiply;
      case ENodeKind.divide:
        return core.CoreNodeType.divide;
      case ENodeKind.equals:
        return core.CoreNodeType.equals;
      case ENodeKind.notEquals:
        return core.CoreNodeType.notEquals;
      case ENodeKind.lessThan:
        return core.CoreNodeType.lessThan;
      case ENodeKind.lessThanEqual:
        return core.CoreNodeType.lessThanEqual;
      case ENodeKind.greaterThan:
        return core.CoreNodeType.greaterThan;
      case ENodeKind.greaterThanEqual:
        return core.CoreNodeType.greaterThanEqual;
      case ENodeKind.factorial:
        return core.CoreNodeType.factorial;
      case ENodeKind.percentage:
        return core.CoreNodeType.percentage;
      case ENodeKind.fraction:
        return core.CoreNodeType.fraction;
      case ENodeKind.power:
        return core.CoreNodeType.power;
      case ENodeKind.rootN:
        return core.CoreNodeType.root;
      case ENodeKind.root2:
        return core.CoreNodeType.root2;
      case ENodeKind.abs:
        return core.CoreNodeType.abs;
      case ENodeKind.degree:
        return core.CoreNodeType.degree;
      case ENodeKind.radian:
        return core.CoreNodeType.radian;
      case ENodeKind.bracket:
        return core.CoreNodeType.bracket;
      case ENodeKind.vector:
        return core.CoreNodeType.list;
      case ENodeKind.system2:
        return core.CoreNodeType.system;
      case ENodeKind.determinant2:
        return core.CoreNodeType.determinant2;
      case ENodeKind.determinant3:
        return core.CoreNodeType.determinant3;
      case ENodeKind.determinant4:
        return core.CoreNodeType.determinant4;
      case ENodeKind.determinant5:
        return core.CoreNodeType.determinant5;
      case ENodeKind.matrix2:
      case ENodeKind.matrix3:
        return core.CoreNodeType.matrix;
      case ENodeKind.sin:
        return core.CoreNodeType.sin;
      case ENodeKind.cos:
        return core.CoreNodeType.cos;
      case ENodeKind.tan:
        return core.CoreNodeType.tan;
      case ENodeKind.cot:
        return core.CoreNodeType.cot;
      case ENodeKind.sec:
        return core.CoreNodeType.sec;
      case ENodeKind.csc:
        return core.CoreNodeType.csc;
      case ENodeKind.asin:
        return core.CoreNodeType.asin;
      case ENodeKind.acos:
        return core.CoreNodeType.acos;
      case ENodeKind.atan:
        return core.CoreNodeType.atan;
      case ENodeKind.acot:
        return core.CoreNodeType.acot;
      case ENodeKind.asec:
        return core.CoreNodeType.asec;
      case ENodeKind.acsc:
        return core.CoreNodeType.acsc;
      case ENodeKind.sinh:
        return core.CoreNodeType.sinh;
      case ENodeKind.cosh:
        return core.CoreNodeType.cosh;
      case ENodeKind.tanh:
        return core.CoreNodeType.tanh;
      case ENodeKind.coth:
        return core.CoreNodeType.coth;
      case ENodeKind.sech:
        return core.CoreNodeType.sech;
      case ENodeKind.csch:
        return core.CoreNodeType.csch;
      case ENodeKind.asinh:
        return core.CoreNodeType.asinh;
      case ENodeKind.acosh:
        return core.CoreNodeType.acosh;
      case ENodeKind.atanh:
        return core.CoreNodeType.atanh;
      case ENodeKind.acoth:
        return core.CoreNodeType.acoth;
      case ENodeKind.asech:
        return core.CoreNodeType.asech;
      case ENodeKind.acsch:
        return core.CoreNodeType.acsch;
      case ENodeKind.ln:
        return core.CoreNodeType.ln;
      case ENodeKind.log10:
        return core.CoreNodeType.log10;
      case ENodeKind.log:
        return core.CoreNodeType.log;
      case ENodeKind.exp:
        return core.CoreNodeType.exp;
      case ENodeKind.floor:
        return core.CoreNodeType.floor;
      case ENodeKind.sign:
        return core.CoreNodeType.sign;
      case ENodeKind.derivative:
        return core.CoreNodeType.derivation1;
      case ENodeKind.derivative2:
        return core.CoreNodeType.derivation2Prime;
      case ENodeKind.prime:
        return core.CoreNodeType.prime;
      case ENodeKind.integral:
        return core.CoreNodeType.integral;
      case ENodeKind.integralDefinite:
        return core.CoreNodeType.integralDefinite;
      case ENodeKind.limit:
        return core.CoreNodeType.limit;
      case ENodeKind.limitLeft:
        return core.CoreNodeType.limitLeft;
      case ENodeKind.limitRight:
        return core.CoreNodeType.limitRight;
      case ENodeKind.sigma:
        return core.CoreNodeType.sigmaDefinite;
      case ENodeKind.choose:
        return core.CoreNodeType.choose;
      case ENodeKind.permutation:
        return core.CoreNodeType.partialPermutation;
      case ENodeKind.variation:
        return core.CoreNodeType.variation;
      case ENodeKind.mixedFraction:
        return core.CoreNodeType.fractionMixed;
      case ENodeKind.powerTwo:
      case ENodeKind.powerThree:
        return core.CoreNodeType.power;
      case ENodeKind.rootThree:
        return core.CoreNodeType.root;
      case ENodeKind.log2:
        return core.CoreNodeType.log;
      case ENodeKind.halfPi:
        // Быстрая клавиша раскрывается в дробь π/2 ещё при вставке
        // (`model.dart`), в документе такой узел не встречается.
        return core.CoreNodeType.fraction;
      case ENodeKind.functionF:
      case ENodeKind.functionG:
        return core.CoreNodeType.function;
      case ENodeKind.functionInverseF:
      case ENodeKind.functionInverseG:
        return core.CoreNodeType.functionInverse;
      case ENodeKind.segment:
        return core.CoreNodeType.lineSegment;
      case ENodeKind.segmentLength:
        return core.CoreNodeType.lineSegmentLength;
      case ENodeKind.newline:
        // Разделитель строк: convert разрезает по нему документ и никогда
        // не преобразует сам токен.
        return core.CoreNodeType.empty;
      case ENodeKind.row:
        return core.CoreNodeType.empty;
    }
  }

  /// Текст клавиши для этого вида, если он используется как подпись.
  String get label {
    switch (this) {
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
      case ENodeKind.fraction:
        return '⁄';
      case ENodeKind.power:
        return 'xⁿ';
      case ENodeKind.root2:
        return '√';
      case ENodeKind.rootN:
        return 'ⁿ√';
      case ENodeKind.abs:
        return '|x|';
      case ENodeKind.bracket:
        return '( )';
      case ENodeKind.vector:
        return '⟨a,b⟩';
      case ENodeKind.system2:
        return tr('{ сист', '{ system');
      case ENodeKind.determinant2:
        return '|2×2|';
      case ENodeKind.determinant3:
        return '|3×3|';
      case ENodeKind.determinant4:
        return '|4×4|';
      case ENodeKind.determinant5:
        return '|5×5|';
      case ENodeKind.matrix2:
        return '2×2';
      case ENodeKind.matrix3:
        return '3×3';
      case ENodeKind.sin:
        return 'sin';
      case ENodeKind.cos:
        return 'cos';
      case ENodeKind.tan:
        return 'tan';
      case ENodeKind.cot:
        return 'cot';
      case ENodeKind.sec:
        return 'sec';
      case ENodeKind.csc:
        return 'csc';
      case ENodeKind.asin:
        return 'sin⁻¹';
      case ENodeKind.acos:
        return 'cos⁻¹';
      case ENodeKind.atan:
        return 'tan⁻¹';
      case ENodeKind.acot:
        return 'cot⁻¹';
      case ENodeKind.asec:
        return 'sec⁻¹';
      case ENodeKind.acsc:
        return 'csc⁻¹';
      case ENodeKind.sinh:
        return 'sinh';
      case ENodeKind.cosh:
        return 'cosh';
      case ENodeKind.tanh:
        return 'tanh';
      case ENodeKind.coth:
        return 'coth';
      case ENodeKind.sech:
        return 'sech';
      case ENodeKind.csch:
        return 'csch';
      case ENodeKind.asinh:
        return 'sinh⁻¹';
      case ENodeKind.acosh:
        return 'cosh⁻¹';
      case ENodeKind.atanh:
        return 'tanh⁻¹';
      case ENodeKind.acoth:
        return 'coth⁻¹';
      case ENodeKind.asech:
        return 'sech⁻¹';
      case ENodeKind.acsch:
        return 'csch⁻¹';
      case ENodeKind.ln:
        return 'ln';
      case ENodeKind.log10:
        return 'log₁₀';
      case ENodeKind.log:
        return 'logᵦ';
      case ENodeKind.exp:
        return 'eˣ';
      case ENodeKind.floor:
        return '⌊x⌋';
      case ENodeKind.sign:
        return 'sgn';
      case ENodeKind.derivative:
        return 'd/dx';
      case ENodeKind.derivative2:
        return 'd²/dx²';
      case ENodeKind.prime:
        return '′';
      case ENodeKind.integral:
        return '∫';
      case ENodeKind.integralDefinite:
        return '∫ᵃᵇ';
      case ENodeKind.limit:
        return 'lim';
      case ENodeKind.limitLeft:
        return 'lim⁻';
      case ENodeKind.limitRight:
        return 'lim⁺';
      case ENodeKind.sigma:
        return 'Σ';
      case ENodeKind.choose:
        return 'Cₙᵏ';
      case ENodeKind.permutation:
        return 'Aₙᵏ';
      case ENodeKind.variation:
        return 'Vₙᵏ';
      case ENodeKind.mixedFraction:
        return '1½';
      case ENodeKind.powerTwo:
        return 'x²';
      case ENodeKind.powerThree:
        return 'x³';
      case ENodeKind.rootThree:
        return '∛';
      case ENodeKind.log2:
        return 'log₂';
      case ENodeKind.halfPi:
        return 'π/2';
      case ENodeKind.functionF:
        return 'f(x)';
      case ENodeKind.functionG:
        return 'g(x)';
      case ENodeKind.functionInverseF:
        return 'f⁻¹(x)';
      case ENodeKind.functionInverseG:
        return 'g⁻¹(x)';
      case ENodeKind.segment:
        return 'AB';
      case ENodeKind.segmentLength:
        return '|AB|';
      case ENodeKind.newline:
        return '⏎';
      default:
        return '';
    }
  }

  /// Описание клавиши словами — для подсказки и screen reader.
  ///
  /// Символьные подписи (`⁄`, `xⁿ`, `|x|`) сами по себе непонятны, поэтому
  /// у каждой конструкции есть короткое название. Для остальных видов
  /// описание совпадает с подписью.
  String get description {
    switch (this) {
      case ENodeKind.add:
        return tr('Плюс', 'Plus');
      case ENodeKind.subtract:
        return tr('Минус', 'Minus');
      case ENodeKind.multiply:
        return tr('Умножить', 'Multiply');
      case ENodeKind.divide:
        return tr('Разделить', 'Divide');
      case ENodeKind.equals:
        return tr('Равно', 'Equals');
      case ENodeKind.notEquals:
        return tr('Не равно', 'Not equals');
      case ENodeKind.lessThan:
        return tr('Меньше', 'Less than');
      case ENodeKind.lessThanEqual:
        return tr('Меньше или равно', 'Less than or equal');
      case ENodeKind.greaterThan:
        return tr('Больше', 'Greater than');
      case ENodeKind.greaterThanEqual:
        return tr('Больше или равно', 'Greater than or equal');
      case ENodeKind.factorial:
        return tr('Факториал', 'Factorial');
      case ENodeKind.percentage:
        return tr('Проценты', 'Percent');
      case ENodeKind.fraction:
        return tr('Дробь', 'Fraction');
      case ENodeKind.power:
        return tr('Степень', 'Power');
      case ENodeKind.root2:
        return tr('Квадратный корень', 'Square root');
      case ENodeKind.rootN:
        return tr('Корень n-й степени', 'Nth root');
      case ENodeKind.abs:
        return tr('Модуль', 'Absolute value');
      case ENodeKind.bracket:
        return tr('Скобки', 'Brackets');
      case ENodeKind.vector:
        return tr('Вектор', 'Vector');
      case ENodeKind.system2:
        return tr('Система уравнений', 'System of equations');
      case ENodeKind.determinant2:
      case ENodeKind.determinant3:
      case ENodeKind.determinant4:
      case ENodeKind.determinant5:
        return tr('Определитель', 'Determinant');
      case ENodeKind.matrix2:
      case ENodeKind.matrix3:
        return tr('Матрица', 'Matrix');
      case ENodeKind.degree:
        return tr('Градусы', 'Degrees');
      case ENodeKind.radian:
        return tr('Радианы', 'Radians');
      case ENodeKind.floor:
        return tr('Целая часть', 'Floor');
      case ENodeKind.sign:
        return tr('Знак числа', 'Sign');
      case ENodeKind.derivative:
        return tr('Производная', 'Derivative');
      case ENodeKind.derivative2:
        return tr('Производная 2-го порядка', 'Second derivative');
      case ENodeKind.prime:
        return tr('Штрих', 'Prime');
      case ENodeKind.integral:
        return tr('Неопределённый интеграл', 'Indefinite integral');
      case ENodeKind.integralDefinite:
        return tr('Определённый интеграл', 'Definite integral');
      case ENodeKind.limit:
        return tr('Предел', 'Limit');
      case ENodeKind.limitLeft:
        return tr('Предел слева', 'Left-hand limit');
      case ENodeKind.limitRight:
        return tr('Предел справа', 'Right-hand limit');
      case ENodeKind.sigma:
        return tr('Сумма', 'Sum');
      case ENodeKind.choose:
        return tr('Биномиальный коэффициент', 'Binomial coefficient');
      case ENodeKind.permutation:
        return tr('Перестановки', 'Permutation');
      case ENodeKind.variation:
        return tr('Размещения', 'Variation');
      case ENodeKind.mixedFraction:
        return tr('Смешанное число', 'Mixed number');
      case ENodeKind.powerTwo:
        return tr('Квадрат', 'Square');
      case ENodeKind.powerThree:
        return tr('Куб', 'Cube');
      case ENodeKind.rootThree:
        return tr('Кубический корень', 'Cube root');
      case ENodeKind.log2:
        return tr('Логарифм по основанию 2', 'Logarithm base 2');
      case ENodeKind.halfPi:
        return tr('Пи пополам', 'Pi over two');
      case ENodeKind.functionF:
        return tr('Функция f', 'Function f');
      case ENodeKind.functionG:
        return tr('Функция g', 'Function g');
      case ENodeKind.functionInverseF:
        return tr('Обратная функция f', 'Inverse function f');
      case ENodeKind.functionInverseG:
        return tr('Обратная функция g', 'Inverse function g');
      case ENodeKind.segment:
        return tr('Отрезок', 'Segment');
      case ENodeKind.segmentLength:
        return tr('Длина отрезка', 'Segment length');
      case ENodeKind.newline:
        return tr('Новая строка', 'New line');
      default:
        return label;
    }
  }
}
