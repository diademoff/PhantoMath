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
String nodeToLatex(CoreNode node, [LatexOptions options = LatexOptions.standard]) {
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
/// её на выбранный символ (`DecimalSeparator` в профиле Photomath).
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
      return _escape(_number(node.value ?? ''));
    case CoreNodeType.variable:
      return _escape(node.value ?? '');

    // ── знаки ───────────────────────────────────────────────────────
    case CoreNodeType.negative:
      return _wrap(node, r'-$0');

    case CoreNodeType.positive:
      return _wrap(node, r'+$0');

    // ── бинарные операции ───────────────────────────────────────────
    case CoreNodeType.add:
      return _wrap(node, r'$0 + $1');

    case CoreNodeType.subtract:
      return _wrap(node, r'$0 - $1');

    case CoreNodeType.multiply:
      return _wrap(node, r'$0 \cdot $1');

    case CoreNodeType.multiplyImplicit:
      return _wrap(node, r'$0 $1');

    case CoreNodeType.divide:
      return _wrap(node, r'\frac{$0}{$1}');

    case CoreNodeType.power:
      return _wrap(node, r'{$0}^{$1}');

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
      return _wrap(node, r'\sin\left($0\right)');

    case CoreNodeType.cos:
      return _wrap(node, r'\cos\left($0\right)');

    case CoreNodeType.tan:
      return _wrap(node, r'\tan\left($0\right)');

    case CoreNodeType.cot:
      return _wrap(node, r'\cot\left($0\right)');

    case CoreNodeType.sec:
      return _wrap(node, r'\sec\left($0\right)');

    case CoreNodeType.csc:
      return _wrap(node, r'\csc\left($0\right)');

    case CoreNodeType.asin:
      return _wrap(node, r'\arcsin\left($0\right)');

    case CoreNodeType.acos:
      return _wrap(node, r'\arccos\left($0\right)');

    case CoreNodeType.atan:
      return _wrap(node, r'\arctan\left($0\right)');

    case CoreNodeType.acot:
      return _wrap(node, r'\mathrm{acot}\left($0\right)');

    case CoreNodeType.asec:
      return _wrap(node, r'\mathrm{asec}\left($0\right)');

    case CoreNodeType.acsc:
      return _wrap(node, r'\mathrm{acsc}\left($0\right)');

    case CoreNodeType.sinh:
      return _wrap(node, r'\sinh\left($0\right)');

    case CoreNodeType.cosh:
      return _wrap(node, r'\cosh\left($0\right)');

    case CoreNodeType.tanh:
      return _wrap(node, r'\tanh\left($0\right)');

    case CoreNodeType.coth:
      return _wrap(node, r'\coth\left($0\right)');

    case CoreNodeType.sech:
      return _wrap(node, r'\mathrm{sech}\left($0\right)');

    case CoreNodeType.csch:
      return _wrap(node, r'\mathrm{csch}\left($0\right)');

    case CoreNodeType.asinh:
      return _wrap(node, r'\mathrm{asinh}\left($0\right)');

    case CoreNodeType.acosh:
      return _wrap(node, r'\mathrm{acosh}\left($0\right)');

    case CoreNodeType.atanh:
      return _wrap(node, r'\mathrm{atanh}\left($0\right)');

    case CoreNodeType.acoth:
      return _wrap(node, r'\mathrm{acoth}\left($0\right)');

    case CoreNodeType.asech:
      return _wrap(node, r'\mathrm{asech}\left($0\right)');

    case CoreNodeType.acsch:
      return _wrap(node, r'\mathrm{acsch}\left($0\right)');

    case CoreNodeType.log:
      return _wrap(node, r'\log_{$1}\left($0\right)');

    case CoreNodeType.log10:
      return _wrap(node, r'\log_{10}\left($0\right)');

    case CoreNodeType.ln:
      return _wrap(node, r'\ln\left($0\right)');

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
      return _wrap(node, r'\frac{d\,$1}{d\,$0}');

    case CoreNodeType.prime:
    case CoreNodeType.derivation1Prime:
      return _wrap(node, r"$0'");

    case CoreNodeType.derivation2Prime:
      return _wrap(node, r"$0''");

    case CoreNodeType.integral:
      return _wrap(node, r'\int $0\,dx');

    case CoreNodeType.integralDefinite:
      return _wrap(node, r'\int_{$0}^{$1} $2\,dx');

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
      return _wrap(node, r'\lim_{x \to $0} $1');

    case CoreNodeType.sigmaDefinite:
      return _wrap(node, r'\sum_{n=$0}^{$1} $2');

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

    case CoreNodeType.partialPermutation:
      return _wrap(node, r'{}^{$0}P_{$1}');

    case CoreNodeType.variation:
      return _wrap(node, r'{}^{$0}A_{$1}');

    // ── матрицы ─────────────────────────────────────────────────────
    case CoreNodeType.determinant2:
      return _matrix(node, 2, r'\begin{vmatrix}', r'\end{vmatrix}');

    case CoreNodeType.determinant3:
      return _matrix(node, 3, r'\begin{vmatrix}', r'\end{vmatrix}');

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
      return _wrap(node, r'$0 = $1');

    case CoreNodeType.notEquals:
      return _wrap(node, r'$0 \ne $1');

    case CoreNodeType.lessThan:
      return _wrap(node, r'$0 < $1');

    case CoreNodeType.lessThanEqual:
      return _wrap(node, r'$0 \le $1');

    case CoreNodeType.greaterThan:
      return _wrap(node, r'$0 > $1');

    case CoreNodeType.greaterThanEqual:
      return _wrap(node, r'$0 \ge $1');

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
      if (node.children.isEmpty) return _escape(node.value ?? '');
      return node.children.map(_childLatex).join();

    case CoreNodeType.textKey:
      return _escape(node.value ?? '');

    // ── упорядочивание ──────────────────────────────────────────────
    case CoreNodeType.order:
      return _delimited(node, '', '', r',\ ');

    // ── составные ───────────────────────────────────────────────────
    case CoreNodeType.list:
      if (node.children.isEmpty) return _placeholder;
      return [
        for (final child in node.children) _childLatex(child),
      ].join(r',\quad ');

    case CoreNodeType.system:
      return _wrap(node, r'\begin{cases}$0\end{cases}');

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

/// Подставить детей в шаблон по позиционным плейсхолдерам.
String _wrap(CoreNode node, String template) {  if (node.children.isEmpty) return '';
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
/// Элементы идут подряд (строка за строкой) — так же, как в нативном
/// решателе. Недостающие ячейки показываются заглушкой.
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
