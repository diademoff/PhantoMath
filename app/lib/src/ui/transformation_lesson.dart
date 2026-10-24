import 'dart:async';

import 'package:flutter/material.dart';

import '../api/solver_api.dart';
import '../i18n.dart';
import '../model/core_node.dart';
import '../render/latex.dart';
import '../theme/phanto_theme.dart';
import 'vertical_result.dart';

typedef LessonFrame = ({String latex, String explanation});

/// Only construct an intermediate expression when its rule is established by
/// the AST. Unknown transformations retain the solver's ordinary text details.
List<LessonFrame> transformationFrames(Substep step, LatexOptions options) {
  final left = step.left;
  final right = step.right;
  if (left == null || right == null) return const [];
  String latex(CoreNode n) => nodeToLatex(n, options);
  final frames = <LessonFrame>[
    (
      latex: latex(left),
      explanation: tr('Исходное выражение', 'Original expression'),
    ),
  ];
  if ({
        CoreNodeType.multiply,
        CoreNodeType.multiplyImplicit,
      }.contains(left.type) &&
      left.children.length == 2) {
    final a = left.children[0];
    var b = left.children[1];
    if (b.type == CoreNodeType.bracket && b.children.length == 1) {
      b = b.children.single;
    }
    if (b.type != CoreNodeType.add ||
        b.children.length < 2 ||
        b.children.length > 4) {
      return const [];
    }
    for (var i = 0; i < b.children.length; i++) {
      frames.add((
        latex:
            '${latex(a)} \\cdot \\left(${b.children.map(latex).join(' + ')}\\right)',
        explanation: tr(
          'Распределительный закон: умножаем общий множитель на ${i + 1}-е слагаемое.',
          'Distributive law: multiply the common factor by term ${i + 1}.',
        ),
      ));
      final completed = b.children
          .take(i + 1)
          .map(
            (term) =>
                '\\left(${latex(a)}\\right)\\cdot\\left(${latex(term)}\\right)',
          )
          .join(' + ');
      final remaining = b.children.skip(i + 1).map(latex).join(' + ');
      frames.add((
        latex:
            completed +
            (remaining.isEmpty
                ? ''
                : ' + \\left(${latex(a)}\\right)\\cdot\\left($remaining\\right)'),
        explanation: i + 1 == b.children.length
            ? tr(
                'Каждое слагаемое умножено на общий множитель.',
                'Every term has been multiplied by the common factor.',
              )
            : tr(
                'Остальные слагаемые пока оставляем в скобках.',
                'The remaining terms are left in parentheses for now.',
              ),
      ));
    }
  } else if (left.type == CoreNodeType.fraction && left.children.length == 2) {
    final a = BigInt.tryParse(left.children[0].value ?? '');
    final b = BigInt.tryParse(left.children[1].value ?? '');
    if (a == null || b == null || a <= BigInt.zero || b <= BigInt.zero) {
      return const [];
    }
    final gcd = a.gcd(b);
    if (gcd <= BigInt.one) return const [];
    frames.add((
      latex: '\\frac{${a ~/ gcd}\\cdot $gcd}{${b ~/ gcd}\\cdot $gcd}',
      explanation: tr(
        'Выделяем общий множитель $gcd в числителе и знаменателе.',
        'Factor out $gcd from the numerator and denominator.',
      ),
    ));
    frames.add((
      latex:
          '\\frac{${a ~/ gcd}\\cdot \\cancel{$gcd}}{${b ~/ gcd}\\cdot \\cancel{$gcd}}',
      explanation: tr(
        'Делим числитель и знаменатель на одно и то же ненулевое число.',
        'Divide the numerator and denominator by the same non-zero number.',
      ),
    ));
  } else if (left.type == CoreNodeType.negative &&
      left.children.length == 1 &&
      left.children.single.type == CoreNodeType.negative &&
      left.children.single.children.length == 1) {
    frames.add((
      latex: latex(left.children.single.children.single),
      explanation: tr(
        'Два противоположных изменения знака взаимно уничтожаются.',
        'Two opposite sign changes cancel each other.',
      ),
    ));
  } else {
    return const [];
  }
  frames.add((
    latex: latex(right),
    explanation: step.text?.startsWith('step_') == false
        ? step.text!
        : tr('Результат преобразования', 'Result of the transformation'),
  ));
  return frames;
}

class TransformationLesson extends StatefulWidget {
  const TransformationLesson({super.key, required this.frames});
  final List<LessonFrame> frames;
  @override
  State<TransformationLesson> createState() => _TransformationLessonState();
}

class _TransformationLessonState extends State<TransformationLesson> {
  int _index = 0;
  Timer? _timer;
  bool get _playing => _timer != null;
  void _pause() {
    _timer?.cancel();
    _timer = null;
  }

  void _play() {
    if (_playing) {
      setState(_pause);
      return;
    }
    if (_index == widget.frames.length - 1) _index = 0;
    _timer = Timer.periodic(const Duration(milliseconds: 1800), (_) {
      if (!mounted) return;
      setState(() {
        if (_index + 1 < widget.frames.length) {
          _index++;
        } else {
          _pause();
        }
      });
    });
    setState(() {});
  }

  @override
  void dispose() {
    _pause();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (MediaQuery.disableAnimationsOf(context)) _pause();
  }

  @override
  Widget build(BuildContext context) {
    final frame = widget.frames[_index];
    return Scaffold(
      appBar: AppBar(
        title: Text(tr('Как это получилось', 'How this was obtained')),
      ),
      body: SafeArea(
        child: Column(
          children: [
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    Text(
                      tr('Преобразование', 'Transformation'),
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const SizedBox(height: 32),
                    AnimatedSwitcher(
                      duration: PhMotion.duration(context, 280),
                      child: StepEquation(
                        key: ValueKey(_index),
                        latex: frame.latex,
                        fontSize: 30,
                      ),
                    ),
                    const SizedBox(height: 32),
                    Semantics(
                      liveRegion: true,
                      child: Text(
                        frame.explanation,
                        style: Theme.of(context).textTheme.bodyLarge,
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                children: [
                  Text(
                    tr(
                      'Этап ${_index + 1} из ${widget.frames.length}',
                      'Stage ${_index + 1} of ${widget.frames.length}',
                    ),
                  ),
                  Wrap(
                    alignment: WrapAlignment.center,
                    spacing: 8,
                    children: [
                      IconButton(
                        tooltip: tr('Повторить', 'Replay'),
                        onPressed: () => setState(() {
                          _pause();
                          _index = 0;
                        }),
                        icon: const Icon(Icons.replay),
                      ),
                      IconButton(
                        tooltip: tr('Предыдущий этап', 'Previous stage'),
                        onPressed: _index == 0
                            ? null
                            : () => setState(() {
                                _pause();
                                _index--;
                              }),
                        icon: const Icon(Icons.chevron_left),
                      ),
                      if (!MediaQuery.disableAnimationsOf(context))
                        IconButton(
                          tooltip: _playing
                              ? tr('Пауза', 'Pause')
                              : tr('Воспроизвести', 'Play'),
                          onPressed: _play,
                          icon: Icon(_playing ? Icons.pause : Icons.play_arrow),
                        ),
                      FilledButton(
                        onPressed: _index + 1 == widget.frames.length
                            ? null
                            : () => setState(() {
                                _pause();
                                _index++;
                              }),
                        child: Text(tr('Далее', 'Next')),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
