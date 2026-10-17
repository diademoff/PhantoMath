import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import '../api/solver_api.dart';
import '../model/core_node.dart';
import '../render/latex.dart';
import '../render/division_trace.dart';
import '../settings/settings.dart';
import '../theme/photomath_theme.dart';
import 'division_lesson.dart';
import 'transformation_lesson.dart';

class VerticalResult extends StatefulWidget {
  const VerticalResult({
    super.key,
    required this.result,
    required this.latexOptions,
    required this.onLink,
    required this.onCopy,
    this.methodSwitcher,
    this.onBack,
    this.expandAll = false,
    this.problem,
    this.divisionMethod = DivisionMethod.ru,
  });
  final SolveResponse result;
  final LatexOptions latexOptions;
  final void Function(ExplanationLink) onLink;
  final void Function(String) onCopy;
  final Widget? methodSwitcher;
  final VoidCallback? onBack;
  final bool expandAll;
  final CoreNode? problem;
  final DivisionMethod divisionMethod;

  @override
  State<VerticalResult> createState() => _VerticalResultState();
}

class _VerticalResultState extends State<VerticalResult> {
  int active = 0;
  final stages = <String, int>{};
  final anchors = <String, GlobalKey>{};

  @override
  void didUpdateWidget(covariant VerticalResult oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.result != widget.result) {
      active = 0;
      stages.clear();
      anchors.clear();
    }
  }

  String identity(int index) => '${widget.result.steps[index].id}:$index';

  void select(int index, {int? stage}) {
    setState(() {
      active = index;
      if (stage != null) stages[identity(index)] = stage;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      final target = anchors[identity(index)]?.currentContext;
      if (target != null) {
        Scrollable.ensureVisible(
          target,
          duration: MediaQuery.disableAnimationsOf(context)
              ? Duration.zero
              : const Duration(milliseconds: 180),
          alignment: 0.1,
        );
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    final result = widget.result;
    return ListView(
      padding: const EdgeInsets.fromLTRB(16, 12, 16, 24),
      children: [
        if (result.solution case final solution?)
          _Reveal(
            delay: Duration.zero,
            enabled: !MediaQuery.disableAnimationsOf(context),
            child: Container(
              padding: const EdgeInsets.all(20),
              margin: const EdgeInsets.only(bottom: 24),
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primaryContainer
                    .withValues(alpha: .35),
                borderRadius: BorderRadius.circular(12),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Icon(
                        Icons.check_circle,
                        size: 16,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        'Ответ',
                        style: Theme.of(context).textTheme.bodySmall,
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: StepEquation(
                          latex: nodeToLatex(solution, widget.latexOptions),
                          fontSize: 28,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
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
            label: const Text('Деление столбиком'),
          ),
        if (result.steps.isEmpty)
          const Padding(
            padding: EdgeInsets.all(16),
            child: Text('Для этой задачи подробные шаги не предоставлены.'),
          ),
        if (result.header case final header? when header.isNotEmpty)
          Padding(
            padding: const EdgeInsets.only(bottom: 16),
            child: Text(header, style: Theme.of(context).textTheme.titleLarge),
          ),
        for (var i = 0; i < result.steps.length; i++)
          if (result.steps[i].substeps.isNotEmpty) _group(context, i),
      ],
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
    final stage = (stages[id] ?? 0).clamp(0, group.substeps.length - 1);
    final selected = active == index;
    final title = group.headers.where((h) => h.isNotEmpty).join(' · ');
    final substep = group.substeps[stage];
    final colors = Theme.of(context).colorScheme;
    final anchor = anchors.putIfAbsent(id, GlobalKey.new);
    final last = group.substeps.length - 1;
    final expandable =
        group.substeps.length > 1 ||
        group.substeps.any(
          (s) => s.subresult != null || s.detail.isNotEmpty || s.theory != null,
        );
    return _Reveal(
      key: anchor,
      delay: Duration(milliseconds: 40 * index.clamp(0, 8)),
      enabled: !MediaQuery.disableAnimationsOf(context),
      child: AnimatedContainer(
        duration: _motion(220),
        curve: Curves.easeOutCubic,
        margin: const EdgeInsets.only(bottom: 12),
        decoration: BoxDecoration(
          color: selected ? PhColor.white : colors.surfaceContainerLow,
          borderRadius: BorderRadius.circular(14),
          border: Border.all(
            color: selected ? colors.primary : colors.outlineVariant,
            width: selected ? 1.5 : 1,
          ),
          boxShadow: [
            if (selected)
              BoxShadow(
                color: colors.primary.withValues(alpha: .14),
                blurRadius: 18,
                offset: const Offset(0, 6),
              ),
          ],
        ),
        child: Material(
          color: Colors.transparent,
          borderRadius: BorderRadius.circular(14),
          clipBehavior: Clip.antiAlias,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Semantics(
                selected: selected,
                button: true,
                child: InkWell(
                  key: ValueKey('solution-group:$index'),
                  onTap: () {
                    HapticFeedback.selectionClick();
                    select(index);
                  },
                  child: Padding(
                    padding: const EdgeInsets.all(16),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          children: [
                            AnimatedContainer(
                              duration: _motion(220),
                              width: 26,
                              height: 26,
                              alignment: Alignment.center,
                              decoration: BoxDecoration(
                                shape: BoxShape.circle,
                                color: selected
                                    ? colors.primary
                                    : PhColor.separatorGray,
                              ),
                              child: Text(
                                '${index + 1}',
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w700,
                                  color: selected
                                      ? PhColor.white
                                      : PhColor.grayMedium,
                                ),
                              ),
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Text(
                                'Шаг ${index + 1}',
                                style: Theme.of(context).textTheme.labelMedium,
                              ),
                            ),
                            if (expandable)
                              AnimatedRotation(
                                turns: selected ? .5 : 0,
                                duration: _motion(220),
                                child: const Icon(
                                  Icons.keyboard_arrow_down,
                                  color: PhColor.grayMedium,
                                ),
                              ),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Text(
                          title.isEmpty ? 'Преобразование' : title,
                          style: Theme.of(context).textTheme.titleMedium,
                        ),
                        _SmoothSize(
                          duration: _motion(220),
                          alignment: Alignment.topCenter,
                          child: selected
                              ? const SizedBox(width: double.infinity)
                              : Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    const SizedBox(height: 8),
                                    if (group.substeps.last.right ??
                                            group.substeps.first.left
                                        case final node?)
                                      StepEquation(
                                        latex: nodeToLatex(
                                          node,
                                          widget.latexOptions,
                                        ),
                                      ),
                                    Text(
                                      '${group.substeps.length} этап(а) · Открыть',
                                      style: Theme.of(context)
                                          .textTheme
                                          .bodySmall,
                                    ),
                                  ],
                                ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
              _SmoothSize(
                duration: _motion(260),
                curve: Curves.easeOutCubic,
                alignment: Alignment.topCenter,
                child: !selected
                    ? const SizedBox(width: double.infinity)
                    : GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onHorizontalDragEnd: (details) {
                          final speed = details.primaryVelocity ?? 0;
                          if (speed < -250 && stage < last) {
                            _go(index, stage + 1, 1);
                          } else if (speed > 250 && stage > 0) {
                            _go(index, stage - 1, -1);
                          }
                        },
                        child: Padding(
                          padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              if (group.substeps.length > 1) ...[
                                Text(
                                  'Этап ${stage + 1} из ${group.substeps.length}',
                                  key: ValueKey('stage-counter:$index'),
                                  style: Theme.of(context).textTheme.labelLarge,
                                ),
                                const SizedBox(height: 8),
                                _StageDots(
                                  count: group.substeps.length,
                                  current: stage,
                                  duration: _motion(220),
                                ),
                                const SizedBox(height: 16),
                              ],
                              AnimatedSwitcher(
                                duration: _motion(260),
                                switchInCurve: Curves.easeOutCubic,
                                switchOutCurve: Curves.easeInCubic,
                                layoutBuilder: (current, previous) => Stack(
                                  alignment: Alignment.topLeft,
                                  children: [...previous, ?current],
                                ),
                                transitionBuilder: (child, animation) {
                                  final entering =
                                      child.key == ValueKey('$id:$stage');
                                  final offset = Tween<Offset>(
                                    begin: Offset(
                                      entering
                                          ? .12 * _direction
                                          : -.12 * _direction,
                                      0,
                                    ),
                                    end: Offset.zero,
                                  ).animate(animation);
                                  return FadeTransition(
                                    opacity: animation,
                                    child: SlideTransition(
                                      position: offset,
                                      child: child,
                                    ),
                                  );
                                },
                                child: Column(
                                  key: ValueKey('$id:$stage'),
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    if (substep.text != null &&
                                        !substep.text!.startsWith('step_'))
                                      _Instruction(
                                        substep: substep,
                                        options: widget.latexOptions,
                                        onLink: widget.onLink,
                                      ),
                                    const SizedBox(height: 12),
                                    if (substep.left case final left?)
                                      StepEquation(
                                        latex: nodeToLatex(
                                          left,
                                          widget.latexOptions,
                                        ),
                                      ),
                                    if (substep.right case final right?) ...[
                                      if (substep.left != null)
                                        Padding(
                                          padding: const EdgeInsets.symmetric(
                                            vertical: 8,
                                          ),
                                          child: _FlowArrow(
                                            color: colors.primary,
                                            duration: _motion(380),
                                          ),
                                        ),
                                      StepEquation(
                                        latex: nodeToLatex(
                                          right,
                                          widget.latexOptions,
                                        ),
                                      ),
                                    ],
                                    _actions(context, substep),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 8),
                              const Divider(),
                              Wrap(
                                alignment: WrapAlignment.spaceBetween,
                                crossAxisAlignment: WrapCrossAlignment.center,
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  if (stage > 0)
                                    IconButton.outlined(
                                      key: const ValueKey('previous-stage'),
                                      tooltip: 'Предыдущий этап',
                                      icon: const Icon(Icons.chevron_left),
                                      onPressed: () =>
                                          _go(index, stage - 1, -1),
                                    )
                                  else if (index > 0)
                                    IconButton.outlined(
                                      tooltip: 'Предыдущий шаг',
                                      icon: const Icon(Icons.undo),
                                      onPressed: () {
                                        HapticFeedback.selectionClick();
                                        _direction = -1;
                                        select(index - 1);
                                      },
                                    ),
                                  if (stage < last)
                                    FilledButton.icon(
                                      key: const ValueKey('next-stage'),
                                      icon: const Icon(Icons.chevron_right),
                                      label: const Text('Следующий этап'),
                                      onPressed: () => _go(index, stage + 1, 1),
                                    )
                                  else if (index + 1 <
                                      widget.result.steps.length)
                                    FilledButton.icon(
                                      key: const ValueKey('next-group'),
                                      icon: const Icon(Icons.arrow_downward),
                                      label: const Text('Следующий шаг'),
                                      onPressed: () {
                                        HapticFeedback.mediumImpact();
                                        _direction = 1;
                                        select(index + 1);
                                      },
                                    ),
                                ],
                              ),
                            ],
                          ),
                        ),
                      ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _actions(BuildContext context, Substep substep) {
    final frames = transformationFrames(substep, widget.latexOptions);
    final nested =
        substep.subresult ??
        (substep.detail.isEmpty ? null : SolveResponse(steps: substep.detail));
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: [
        if (nested != null && nested.steps.any((s) => s.substeps.isNotEmpty))
          TextButton.icon(
            key: const ValueKey('step-details'),
            icon: const Icon(Icons.account_tree_outlined),
            label: const Text('Подробнее'),
            onPressed: () => Navigator.of(context).push(
              _riseRoute(
                context,
                (_) => Scaffold(
                  appBar: AppBar(title: const Text('Подробный разбор')),
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
          TextButton.icon(
            key: const ValueKey('step-theory'),
            icon: const Icon(Icons.lightbulb_outline),
            label: const Text('Почему?'),
            onPressed: () => Navigator.of(
              context,
            ).push(_riseRoute(context, (_) => _TheoryPage(article: article))),
          ),
        if (frames.isNotEmpty)
          TextButton.icon(
            icon: const Icon(Icons.play_circle_outline),
            label: const Text('Показать преобразование'),
            onPressed: () => Navigator.of(context).push(
              _riseRoute(context, (_) => TransformationLesson(frames: frames)),
            ),
          ),
      ],
    );
  }
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
    // Short coefficients stay in the sentence; compound arguments use display
    // blocks below so a root/fraction can scroll instead of overflowing prose.
    if (substep.links.isEmpty &&
        substep.parts.every(
          (p) =>
              p.node == null ||
              (p.node!.children.isEmpty && (p.node!.value?.length ?? 0) <= 4),
        )) {
      final style = Theme.of(context).textTheme.bodyLarge!;
      return Text.rich(
        TextSpan(
          children: [
            for (final part in substep.parts)
              if (part.node case final node?)
                WidgetSpan(
                  alignment: PlaceholderAlignment.middle,
                  child: Math.tex(
                    nodeToLatex(node, options),
                    mathStyle: MathStyle.text,
                    textStyle: style.copyWith(
                      fontSize: MediaQuery.textScalerOf(context)
                          .scale(style.fontSize!),
                    ),
                    onErrorFallback: (_) => Text(node.value ?? ''),
                  ),
                )
              else
                TextSpan(text: part.text),
          ],
        ),
        style: style,
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

class _TheoryPage extends StatelessWidget {
  const _TheoryPage({required this.article});
  final TheoryArticle article;
  @override
  Widget build(BuildContext context) => Scaffold(
    appBar: AppBar(title: const Text('Теория')),
    body: ListView(
      padding: const EdgeInsets.all(24),
      children: [
        Text(article.title, style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 16),
        Text(article.summary),
        if (article.formula.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(vertical: 16),
            child: StepEquation(latex: article.formula),
          ),
        for (final section in [
          ('Условия применения', article.conditions),
          ('Пример', article.example),
          ('Частая ошибка', article.mistake),
        ])
          if (section.$2.isNotEmpty) ...[
            const SizedBox(height: 20),
            Text(section.$1, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: 8),
            Text(section.$2),
          ],
      ],
    ),
  );
}

/// Long equations scroll instead of shrinking text below a readable size.
class StepEquation extends StatelessWidget {
  const StepEquation({super.key, required this.latex, this.fontSize = 22});
  final String latex;
  final double fontSize;
  @override
  Widget build(BuildContext context) => SingleChildScrollView(
    scrollDirection: Axis.horizontal,
    child: Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Math.tex(
        latex.replaceAllMapped(RegExp(r'\\textcolor\{#[0-9a-fA-F]{6}\}'), (_) {
          final accent = Theme.of(context).colorScheme.primary
              .toARGB32()
              .toRadixString(16)
              .padLeft(8, '0')
              .substring(2);
          return '\\textcolor{#$accent}';
        }),
        mathStyle: MathStyle.display,
        textStyle: TextStyle(
          fontSize: fontSize,
          color: Theme.of(context).colorScheme.onSurface,
        ),
        onErrorFallback: (_) =>
            Text(latex, style: Theme.of(context).textTheme.bodyLarge),
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
    super.key,
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
    label: 'Этап ${current + 1} из $count',
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
                  : PhColor.light,
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
