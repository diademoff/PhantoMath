/// A display formula that breaks across lines instead of scrolling sideways.
///
/// A textbook breaks a long formula before its top-level relations and `+`/`-`
/// and starts the continuation line with the operator; a list drawn with
/// `,\quad` gets one item per line. Only a single unbreakable piece is shrunk
/// (to at least [minFormulaScale]); if even that does not fit, the formula keeps
/// the horizontal scroll and fades at the cut edge so the student sees that
/// there is more to the right.
///
/// Short formulas are drawn as one `Math`, exactly as before.
library;

import 'dart:math' as math;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_math_fork/flutter_math.dart';

/// How a formula fitted its box.
enum FormulaFit {
  /// Short enough: one line, exactly as before.
  single,

  /// Broken at top-level relations/`±`, or one list item per line.
  broken,

  /// One unbreakable piece, shrunk but not below [minFormulaScale].
  scaled,

  /// Still wider than the box: horizontal scroll with a fade at the cut edge.
  scrolled,
}

/// The smallest scale a formula may be shrunk to (70 % of the font size).
const double minFormulaScale = 0.7;

/// One piece of a broken formula.
class FormulaPiece {
  const FormulaPiece(this.latex, {this.space = 0, this.breaksLine = false});

  final String latex;

  /// Space before the piece when it follows another one on the same line, in em
  /// (`\;` for a relation, `\:` for a binary operator — TeX's own skips).
  final double space;

  /// The piece starts a line of its own: the next item of a `,\quad` list.
  final bool breaksLine;

  @override
  String toString() => latex;
}

/// A formula split where a book would break it.
class FormulaParts {
  const FormulaParts(this.pieces);

  final List<FormulaPiece> pieces;

  bool get breakable => pieces.length > 1;

  static const FormulaParts none = FormulaParts(<FormulaPiece>[]);
}

const double _relationSpace = 5 / 18;
const double _binarySpace = 4 / 18;

const Set<String> _relationMacros = {
  'le',
  'leq',
  'ge',
  'geq',
  'ne',
  'neq',
  'approx',
  'equiv',
  'sim',
  'to',
  'rightarrow',
  'Rightarrow',
  'implies',
  'in',
  'notin',
  'subset',
  'subseteq',
  'supset',
  'supseteq',
  'propto',
  'leftrightarrow',
};

const Set<String> _binaryMacros = {'pm', 'mp'};

bool _isLetter(int code) =>
    (code >= 0x41 && code <= 0x5a) || (code >= 0x61 && code <= 0x7a);

/// A macro at [start] (which must be a backslash): name and the index after it.
/// An escaped character (`\,`, `\{`, `\%`) has an empty name.
({String name, int next}) _macro(String latex, int start) {
  var i = start + 1;
  final n = latex.length;
  if (i >= n) return (name: '', next: n);
  if (!_isLetter(latex.codeUnitAt(i))) return (name: '', next: i + 1);
  final from = i;
  while (i < n && _isLetter(latex.codeUnitAt(i))) {
    i++;
  }
  return (name: latex.substring(from, i), next: i);
}

/// Splits a display formula the way a book breaks it.
///
/// Pieces of an operator split start with the operator (`= …`, `+ …`, `− …`);
/// every item of a `,\quad` list starts a line of its own, and a long item may
/// still be broken at its own operators. A matrix or a `cases` block is one
/// piece: it is never broken.
FormulaParts splitFormula(String latex) {
  final text = latex.trim();
  if (text.isEmpty) return FormulaParts.none;

  final items = _listStarts(text);
  final pieces = <FormulaPiece>[];
  if (items.isNotEmpty) {
    var from = 0;
    var item = 0;
    for (final start in [...items, text.length]) {
      final source = _cleanItem(text.substring(from, start));
      if (source.isNotEmpty) {
        _splitOperators(source, pieces, breaksLine: item > 0);
        item++;
      }
      from = start;
    }
    if (pieces.length > 1) return FormulaParts(pieces);
  }

  _splitOperators(text, pieces, breaksLine: false);
  return pieces.length > 1 ? FormulaParts(pieces) : FormulaParts.none;
}

/// Appends the operator pieces of [source]; the first one may start a line.
void _splitOperators(
  String source,
  List<FormulaPiece> pieces, {
  required bool breaksLine,
}) {
  final cuts = _operatorCuts(source);
  final bounds = [0, ...cuts.map((cut) => cut.position), source.length];
  var first = true;
  for (var i = 0; i + 1 < bounds.length; i++) {
    final piece = source.substring(bounds[i], bounds[i + 1]).trim();
    if (piece.isEmpty) continue;
    // A piece starting with `+`/`−` would draw a unary sign (no space after
    // it); `{}` keeps it binary, and TeX then spaces it on both sides itself.
    final binary = i > 0 && cuts[i - 1].space == _binarySpace;
    pieces.add(
      FormulaPiece(
        binary ? '{}$piece' : piece,
        space: i == 0 || binary ? 0 : cuts[i - 1].space,
        breaksLine: first && breaksLine,
      ),
    );
    first = false;
  }
}

String _cleanItem(String item) =>
    item.replaceFirst(RegExp(r',\s*$'), '').trim();

/// Indexes where a list item after `,\quad` starts.
List<int> _listStarts(String latex) {
  final starts = <int>[];
  var braces = 0;
  var delimiters = 0;
  var i = 0;
  final n = latex.length;
  while (i < n) {
    final char = latex[i];
    if (char == r'\') {
      final macro = _macro(latex, i);
      if (macro.name == 'begin') return const [];
      if (macro.name == 'left') {
        delimiters++;
      } else if (macro.name == 'right' && delimiters > 0) {
        delimiters--;
      }
      i = macro.next;
      continue;
    }
    if (char == '{') {
      braces++;
    } else if (char == '}') {
      if (braces > 0) braces--;
    } else if (char == ',' && braces == 0 && delimiters == 0) {
      var j = i + 1;
      while (j < n && latex[j].trim().isEmpty) {
        j++;
      }
      if (j < n && latex[j] == r'\') {
        final macro = _macro(latex, j);
        if (macro.name == 'quad' || macro.name == 'qquad') {
          starts.add(macro.next);
          i = macro.next;
          continue;
        }
      }
    }
    i++;
  }
  return starts;
}

class _Cut {
  const _Cut(this.position, this.space);
  final int position;
  final double space;
}

/// Indexes where a source line may break: before a top-level relation or a
/// binary `+`/`-`.
List<_Cut> _operatorCuts(String latex) {
  final cuts = <_Cut>[];
  var braces = 0;
  var delimiters = 0;
  var i = 0;
  // Whether the previous token can end an operand: `-` there is binary.
  var operand = false;
  final n = latex.length;
  while (i < n) {
    final char = latex[i];
    if (char == r'\') {
      final macro = _macro(latex, i);
      if (macro.name == 'begin') return const [];
      if (macro.name == 'left') {
        delimiters++;
        operand = false;
        i = macro.next;
        continue;
      }
      if (macro.name == 'right') {
        if (delimiters > 0) delimiters--;
        operand = true;
        i = macro.next;
        continue;
      }
      if (macro.name.isEmpty) {
        // A spacing macro (`\,`, `\;`) or an escaped character: no operand.
        i = macro.next;
        continue;
      }
      if (braces == 0 && delimiters == 0) {
        if (_relationMacros.contains(macro.name)) {
          cuts.add(_Cut(i, _relationSpace));
          operand = false;
          i = macro.next;
          continue;
        }
        if (_binaryMacros.contains(macro.name) && operand) {
          cuts.add(_Cut(i, _binarySpace));
          operand = false;
          i = macro.next;
          continue;
        }
      }
      operand = macro.name != 'cdot' && macro.name != 'times';
      i = macro.next;
      continue;
    }
    if (char == '{') {
      braces++;
      operand = false;
      i++;
      continue;
    }
    if (char == '}') {
      if (braces > 0) braces--;
      operand = true;
      i++;
      continue;
    }
    if (braces == 0 && delimiters == 0) {
      if (char == '=' || char == '<' || char == '>') {
        cuts.add(_Cut(i, _relationSpace));
        operand = false;
        i++;
        continue;
      }
      if (char == '+' || char == '-' || char == '−') {
        if (operand) cuts.add(_Cut(i, _binarySpace));
        operand = false;
        i++;
        continue;
      }
      if (char == '(' || char == '[') {
        operand = false;
        i++;
        continue;
      }
      if (char == ')' || char == ']') {
        operand = true;
        i++;
        continue;
      }
      if (',;:*!/^_'.contains(char)) {
        operand = false;
        i++;
        continue;
      }
    }
    if (char.trim().isNotEmpty) operand = true;
    i++;
  }
  return cuts;
}

final Map<String, FormulaParts> _plans = <String, FormulaParts>{};

/// The break plan of [latex]: a formula without TeX break points stays one piece.
FormulaParts _plan(String latex) {
  final cached = _plans[latex];
  if (cached != null) return cached;
  var parts = splitFormula(latex);
  if (parts.breakable) {
    // TeX's own break points decide whether the operator split is legitimate
    // (`\nobreak`, a relation inside a group): a formula without them is one
    // piece that may only be scaled or scrolled.
    final breaks = Math.tex(latex).texBreak();
    if (breaks.parts.length <= 1) parts = FormulaParts.none;
  }
  if (_plans.length > 256) _plans.clear();
  _plans[latex] = parts;
  return parts;
}

/// A display formula that fits its box: broken, scaled, or scrolled with a hint.
class BreakableFormula extends StatefulWidget {
  const BreakableFormula({
    super.key,
    required this.latex,
    this.fontSize = 22,
    this.mathStyle = MathStyle.display,
    this.transform,
    this.padding = const EdgeInsets.symmetric(vertical: 4),
    this.minScale = minFormulaScale,
  });

  /// How far the formula may shrink before it scrolls (the answer shrinks more).
  final double minScale;

  final String latex;
  final double fontSize;
  final MathStyle mathStyle;

  /// Maps the latex before it is drawn (the theme accent of `\textcolor`).
  final String Function(String latex)? transform;

  final EdgeInsetsGeometry padding;

  @override
  State<BreakableFormula> createState() => _BreakableFormulaState();
}

class _BreakableFormulaState extends State<BreakableFormula> {
  FormulaFit _fit = FormulaFit.single;

  void _onFit(FormulaFit fit) {
    if (!mounted || fit == _fit) return;
    setState(() => _fit = fit);
  }

  @override
  Widget build(BuildContext context) {
    final transform = widget.transform;
    String tex(String value) => transform == null ? value : transform(value);
    final style = TextStyle(
      fontSize: widget.fontSize,
      color: Theme.of(context).colorScheme.onSurface,
    );

    final parts = _plan(widget.latex);

    final whole = _MathPiece(
      latex: tex(widget.latex),
      style: style,
      mathStyle: widget.mathStyle,
      fallback: widget.latex,
    );
    final pieces = parts.breakable
        ? [
            for (final piece in parts.pieces)
              _MathPiece(
                latex: tex(piece.latex),
                style: style,
                mathStyle: widget.mathStyle,
                fallback: piece.latex,
              ),
          ]
        : const <Widget>[];

    return LayoutBuilder(
      builder: (context, constraints) {
        final flow = FormulaFlow(
          maxWidth: constraints.maxWidth,
          fontSize: widget.fontSize,
          spaces: [for (final piece in parts.pieces) piece.space],
          breaks: [for (final piece in parts.pieces) piece.breaksLine],
          fit: _fit,
          onFit: _onFit,
          minScale: widget.minScale,
          children: [whole, ...pieces],
        );
        final view = _fit == FormulaFit.scrolled
            ? ScrollFade(
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: flow,
                ),
              )
            : flow;
        return widget.padding == EdgeInsets.zero
            ? view
            : Padding(padding: widget.padding, child: view);
      },
    );
  }
}

class _MathPiece extends StatelessWidget {
  const _MathPiece({
    required this.latex,
    required this.style,
    required this.mathStyle,
    required this.fallback,
  });

  final String latex;
  final TextStyle style;
  final MathStyle mathStyle;
  final String fallback;

  @override
  Widget build(BuildContext context) => Math.tex(
    latex,
    mathStyle: mathStyle,
    textStyle: style,
    onErrorFallback: (_) =>
        Text(fallback, style: Theme.of(context).textTheme.bodyLarge),
  );
}

class FormulaParentData extends ContainerBoxParentData<RenderBox> {
  double scale = 1;
}

/// Lays out a whole formula and its pieces, and reports how it had to fit.
class FormulaFlow extends MultiChildRenderObjectWidget {
  const FormulaFlow({
    super.key,
    required this.maxWidth,
    required this.fontSize,
    required this.spaces,
    required this.breaks,
    required this.fit,
    required this.onFit,
    this.minScale = minFormulaScale,
    super.children,
  });

  final double minScale;

  final double maxWidth;
  final double fontSize;
  final List<double> spaces;

  /// Whether each piece starts a line of its own (a list item).
  final List<bool> breaks;

  final FormulaFit fit;
  final ValueChanged<FormulaFit>? onFit;

  @override
  RenderFormulaFlow createRenderObject(BuildContext context) =>
      RenderFormulaFlow()
        ..maxWidth = maxWidth
        ..minScale = minScale
        ..fontSize = fontSize
        ..spaces = spaces
        ..breaks = breaks
        ..expectedFit = fit
        ..onFit = onFit;

  @override
  void updateRenderObject(
    BuildContext context,
    RenderFormulaFlow renderObject,
  ) {
    renderObject
      ..maxWidth = maxWidth
      ..minScale = minScale
      ..fontSize = fontSize
      ..spaces = spaces
      ..breaks = breaks
      ..expectedFit = fit
      ..onFit = onFit;
  }
}

class RenderFormulaFlow extends RenderBox
    with
        ContainerRenderObjectMixin<RenderBox, FormulaParentData>,
        RenderBoxContainerDefaultsMixin<RenderBox, FormulaParentData> {
  double get maxWidth => _maxWidth;
  double _maxWidth = 0;
  set maxWidth(double value) {
    if (_maxWidth == value) return;
    _maxWidth = value;
    markNeedsLayout();
  }

  double get minScale => _minScale;
  double _minScale = minFormulaScale;
  set minScale(double value) {
    if (_minScale == value) return;
    _minScale = value;
    markNeedsLayout();
  }

  double get fontSize => _fontSize;
  double _fontSize = 22;
  set fontSize(double value) {
    if (_fontSize == value) return;
    _fontSize = value;
    markNeedsLayout();
  }

  List<double> get spaces => _spaces;
  List<double> _spaces = const [];
  set spaces(List<double> value) {
    if (listEquals(_spaces, value)) return;
    _spaces = value;
    markNeedsLayout();
  }

  List<bool> get breaks => _breaks;
  List<bool> _breaks = const [];
  set breaks(List<bool> value) {
    if (listEquals(_breaks, value)) return;
    _breaks = value;
    markNeedsLayout();
  }

  FormulaFit get expectedFit => _expectedFit;
  FormulaFit _expectedFit = FormulaFit.single;
  set expectedFit(FormulaFit value) {
    if (_expectedFit == value) return;
    _expectedFit = value;
    markNeedsLayout();
  }

  ValueChanged<FormulaFit>? onFit;

  /// How the formula was fitted in the last layout (read by the layout test).
  FormulaFit get fit => _fit;
  FormulaFit _fit = FormulaFit.single;

  /// Number of lines of the last layout (1 for a single line).
  int get lines => _lines;
  int _lines = 1;

  /// The children actually painted: the whole formula or its pieces.
  final List<RenderBox> _painted = <RenderBox>[];

  /// How many `Math` widgets the formula paints (1 when it stays one formula).
  int get painted => _painted.length;

  @override
  void setupParentData(RenderBox child) {
    if (child.parentData is! FormulaParentData) {
      child.parentData = FormulaParentData();
    }
  }

  List<RenderBox> _children() {
    final out = <RenderBox>[];
    RenderBox? child = firstChild;
    while (child != null) {
      out.add(child);
      child = childAfter(child);
    }
    return out;
  }

  @override
  void performLayout() {
    final children = _children();
    if (children.isEmpty) {
      size = constraints.smallest;
      return;
    }
    // Every child is laid out (the semantics tree asserts it), so a breakable
    // formula costs one layout per piece even while it fits on one line.
    for (final child in children) {
      child.layout(const BoxConstraints(), parentUsesSize: true);
    }
    final whole = children.first;
    final wholeSize = whole.size;
    final available = _maxWidth.isFinite ? _maxWidth : constraints.maxWidth;
    final fits = !available.isFinite || wholeSize.width <= available + .5;
    final pieces = children.length > 1
        ? children.sublist(1)
        : const <RenderBox>[];

    _painted.clear();
    var outSize = wholeSize;
    var fit = FormulaFit.single;
    var lineCount = 1;

    void place(int index, Offset offset, double scale) {
      final data = children[index].parentData! as FormulaParentData;
      data.offset = offset;
      data.scale = scale;
      _painted.add(children[index]);
    }

    if (fits) {
      place(0, Offset.zero, 1);
    } else if (pieces.length > 1) {
      final lines = _packLines(pieces, available);
      final widths = [for (final line in lines) _lineWidth(pieces, line)];
      final scales = [
        for (final width in widths) width > available ? available / width : 1.0,
      ];
      final smallest = scales.reduce(math.min);
      if (lines.length > 1 && smallest >= minScale) {
        fit = FormulaFit.broken;
        lineCount = lines.length;
        var top = 0.0;
        for (var i = 0; i < lines.length; i++) {
          final line = lines[i];
          final scale = scales[i];
          final baselines = [
            for (final index in line) _baseline(pieces[index]),
          ];
          final baseline = baselines.reduce(math.max);
          final height = [
            for (var k = 0; k < line.length; k++)
              baseline - baselines[k] + pieces[line[k]].size.height,
          ].reduce(math.max);
          var left = 0.0;
          for (var k = 0; k < line.length; k++) {
            final index = line[k];
            if (k > 0) left += _space(index) * _fontSize;
            place(
              index + 1,
              Offset(left * scale, top + (baseline - baselines[k]) * scale),
              scale,
            );
            left += pieces[index].size.width;
          }
          top +=
              height * scale +
              (i + 1 < lines.length ? _gapAt(lines[i + 1]) : 0);
        }
        outSize = Size(available, top);
      } else if (lines.length == 1 && scales.first >= minScale) {
        final scale = scales.first;
        fit = scale < 1 ? FormulaFit.scaled : FormulaFit.single;
        place(0, Offset.zero, scale);
        outSize = scale < 1
            ? Size(wholeSize.width * scale, wholeSize.height * scale)
            : wholeSize;
      } else {
        final scale = available / wholeSize.width;
        if (scale >= minScale) {
          fit = FormulaFit.scaled;
          place(0, Offset.zero, scale);
          outSize = Size(wholeSize.width * scale, wholeSize.height * scale);
        } else {
          fit = FormulaFit.scrolled;
          place(0, Offset.zero, 1);
          outSize = wholeSize;
        }
      }
    } else {
      final scale = available / wholeSize.width;
      if (scale >= minScale) {
        fit = FormulaFit.scaled;
        place(0, Offset.zero, scale);
        outSize = Size(wholeSize.width * scale, wholeSize.height * scale);
      } else {
        fit = FormulaFit.scrolled;
        place(0, Offset.zero, 1);
        outSize = wholeSize;
      }
    }

    size = constraints.constrain(outSize);
    _fit = fit;
    _lines = lineCount;
    if (fit != _expectedFit) {
      final callback = onFit;
      if (callback != null) {
        // The parent must rebuild with (or without) the scroll view; layout
        // cannot call setState directly.
        WidgetsBinding.instance.addPostFrameCallback((_) => callback(fit));
      }
    }
  }

  /// Greedy packing of the pieces into lines that fit [available].
  List<List<int>> _packLines(List<RenderBox> pieces, double available) {
    final lines = <List<int>>[];
    var current = <int>[0];
    var width = pieces.first.size.width;
    for (var i = 1; i < pieces.length; i++) {
      final pieceWidth = pieces[i].size.width;
      final gap = _space(i) * _fontSize;
      if (!_breaksLine(i) && width + gap + pieceWidth <= available + .5) {
        current.add(i);
        width += gap + pieceWidth;
      } else {
        lines.add(current);
        current = [i];
        width = pieceWidth;
      }
    }
    lines.add(current);
    return lines;
  }

  double _lineWidth(List<RenderBox> pieces, List<int> line) {
    var width = 0.0;
    for (var k = 0; k < line.length; k++) {
      if (k > 0) width += _space(line[k]) * _fontSize;
      width += pieces[line[k]].size.width;
    }
    return width;
  }

  double _space(int piece) => piece < _spaces.length ? _spaces[piece] : 0;

  bool _breaksLine(int piece) => piece < _breaks.length && _breaks[piece];

  /// A list item starts a new paragraph; a broken formula continues tightly.
  double _gapAt(List<int> line) =>
      _breaksLine(line.first) ? _fontSize * .3 : _fontSize * .08;

  double _baseline(RenderBox child) =>
      child.getDistanceToBaseline(TextBaseline.alphabetic) ??
      child.size.height * .75;

  @override
  void paint(PaintingContext context, Offset offset) {
    for (final child in _painted) {
      final data = child.parentData! as FormulaParentData;
      if (data.scale == 1) {
        context.paintChild(child, offset + data.offset);
      } else {
        context.canvas.save();
        context.canvas.translate(
          offset.dx + data.offset.dx,
          offset.dy + data.offset.dy,
        );
        context.canvas.scale(data.scale);
        context.paintChild(child, Offset.zero);
        context.canvas.restore();
      }
    }
  }

  @override
  bool hitTestChildren(BoxHitTestResult result, {required Offset position}) {
    for (final child in _painted) {
      final data = child.parentData! as FormulaParentData;
      final local = (position - data.offset) / data.scale;
      if (child.hitTest(result, position: local)) return true;
    }
    return false;
  }
}

/// The horizontal scroll a formula keeps when nothing else fits, with a fade at
/// the edge that hides a part of it.
class ScrollFade extends StatefulWidget {
  const ScrollFade({super.key, required this.child});

  final Widget child;

  @override
  State<ScrollFade> createState() => _ScrollFadeState();
}

class _ScrollFadeState extends State<ScrollFade> {
  bool _more = false;
  bool _less = false;

  void _update(ScrollMetrics metrics) {
    final more = metrics.maxScrollExtent - metrics.pixels > 1;
    final less = metrics.pixels > 1;
    if (more == _more && less == _less) return;
    setState(() {
      _more = more;
      _less = less;
    });
  }

  @override
  Widget build(BuildContext context) =>
      NotificationListener<ScrollMetricsNotification>(
        onNotification: (notification) {
          _update(notification.metrics);
          return false;
        },
        child: NotificationListener<ScrollNotification>(
          onNotification: (notification) {
            _update(notification.metrics);
            return false;
          },
          child: ShaderMask(
            blendMode: BlendMode.dstIn,
            shaderCallback: (rect) => LinearGradient(
              colors: [
                _less ? Colors.transparent : Colors.white,
                Colors.white,
                _more ? Colors.transparent : Colors.white,
              ],
              stops: const [0, .88, 1],
            ).createShader(rect),
            child: widget.child,
          ),
        ),
      );
}
