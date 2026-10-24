import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import '../api/solver_api.dart';
import '../i18n.dart';
import '../model/core_node.dart';
import '../render/division_trace.dart';
import '../render/highlight.dart';
import '../render/latex.dart';
import '../settings/settings.dart';
import 'division_lesson.dart';
import 'formula_break.dart';
import 'transformation_lesson.dart';

/// The step screen: the answer, then the steps as quiet grey rows with
/// one open white card; «Далее» stays at the bottom of the screen, so the
/// student's thumb never chases a button that moves with the card.
class VerticalResult extends StatefulWidget {
  const VerticalResult({
    super.key,
    required this.result,
    required this.latexOptions,
    required this.onLink,
    required this.onCopy,
    this.methodSwitcher,
    this.leading,
    this.problem,
    this.divisionMethod = DivisionMethod.ru,
  });
  final SolveResponse result;
  final LatexOptions latexOptions;
  final void Function(ExplanationLink) onLink;
  final void Function(String) onCopy;
  final Widget? methodSwitcher;

  /// The left end of the bottom bar («Изменить задачу» on the main screen).
  final Widget? leading;
  final CoreNode? problem;
  final DivisionMethod divisionMethod;

  @override
  State<VerticalResult> createState() => _VerticalResultState();
}

class _VerticalResultState extends State<VerticalResult> {
  int active = 0;
  final stages = <String, int>{};
  final anchors = <String, GlobalKey>{};
  final bodies = <String, GlobalKey>{};
  final summaries = <String, GlobalKey>{};

  @override
  void didUpdateWidget(covariant VerticalResult oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.result != widget.result) {
      active = 0;
      stages.clear();
      anchors.clear();
      bodies.clear();
      summaries.clear();
    }
  }

  String identity(int index) => '${widget.result.steps[index].id}:$index';

  int _stageOf(int index) => (stages[identity(index)] ?? 0).clamp(
    0,
    math.max(0, widget.result.steps[index].substeps.length - 1),
  );

  List<int> get _shown => [
    for (var i = 0; i < widget.result.steps.length; i++)
      if (widget.result.steps[i].substeps.isNotEmpty) i,
  ];

  double _height(GlobalKey? key) =>
      (key?.currentContext?.findRenderObject() as RenderBox?)?.size.height ?? 0;

  /// Opens step [index] and scrolls it into view in one smooth motion.
  ///
  /// The old card closes while the new one opens; both animate with the same
  /// duration and curve as the scroll, and the scroll target already counts
  /// the height the old card is about to lose, so the new card glides to its
  /// place instead of jumping when the list above it shrinks.
  void select(int index, {int? stage}) {
    final previous = active;
    final lost = previous != index && previous < index
        ? math.max(
            0.0,
            _height(bodies[identity(previous)]) -
                _height(summaries[identity(index)]),
          )
        : 0.0;
    final target = anchors[identity(index)]?.currentContext;
    final box = target?.findRenderObject() as RenderBox?;
    setState(() {
      active = index;
      if (stage != null) stages[identity(index)] = stage;
    });
    if (target == null || box == null || !box.attached) return;
    final position = Scrollable.maybeOf(target)?.position;
    final viewport = RenderAbstractViewport.maybeOf(box);
    if (position == null || viewport == null) return;
    // where the card's top lands once the old card has closed
    final top = viewport.getOffsetToReveal(box, 0).offset - lost - 12;
    final pixels = position.pixels;
    final goal = previous == index
        ? null
        : top < pixels
        ? top
        : top > pixels + position.viewportDimension * .35
        ? top
        : null;
    if (goal == null) return;
    final duration = _motion(320);
    final clamped = math.max(position.minScrollExtent, goal);
    if (duration == Duration.zero) {
      WidgetsBinding.instance.addPostFrameCallback(
        (_) => position.jumpTo(math.min(clamped, position.maxScrollExtent)),
      );
    } else {
      position.animateTo(clamped, duration: duration, curve: _curve);
    }
  }

  static const _curve = Curves.easeInOutCubic;

  bool get _canNext {
    final shown = _shown;
    if (shown.isEmpty) return false;
    final group = widget.result.steps[active];
    return _stageOf(active) < group.substeps.length - 1 ||
        shown.any((i) => i > active);
  }

  bool get _canPrevious =>
      _stageOf(active) > 0 || _shown.any((i) => i < active);

  /// «Далее»: the next stage of the open step, else the next step.
  void _next() {
    final group = widget.result.steps[active];
    final stage = _stageOf(active);
    if (stage < group.substeps.length - 1) {
      _go(active, stage + 1, 1);
      return;
    }
    final next = _shown.firstWhere((i) => i > active, orElse: () => -1);
    if (next < 0) return;
    HapticFeedback.mediumImpact();
    _direction = 1;
    select(next);
  }

  void _previous() {
    final stage = _stageOf(active);
    if (stage > 0) {
      _go(active, stage - 1, -1);
      return;
    }
    final before = _shown.lastWhere((i) => i < active, orElse: () => -1);
    if (before < 0) return;
    HapticFeedback.selectionClick();
    _direction = -1;
    select(before);
  }

  @override
  Widget build(BuildContext context) {
    final result = widget.result;
    final list = ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        if ((result.solution, result.verdictLatex)
            case (final solution, final verdict)
            when solution != null || verdict != null)
          _Reveal(
            delay: Duration.zero,
            enabled: !MediaQuery.disableAnimationsOf(context),
            child: _Answer(
              main: solution != null && solution.type != CoreNodeType.empty
                  ? (
                      latex: nodeToLatex(solution, widget.latexOptions),
                      decimal: _isDecimal(solution),
                    )
                  : (latex: verdict!, decimal: false),
              alternatives: [
                for (final form in result.alternatives)
                  (
                    latex: nodeToLatex(form, widget.latexOptions),
                    decimal: _isDecimal(form),
                  ),
              ],
            ),
          ),
        ?widget.methodSwitcher,
        if (widget.problem != null &&
            DivisionTrace.fromNode(widget.problem!) != null)
          TextButton.icon(
            onPressed: () => Navigator.of(context).push(
              _riseRoute(
                context,
                (_) => DivisionLesson(
                  trace: DivisionTrace.fromNode(widget.problem!)!,
                  method: widget.divisionMethod,
                  separator: widget.latexOptions.decimalSeparator.symbol,
                ),
              ),
            ),
            icon: const Icon(Icons.view_agenda_outlined),
            label: Text(tr('Деление столбиком', 'Long division')),
          ),
        if (result.steps.isEmpty)
          Padding(
            padding: const EdgeInsets.all(16),
            child: Text(
              tr(
                'Для этой задачи подробные шаги не предоставлены.',
                'Detailed steps are not provided for this problem.',
              ),
            ),
          ),
        if (result.header case final header? when header.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: Text(header, style: Theme.of(context).textTheme.titleLarge),
          ),
        for (final i in _shown) _group(context, i),
      ],
    );
    return Column(
      children: [
        Expanded(child: list),
        _bottomBar(context),
      ],
    );
  }

  /// `view_vertical_result_controls.xml`: back a stage on the left of the red
  /// «Далее» pill; the screen's own action (edit the problem) at the far left.
  Widget _bottomBar(BuildContext context) {
    if (_shown.isEmpty) {
      return widget.leading == null
          ? const SizedBox.shrink()
          : Padding(
              padding: const EdgeInsets.fromLTRB(16, 8, 16, 20),
              child: Row(children: [widget.leading!]),
            );
    }
    final stage = _stageOf(active);
    final lastStage = widget.result.steps.isEmpty
        ? 0
        : widget.result.steps[active].substeps.length - 1;
    return Padding(
      // above the gesture bar on the «Подробный разбор» pages (no SafeArea there)
      padding: EdgeInsets.fromLTRB(
        16,
        8,
        16,
        20 + MediaQuery.paddingOf(context).bottom,
      ),
      child: Row(
        children: [
          ?widget.leading,
          const Spacer(),
          if (_canPrevious)
            IconButton(
              key: ValueKey(stage > 0 ? 'previous-stage' : 'previous-group'),
              tooltip: stage > 0
                  ? tr('Предыдущий этап', 'Previous stage')
                  : tr('Предыдущий шаг', 'Previous step'),
              style: IconButton.styleFrom(
                backgroundColor: Theme.of(context).colorScheme.surface,
                elevation: 3,
                shadowColor: Colors.black26,
                fixedSize: const Size(48, 48),
              ),
              icon: const Icon(Icons.undo),
              onPressed: _previous,
            ),
          const SizedBox(width: 12),
          if (_canNext)
            Flexible(
              child: FilledButton.icon(
                key: ValueKey(stage < lastStage ? 'next-stage' : 'next-group'),
                style: FilledButton.styleFrom(
                  shape: const StadiumBorder(),
                  padding: const EdgeInsets.symmetric(horizontal: 28),
                  minimumSize: const Size(120, 48),
                ),
                iconAlignment: IconAlignment.end,
                icon: const Icon(Icons.arrow_forward),
                label: Text(
                  tr('Далее', 'Next'),
                  overflow: TextOverflow.ellipsis,
                ),
                onPressed: _next,
              ),
            ),
        ],
      ),
    );
  }

  Duration _motion(int milliseconds) => MediaQuery.disableAnimationsOf(context)
      ? Duration.zero
      : Duration(milliseconds: milliseconds);

  /// Moves one stage back or forth inside the open step; `direction` is the slide side.
  void _go(int index, int stage, int direction) {
    _direction = direction;
    HapticFeedback.selectionClick();
    select(index, stage: stage);
  }

  int _direction = 1;

  Widget _group(BuildContext context, int index) {
    final group = widget.result.steps[index];
    final id = identity(index);
    final stage = _stageOf(index);
    final selected = active == index;
    final title = group.headers.where((h) => h.isNotEmpty).join(' · ');
    final substep = group.substeps[stage];
    final colors = Theme.of(context).colorScheme;
    final anchor = anchors.putIfAbsent(id, GlobalKey.new);
    final body = bodies.putIfAbsent(id, GlobalKey.new);
    final summary = summaries.putIfAbsent(id, GlobalKey.new);
    final last = group.substeps.length - 1;
    final (left, right) = switch ((substep.left, substep.right)) {
      (final l?, final r?) => highlightChange(l, r),
      (final l, final r) => (l, r),
    };
    final outcome = group.substeps.last.right ?? group.substeps.first.left;
    return Container(
      key: anchor,
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        color: selected ? colors.surface : colors.surfaceContainerLow,
        borderRadius: BorderRadius.circular(selected ? 12 : 8),
        boxShadow: [
          if (selected)
            const BoxShadow(
              color: Color(0x22000000),
              blurRadius: 16,
              offset: Offset(0, 4),
            ),
        ],
      ),
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(selected ? 12 : 8),
        clipBehavior: Clip.antiAlias,
        child: _SmoothSize(
          duration: _motion(320),
          curve: _curve,
          alignment: Alignment.topCenter,
          child: selected
              ? Padding(
                  key: body,
                  padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
                  child: _openCard(
                    context,
                    index: index,
                    id: id,
                    title: title,
                    stage: stage,
                    last: last,
                    substep: substep,
                    left: left,
                    right: right,
                  ),
                )
              : Semantics(
                  button: true,
                  child: InkWell(
                    key: ValueKey('solution-group:$index'),
                    onTap: () {
                      HapticFeedback.selectionClick();
                      _direction = index > active ? 1 : -1;
                      select(index);
                    },
                    child: Padding(
                      key: summary,
                      padding: const EdgeInsets.fromLTRB(16, 12, 8, 12),
                      child: Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (outcome != null)
                                  // done or later steps stay quiet grey rows
                                  Opacity(
                                    opacity: .6,
                                    child: StepEquation(
                                      latex: nodeToLatex(
                                        outcome,
                                        widget.latexOptions,
                                      ),
                                      fontSize: 18,
                                    ),
                                  ),
                                const SizedBox(height: 2),
                                Text(
                                  title.isEmpty
                                      ? tr('Преобразование', 'Transformation')
                                      : title,
                                  style: TextStyle(
                                    fontSize: 14,
                                    color: colors.onSurfaceVariant,
                                  ),
                                ),
                              ],
                            ),
                          ),
                          Icon(
                            Icons.keyboard_arrow_down,
                            color: colors.onSurfaceVariant,
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
        ),
      ),
    );
  }

  /// The open step: its title, the stage dots, the instruction and the
  /// before → after formulas with the changed parts in red.
  Widget _openCard(
    BuildContext context, {
    required int index,
    required String id,
    required String title,
    required int stage,
    required int last,
    required Substep substep,
    required CoreNode? left,
    required CoreNode? right,
  }) {
    final colors = Theme.of(context).colorScheme;
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onHorizontalDragEnd: (details) {
        final speed = details.primaryVelocity ?? 0;
        if (speed < -250 && stage < last) {
          _go(index, stage + 1, 1);
        } else if (speed > 250 && stage > 0) {
          _go(index, stage - 1, -1);
        }
      },
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title.isEmpty
                      ? tr('Преобразование', 'Transformation')
                      : title,
                  style: Theme.of(context).textTheme.titleMedium,
                ),
              ),
              if (last > 0)
                Text(
                  '${stage + 1}/${last + 1}',
                  key: ValueKey('stage-counter:$index'),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
            ],
          ),
          const SizedBox(height: 12),
          AnimatedSwitcher(
            duration: _motion(260),
            switchInCurve: Curves.easeOutCubic,
            switchOutCurve: Curves.easeInCubic,
            layoutBuilder: (current, previous) => Stack(
              alignment: Alignment.topLeft,
              children: [...previous, ?current],
            ),
            transitionBuilder: (child, animation) {
              final entering = child.key == ValueKey('$id:$stage');
              final offset = Tween<Offset>(
                begin: Offset(
                  entering ? .12 * _direction : -.12 * _direction,
                  0,
                ),
                end: Offset.zero,
              ).animate(animation);
              return FadeTransition(
                opacity: animation,
                child: SlideTransition(position: offset, child: child),
              );
            },
            child: Column(
              key: ValueKey('$id:$stage'),
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (left case final left?)
                  StepEquation(
                    latex: nodeToLatex(left, widget.latexOptions),
                    label: nodeToLatex(substep.left!, widget.latexOptions),
                  ),
                if (substep.text != null && !substep.text!.startsWith('step_'))
                  Row(
                    children: [
                      // a thin arrow runs down beside the explanation
                      if (left != null && right != null)
                        Padding(
                          padding: const EdgeInsets.only(left: 2, right: 12),
                          child: _FlowArrow(
                            color: colors.outline,
                            duration: _motion(380),
                          ),
                        ),
                      Expanded(
                        child: Padding(
                          padding: const EdgeInsets.symmetric(vertical: 10),
                          child: _Instruction(
                            substep: substep,
                            options: widget.latexOptions,
                            onLink: widget.onLink,
                          ),
                        ),
                      ),
                    ],
                  )
                else if (left != null && right != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(2, 6, 0, 6),
                    child: _FlowArrow(
                      color: colors.outline,
                      duration: _motion(380),
                    ),
                  ),
                if (right case final right?)
                  StepEquation(
                    latex: nodeToLatex(right, widget.latexOptions),
                    label: nodeToLatex(substep.right!, widget.latexOptions),
                  ),
                _actions(context, substep),
              ],
            ),
          ),
          if (last > 0) ...[
            const SizedBox(height: 12),
            _StageDots(count: last + 1, current: stage, duration: _motion(220)),
          ],
        ],
      ),
    );
  }

  Widget _actions(BuildContext context, Substep substep) {
    final frames = transformationFrames(substep, widget.latexOptions);
    final nested =
        substep.subresult ??
        (substep.detail.isEmpty ? null : SolveResponse(steps: substep.detail));
    final buttons = [
      if (nested != null && nested.steps.any((s) => s.substeps.isNotEmpty))
        _ActionChip(
          key: const ValueKey('step-details'),
          icon: Icons.unfold_more,
          label: tr('Подробнее', 'More details'),
          onPressed: () => Navigator.of(context).push(
            _riseRoute(
              context,
              (_) => Scaffold(
                appBar: AppBar(
                  title: Text(tr('Подробный разбор', 'Detailed breakdown')),
                ),
                body: VerticalResult(
                  result: nested,
                  latexOptions: widget.latexOptions,
                  onLink: widget.onLink,
                  onCopy: widget.onCopy,
                ),
              ),
            ),
          ),
        ),
      if (substep.theory case final article?)
        _ActionChip(
          key: const ValueKey('step-theory'),
          icon: Icons.lightbulb_outline,
          label: tr('Почему?', 'Why?'),
          onPressed: () => Navigator.of(context)
              .push(_riseRoute(context, (_) => TheoryPage(article: article))),
        ),
      if (frames.isNotEmpty)
        _ActionChip(
          icon: Icons.play_circle_outline,
          label: tr('Показать преобразование', 'Show transformation'),
          onPressed: () => Navigator.of(context).push(
            _riseRoute(context, (_) => TransformationLesson(frames: frames)),
          ),
        ),
    ];
    if (buttons.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Wrap(spacing: 8, runSpacing: 8, children: buttons),
    );
  }
}

typedef _Form = ({String latex, bool decimal});

/// Whether an answer is written with decimals (`0.5`, `≈ 2.236`) and not as fractions.
bool _isDecimal(CoreNode node) =>
    node.type == CoreNodeType.approximateSign ||
    RegExp(r'^\d*[.,]\d+$').hasMatch(node.value ?? '') ||
    node.children.any(_isDecimal);

/// «Решение» with the red accent bar on the left.
///
/// A switch «Обыкновенная / Десятичная» shows the same answer in either form.
class _Answer extends StatefulWidget {
  const _Answer({required this.main, required this.alternatives});
  final _Form main;
  final List<_Form> alternatives;
  @override
  State<_Answer> createState() => _AnswerState();
}

class _AnswerState extends State<_Answer> {
  bool _decimal = false;

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final forms = [widget.main, ...widget.alternatives];
    _Form? pick(bool decimal) {
      for (final form in forms) {
        if (form.decimal == decimal) return form;
      }
      return null;
    }

    final common = pick(false);
    final decimal = pick(true);
    final switchable = common != null && decimal != null;
    final shown = switchable ? (_decimal ? decimal : common) : widget.main;
    final others = [
      for (final form in widget.alternatives)
        if (form != shown && (!switchable || form.decimal == shown.decimal))
          form,
    ];
    return Container(
      margin: const EdgeInsets.only(bottom: 20),
      decoration: BoxDecoration(
        border: Border(left: BorderSide(color: colors.primary, width: 4)),
      ),
      padding: const EdgeInsets.fromLTRB(16, 4, 0, 4),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            tr('Ответ', 'Answer'),
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: colors.primary,
            ),
          ),
          const SizedBox(height: 8),
          if (switchable) ...[
            SegmentedButton<bool>(
              showSelectedIcon: false,
              style: const ButtonStyle(visualDensity: VisualDensity.compact),
              segments: [
                ButtonSegment(
                  value: false,
                  label: Text(tr('Обыкновенная', 'Fraction')),
                ),
                ButtonSegment(
                  value: true,
                  label: Text(tr('Десятичная', 'Decimal')),
                ),
              ],
              selected: {_decimal},
              onSelectionChanged: (value) =>
                  setState(() => _decimal = value.first),
            ),
            const SizedBox(height: 8),
          ],
          StepEquation(latex: shown.latex, fontSize: 26, minScale: .35),
          if (others.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              tr('Альтернативная форма', 'Alternative form'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
            for (final form in others)
              StepEquation(latex: form.latex, fontSize: 20, minScale: .35),
          ],
        ],
      ),
    );
  }
}

/// A small outlined action under the formulas: «Подробнее», «Почему?».
class _ActionChip extends StatelessWidget {
  const _ActionChip({
    super.key,
    required this.icon,
    required this.label,
    required this.onPressed,
  });
  final IconData icon;
  final String label;
  final VoidCallback onPressed;
  @override
  Widget build(BuildContext context) => OutlinedButton.icon(
    style: OutlinedButton.styleFrom(
      minimumSize: const Size(48, 40),
      padding: const EdgeInsets.symmetric(horizontal: 14),
      shape: const StadiumBorder(),
      side: BorderSide(color: Theme.of(context).colorScheme.outlineVariant),
    ),
    icon: Icon(icon, size: 18),
    label: Text(label),
    onPressed: onPressed,
  );
}

class _Instruction extends StatelessWidget {
  const _Instruction({
    required this.substep,
    required this.options,
    required this.onLink,
  });
  final Substep substep;
  final LatexOptions options;
  final void Function(ExplanationLink) onLink;
  @override
  Widget build(BuildContext context) {
    if (!substep.parts.any((p) => p.node != null)) {
      return ExplanationText(
        text: substep.text ?? '',
        links: substep.links,
        onLink: onLink,
      );
    }
    // Short arguments (-5x, 1/2, x + 3) stay in the sentence; long ones use display
    // blocks below so a root/fraction can scroll instead of overflowing prose.
    if (substep.links.isEmpty) {
      final style = Theme.of(context).textTheme.bodyLarge!;
      InlineSpan span(ExplanationPart part) => switch (part.node) {
        final node? => WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: Semantics(
            container: true,
            label: nodeToLatex(node, options),
            excludeSemantics: true,
            child: Math.tex(
              nodeToLatex(node, options),
              mathStyle: MathStyle.text,
              textStyle: style.copyWith(
                fontSize: MediaQuery.textScalerOf(context)
                    .scale(style.fontSize!),
              ),
              onErrorFallback: (_) => Text(node.value ?? ''),
            ),
          ),
        ),
        _ => TextSpan(text: part.text),
      };
      // Text and short formulas flow as one sentence; only a long formula
      // breaks it into a display block (each part on its own line read as a list).
      final blocks = <Widget>[];
      var run = <InlineSpan>[];
      void flush() {
        if (run.isNotEmpty) {
          blocks.add(Text.rich(TextSpan(children: run), style: style));
        }
        run = [];
      }

      for (final part in substep.parts) {
        if (part.node case final node? when !isInlineFormula(node, options)) {
          flush();
          blocks.add(
            StepEquation(latex: nodeToLatex(node, options), fontSize: 20),
          );
        } else if (part.node != null || (part.text ?? '').isNotEmpty) {
          run.add(span(part));
        }
      }
      flush();
      return blocks.length == 1
          ? blocks.single
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: blocks,
            );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        for (final part in substep.parts)
          if (part.node case final node?)
            StepEquation(latex: nodeToLatex(node, options), fontSize: 20)
          else if (part.text case final text? when text.trim().isNotEmpty)
            ExplanationText(text: text, links: substep.links, onLink: onLink),
      ],
    );
  }
}

/// Whether a formula part stays inside the sentence instead of becoming a
/// display block.
///
/// Short arguments (`-5x`, `1/2`, `x + 3`) stay in the text; long fractions and
/// roots use a display block so they can scroll instead of overflowing prose.
/// `y|_{x=0}` is drawn as five glyphs, not 20 characters of TeX, hence the
/// visible-length rule. The transcript (`app/test/card_transcript_test.dart`)
/// uses the same rule to show the card exactly as the app draws it.
bool isInlineFormula(CoreNode node, LatexOptions options) {
  final latex = nodeToLatex(node, options);
  final visible = latex.replaceAll(RegExp(r'\\[a-zA-Z]+|[{}\s]'), '');
  return visible.length <= 18 && !latex.contains(r'\begin');
}

/// «Почему?»: the rule behind a step, built to be read at a glance — the
/// rule in one sentence, its formula large on a tinted plate, then short cards
/// for when it applies, a worked example line by line and the usual mistake.
class TheoryPage extends StatelessWidget {
  const TheoryPage({super.key, required this.article});
  final TheoryArticle article;
  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    final text = Theme.of(context).textTheme;
    // «a → b; c → d.» reads better as one line per move
    final example = [
      for (final line in article.example.split(RegExp(r';\s*')))
        if (line.trim().isNotEmpty) line.trim(),
    ];
    return Scaffold(
      appBar: AppBar(title: Text(tr('Почему так?', 'Why is that?'))),
      body: ListView(
        // clear the gesture bar, the last card must not sit under it
        padding: EdgeInsets.fromLTRB(
          20,
          8,
          20,
          32 + MediaQuery.paddingOf(context).bottom,
        ),
        children: [
          Text(article.title, style: text.headlineSmall),
          const SizedBox(height: 12),
          Text(article.summary, style: text.bodyLarge),
          if (article.formula.isNotEmpty)
            Container(
              margin: const EdgeInsets.only(top: 20),
              padding: const EdgeInsets.symmetric(vertical: 20, horizontal: 12),
              decoration: BoxDecoration(
                color: colors.primaryContainer,
                borderRadius: BorderRadius.circular(12),
              ),
              // a table of rules («∫xⁿdx = …; ∫dx/x = …») is one rule per line
              child: Column(
                children: [
                  for (final rule in article.formula.split(RegExp(r';\s*')))
                    if (rule.trim().isNotEmpty)
                      StepEquation(latex: rule.trim(), fontSize: 22),
                ],
              ),
            ),
          if (article.conditions.isNotEmpty)
            _TheoryCard(
              icon: Icons.check_circle_outline,
              title: tr('Когда применять', 'When to apply'),
              color: colors.onSurfaceVariant,
              child: Text(article.conditions, style: text.bodyLarge),
            ),
          if (example.isNotEmpty)
            _TheoryCard(
              icon: Icons.edit_note,
              title: tr('Пример', 'Example'),
              color: colors.onSurfaceVariant,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  for (final line in example)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 6),
                      child: Text(line, style: text.bodyLarge),
                    ),
                ],
              ),
            ),
          if (article.mistake.isNotEmpty)
            _TheoryCard(
              icon: Icons.warning_amber_rounded,
              title: tr('Частая ошибка', 'Common mistake'),
              color: colors.primary,
              tint: colors.primaryContainer.withValues(alpha: .5),
              child: Text(article.mistake, style: text.bodyLarge),
            ),
        ],
      ),
    );
  }
}

class _TheoryCard extends StatelessWidget {
  const _TheoryCard({
    required this.icon,
    required this.title,
    required this.color,
    required this.child,
    this.tint,
  });
  final IconData icon;
  final String title;
  final Color color;
  final Color? tint;
  final Widget child;
  @override
  Widget build(BuildContext context) => Container(
    margin: const EdgeInsets.only(top: 16),
    padding: const EdgeInsets.all(16),
    decoration: BoxDecoration(
      color: tint ?? Theme.of(context).colorScheme.surfaceContainerLow,
      borderRadius: BorderRadius.circular(12),
    ),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(icon, size: 20, color: color),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                title,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                  color: color,
                ),
              ),
            ),
          ],
        ),
        const SizedBox(height: 8),
        child,
      ],
    ),
  );
}

/// A display formula of a card: broken across lines when it does not fit (see
/// [BreakableFormula]); the whole LaTeX stays its semantics label.
class StepEquation extends StatelessWidget {
  const StepEquation({
    super.key,
    required this.latex,
    this.fontSize = 22,
    this.label,
    this.minScale = minFormulaScale,
  });
  final String latex;
  final double fontSize;
  final double minScale;

  /// What a screen reader says; the change colours are not read out.
  final String? label;
  @override
  Widget build(BuildContext context) => Semantics(
    container: true,
    label: label ?? latex,
    excludeSemantics: true,
    child: BreakableFormula(
      latex: latex,
      fontSize: fontSize,
      minScale: minScale,
      transform: (value) => value.replaceAllMapped(
        RegExp(r'\\textcolor\{#[0-9a-fA-F]{6}\}'),
        (_) {
          final accent = Theme.of(context).colorScheme.primary
              .toARGB32()
              .toRadixString(16)
              .padLeft(8, '0')
              .substring(2);
          return '\\textcolor{#$accent}';
        },
      ),
    ),
  );
}

class ExplanationText extends StatelessWidget {
  const ExplanationText({
    super.key,
    required this.text,
    required this.links,
    required this.onLink,
  });
  final String text;
  final List<ExplanationLink> links;
  final void Function(ExplanationLink) onLink;
  @override
  Widget build(BuildContext context) {
    final spans = <InlineSpan>[];
    var cursor = 0;
    for (final link in links) {
      if (link.definition.isEmpty) continue;
      final at = text.indexOf(link.label, cursor);
      if (at < 0) continue;
      if (at > cursor) spans.add(TextSpan(text: text.substring(cursor, at)));
      spans.add(
        WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: TextButton(
            onPressed: () => onLink(link),
            child: Text(
              link.label,
              style: const TextStyle(decoration: TextDecoration.underline),
            ),
          ),
        ),
      );
      cursor = at + link.label.length;
    }
    if (cursor < text.length) spans.add(TextSpan(text: text.substring(cursor)));
    return Text.rich(
      TextSpan(children: spans),
      style: Theme.of(context).textTheme.bodyLarge,
    );
  }
}

/// Fades and lifts a child in once, with a small stagger between neighbours.
class _Reveal extends StatelessWidget {
  const _Reveal({
    required this.child,
    required this.delay,
    required this.enabled,
  });
  final Widget child;
  final Duration delay;
  final bool enabled;
  @override
  Widget build(BuildContext context) {
    if (!enabled) return child;
    final total = const Duration(milliseconds: 360) + delay;
    final start = delay.inMilliseconds / total.inMilliseconds;
    return TweenAnimationBuilder<double>(
      tween: Tween(begin: 0, end: 1),
      duration: total,
      curve: Interval(start, 1, curve: Curves.easeOutCubic),
      builder: (context, value, child) => Opacity(
        opacity: value,
        child: Transform.translate(
          offset: Offset(0, 14 * (1 - value)),
          child: child,
        ),
      ),
      child: child,
    );
  }
}

/// Page dots whose active dot stretches into a pill.
class _StageDots extends StatelessWidget {
  const _StageDots({
    required this.count,
    required this.current,
    required this.duration,
  });
  final int count;
  final int current;
  final Duration duration;
  @override
  Widget build(BuildContext context) => Semantics(
    label: tr(
      'Этап ${current + 1} из $count',
      'Stage ${current + 1} of $count',
    ),
    child: Row(
      children: [
        for (var i = 0; i < count; i++)
          AnimatedContainer(
            duration: duration,
            curve: Curves.easeOutCubic,
            margin: const EdgeInsets.only(right: 6),
            width: i == current ? 22 : 8,
            height: 8,
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(4),
              color: i <= current
                  ? Theme.of(context).colorScheme.primary
                        .withValues(alpha: i == current ? 1 : .35)
                  : Theme.of(context).colorScheme.outlineVariant,
            ),
          ),
      ],
    ),
  );
}

/// The "before -> after" arrow draws itself downwards.
class _FlowArrow extends StatelessWidget {
  const _FlowArrow({required this.color, required this.duration});
  final Color color;
  final Duration duration;
  @override
  Widget build(BuildContext context) => TweenAnimationBuilder<double>(
    tween: Tween(begin: 0, end: 1),
    duration: duration,
    curve: Curves.easeOutCubic,
    builder: (context, value, _) => Opacity(
      opacity: value,
      child: Transform.translate(
        offset: Offset(0, -6 * (1 - value)),
        child: Icon(Icons.south, size: 18, color: color),
      ),
    ),
  );
}

/// Detail screens rise from below and fade in; reduced motion falls back to an instant swap.
Route<void> _riseRoute(BuildContext context, WidgetBuilder builder) {
  final still = MediaQuery.disableAnimationsOf(context);
  return PageRouteBuilder<void>(
    transitionDuration: still
        ? Duration.zero
        : const Duration(milliseconds: 320),
    reverseTransitionDuration: still
        ? Duration.zero
        : const Duration(milliseconds: 240),
    pageBuilder: (context, _, _) => builder(context),
    transitionsBuilder: (context, animation, secondary, child) {
      final curved = CurvedAnimation(
        parent: animation,
        curve: Curves.easeOutCubic,
        reverseCurve: Curves.easeInCubic,
      );
      return FadeTransition(
        opacity: curved,
        child: SlideTransition(
          position: Tween<Offset>(
            begin: const Offset(0, .06),
            end: Offset.zero,
          ).animate(curved),
          child: child,
        ),
      );
    },
  );
}

/// `AnimatedSize` that steps aside when motion is reduced (a zero duration trips its layout assert).
class _SmoothSize extends StatelessWidget {
  const _SmoothSize({
    required this.duration,
    required this.alignment,
    required this.child,
    this.curve = Curves.easeOutCubic,
  });
  final Duration duration;
  final AlignmentGeometry alignment;
  final Curve curve;
  final Widget child;
  @override
  Widget build(BuildContext context) => duration == Duration.zero
      ? child
      : AnimatedSize(
          duration: duration,
          curve: curve,
          alignment: alignment,
          child: child,
        );
}
