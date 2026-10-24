import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';
import 'package:mymath_app/src/ui/vertical_result.dart';

import 'support/card_rules.dart';

/// Reads the solver's cards as the student sees them and writes a transcript,
/// an index and the problems found by [card_rules.dart].
///
/// The cards come from `tools/audit/dump_cards.py` (`make cards`); without
/// `CARDS`/`CARDS_OUT` the test is skipped.
void main() {
  final cards = Platform.environment['CARDS'];
  final out = Platform.environment['CARDS_OUT'];
  test(
    'solution cards read as text',
    skip: cards == null || out == null
        ? 'set CARDS and CARDS_OUT (make cards)'
        : false,
    () async {
      cards!;
      out!;
      final cases = jsonDecode(File(cards).readAsStringSync()) as List<dynamic>;
      final directory = Directory(out)..createSync(recursive: true);
      final index = <String>[];
      final found = <({String id, CardProblem problem})>[];
      final counts = <String, int>{};
      var total = 0;
      var stages = 0;

      for (final raw in cases.cast<Map<String, dynamic>>()) {
        final id = raw['id'] as String;
        final proto = raw['proto'] as String;
        final error = raw['error'] as String?;
        if (error != null) {
          File('${directory.path}/$id.md')
              .writeAsStringSync('# $id   $proto\n\nОшибка решателя: $error\n');
          index.add('$id | — | шагов 0, этапов 0 | проблем 0');
          continue;
        }
        final api = SolverApi(
          baseUrl: 'http://t',
          client: MockClient(
            (_) async => http.Response.bytes(
              utf8.encode(jsonEncode(raw['response'])),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            ),
          ),
        );
        final result = await api.solve(
          const CoreNode(type: CoreNodeType.constant, value: '1'),
        );
        api.close();

        final caseProblems = <CardProblem>[];
        final text = _transcript(id, proto, result, caseProblems);
        File('${directory.path}/$id.md').writeAsStringSync(text);

        for (final problem in caseProblems) {
          found.add((id: id, problem: problem));
          counts[problem.rule] = (counts[problem.rule] ?? 0) + 1;
        }
        total += caseProblems.length;
        final caseStages = result.steps.fold<int>(
          0,
          (sum, step) => sum + step.substeps.length,
        );
        stages += caseStages;
        index.add(
          '$id | ${_answer(result) ?? '—'} | '
          'шагов ${result.steps.length}, этапов $caseStages | '
          'проблем ${caseProblems.length}',
        );
      }
      File('${directory.path}/index.md')
          .writeAsStringSync('# cards index\n\n${index.join('\n')}\n');
      // `text-math` repeats word for word across cards («Положим y = uv.» is in
      // eight); report each distinct phrase once and count the cards, otherwise
      // the rule drowns the file.
      final lines = <String>[];
      final positions = <String, int>{};
      final repeats = <String, int>{};
      final distinct = <String, int>{};
      for (final entry in found) {
        final problem = entry.problem;
        final key = '${problem.rule}\t${problem.detail}';
        if (problem.rule == 'text-math') {
          final at = positions[key];
          if (at != null) {
            repeats[key] = repeats[key]! + 1;
            continue;
          }
          positions[key] = lines.length;
          repeats[key] = 1;
          distinct[problem.rule] = (distinct[problem.rule] ?? 0) + 1;
        }
        lines.add(problem.line(entry.id));
      }
      for (final entry in positions.entries) {
        final count = repeats[entry.key]!;
        if (count > 1) {
          lines[entry.value] =
              '${lines[entry.value]} — $count ${_cards(count)}';
        }
      }
      File('${directory.path}/problems.txt')
          .writeAsStringSync(lines.isEmpty ? '' : '${lines.join('\n')}\n');
      counts['__cases'] = cases.length;
      counts['__stages'] = stages;
      // ignore: avoid_print
      print(
        'cards: ${cases.length} cases, $stages stages, $total problems, '
        'by rule: ${_sorted(counts)}, distinct text-math: '
        '${distinct['text-math'] ?? 0}',
      );
    },
  );
}

String _transcript(
  String id,
  String proto,
  SolveResponse result,
  List<CardProblem> problems,
) {
  final buffer = StringBuffer()
    ..writeln('# $id   $proto')
    ..writeln();
  final answer = _answer(result);
  buffer.write('Ответ: ${answer == null ? '—' : '\$$answer\$'}');
  if (result.alternatives.isNotEmpty) {
    buffer.write(
      '        (alternatives: '
      '${result.alternatives.map((n) => '\$${nodeToLatex(n, _options)}\$').join(', ')})',
    );
  }
  buffer.writeln();
  if (answer != null) {
    problems.addAll(answerProblems('ответ', answer));
  }
  for (var i = 0; i < result.alternatives.length; i++) {
    problems.addAll(
      answerProblems(
        'альтернатива ${i + 1}',
        nodeToLatex(result.alternatives[i], _options),
      ),
    );
  }

  final methods = result.methods.isEmpty ? [result] : result.methods;
  final switcher = result.selectMethodText ?? 'Способ решения';
  for (var m = 0; m < methods.length; m++) {
    final method = methods[m];
    final header = method.header?.trim() ?? '';
    final title = header.isEmpty ? 'Способ ${m + 1}' : header;
    buffer
      ..writeln()
      ..writeln(
        '## $title'
        '${methods.length > 1 ? '   ($switcher ${m + 1}/${methods.length})' : ''}',
      );
    _steps(buffer, method.steps, problems, prefix: '', depth: 0);
  }
  return buffer.toString();
}

const _options = LatexOptions.standard;

String? _answer(SolveResponse result) {
  final solution = result.solution;
  if (solution != null && solution.type != CoreNodeType.empty) {
    return nodeToLatex(solution, _options);
  }
  return result.verdictLatex;
}

void _steps(
  StringBuffer buffer,
  List<SolveStep> steps,
  List<CardProblem> problems, {
  required String prefix,
  required int depth,
}) {
  final pad = '  ' * depth;
  final headings = <({String where, String heading})>[];
  for (var i = 0; i < steps.length; i++) {
    final step = steps[i];
    if (step.substeps.isEmpty) continue;
    final heading = _heading(step);
    headings.add((where: '$prefixШаг ${i + 1} · заголовок', heading: heading));
  }
  problems.addAll(headingProblems(headings));
  for (var i = 0; i < steps.length; i++) {
    final step = steps[i];
    if (step.substeps.isEmpty) continue;
    buffer.writeln('$pad### Шаг ${i + 1} — ${_heading(step)}');
    for (var s = 0; s < step.substeps.length; s++) {
      _stage(
        buffer,
        step.substeps[s],
        problems,
        where: '$prefixШаг ${i + 1} Этап ${s + 1}',
        number: '${s + 1}/${step.substeps.length}',
        pad: pad,
        depth: depth,
      );
    }
  }
}

void _stage(
  StringBuffer buffer,
  Substep stage,
  List<CardProblem> problems, {
  required String where,
  required String number,
  required String pad,
  required int depth,
}) {
  final left = _latex(stage.left);
  final right = _latex(stage.right);
  problems.addAll(stageFormulaProblems(where, left: left, right: right));

  final lines = _textLines(stage, problems, where);
  final indent = '$pad     ';
  if (lines.isEmpty) {
    buffer.writeln('$pad$number.');
  } else {
    buffer.writeln('$pad$number. ${lines.first}');
    for (final line in lines.skip(1)) {
      buffer.writeln('$indent$line');
    }
  }
  if (left != null || right != null) {
    final arrow = left != null && right != null ? ' → ' : '';
    buffer.writeln(
      '$indent${[if (left != null) '\$$left\$', if (right != null) '\$$right\$'].join(arrow)}',
    );
  }

  final nested =
      stage.subresult ??
      (stage.detail.isEmpty ? null : SolveResponse(steps: stage.detail));
  if (nested != null && nested.steps.any((s) => s.substeps.isNotEmpty)) {
    final title = nested.header?.trim() ?? '';
    final nestedTitle = title.isEmpty ? 'Подробный разбор' : title;
    buffer.writeln('$indent[Подробнее: $nestedTitle]');
    if (depth < 3) {
      final nestedPad = '$pad      ';
      final nestedAnswer = _answer(nested);
      if (nestedAnswer != null) {
        buffer.writeln('$nestedPadОтвет: \$$nestedAnswer\$');
        problems.addAll(
          answerProblems('$where · Подробнее · ответ', nestedAnswer),
        );
      }
      _steps(
        buffer,
        nested.steps,
        problems,
        prefix: '$where · Подробнее · ',
        depth: depth + 1,
      );
    }
  }
  if (stage.theory case final theory?) {
    buffer.writeln('$indent[Теория: ${theory.title}]');
  }
}

/// Prose of a stage with inline formulas as `$latex$` and display formulas on
/// their own line — the same split as `_Instruction` in `vertical_result.dart`.
List<String> _textLines(
  Substep stage,
  List<CardProblem> problems,
  String where,
) {
  final text = stage.text;
  if (text == null || text.startsWith('step_')) return const [];
  final nodes = [for (final part in stage.parts) ?part.node];
  if (nodes.isEmpty) {
    problems.addAll(textProblems('$where · текст', text));
    return [text];
  }

  final lines = <String>[];
  final run = <String>[];
  void flush() {
    if (run.isNotEmpty) lines.add(run.join());
    run.clear();
  }

  for (final part in stage.parts) {
    final node = part.node;
    if (node != null) {
      final latex = nodeToLatex(node, _options);
      problems.addAll(partProblems('$where · текст', latex));
      if (stage.links.isEmpty && isInlineFormula(node, _options)) {
        run.add('\$$latex\$');
      } else {
        flush();
        lines.add('\$$latex\$');
      }
    } else if ((part.text ?? '').isNotEmpty) {
      // A stage that already draws formula parts has its formula split on
      // purpose; the prose between the parts is glue, not missed maths. Only a
      // text-only stage is checked for typed maths (see `card_rules.dart`).
      problems.addAll(englishProblems('$where · текст', part.text!));
      run.add(part.text!);
    }
  }
  flush();
  problems.addAll(
    repeatProblems(
      where,
      [for (final node in nodes) nodeToLatex(node, _options)],
      left: _latex(stage.left),
      right: _latex(stage.right),
    ),
  );
  return lines;
}

String? _latex(CoreNode? node) {
  if (node == null) return null;
  final latex = nodeToLatex(node, _options);
  return latex.isEmpty ? null : latex;
}

String _heading(SolveStep step) {
  final title = step.headers.where((h) => h.isNotEmpty).join(' · ');
  return title.isEmpty ? 'Преобразование' : title;
}

String _sorted(Map<String, int> counts) {
  final keys = counts.keys.toList()..sort();
  return keys.map((key) => '$key: ${counts[key]}').join(', ');
}

/// «1 карточка», «2 карточки», «5 карточек».
String _cards(int count) {
  final tens = count % 100;
  final last = count % 10;
  if (tens >= 11 && tens <= 14) return 'карточек';
  if (last == 1) return 'карточка';
  if (last >= 2 && last <= 4) return 'карточки';
  return 'карточек';
}
