/// Rules for reading solution cards as text.
///
/// The functions are pure: they receive the strings the card actually draws
/// (`nodeToLatex(…, LatexOptions.standard)`) and report what looks wrong for a
/// student. `app/test/card_transcript_test.dart` writes the reports with the
/// transcript; `app/test/card_rules_test.dart` pins each rule to a fixed string.
library;

import 'package:flutter_math_fork/flutter_math.dart';

/// One finding of a card rule.
class CardProblem {
  const CardProblem(this.where, this.rule, this.detail);

  /// Place on the card: «ответ», «Шаг 2 Этап 1 · слева», …
  final String where;

  /// `tex-error`, `same`, `repeat`, `text-math`, `heading`, `english`, `dot`.
  final String rule;

  final String detail;

  /// Line of `problems.txt`: `id<TAB>where<TAB>rule<TAB>detail`.
  String line(String id) => '$id\t$where\t$rule\t$detail';

  @override
  String toString() => '$where\t$rule\t$detail';
}

/// Typed mathematics inside a prose part.
///
/// A letter (latin or greek), optional prime, then an operator is an equation
/// (`y = uv`, `v' + p v = 0`, `α = −1`).  A lone `y′` is a normal word, not math.
final RegExp _typedMath = RegExp(
  r'\^|\*|sqrt\(|_\{|\\|ARG\d|\bNone\b|\bnull\b|\?\?|'
  r"[A-Za-z\u0370-\u03ff]\s*[′'’]?\s*[=+<>]",
);

final RegExp _englishWord = RegExp(r'[A-Za-z]{4,}');
final RegExp _dot = RegExp(r'\\cdot\s*(.)', dotAll: true);

/// LaTeX that the app's TeX parser cannot read (the card then shows plain text).
String? texError(String latex) => Math.tex(latex).parseError?.toString();

/// A formula the student sees must parse.
List<CardProblem> formulaProblems(String where, String latex) {
  if (latex.trim().isEmpty) return const [];
  final error = texError(latex);
  if (error == null) return const [];
  return [CardProblem(where, 'tex-error', '$latex :: $error')];
}

/// `true` when the text part contains typed mathematics instead of prose.
bool hasTypedMath(String text) => _typedMath.hasMatch(text);

/// The first latin word of four letters or more (a word that missed translation).
String? firstEnglishWord(String text) =>
    _englishWord.firstMatch(text)?.group(0);

/// Both sides of a stage draw the same formula: the step shows no change.
bool sameFormula(String? left, String? right) =>
    left != null && right != null && left.isNotEmpty && left == right;

/// A formula part of the stage text repeats the stage's left or right formula.
bool repeatsFormula(String part, String? left, String? right) =>
    part.isNotEmpty && (part == left || part == right);

/// `\cdot` between factors where the right factor is not a number.
///
/// The book writes `Ce^{-x}` and `2x` without a dot; a dot is only expected
/// before a numeric factor (`x \cdot 2^{x}`).
List<String> misplacedDots(String latex) => [
  for (final match in _dot.allMatches(latex))
    if (!_startsWithNumber(match.group(1)!)) match.group(0)!,
];

/// `true` when `\cdot` is followed by something that is not a digit or a minus.
bool hasMisplacedDot(String latex) => misplacedDots(latex).isNotEmpty;

bool _startsWithNumber(String char) => RegExp(r'[0-9\-−]').hasMatch(char);

/// A heading the app falls back to («Преобразование») tells the student nothing.
bool isFallbackHeading(String heading) {
  final text = heading.trim();
  return text.isEmpty || text == 'Преобразование';
}

/// Problems of the step headings of one card.
List<CardProblem> headingProblems(
  List<({String where, String heading})> steps,
) {
  final out = <CardProblem>[];
  for (var i = 0; i < steps.length; i++) {
    final heading = steps[i].heading.trim();
    if (isFallbackHeading(heading)) {
      out.add(
        CardProblem(
          steps[i].where,
          'heading',
          heading.isEmpty
              ? 'пустой заголовок показан как «Преобразование»'
              : 'заголовок «Преобразование»',
        ),
      );
    }
    if (i > 0 && heading.isNotEmpty && heading == steps[i - 1].heading.trim()) {
      out.add(
        CardProblem(steps[i].where, 'heading', 'два шага подряд: «$heading»'),
      );
    }
  }
  return out;
}

/// Problems of one prose part: typed math and untranslated words.
List<CardProblem> textProblems(String where, String text) => [
  if (hasTypedMath(text)) CardProblem(where, 'text-math', '«${_clip(text)}»'),
  ...englishProblems(where, text),
];

/// Untranslated latin words of one prose part.
List<CardProblem> englishProblems(String where, String text) => [
  if (firstEnglishWord(text) case final word?)
    CardProblem(where, 'english', '«$word» в «${_clip(text)}»'),
];

/// Problems of a formula that is a part of the stage text.
List<CardProblem> partProblems(String where, String latex) => [
  ...formulaProblems(where, latex),
  if (hasMisplacedDot(latex))
    CardProblem(where, 'dot', '«${_clip(latex, 200)}»'),
];

/// `same` + `dot` of the two stage formulas.
List<CardProblem> stageFormulaProblems(
  String where, {
  String? left,
  String? right,
}) => [
  ...formulaProblems('$where · слева', left ?? ''),
  ...formulaProblems('$where · справа', right ?? ''),
  if (sameFormula(left, right))
    CardProblem(
      where,
      'same',
      'слева и справа одна формула: «${_clip(left!)}»',
    ),
];

/// A formula part repeats the stage's left/right formula.
List<CardProblem> repeatProblems(
  String where,
  Iterable<String> parts, {
  String? left,
  String? right,
}) => [
  for (final part in parts)
    if (repeatsFormula(part, left, right))
      CardProblem(
        where,
        'repeat',
        'часть «${_clip(part)}» повторяет формулу этапа',
      ),
];

/// `dot` problem of the answer card.
List<CardProblem> answerProblems(String where, String latex) => [
  ...formulaProblems(where, latex),
  if (hasMisplacedDot(latex))
    CardProblem(where, 'dot', '«${_clip(latex, 200)}»'),
];

String _clip(String text, [int limit = 120]) {
  final flat = text.replaceAll(RegExp(r'\s+'), ' ').trim();
  return flat.length <= limit ? flat : '${flat.substring(0, limit)}…';
}
