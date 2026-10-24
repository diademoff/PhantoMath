/// Приведение узла к LaTeX.
///
/// Рендер формул делает `flutter_math_fork`; наша задача — превратить
/// `CoreNode` в строку, которую он понимает. Писать свой рентер дробей,
/// корней и матриц — отдельный проект, поэтому здесь только перевод.
///
/// Шаблон использует позиционные плейсхолдеры `$0`, `$1`, … — по одному
/// на каждого ребёнка. Это позволяет разводить аргументы по разным
/// местам: `\frac{$0}{$1}` кладёт первого в числитель, второго — в
/// знаменатель.
///
/// Результат — «сырой» LaTeX без обёрток `$…$`: `flutter_math` (парсер
/// KaTeX) не принимает `$` внутри формулы и падает с `ParseException`.
/// Поэтому в шаблонах допустимы только позиционные плейсхолдеры, а дети
/// подставляются как есть.
///
/// Незавершённый узел (ребёнок без значения) даёт `\square`: в интерфейсе
/// видно, что выражение ждёт продолжения ввода, а не молчаливый пропуск.
library;

import '../model/core_node.dart';
import '../settings/settings.dart';
import '../i18n.dart';

const String _placeholder = r'\square';

/// Настройки отрисовки: десятичный разделитель и нотация биномиального
/// коэффициента. Значения по умолчанию совпадают с нейтральной записью
/// (точка, «этажная» запись) — так уже сохранённые тесты не меняются.
class LatexOptions {
  const LatexOptions({
    this.decimalSeparator = DecimalSeparator.point,
    this.binomialNotation = BinomialNotation.notationOne,
  });

  final DecimalSeparator decimalSeparator;
  final BinomialNotation binomialNotation;

  /// Умолчание: точка и «этажная» запись.
  static const LatexOptions standard = LatexOptions();
}

/// Текущие настройки отрисовки на время одного вызова [nodeToLatex].
///
/// Рендер синхронный и однопоточный, а помощники (`_wrap`, `_childLatex`, …)
/// вызываются рекурсивно и глубоко; прокидывать параметр через каждый из них
/// шумно. Поэтому настройки выставляются на входе и восстанавливаются на
/// выходе.
LatexOptions _current = LatexOptions.standard;

/// Собрать LaTeX для узла.
///
/// Возвращает пустую строку для листьев без значения и для `EMPTY`:
/// вызывающий покажет заглушку. Подсветка (`color`) и зачёркивание
/// (`crossed`) оборачивают результат: это микро-анимация шага.
String nodeToLatex(
  CoreNode node, [
  LatexOptions options = LatexOptions.standard,
]) {
  final previous = _current;
  _current = options;
  try {
    return _styled(node, _nodeBody(node));
  } finally {
    _current = previous;
  }
}

/// Показать число с учётом выбранного десятичного разделителя.
///
/// Внутри решателя дробная часть всегда через точку; для показа заменяем
/// её на выбранный символ (`DecimalSeparator` в настройках).
String _number(String value, [LatexOptions? options]) {
  final separator = (options ?? _current).decimalSeparator;
  if (separator == DecimalSeparator.comma) return value.replaceAll('.', ',');
  return value;
}

/// Обернуть LaTeX подсветкой/зачёркиванием узла.
String _styled(CoreNode node, String latex) {
  if (latex.isEmpty) return latex;
  var out = latex;
  if (node.crossed == true) out = '\\cancel{$out}';
  if (node.color != null) {
    final rgb = (node.color! & 0xFFFFFF).toRadixString(16).padLeft(6, '0');
    out = '\\textcolor{#$rgb}{$out}';
  }
  return out;
}

/// Тело узла без подсветки и зачёркивания.
String _nodeBody(CoreNode node) {
  switch (node.type) {
    // ── листья ──────────────────────────────────────────────────────
    case CoreNodeType.constant:
      final fraction = RegExp(r'^(-?)(\d+)/(\d+)$')
          .firstMatch(node.value ?? '');
      if (fraction != null) {
        // A rational result such as 22/5 is drawn stacked, like a typed fraction.
        return '${fraction[1]}\\frac{${fraction[2]}}{${fraction[3]}}';
      }
      return _escape(_number(node.value ?? ''));
    case CoreNodeType.variable:
      // Постоянные высших порядков приходят как VARIABLE `C1`, `C2`:
      // в учебнике они пишутся C₁, C₂ (одна буква и цифры).
      final constant = RegExp(r'^([A-Za-z])(\d+)$')
          .firstMatch(node.value ?? '');
      if (constant != null) {
        return '${constant[1]}_{${constant[2]}}';
      }
      return _escape(node.value ?? '');

    // ── знаки ───────────────────────────────────────────────────────
    case CoreNodeType.negative:
      return node.children.isEmpty ? '' : '-${_operand(node.children[0], 3)}';

    case CoreNodeType.positive:
      return node.children.isEmpty ? '' : '+${_operand(node.children[0], 3)}';

    // ── бинарные операции ───────────────────────────────────────────
    // Сумма, разность и произведение бывают с тремя и более детьми
    // (`4·a·c`, `a + b + c`): шаблон на два операнда терял остальных.
    case CoreNodeType.add:
      return _infix(node, ' + ', 1, 3);

    case CoreNodeType.subtract:
      return _infix(node, ' - ', 1, 3);

    case CoreNodeType.multiply:
      return _infix(node, r' \cdot ', 2, 3);

    case CoreNodeType.multiplyImplicit:
      // 2x\,dx: a differential stands apart, as in the book (was 2xdx).
      final last = node.children.isEmpty ? null : node.children.last;
      if (node.children.length > 1 &&
          last!.type == CoreNodeType.variable &&
          RegExp(r'^d[a-zA-Z]$').hasMatch(last.value ?? '')) {
        final head = CoreNode(
          type: node.type,
          children: node.children.sublist(0, node.children.length - 1),
        );
        final left = head.children.length == 1
            ? _operand(head.children.single, 2)
            : _infix(head, ' ', 2, 3);
        return '$left\\,${_escape(last.value!)}';
      }
      return _infix(node, ' ', 2, 3);

    case CoreNodeType.divide:
      return _wrap(node, r'\frac{$0}{$1}');

    case CoreNodeType.power:
      if (node.children.length < 2) return _wrap(node, r'{$0}^{$1}');
      final exponent = node.children[1];
      // flutter_math breaks its size constraints on \left(…\right) inside an
      // exponent that holds a power (2^(x²−3x)); plain parentheses fit the same.
      final shown =
          exponent.type == CoreNodeType.bracket && exponent.children.length == 1
          ? '(${_childLatex(exponent.children.single)})'
          : _childLatex(exponent);
      return '{${_base(node.children[0])}}^{$shown}';

    case CoreNodeType.factorial:
      return _wrap(node, r'{$0}!');

    // ── единицы угла ────────────────────────────────────────────────
    case CoreNodeType.degree:
      return _wrap(node, r'{$0}^{\circ}');

    case CoreNodeType.radian:
      return _wrap(node, r'{$0}\ \mathrm{rad}');

    case CoreNodeType.periodic:
      return _periodic(node);

    // ── многочленные конструкции ────────────────────────────────────
    case CoreNodeType.fraction:
      return _wrap(node, r'\frac{$0}{$1}');

    case CoreNodeType.fractionMixed:
      return _wrap(node, r'$0\;\frac{$1}{$2}');

    case CoreNodeType.root:
      return _wrap(node, r'\sqrt[$0]{$1}');

    case CoreNodeType.root2:
      return _wrap(node, r'\sqrt{$0}');

    case CoreNodeType.abs:
      return _wrap(node, r'\left|$0\right|');

    case CoreNodeType.bracket:
      return _wrap(node, r'\left($0\right)');

    // ── функции ─────────────────────────────────────────────────────
    case CoreNodeType.sin:
      return _function(node, r'\sin');

    case CoreNodeType.cos:
      return _function(node, r'\cos');

    case CoreNodeType.tan:
      return _function(node, r'\tan');

    case CoreNodeType.cot:
      return _function(node, r'\cot');

    case CoreNodeType.sec:
      return _function(node, r'\sec');

    case CoreNodeType.csc:
      return _function(node, r'\csc');

    case CoreNodeType.asin:
      return _function(node, r'\arcsin');

    case CoreNodeType.acos:
      return _function(node, r'\arccos');

    case CoreNodeType.atan:
      return _function(node, r'\arctan');

    case CoreNodeType.acot:
      return _function(node, r'\mathrm{acot}');

    case CoreNodeType.asec:
      return _function(node, r'\mathrm{asec}');

    case CoreNodeType.acsc:
      return _function(node, r'\mathrm{acsc}');

    case CoreNodeType.sinh:
      return _function(node, r'\sinh');

    case CoreNodeType.cosh:
      return _function(node, r'\cosh');

    case CoreNodeType.tanh:
      return _function(node, r'\tanh');

    case CoreNodeType.coth:
      return _function(node, r'\coth');

    case CoreNodeType.sech:
      return _function(node, r'\mathrm{sech}');

    case CoreNodeType.csch:
      return _function(node, r'\mathrm{csch}');

    case CoreNodeType.asinh:
      return _function(node, r'\mathrm{asinh}');

    case CoreNodeType.acosh:
      return _function(node, r'\mathrm{acosh}');

    case CoreNodeType.atanh:
      return _function(node, r'\mathrm{atanh}');

    case CoreNodeType.acoth:
      return _function(node, r'\mathrm{acoth}');

    case CoreNodeType.asech:
      return _function(node, r'\mathrm{asech}');

    case CoreNodeType.acsch:
      return _function(node, r'\mathrm{acsch}');

    case CoreNodeType.log:
      if (node.children.length != 2) return '';
      return _function(node, '\\log_{${_childLatex(node.children[1])}}');

    case CoreNodeType.log10:
      return _function(node, r'\log_{10}');

    case CoreNodeType.ln:
      // ln|x|, а не ln(|x|): модуль уже служит скобками.
      if (node.children.length == 1 &&
          node.children.single.type == CoreNodeType.abs) {
        return '\\ln${_childLatex(node.children.single)}';
      }
      return _function(node, r'\ln');

    case CoreNodeType.exp:
      return _wrap(node, r'e^{$0}');

    case CoreNodeType.sign:
      return _wrap(node, r'\mathrm{sign}\left($0\right)');

    case CoreNodeType.floor:
      return _wrap(node, r'\lfloor $0 \rfloor');

    case CoreNodeType.percentage:
      return _wrap(node, r'{$0}\,\%');

    case CoreNodeType.approximate:
      return _wrap(node, r'$0 \approx $1');

    case CoreNodeType.approximateSign:
      return _wrap(node, r'\approx $0');

    // ── исчисление ──────────────────────────────────────────────────
    case CoreNodeType.derivation:
    case CoreNodeType.derivation1:
      return _wrap(node, r'\frac{d}{dx}\left($0\right)');

    case CoreNodeType.derivation1Diff:
      // d(x² + 1)/dx: составное выражение под d — в скобках.
      if (node.children.length < 2) return _wrap(node, r'\frac{d\,$1}{d\,$0}');
      return '\\frac{d\\,${_operand(node.children[1], 5)}}{d\\,${_childLatex(node.children[0])}}';

    case CoreNodeType.prime:
    case CoreNodeType.derivation1Prime:
      // y″ — одна группа штрихов: PRIME(PRIME(y)) рисуется `y''`,
      // а не `y'′` с промежутком между знаками.
      final nested =
          node.children.length == 1 &&
          (node.children.first.type == CoreNodeType.prime ||
              node.children.first.type == CoreNodeType.derivation1Prime);
      return nested ? _prime(node.children.first, "''") : _prime(node, "'");

    case CoreNodeType.derivation2Prime:
      return _prime(node, "''");

    // Сумма под знаком интеграла — в скобках: ∫(x + 1) dx, а не ∫x + 1 dx.
    case CoreNodeType.integral:
      if (node.children.isEmpty) return '';
      return '\\int ${_operand(node.children[0], 2)}'
          '\\,d${_integralVariable(node, 0)}';

    case CoreNodeType.integralDefinite:
      if (node.children.isEmpty) return '';
      final integrand = node.children.length > 2
          ? _operand(node.children[2], 2)
          : _placeholder;
      return '${_wrap(node, r'\int_{$0}^{$1} ')}$integrand'
          '\\,d${_integralVariable(node, 2)}';

    case CoreNodeType.integralRightDash:
      return _wrap(node, r'\left.$0\right|_{$1}^{$2}');

    // ── углы: градусы-минуты-секунды ────────────────────────────────
    case CoreNodeType.degreeMinute:
      return _wrap(node, r'{$0}^{\circ}{$1}^{\prime}');

    case CoreNodeType.degreeMinuteSecond:
      return _wrap(node, r'{$0}^{\circ}{$1}^{\prime}{$2}^{\prime\prime}');

    case CoreNodeType.degreeSecond:
      return _wrap(node, r'{$0}^{\circ}{$1}^{\prime\prime}');

    case CoreNodeType.minute:
      return _wrap(node, r'{$0}^{\prime}');

    case CoreNodeType.second:
      return _wrap(node, r'{$0}^{\prime\prime}');

    case CoreNodeType.minuteSecond:
      return _wrap(node, r'{$0}^{\prime}{$1}^{\prime\prime}');

    case CoreNodeType.limit:
      return _limit(node, '');

    case CoreNodeType.limitLeft:
      return _limit(node, '^{-}');

    case CoreNodeType.limitRight:
      return _limit(node, '^{+}');

    // ── знак «плюс-минус» и комплексные величины ───────────────────
    case CoreNodeType.addSubtract:
      if (node.children.isEmpty) return _placeholder;
      return node.children.length == 1
          ? '\\pm ${_childLatex(node.children[0])}'
          : '${_childLatex(node.children[0])} \\pm ${_childLatex(node.children[1])}';

    case CoreNodeType.conjugate:
      return _wrap(node, r'\overline{$0}');

    case CoreNodeType.real:
      return _wrap(node, r'\mathrm{Re}\left($0\right)');

    case CoreNodeType.imaginary:
      // Без аргумента это мнимая единица, с аргументом — Im(z).
      final argument = node.children.isEmpty ? null : node.children.first;
      if (argument == null || argument.type == CoreNodeType.empty) return 'i';
      return _wrap(node, r'\mathrm{Im}\left($0\right)');

    case CoreNodeType.sigmaDefinite:
      return _wrap(
        node,
        node.children.length == 4
            ? r'\sum_{$0=$1}^{$2} $3'
            : r'\sum_{n=$0}^{$1} $2',
      );

    // ── комбинаторика ───────────────────────────────────────────────
    case CoreNodeType.choose:
      // Нотация биномиального коэффициента из профиля (`BinomialType`):
      // «этажная» (`\binom`) или строчная `C(n, k)`.
      return _wrap(
        node,
        _current.binomialNotation == BinomialNotation.notationTwo
            ? r'C\left($0,\ $1\right)'
            : r'\binom{$0}{$1}',
      );

    case CoreNodeType.evaluateExpression:
      return _wrap(node, r'\left.$0\right|_{x=$1}');

    case CoreNodeType.piecewiseDefinition:
      // Пары «значение, условие» подряд: первое значение идёт после переменной.
      final pairs = node.children.length.isOdd
          ? node.children.skip(1).toList()
          : node.children;
      final rows = <String>[];
      for (var i = 0; i + 1 < pairs.length; i += 2) {
        rows.add('${_childLatex(pairs[i])} & ${_childLatex(pairs[i + 1])}');
      }
      return rows.isEmpty
          ? _placeholder
          : '\\begin{cases}${rows.join(r' \\ ')}\\end{cases}';

    case CoreNodeType.matrixSplitLast:
      if (node.children.isEmpty) return _placeholder;
      final width = node.children.first.type == CoreNodeType.matrixRow
          ? node.children.first.children.length
          : 1;
      final spec = '${'c' * (width - 1)}|c';
      final lines = [
        for (final row in node.children)
          (row.type == CoreNodeType.matrixRow ? row.children : [row])
              .map(_childLatex)
              .join(' & '),
      ];
      return '\\left(\\begin{array}{$spec}${lines.join(r' \\ ')}\\end{array}\\right)';

    case CoreNodeType.usLongdiv:
    case CoreNodeType.ruLongdiv:
    case CoreNodeType.verticalDivide:
      return _wrap(node, r'$0 \div $1');

    case CoreNodeType.chooseSubscript:
      return _wrap(node, r'{}_{$0}C_{$1}');

    case CoreNodeType.mean:
      if (node.children.isEmpty) return _placeholder;
      return '\\overline{${node.children.map(_childLatex).join(', ')}}';

    case CoreNodeType.sequence:
      return _delimited(node, '', '', r',\ ');

    case CoreNodeType.partialPermutation:
      return _wrap(node, r'{}^{$0}P_{$1}');

    case CoreNodeType.variation:
      return _wrap(node, r'{}^{$0}A_{$1}');

    // ── функции как объекты ─────────────────────────────────────────
    case CoreNodeType.function:
      return _wrap(node, '${_escape(node.value ?? 'f')}\\left(\$0\\right)');

    case CoreNodeType.functionInverse:
      return _wrap(
        node,
        '${_escape(node.value ?? 'f')}^{-1}\\left(\$0\\right)',
      );

    // ── геометрия: отрезок и его длина ──────────────────────────────
    case CoreNodeType.lineSegment:
      if (node.children.isEmpty) return _placeholder;
      return '\\overline{${node.children.map(_childLatex).join(' ')}}';

    case CoreNodeType.lineSegmentLength:
      if (node.children.isEmpty) return _placeholder;
      return '\\left|${node.children.map(_childLatex).join(' ')}\\right|';

    // ── матрицы ─────────────────────────────────────────────────────
    case CoreNodeType.determinant2:
      return _matrix(node, 2, r'\begin{vmatrix}', r'\end{vmatrix}');

    case CoreNodeType.determinant3:
    case CoreNodeType.determinant3Sarrus:
      return _matrix(node, 3, r'\begin{vmatrix}', r'\end{vmatrix}');

    case CoreNodeType.determinant4:
      return _matrix(node, 4, r'\begin{vmatrix}', r'\end{vmatrix}');

    case CoreNodeType.determinant5:
      return _matrix(node, 5, r'\begin{vmatrix}', r'\end{vmatrix}');

    case CoreNodeType.determinant:
      return _matrixLatex(node, r'\begin{vmatrix}', r'\end{vmatrix}');

    case CoreNodeType.matrix:
      return _matrixLatex(node, r'\begin{pmatrix}', r'\end{pmatrix}');

    case CoreNodeType.matrixRow:
      return node.children.map(_childLatex).join(' & ');

    // ── столбиковые вычисления ──────────────────────────────────────
    case CoreNodeType.verticalAdd:
      return _vertical(node, '+');

    case CoreNodeType.verticalSubtract:
      return _vertical(node, '-');

    case CoreNodeType.verticalMultiply:
      return _vertical(node, r'\times');

    case CoreNodeType.horizontalMultiply:
      return _wrap(node, r'$0 \times $1');

    // ── отношения ───────────────────────────────────────────────────
    case CoreNodeType.equals:
      return _joined(node, ' = ') ?? _wrap(node, r'$0 = $1');

    case CoreNodeType.notEquals:
      return _wrap(node, r'$0 \ne $1');

    case CoreNodeType.lessThan:
      return _joined(node, ' < ') ?? _wrap(node, r'$0 < $1');

    case CoreNodeType.lessThanEqual:
      return _joined(node, r' \le ') ?? _wrap(node, r'$0 \le $1');

    case CoreNodeType.greaterThan:
      return _joined(node, ' > ') ?? _wrap(node, r'$0 > $1');

    case CoreNodeType.greaterThanEqual:
      return _joined(node, r' \ge ') ?? _wrap(node, r'$0 \ge $1');

    // ── промежутки ──────────────────────────────────────────────────
    case CoreNodeType.openOpenInterval:
      return _wrap(node, r'\left($0, $1\right)');

    case CoreNodeType.openClosedInterval:
      return _wrap(node, r'\left($0, $1\right]');

    case CoreNodeType.closedOpenInterval:
      return _wrap(node, r'\left[$0, $1\right)');

    case CoreNodeType.closedClosedInterval:
      return _wrap(node, r'\left[$0, $1\right]');

    // ── множества ───────────────────────────────────────────────────
    case CoreNodeType.set:
      return _delimited(node, r'\left\{', r'\right\}', r',\ ');

    case CoreNodeType.union:
      return _delimited(node, '', '', r' \cup ');

    case CoreNodeType.intersection:
      return _delimited(node, '', '', r' \cap ');

    case CoreNodeType.difference:
      return _wrap(node, r'$0 \setminus $1');

    case CoreNodeType.elementOf:
      return _wrap(node, r'$0 \in $1');

    case CoreNodeType.elementNotOf:
      return _wrap(node, r'$0 \notin $1');

    case CoreNodeType.subsetOrEquals:
      return _wrap(node, r'$0 \subseteq $1');

    case CoreNodeType.properSubset:
      return _wrap(node, r'$0 \subset $1');

    case CoreNodeType.notProperSubset:
      return _wrap(node, r'$0 \not\subset $1');

    case CoreNodeType.supersetOrEquals:
      return _wrap(node, r'$0 \supseteq $1');

    case CoreNodeType.properSuperset:
      return _wrap(node, r'$0 \supset $1');

    case CoreNodeType.notProperSuperset:
      return _wrap(node, r'$0 \not\supset $1');

    // ── текст ───────────────────────────────────────────────────────
    case CoreNodeType.text:
      if (node.children.isEmpty) return _textValue(node.value ?? '');
      return node.children.map(_childLatex).join();

    case CoreNodeType.textKey:
      // The verdict of a comparison is shown as a word, not as a raw key in math italics.
      return switch (node.value) {
        'true' => '\\text{${tr('Истина', 'True')}}',
        'false' => '\\text{${tr('Ложь', 'False')}}',
        final key => _escape(key ?? ''),
      };

    // ── упорядочивание ──────────────────────────────────────────────
    case CoreNodeType.order:
      return _delimited(node, '', '', r',\ ');

    // ── составные ───────────────────────────────────────────────────
    case CoreNodeType.list:
    case CoreNodeType.verticalList:
    case CoreNodeType.alternativeForm:
      if (node.children.isEmpty) return _placeholder;
      return [for (final child in node.children) _childLatex(child)]
          .join(r',\quad ');

    case CoreNodeType.system:
      // Каждое уравнение — своя строка; шаблон с одним `$0` показывал только первое.
      final rows = node.children.map(_childLatex).toList();
      // flutter_math не учитывает высоту дробей в cases: строки с \frac налезают друг на друга.
      final gap = rows.any((row) => row.contains(r'\frac'))
          ? r' \\[0.4em] '
          : r' \\ ';
      return '\\begin{cases}${rows.join(gap)}\\end{cases}';

    case CoreNodeType.empty:
      return '';
  }
}

/// Столбик: операнды друг под другом с общим знаком слева.
String _vertical(CoreNode node, String sign) {
  if (node.children.isEmpty) return _placeholder;
  final rows = node.children.map((child) => '$sign\\; ${_childLatex(child)}');
  return '\\begin{array}{r}${rows.join(r' \\ ')}\\end{array}';
}

/// Периодическая дробь: цифры и длина периода во втором ребёнке.
String _periodic(CoreNode node) {
  final digits = node.children.isNotEmpty ? (node.children[0].value ?? '') : '';
  final declared = node.children.length > 1
      ? int.tryParse(node.children[1].value ?? '')
      : null;
  final period = declared ?? digits.length;
  final split = digits.length - period;
  if (split <= 0) return '0{,}\\overline{$digits}';
  return '0{,}${digits.substring(0, split)}\\overline{${digits.substring(split)}}';
}

/// Все дети через разделитель; `null`, если детей не больше двух.
String? _joined(CoreNode node, String separator) {
  if (node.children.length <= 2) return null;
  return node.children.map(_childLatex).join(separator);
}

/// Приоритет узла для расстановки скобок: 1 — сумма, 2 — унарный знак, 3 — произведение,
/// 4 — степень, 5 — атом (число, функция, дробь, скобки).
int _level(CoreNode node) => switch (node.type) {
  CoreNodeType.add || CoreNodeType.subtract => 1,
  CoreNodeType.negative || CoreNodeType.positive => 2,
  CoreNodeType.constant when (node.value ?? '').startsWith('-') => 2,
  CoreNodeType.multiply || CoreNodeType.multiplyImplicit => 3,
  CoreNodeType.power => 4,
  _ => 5,
};

/// Операнд в скобках, если его приоритет ниже нужного. Узлы из sympy приходят без
/// BRACKET: без этого `(x − 1)²` рисовалось как `x − 1²`, `−2(x − 3)` — как `−2x − 3`.
String _operand(CoreNode child, int min) {
  final latex = _childLatex(child);
  return _level(child) < min ? '\\left($latex\\right)' : latex;
}

/// Предел: сумма под lim — в скобках, иначе lim 1 − 1/b читается как (lim 1) − 1/b.
String _limit(CoreNode node, String side) {
  if (node.children.isEmpty) return '';
  final body = node.children.length > 1
      ? _operand(node.children[1], 2)
      : _placeholder;
  return '${_wrap(node, '\\lim_{${_limitVariable(node)} \\to \$0$side} ')}$body';
}

/// Основание степени или штриха: любое составное выражение и дробь — в скобках.
String _base(CoreNode child) => switch (child.type) {
  CoreNodeType.fraction ||
  CoreNodeType.fractionMixed ||
  CoreNodeType.divide => '\\left(${_childLatex(child)}\\right)',
  _ => _operand(child, 5),
};

/// Бинарная или n-арная операция: первый операнд с приоритетом от [first], остальные — от [rest].
String _infix(CoreNode node, String separator, int first, int rest) {
  if (node.children.isEmpty) return '';
  final parts = [
    for (var i = 0; i < node.children.length; i++)
      _operand(node.children[i], i == 0 ? first : rest),
  ];
  // Незаконченная операция: недостающий операнд — плейсхолдер, как в шаблонах.
  while (parts.length < 2) {
    parts.add(_placeholder);
  }
  return parts.join(separator);
}

/// Штрих производной. Составной операнд — в скобках: `(3x²)″`, не `3x²″`.
String _prime(CoreNode node, String mark) {
  if (node.children.isEmpty) return '';
  final base = _base(node.children.first);
  return base.startsWith(r'\left(') ? '$base$mark' : '{$base}$mark';
}

/// Переменная интегрирования: единственная свободная переменная
/// подынтегрального выражения, иначе `x`.
///
/// Слота дифференциала в узле интеграла нет, а решатель интегрирует по
/// единственной свободной переменной (`solver/integrals.py`). Без этого
/// `∫t²` рисовалось бы с `dx`, хотя считается по `t`.
String _integralVariable(CoreNode node, int index) {
  final integrand = index < node.children.length ? node.children[index] : null;
  final names = <String>{};
  void collect(CoreNode current) {
    // e, π, i — константы и для решателя (`sympy_bridge.py`).
    if (current.type == CoreNodeType.variable &&
        (current.value ?? '').isNotEmpty &&
        !const {'e', 'π', 'i'}.contains(current.value)) {
      names.add(current.value!);
    }
    for (final child in current.children) {
      collect(child);
    }
  }

  if (integrand != null) collect(integrand);
  // ∫tⁿ dt в табличной формуле: n — параметр, переменная — t.
  if (names.length == 1) return _escape(names.single);
  return names.contains('t') && !names.contains('x') ? 't' : 'x';
}

/// Переменная предела: единственная свободная переменная выражения
/// (`n` у последовательности, `b` у lim∫₁ᵇ), иначе `x`.
String _limitVariable(CoreNode node) {
  final names = node.children.length > 1
      ? _freeNames(node.children[1])
      : <String>{};
  return _escape(names.length == 1 ? names.single : 'x');
}

/// Свободные переменные; переменная интегрирования внутри ∫ связана.
Set<String> _freeNames(CoreNode node) {
  if (node.type == CoreNodeType.variable) {
    final name = node.value ?? '';
    return name.isEmpty || const {'e', 'π', 'i'}.contains(name)
        ? <String>{}
        : {name};
  }
  final integrand = switch (node.type) {
    CoreNodeType.integral => 0,
    CoreNodeType.integralDefinite => 2,
    _ => -1,
  };
  final names = <String>{};
  for (var i = 0; i < node.children.length; i++) {
    final inner = _freeNames(node.children[i]);
    if (i == integrand) inner.remove(_integralVariable(node, i));
    names.addAll(inner);
  }
  return names;
}

/// Слова (ответ «Интеграл расходится») — текстом с пробелами; формула
/// вида «∫u dv = uv − ∫v du» — в математике, пробелы узкие.
String _textValue(String value) => RegExp('[а-яА-ЯёЁ]').hasMatch(value)
    ? '\\text{${_escape(value)}}'
    : _escape(value).replaceAll(' ', r'\,');

/// Подставить детей в позиционные плейсхолдеры `$0`, `$1`, ….
/// Нужны ли скобки вокруг аргумента функции.
///
/// `sin x`, `sin 2x`, `ln x`; скобки — для суммы, разности,
/// дроби и отрицательного аргумента. Собственные ограничители (`|x|`,
/// `\sqrt{x}`, `(x+1)`) уже служат скобками.
bool _functionNeedsParens(CoreNode node) {
  switch (node.type) {
    case CoreNodeType.add:
    case CoreNodeType.subtract:
    case CoreNodeType.fraction:
    case CoreNodeType.divide:
    case CoreNodeType.negative:
      return true;
    case CoreNodeType.multiply:
    case CoreNodeType.multiplyImplicit:
    case CoreNodeType.power:
      return node.children.any(_functionNeedsParens);
    default:
      return false;
  }
}

/// Функция с аргументом `node.children[argument]`.
String _function(CoreNode node, String name, {int argument = 0}) {
  if (node.children.length <= argument) return '';
  final child = node.children[argument];
  final body = _childLatex(child);
  return _functionNeedsParens(child)
      ? '$name\\left($body\\right)'
      : '$name $body';
}

String _wrap(CoreNode node, String template) {
  if (node.children.isEmpty) return '';
  // Сначала плейсхолдеры без соответствующего ребёнка: иначе на следующем
  // проходе regex начнёт цеплять `$` уже вставленных формул.
  var out = template.replaceAllMapped(
    RegExp(r'\$(\d+)'),
    (m) => int.parse(m[1]!) < node.children.length ? m[0]! : _placeholder,
  );
  for (var i = 0; i < node.children.length; i++) {
    out = out.replaceAll('\$$i', _childLatex(node.children[i]));
  }
  return out;
}

/// Матрица `size×size` из детей в порядке «по строкам».
///
/// Элементы идут подряд (строка за строкой), как их отдаёт решатель.
/// Недостающие ячейки показываются заглушкой.
String _matrix(CoreNode node, int size, String open, String close) {
  final rows = <String>[];
  for (var row = 0; row < size; row++) {
    final cells = <String>[];
    for (var column = 0; column < size; column++) {
      final index = row * size + column;
      cells.add(
        index < node.children.length
            ? _childLatex(node.children[index])
            : _placeholder,
      );
    }
    rows.add(cells.join(' & '));
  }
  return '$open ${rows.join(r' \\ ')} $close';
}

/// LaTeX ребёнка или заглушка, если узел пуст.
///
/// Рендерим в текущих настройках напрямую (не через [nodeToLatex]): иначе
/// вложенный вызов сбросил бы [_current] к умолчанию.
String _childLatex(CoreNode child) {
  final latex = _styled(child, _nodeBody(child));
  return latex.isEmpty ? _placeholder : latex;
}

/// Матрица переменного размера из строк `MATRIX_ROW`.
String _matrixLatex(CoreNode node, String open, String close) {
  if (node.children.isEmpty) return _placeholder;
  final rows = <String>[];
  for (final row in node.children) {
    final cells = row.type == CoreNodeType.matrixRow ? row.children : [row];
    rows.add(cells.map(_childLatex).join(' & '));
  }
  return '$open ${rows.join(r' \\ ')} $close';
}

/// Соединить детей разделителем, при необходимости обернув в скобки.
String _delimited(CoreNode node, String open, String close, String separator) {
  if (node.children.isEmpty) return _placeholder;
  final body = node.children.map(_childLatex).join(separator);
  if (open.isEmpty && close.isEmpty) return body;
  return '$open $body $close';
}

/// Экранировать символы, которые LaTeX считает служебными.
String _escape(String text) => text
    .replaceAll(r'\', r'\backslash{}')
    .replaceAll('{', r'\{')
    .replaceAll('}', r'\}')
    .replaceAll(r'$', r'\$')
    .replaceAll('&', r'\&')
    .replaceAll('#', r'\#')
    .replaceAll('_', r'\_')
    .replaceAll('%', r'\%');
