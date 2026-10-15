/// Приведение узла к LaTeX.
///
/// Рендер формул делает `flutter_math_fork`; наша задача — превратить
/// `CoreNode` в строку, которую он понимает. Писать свой рентер дробей,
/// корней и матриц — отдельный проект, поэтому здесь только перевод.
///
/// Шаблон использует позиционные плейсхолдеры `$0`, `$1`, … — по одному
/// на каждого ребёнка. Это позволяет разводить аргументы по разным
/// местам: `\frac{$0}{$1}` кладёт первого в числитель, второго — в
/// знаменатель. Каждый аргумент оборачивается в `$…$`, чтобы движок
/// понимал, где математика.
///
/// Незавершённый узел (ребёнок без значения) даёт `\square`: в интерфейсе
/// видно, что выражение ждёт продолжения ввода, а не молчаливый пропуск.
library;

import '../model/core_node.dart';

const String _placeholder = r'\square';

/// Собрать LaTeX для узла.
///
/// Возвращает пустую строку для листьев без значения и для `EMPTY`:
/// вызывающий покажет заглушку.
String nodeToLatex(CoreNode node) {
  switch (node.type) {
    // ── листья ──────────────────────────────────────────────────────
    case CoreNodeType.constant:
    case CoreNodeType.variable:
    case CoreNodeType.text:
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

    // ── исчисление ──────────────────────────────────────────────────
    case CoreNodeType.derivation:
    case CoreNodeType.derivation1:
      return _wrap(node, r'\frac{d}{dx}\left($0\right)');

    case CoreNodeType.integral:
      return _wrap(node, r'\int $0\,dx');

    case CoreNodeType.integralDefinite:
      return _wrap(node, r'\int_{$0}^{$1} $2\,dx');

    case CoreNodeType.limit:
      return _wrap(node, r'\lim_{x \to $0} $1');

    case CoreNodeType.sigmaDefinite:
      return _wrap(node, r'\sum_{n=$0}^{$1} $2');

    // ── комбинаторика ───────────────────────────────────────────────
    case CoreNodeType.choose:
      return _wrap(node, r'\binom{$0}{$1}');

    case CoreNodeType.partialPermutation:
      return _wrap(node, r'{}^{$0}P_{$1}');

    case CoreNodeType.variation:
      return _wrap(node, r'{}^{$0}A_{$1}');

    // ── матрицы ─────────────────────────────────────────────────────
    case CoreNodeType.determinant2:
      return _matrix(node, 2, r'\begin{vmatrix}', r'\end{vmatrix}');

    case CoreNodeType.determinant3:
      return _matrix(node, 3, r'\begin{vmatrix}', r'\end{vmatrix}');

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

    // ── составные ───────────────────────────────────────────────────
    case CoreNodeType.list:
      if (node.children.isEmpty) return _placeholder;
      return [
        for (final child in node.children) _asMath(child),
      ].join(r',\quad ');

    case CoreNodeType.system:
      return _wrap(node, r'\begin{cases}$0\end{cases}');

    case CoreNodeType.empty:
      return '';
  }
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
    out = out.replaceAll('\$$i', _asMath(node.children[i]));
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
            ? _asMath(node.children[index])
            : _placeholder,
      );
    }
    rows.add(cells.join(' & '));
  }
  return '$open ${rows.join(r' \\ ')} $close';
}

/// Обернуть узел в `$…$`, если он ещё не обёрнут.
String _asMath(CoreNode child) {  final latex = nodeToLatex(child);
  if (latex.isEmpty) return _placeholder;
  if (latex.startsWith(r'$') && latex.endsWith(r'$')) return latex;
  return '\$$latex\$';
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
