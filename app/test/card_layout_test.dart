import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_math_fork/flutter_math.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:mymath_app/src/api/solver_api.dart';
import 'package:mymath_app/src/model/core_node.dart';
import 'package:mymath_app/src/render/latex.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';
import 'package:mymath_app/src/ui/formula_break.dart';
import 'package:mymath_app/src/ui/vertical_result.dart';

/// Draws every solution card on a Pixel 4a screen with real fonts and reports
/// layout that the operator cannot see in a screenshot: overflow, formulas the
/// card had to break or shrink, and formulas that only fit by scrolling
/// sideways (nothing else helped).
///
/// The cards come from `tools/audit/dump_cards.py` (`make cards`); without
/// `CARDS`/`CARDS_OUT` the test is skipped. `CARDS_PNG=all` saves a PNG of every
/// screen, not only of the flagged ones.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  final cards = Platform.environment['CARDS'];
  final out = Platform.environment['CARDS_OUT'];
  final skip = cards == null || out == null
      ? 'set CARDS and CARDS_OUT (make cards)'
      : null;
  final pngAll = Platform.environment['CARDS_PNG'] == 'all';
  final counts = <String, int>{
    'cases': 0,
    'screens': 0,
    'wide': 0,
    'overflow': 0,
    'broken': 0,
    'scaled': 0,
  };

  if (skip == null) {
    setUpAll(() async {
      await _loadFonts();
      final directory = Directory(out!)..createSync(recursive: true);
      Directory('${directory.path}/png').createSync(recursive: true);
      File('${directory.path}/layout.txt').writeAsStringSync('');
    });
    tearDownAll(() {
      // ignore: avoid_print
      print(
        'layout: ${counts['cases']} cases, ${counts['screens']} screens, '
        '${counts['wide']} wide, ${counts['overflow']} overflow, '
        '${counts['broken']} broken, ${counts['scaled']} scaled',
      );
    });
  }

  final cases = skip == null
      ? (jsonDecode(File(cards!).readAsStringSync()) as List<dynamic>)
            .cast<Map<String, dynamic>>()
      : const <Map<String, dynamic>>[];
  for (final item in cases) {
    testWidgets('layout ${item['id']}', skip: skip != null, (tester) async {
      final response = await _solve(item);
      if (response == null) return;
      counts['cases'] = counts['cases']! + 1;
      tester.view.physicalSize = const Size(1080, 2340);
      tester.view.devicePixelRatio = 2.75;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final id = item['id'] as String;
      final methods = response.methods.isEmpty ? [response] : response.methods;
      for (var m = 0; m < methods.length; m++) {
        await _pumpCase(
          tester,
          id: id,
          method: m,
          result: methods[m],
          out: out!,
          pngAll: pngAll,
          counts: counts,
        );
      }
    });
  }

  testWidgets('fonts are real, not the Ahem boxes', skip: skip != null, (
    tester,
  ) async {
    expect(_textWidth('x', null), closeTo(20, .5)); // Ahem paints a square
    expect(
      _textWidth('x', null),
      isNot(closeTo(_textWidth('x', _katexMain), .5)),
    );
    expect(
      _textWidth('MMMM', null),
      isNot(closeTo(_textWidth('MMMM', 'Roboto'), .5)),
    );
    await tester.pumpWidget(
      MaterialApp(
        home: Center(child: Math.tex(r'x+y', mathStyle: MathStyle.display)),
      ),
    );
    final math = tester.getSize(find.byType(Math)).width;
    expect(math, isNot(closeTo(_textWidth('x+y', null), .5)));
  });
}

const String _katexMain = 'packages/flutter_math_fork/KaTeX_Main';

Future<SolveResponse?> _solve(Map<String, dynamic> item) async {
  if (item['error'] != null) return null;
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
    const CoreNode(type: CoreNodeType.constant, value: '1'),
  );
  api.close();
  return response;
}

// The theme's own text styles name no family: on the phone that is the system
// Roboto, in a test the box font — so give every style Roboto explicitly.
final _theme = PhantoTheme.light().copyWith(
  textTheme: PhantoTheme.light().textTheme.apply(fontFamily: 'Roboto'),
  primaryTextTheme: PhantoTheme.light().primaryTextTheme.apply(
    fontFamily: 'Roboto',
  ),
);

Widget _page(SolveResponse result, GlobalKey boundary) => MaterialApp(
  theme: _theme,
  builder: (context, child) => MediaQuery(
    data: MediaQuery.of(context)
        .copyWith(textScaler: TextScaler.noScaling, disableAnimations: true),
    child: child!,
  ),
  home: Scaffold(
    body: RepaintBoundary(
      key: boundary,
      child: ColoredBox(
        color: PhantoTheme.light().scaffoldBackgroundColor,
        child: VerticalResult(
          result: result,
          latexOptions: LatexOptions.standard,
          onLink: (_) {},
          onCopy: (_) {},
        ),
      ),
    ),
  ),
);

Future<void> _pumpCase(
  WidgetTester tester, {
  required String id,
  required int method,
  required SolveResponse result,
  required String out,
  required bool pngAll,
  required Map<String, int> counts,
}) async {
  final boundary = GlobalKey();
  await tester.pumpWidget(_page(result, boundary));
  await tester.pumpAndSettle();
  final reported = <String>{};
  final tag = method == 0 ? id : '${id}_m${method + 1}';

  Future<void> screen(int group, int stage) async {
    counts['screens'] = counts['screens']! + 1;
    final position = 'g${group + 1}/s${stage + 1}';
    final problems = <String>[];
    Object? error;
    try {
      error = tester.takeException();
    } on Object catch (problem) {
      error = problem;
    }
    if (error != null) {
      counts['overflow'] = counts['overflow']! + 1;
      final line =
          '$id\t$position\toverflow\t${error.toString().split('\n').first}';
      File('$out/layout.txt')
          .writeAsStringSync('$line\n', mode: FileMode.append);
      problems.add(line);
    }
    for (final hit in _fitted(tester, result, group, stage)) {
      final key = '${hit.fit.name}\t${hit.place}\t${hit.latex}';
      if (!reported.add(key)) continue;
      counts[hit.fit.name] = counts[hit.fit.name]! + 1;
    }
    for (final hit in _wide(tester, result, group, stage)) {
      final key = '${hit.place}\t${hit.latex}';
      if (!reported.add(key)) continue;
      counts['wide'] = counts['wide']! + 1;
      final line =
          '$id\t$position\twide\t'
          '${hit.place}: ${hit.latex} — шире на '
          '${hit.overflow.toStringAsFixed(0)} dp';
      File('$out/layout.txt')
          .writeAsStringSync('$line\n', mode: FileMode.append);
      problems.add(line);
    }
    if (pngAll || problems.isNotEmpty) {
      await _png(
        tester,
        boundary,
        '$out/png/${tag}_${group + 1}_${stage + 1}.png',
      );
    }
  }

  await screen(0, 0);
  for (var g = 0; g < result.steps.length; g++) {
    final step = result.steps[g];
    if (step.substeps.isEmpty) continue;
    if (g > 0) {
      final finder = find.byKey(ValueKey('solution-group:$g'));
      await tester.scrollUntilVisible(
        finder,
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(finder);
      await tester.pumpAndSettle();
    }
    for (var s = 0; s < step.substeps.length; s++) {
      await tester.ensureVisible(find.byKey(ValueKey('${step.id}:$g:$s')));
      await tester.pumpAndSettle();
      if (g > 0 || s > 0) await screen(g, s);
      if (s + 1 < step.substeps.length) {
        final next = find.byKey(const ValueKey('next-stage'));
        await tester.ensureVisible(next);
        await tester.pumpAndSettle();
        await tester.tap(next);
        await tester.pumpAndSettle();
      }
    }
  }
}

class _Wide {
  const _Wide(this.place, this.latex, this.overflow);
  final String place;
  final String latex;
  final double overflow;
}

class _Fitted {
  const _Fitted(this.fit, this.place, this.latex);
  final FormulaFit fit;
  final String place;
  final String latex;
}

/// Formulas the card had to break across lines or shrink (`formula_break.dart`).
List<_Fitted> _fitted(
  WidgetTester tester,
  SolveResponse result,
  int activeGroup,
  int stage,
) {
  final out = <_Fitted>[];
  for (final element in find.byType(FormulaFlow).evaluate()) {
    final render = element.renderObject;
    if (render is! RenderFormulaFlow) continue;
    final fit = render.fit;
    if (fit != FormulaFit.broken && fit != FormulaFit.scaled) continue;
    final latex = _stepLatex(element);
    if (latex == null) continue;
    final place = _place(element, result, activeGroup, stage, latex);
    if (place == null) continue;
    out.add(_Fitted(fit, place, latex));
  }
  return out;
}

/// Formulas that still need the horizontal scroll: broken lines and shrinkage
/// could not make them fit (`formula_break.dart`), so the student only sees the
/// left part with a fade at the cut edge.
List<_Wide> _wide(
  WidgetTester tester,
  SolveResponse result,
  int activeGroup,
  int stage,
) {
  final out = <_Wide>[];
  for (final element in find.byType(Scrollable).evaluate()) {
    final widget = element.widget as Scrollable;
    if (widget.axisDirection != AxisDirection.right &&
        widget.axisDirection != AxisDirection.left) {
      continue;
    }
    final state = (element as StatefulElement).state;
    if (state is! ScrollableState) continue;
    final position = state.position;
    if (position.maxScrollExtent <= 1) continue;
    final latex = _stepLatex(element);
    if (latex == null) continue;
    final place = _place(element, result, activeGroup, stage, latex);
    if (place == null) continue;
    out.add(_Wide(place, latex, position.maxScrollExtent));
  }
  return out;
}

/// Answer card / stage left / stage right / text block, or `null` for a
/// collapsed card preview (it is checked when its own step is open).
String? _place(
  Element element,
  SolveResponse result,
  int activeGroup,
  int stage,
  String latex,
) {
  int? headerGroup;
  var inStage = false;
  final step = activeGroup < result.steps.length
      ? result.steps[activeGroup]
      : null;
  final stageKey = step == null ? null : '${step.id}:$activeGroup:$stage';
  element.visitAncestorElements((ancestor) {
    final key = ancestor.widget.key;
    if (key is ValueKey<String>) {
      final value = key.value;
      if (value.startsWith('solution-group:')) {
        headerGroup = int.tryParse(value.split(':').last);
      } else if (value == stageKey) {
        inStage = true;
      }
    }
    return true;
  });
  if (inStage) {
    final substep = step?.substeps[stage];
    if (substep == null) return 'stage';
    if (_latex(substep.left) == latex) return 'stage left';
    if (_latex(substep.right) == latex) return 'stage right';
    return 'text block';
  }
  // A formula of a collapsed card header: its own step checks it when open.
  if (headerGroup != null) return null;
  return 'answer';
}

String? _stepLatex(Element element) {
  String? latex;
  element.visitAncestorElements((ancestor) {
    if (ancestor.widget case final StepEquation equation) {
      latex = equation.latex;
      return false;
    }
    return true;
  });
  return latex;
}

String? _latex(CoreNode? node) {
  if (node == null) return null;
  final latex = nodeToLatex(node, LatexOptions.standard);
  return latex.isEmpty ? null : latex;
}

Future<void> _png(WidgetTester tester, GlobalKey boundary, String path) async {
  final object = tester.renderObject<RenderRepaintBoundary>(
    find.byKey(boundary),
  );
  await tester.runAsync(() async {
    final image = await object.toImage(pixelRatio: 2);
    final data = await image.toByteData(format: ui.ImageByteFormat.png);
    image.dispose();
    if (data != null) {
      File(path).writeAsBytesSync(data.buffer.asUint8List());
    }
  });
}

double _textWidth(String text, String? family) {
  final painter = TextPainter(
    text: TextSpan(
      text: text,
      style: TextStyle(fontFamily: family, fontSize: 20),
    ),
    textDirection: TextDirection.ltr,
  )..layout();
  return painter.width;
}

/// Roboto and the KaTeX families of `flutter_math_fork`.
///
/// Without them `flutter test` draws every text in the Ahem block font and the
/// measured widths mean nothing. KaTeX is registered under the family name the
/// package asks for (`packages/flutter_math_fork/KaTeX_Main`, …); a wrong name
/// silently keeps Ahem.
Future<void> _loadFonts() async {
  final flutter = _flutterRoot();
  final roboto = FontLoader('Roboto');
  for (final name in const [
    'Roboto-Regular.ttf',
    'Roboto-Medium.ttf',
    'Roboto-Bold.ttf',
  ]) {
    final file = File('$flutter/bin/cache/artifacts/material_fonts/$name');
    if (!file.existsSync()) continue;
    roboto.addFont(Future.value(ByteData.sublistView(file.readAsBytesSync())));
  }
  await roboto.load();
  final icons = File(
    '$flutter/bin/cache/artifacts/material_fonts/MaterialIcons-Regular.otf',
  );
  if (icons.existsSync()) {
    await (FontLoader(
          'MaterialIcons',
        )..addFont(Future.value(ByteData.sublistView(icons.readAsBytesSync()))))
        .load();
  }

  const families = <String, List<String>>{
    'KaTeX_Main': [
      'KaTeX_Main-Regular.ttf',
      'KaTeX_Main-Italic.ttf',
      'KaTeX_Main-Bold.ttf',
      'KaTeX_Main-BoldItalic.ttf',
    ],
    'KaTeX_Math': ['KaTeX_Math-Italic.ttf', 'KaTeX_Math-BoldItalic.ttf'],
    'KaTeX_AMS': ['KaTeX_AMS-Regular.ttf'],
    'KaTeX_Caligraphic': [
      'KaTeX_Caligraphic-Regular.ttf',
      'KaTeX_Caligraphic-Bold.ttf',
    ],
    'KaTeX_Fraktur': ['KaTeX_Fraktur-Regular.ttf', 'KaTeX_Fraktur-Bold.ttf'],
    'KaTeX_SansSerif': [
      'KaTeX_SansSerif-Regular.ttf',
      'KaTeX_SansSerif-Bold.ttf',
      'KaTeX_SansSerif-Italic.ttf',
    ],
    'KaTeX_Script': ['KaTeX_Script-Regular.ttf'],
    'KaTeX_Size1': ['KaTeX_Size1-Regular.ttf'],
    'KaTeX_Size2': ['KaTeX_Size2-Regular.ttf'],
    'KaTeX_Size3': ['KaTeX_Size3-Regular.ttf'],
    'KaTeX_Size4': ['KaTeX_Size4-Regular.ttf'],
    'KaTeX_Typewriter': ['KaTeX_Typewriter-Regular.ttf'],
  };
  for (final entry in families.entries) {
    final loader = FontLoader('packages/flutter_math_fork/${entry.key}');
    for (final name in entry.value) {
      final data = await rootBundle.load(
        'packages/flutter_math_fork/lib/katex_fonts/fonts/$name',
      );
      loader.addFont(Future.value(data));
    }
    await loader.load();
  }
}

String _flutterRoot() {
  final fromEnvironment = Platform.environment['FLUTTER_ROOT'];
  if (fromEnvironment != null && fromEnvironment.isNotEmpty) {
    return fromEnvironment;
  }
  // flutter/bin/cache/artifacts/engine/<platform>/flutter_tester
  var directory = File(Platform.resolvedExecutable).parent;
  for (var i = 0; i < 5; i++) {
    directory = directory.parent;
  }
  return directory.path;
}
