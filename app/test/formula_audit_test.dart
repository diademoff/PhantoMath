import 'dart:convert';
import 'dart:io';

import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';

/// Parses every formula of the solver's answers with the real TeX parser. The answers come from
/// `tools/audit/dump_contracts.py` (`make audit`); without `CONTRACTS` the test is skipped.
void main() {
  final path = Platform.environment['CONTRACTS'];
  test(
    'every formula of the backend answers parses',
    skip: path == null ? 'set CONTRACTS (make audit)' : false,
    () async {
      path!;
      final cases = jsonDecode(File(path).readAsStringSync()) as List<dynamic>;
      final problems = <String, String>{};
      var formulas = 0;
      final lost = <String, String>{};
      String flat(String text) => text.replaceAll(RegExp(r'\s+'), '');
      // A node that renders fewer operands than it has silently hides part of the answer.
      void everyChildShown(CoreNode node, String source, String where) {
        // digits of a periodic fraction are drawn, not child formulas
        if (node.type == CoreNodeType.periodic) {
          return;
        }
        final latex = flat(nodeToLatex(node, LatexOptions.standard));
        for (final (index, child) in node.children.indexed) {
          // a bracketed exponent is drawn with plain parentheses (latex.dart, power)
          final plain =
              node.type == CoreNodeType.power &&
              index == 1 &&
              child.type == CoreNodeType.bracket &&
              child.children.length == 1;
          final part = flat(
            plain
                ? '(${nodeToLatex(child.children.single, LatexOptions.standard)})'
                : nodeToLatex(child, LatexOptions.standard),
          );
          if (part.isNotEmpty && !latex.contains(part)) {
            lost['$source @ $where ${node.type.wire}'] =
                'child ${child.type.wire} missing in $latex';
          }
          everyChildShown(child, source, where);
        }
      }

      void check(CoreNode? node, String source, String where) {
        if (node == null) return;
        everyChildShown(node, source, where);
        final latex = nodeToLatex(node, LatexOptions.standard);
        formulas++;
        if (latex.contains('□') ||
            latex.trim().isEmpty && node.type != CoreNodeType.empty) {
          problems['$source @ $where'] = 'empty/placeholder: ${node.type.wire}';
          return;
        }
        final error = Math.tex(latex).parseError;
        if (error != null) problems['$source @ $where'] = '$error :: $latex';
      }

      void steps(List<SolveStep> list, String source, String where) {
        for (final step in list) {
          for (final sub in step.substeps) {
            check(sub.left, source, '$where.left');
            check(sub.right, source, '$where.right');
            for (final part in sub.parts) {
              check(part.node, source, '$where.part');
            }
            steps(sub.detail, source, '$where.detail');
          }
        }
      }

      for (final item in cases.cast<Map<String, dynamic>>()) {
        final source = item['input'] as String;
        final api = SolverApi(
          baseUrl: 'http://t',
          client: MockClient(
            (_) async => http.Response.bytes(
              utf8.encode(jsonEncode(item['response'])),
              200,
              headers: {'content-type': 'application/json; charset=utf-8'},
            ),
          ),
        );
        final response = await api.solve(
          CoreNode(type: CoreNodeType.constant, value: '1'),
        );
        check(response.solution, source, 'solution');
        for (final form in response.alternatives) {
          check(form, source, 'alternative');
        }
        steps(response.steps, source, 'steps');
        for (final m in response.methods) {
          check(m.solution, source, 'method.solution');
          steps(m.steps, source, 'method');
        }
      }
      // ignore: avoid_print
      print(
        'formulas checked: $formulas, problems: ${problems.length}, '
        'lost operands: ${lost.length}',
      );
      final kinds = <String, int>{};
      for (final key in lost.keys) {
        final type = key.split(' ').last;
        kinds[type] = (kinds[type] ?? 0) + 1;
      }
      // ignore: avoid_print
      print('lost by node type: $kinds');
      for (final e in lost.entries.take(12)) {
        // ignore: avoid_print
        print('LOST ${e.key} -> ${e.value}');
      }
      for (final e in problems.entries.take(40)) {
        // ignore: avoid_print
        print('${e.key} -> ${e.value}');
      }
      expect(problems, isEmpty);
      expect(
        lost,
        isEmpty,
        reason: "a node rendered fewer operands than it has",
      );
    },
  );
}
