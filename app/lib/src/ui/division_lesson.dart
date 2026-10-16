import 'package:flutter/material.dart';
import '../render/division_trace.dart';
import '../settings/settings.dart';
import '../theme/phanto_theme.dart';

class DivisionLesson extends StatefulWidget {
  const DivisionLesson({super.key, required this.trace, this.method = DivisionMethod.ru, this.separator = ','});
  final DivisionTrace trace;
  final DivisionMethod method;
  final String separator;
  @override
  State<DivisionLesson> createState() => _DivisionLessonState();
}

class _DivisionLessonState extends State<DivisionLesson> {
  int _frame = 0;
  late final _anchors = List.generate(widget.trace.digits.length, (_) => GlobalKey());
  int get _last => widget.trace.digits.length * 4 - 1;
  @override
  Widget build(BuildContext context) {
    final trace = widget.trace;
    final index = _frame ~/ 4;
    final phase = _frame % 4;
    final step = trace.digits[index];
    final source = trace.dividend + (trace.decimalPlaces == 0 ? '' : widget.separator + '0' * trace.decimalPlaces);
    final quotient = (phase == 0 && index > 0 ? trace.digits[index - 1].quotient : step.quotient).replaceAll('.', widget.separator);
    final explanation = switch (phase) {
      0 => 'Берём ${step.partial}. Делим на ${trace.divisor}.',
      1 => 'Записываем ${step.digit} в частное: ${trace.divisor} помещается ${step.digit} раз.',
      2 => '${trace.divisor} × ${step.digit} = ${step.product}. Подписываем произведение под разрядами.',
      _ => '${step.partial} − ${step.product} = ${step.remainder}.${index + 1 < trace.digits.length ? ' Сносим следующую цифру.' : ''}',
    };
    final colors = Theme.of(context).colorScheme;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final anchor = _anchors[index].currentContext;
      if (mounted && anchor != null) Scrollable.ensureVisible(anchor, alignment: .6, duration: PhMotion.duration(context));
    });
    const cell = 22.0;
    final bodyOffset = widget.method == DivisionMethod.us ? (trace.divisor.toString().length + 2) * cell : 0.0;
    Widget cells(String text, {Color? color, bool highlight = false}) => Row(mainAxisSize: MainAxisSize.min, children: [
      for (var i = 0; i < text.length; i++) Container(width: cell, height: 32,
        color: highlight && phase == 0 && i == step.column ? colors.primaryContainer : null,
        alignment: Alignment.center,
        child: Text(text[i], style: TextStyle(fontFamily: 'monospace', fontSize: 22, color: color ?? colors.onSurface))),
    ]);
    Widget row(String text, int column, {bool line = false, bool active = false}) => Padding(
      padding: EdgeInsets.only(left: bodyOffset + (column + 1 - text.length).clamp(0, 40) * cell),
      child: AnimatedContainer(duration: PhMotion.duration(context), width: text.length * cell, height: 32,
        decoration: BoxDecoration(color: active ? colors.primaryContainer : null,
          border: line ? Border(bottom: BorderSide(color: colors.onSurface)) : null),
        child: cells(text, color: active ? colors.onPrimaryContainer : colors.onSurface),
      ),
    );
    return Scaffold(appBar: AppBar(title: const Text('Деление столбиком')), body: SafeArea(child: Column(children: [
      Expanded(child: SingleChildScrollView(padding: const EdgeInsets.all(20), child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: [
        SingleChildScrollView(scrollDirection: Axis.horizontal, child: SizedBox(
          width: (source.length + trace.divisor.toString().length + 5) * cell,
          child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
            if (widget.method == DivisionMethod.us) Row(children: [SizedBox(width: bodyOffset, child: cells('${trace.divisor} ⟌')), cells(source, highlight: true)]),
            if (widget.method != DivisionMethod.us) Row(children: [cells(source, highlight: true), cells(' │ ${trace.divisor}')]),
            Text('Частное: ${phase == 0 && index == 0 ? '—' : quotient}', style: TextStyle(fontSize: 18, color: colors.primary)),
            const SizedBox(height: 16),
            // Reserve every row from the start; advancing never moves old rows.
            for (var i = 0; i < trace.digits.length; i++) AnimatedOpacity(
              duration: PhMotion.duration(context), opacity: i <= index ? 1 : 0,
              child: ExcludeSemantics(excluding: i > index, child: Column(key: _anchors[i], crossAxisAlignment: CrossAxisAlignment.start, children: [
                row(trace.digits[i].partial.toString(), trace.digits[i].column),
                Opacity(opacity: i < index || phase >= 2 ? 1 : 0,
                  child: row(trace.digits[i].product.toString(), trace.digits[i].column, line: true, active: i == index && phase == 2)),
                Opacity(opacity: i < index || phase == 3 ? 1 : 0,
                  child: row(trace.digits[i].remainder.toString(), trace.digits[i].column, active: i == index && phase == 3)),
                const SizedBox(height: 8),
              ])),
            ),
          ]),
        )),
        if (_frame == _last) ...[
          const SizedBox(height: 12),
          Text(trace.repeatAt != null ? 'Остаток повторился: десятичная запись периодическая. Период начинается с ${trace.repeatAt! + 1}-й цифры после разделителя.'
            : trace.truncated ? 'Показаны первые 12 десятичных разрядов. Это не точная конечная запись.' : 'Остаток равен нулю. Деление завершено.'),
        ],
      ]))),
      Padding(padding: const EdgeInsets.all(16), child: Column(children: [
        AnimatedSwitcher(duration: PhMotion.duration(context), child: Text(explanation, key: ValueKey(_frame), style: Theme.of(context).textTheme.bodyLarge)),
        const SizedBox(height: 12),
        Semantics(liveRegion: true, child: Text('Этап ${_frame + 1} из ${_last + 1}')),
        Wrap(alignment: WrapAlignment.center, spacing: 8, children: [
          TextButton.icon(onPressed: () => setState(() => _frame = 0), icon: const Icon(Icons.replay), label: const Text('Повторить')),
          IconButton(tooltip: 'Предыдущий этап', onPressed: _frame == 0 ? null : () => setState(() => _frame--), icon: const Icon(Icons.chevron_left)),
          FilledButton(onPressed: _frame == _last ? null : () => setState(() => _frame++), child: const Text('Далее')),
        ]),
      ])),
    ])));
  }
}
