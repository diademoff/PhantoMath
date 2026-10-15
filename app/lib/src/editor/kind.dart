/// Виды узлов редактора и их свойства.
///
/// Редактор держит собственное дерево (`ENode`), отличное от `CoreNode`:
/// в нём есть ряды-последовательности и пустые слоты шаблонов, которых в
/// `CoreNode` нет. Вид узла (`ENodeKind`) описывает и то, как узел
/// разбирается в `CoreNode`, и то, как он отрисовывается.
///
/// Перечень намеренно повторяет `editor_operators` из
/// `truth/data/enums.json`, но взят по частям: сначала базовые знаки и
/// функции, затем — панели исчисления и комбинаторики.
library;

import '../model/core_node.dart' as core;

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
  integral,
  integralDefinite,
  limit,
  sigma,

  // ── шаблоны: комбинаторика ──────────────────────────────────────────
  choose,
  permutation,
  variation,
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
      case ENodeKind.integralDefinite:
      case ENodeKind.sigma:
        return 3;
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
      case ENodeKind.integral:
        return 1;
      case ENodeKind.row:
      case ENodeKind.constant:
      case ENodeKind.variable:
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

  /// Шаблон: узел с фиксированным числом слотов.
  bool get isTemplate => arity > 0;

  /// Поглощает ли шаблон предыдущий операнд при вставке.
  ///
  /// Так ведут себя дробь, степень, корень, модуль и скобки: набранное `2`,
  /// затем клавиша дроби — и `2` становится числителем. Функции и исчисление
  /// вставляются пустыми: их аргумент набирается после.
  bool get absorbsPrevious {
    switch (this) {
      case ENodeKind.fraction:
      case ENodeKind.power:
      case ENodeKind.root2:
      case ENodeKind.abs:
      case ENodeKind.bracket:
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
      case ENodeKind.limit:
        return 1;
      case ENodeKind.integralDefinite:
      case ENodeKind.sigma:
        return 2;
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
      case ENodeKind.integral:
        return core.CoreNodeType.integral;
      case ENodeKind.integralDefinite:
        return core.CoreNodeType.integralDefinite;
      case ENodeKind.limit:
        return core.CoreNodeType.limit;
      case ENodeKind.sigma:
        return core.CoreNodeType.sigmaDefinite;
      case ENodeKind.choose:
        return core.CoreNodeType.choose;
      case ENodeKind.permutation:
        return core.CoreNodeType.partialPermutation;
      case ENodeKind.variation:
        return core.CoreNodeType.variation;
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
        return '{ сист';
      case ENodeKind.determinant2:
        return '|2×2|';
      case ENodeKind.determinant3:
        return '|3×3|';
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
      case ENodeKind.integral:
        return '∫';
      case ENodeKind.integralDefinite:
        return '∫ᵃᵇ';
      case ENodeKind.limit:
        return 'lim';
      case ENodeKind.sigma:
        return 'Σ';
      case ENodeKind.choose:
        return 'Cₙᵏ';
      case ENodeKind.permutation:
        return 'Aₙᵏ';
      case ENodeKind.variation:
        return 'Vₙᵏ';
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
        return 'Плюс';
      case ENodeKind.subtract:
        return 'Минус';
      case ENodeKind.multiply:
        return 'Умножить';
      case ENodeKind.divide:
        return 'Разделить';
      case ENodeKind.equals:
        return 'Равно';
      case ENodeKind.notEquals:
        return 'Не равно';
      case ENodeKind.lessThan:
        return 'Меньше';
      case ENodeKind.lessThanEqual:
        return 'Меньше или равно';
      case ENodeKind.greaterThan:
        return 'Больше';
      case ENodeKind.greaterThanEqual:
        return 'Больше или равно';
      case ENodeKind.factorial:
        return 'Факториал';
      case ENodeKind.percentage:
        return 'Проценты';
      case ENodeKind.fraction:
        return 'Дробь';
      case ENodeKind.power:
        return 'Степень';
      case ENodeKind.root2:
        return 'Квадратный корень';
      case ENodeKind.rootN:
        return 'Корень n-й степени';
      case ENodeKind.abs:
        return 'Модуль';
      case ENodeKind.bracket:
        return 'Скобки';
      case ENodeKind.vector:
        return 'Вектор';
      case ENodeKind.system2:
        return 'Система уравнений';
      case ENodeKind.determinant2:
      case ENodeKind.determinant3:
        return 'Определитель';
      case ENodeKind.degree:
        return 'Градусы';
      case ENodeKind.radian:
        return 'Радианы';
      case ENodeKind.floor:
        return 'Целая часть';
      case ENodeKind.sign:
        return 'Знак числа';
      case ENodeKind.derivative:
        return 'Производная';
      case ENodeKind.integral:
        return 'Неопределённый интеграл';
      case ENodeKind.integralDefinite:
        return 'Определённый интеграл';
      case ENodeKind.limit:
        return 'Предел';
      case ENodeKind.sigma:
        return 'Сумма';
      case ENodeKind.choose:
        return 'Биномиальный коэффициент';
      case ENodeKind.permutation:
        return 'Перестановки';
      case ENodeKind.variation:
        return 'Размещения';
      default:
        return label;
    }
  }
}
