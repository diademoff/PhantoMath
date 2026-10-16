/// Клиент бэкенда решателя.
///
/// Формат запроса и ответа — контракт Photomah
/// (`truth/03-solver-contract.md`): на входе `CoreNode`, на выходе
/// `CoreSolverData` с вертикальными шагами и готовыми текстами пояснений.
library;

import 'dart:convert';

import 'package:http/http.dart' as http;

import '../model/core_node.dart';

/// Бэкенд не смог решить задачу — это не поломка сервиса.
class SolveFailure implements Exception {
  const SolveFailure(this.message, {this.explanationKey});

  /// Текст для показа пользователю.
  final String message;

  /// Ключ словаря объяснений, если бэкенд его прислал.
  final String? explanationKey;

  @override
  String toString() => message;
}

/// Ответ бэкенда: дерево, шаги и тексты.
///
/// Если решатель предложил несколько способов решения, в [methods] лежат все
/// (включая основной), а [steps] и [solution] повторяют первый из них.
class SolveResponse {
  const SolveResponse({
    required this.steps,
    this.solution,
    this.methods = const [],
    this.selectMethodText,
  });

  /// Шаги решения по порядку следования.
  final List<SolveStep> steps;

  /// Итоговый ответ, если бэкенд его посчитал.
  final CoreNode? solution;

  /// Способы решения: основной и альтернативные. Пусто, если способ один.
  final List<SolveResponse> methods;

  /// Подпись переключателя способов («показать другой способ»).
  final String? selectMethodText;
}

/// Шаг решения: список подшагов под общим заголовком.
class SolveStep {
  const SolveStep({this.headers = const [], this.substeps = const []});

  final List<String> headers;
  final List<Substep> substeps;
}

/// Ссылка в тексте пояснения: метка, идентификатор и определение понятия.
class ExplanationLink {
  const ExplanationLink({
    required this.label,
    required this.uuid,
    this.definition = '',
  });

  final String label;
  final String uuid;

  /// Краткое определение понятия; пусто, если его нет.
  final String definition;
}

/// Подшаг: «было → стало» с пояснением.
class Substep {
  const Substep({
    this.left,
    this.right,
    this.text,
    this.explanationKey,
    this.links = const [],
    this.detail = const [],
  });

  final CoreNode? left;
  final CoreNode? right;

  /// Готовый текст пояснения; `null`, если запрос шёл без развёртки.
  final String? text;

  /// Ключ словаря объяснений — нужен для ссылок «показать другой способ».
  final String? explanationKey;

  /// Ссылки внутри текста (метка + uuid) для навигации.
  final List<ExplanationLink> links;

  /// Раскрываемое углублённое пояснение шага (`subresult`): вложенные шаги.
  /// Пусто, если у шага нет деталей.
  final List<SolveStep> detail;
}

/// Точка графика.
class GraphPoint {
  const GraphPoint(this.x, this.y);

  final double x;
  final double y;
}

/// Опорные точки графика: корни, пересечение с осью y, экстремумы, асимптоты.
///
/// Соответствует меткам `graph_rt_info_*` Photomath. Все списки могут быть
/// пустыми; для кусочно-заданной функции приходит только признак [piecewise].
class GraphAnnotations {
  const GraphAnnotations({
    this.roots = const [],
    this.yIntercept,
    this.maxima = const [],
    this.minima = const [],
    this.verticalAsymptotes = const [],
    this.horizontalAsymptotes = const [],
    this.piecewise = false,
  });

  final List<GraphPoint> roots;
  final GraphPoint? yIntercept;
  final List<GraphPoint> maxima;
  final List<GraphPoint> minima;
  final List<double> verticalAsymptotes;
  final List<double> horizontalAsymptotes;
  final bool piecewise;

  bool get isEmpty =>
      roots.isEmpty &&
      yIntercept == null &&
      maxima.isEmpty &&
      minima.isEmpty &&
      verticalAsymptotes.isEmpty &&
      horizontalAsymptotes.isEmpty;
}

/// Данные для графика `y = f(x)`.
class GraphData {
  const GraphData({
    required this.points,
    required this.xMin,
    required this.xMax,
    required this.yMin,
    required this.yMax,
    required this.variable,
    this.annotations = const GraphAnnotations(),
  });

  final List<GraphPoint> points;
  final double xMin;
  final double xMax;
  final double yMin;
  final double yMax;
  final String variable;
  final GraphAnnotations annotations;
}

/// Клиент решателя.
class SolverApi {
  SolverApi({required this.baseUrl, http.Client? client})
    : _client = client ?? http.Client();

  /// Адрес бэкенда, например `http://10.0.2.2:8000` с эмулятора Android.
  final String baseUrl;

  final http.Client _client;

  /// Решить выражение.
  ///
  /// Бросает [SolveFailure], если задача не решилась: это ожидаемый
  /// исход, а не сбой, и вызывающий покажет текст пользователю.
  Future<SolveResponse> solve(
    CoreNode node, {
    String locale = 'default',
    bool render = true,
    String? command,
    List<CoreNode> args = const [],
    CoreNode? intervalMin,
    CoreNode? intervalMax,
    List<CoreNode> definitions = const [],
  }) async {
    final response = await _post(Uri.parse('$baseUrl/api/v1/solve'), {
      'node': _toJson(node),
      'locale': locale,
      'render': render,
      if (command != null)
        'action': {
          'command': command,
          'args': [for (final arg in args) _toJson(arg)],
        },
      // Промежуток отбора корней: применим к тригонометрическим уравнениям.
      if (intervalMin != null && intervalMax != null)
        'interval': {
          'min': _toJson(intervalMin),
          'max': _toJson(intervalMax),
        },
      // Определения функций: вызовы f(…) подставляются перед решением.
      if (definitions.isNotEmpty)
        'definitions': [
          for (final definition in definitions) _toJson(definition),
        ],
    });

    if (response.statusCode != 200) {
      throw _failure(response);
    }
    return _parseSolve(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Разобрать строку протокола Photomath в дерево.
  ///
  /// Нужен для отладки ввода: показывает, что именно бэкенд понял.
  Future<CoreNode> parse(String source) async {
    final response = await _post(Uri.parse('$baseUrl/api/v1/parse'), {
      'source': source,
    });
    if (response.statusCode != 200) {
      throw _failure(response, fallback: 'Не удалось разобрать выражение');
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return CoreNode.fromJson(body['node'] as Map<String, dynamic>);
  }

  /// Точки графика `y = f(x)` на отрезке.
  ///
  /// Бросает [SolveFailure], если график не построить (например, нет
  /// вещественных значений или неверный диапазон).
  Future<GraphData> graph(
    CoreNode node, {
    double xMin = -10,
    double xMax = 10,
    int samples = 400,
  }) async {
    final response = await _post(Uri.parse('$baseUrl/api/v1/graph'), {
      'node': _toJson(node),
      'xMin': xMin,
      'xMax': xMax,
      'samples': samples,
    });
    if (response.statusCode != 200) {
      throw _failure(response);
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    final points = [
      for (final point in _asList(body['points']))
        if (point is List && point.length >= 2)
          GraphPoint(
            (point[0] as num).toDouble(),
            (point[1] as num).toDouble(),
          ),
    ];
    return GraphData(
      points: points,
      xMin: (body['xMin'] as num).toDouble(),
      xMax: (body['xMax'] as num).toDouble(),
      yMin: (body['yMin'] as num).toDouble(),
      yMax: (body['yMax'] as num).toDouble(),
      variable: body['variable'] as String? ?? 'x',
      annotations: _parseAnnotations(body['annotations']),
    );
  }

  /// Опорные точки графика из ответа бэкенда.
  GraphAnnotations _parseAnnotations(Object? raw) {
    if (raw is! Map<String, dynamic>) return const GraphAnnotations();
    return GraphAnnotations(
      roots: _points(raw['roots']),
      yIntercept: _point(raw['yIntercept']),
      maxima: _points(raw['maxima']),
      minima: _points(raw['minima']),
      verticalAsymptotes: _numbers(raw['verticalAsymptotes']),
      horizontalAsymptotes: _numbers(raw['horizontalAsymptotes']),
      piecewise: raw['piecewise'] == true,
    );
  }

  List<GraphPoint> _points(Object? raw) {
    final out = <GraphPoint>[];
    for (final item in _asList(raw)) {
      final point = _point(item);
      if (point != null) out.add(point);
    }
    return out;
  }

  GraphPoint? _point(Object? raw) {
    if (raw is List && raw.length >= 2 && raw[0] is num && raw[1] is num) {
      return GraphPoint((raw[0] as num).toDouble(), (raw[1] as num).toDouble());
    }
    return null;
  }

  List<double> _numbers(Object? raw) => [
    for (final item in _asList(raw))
      if (item is num) item.toDouble(),
  ];

  Future<bool> isHealthy() async {
    try {
      final response = await _client.get(Uri.parse('$baseUrl/api/v1/health'));
      return response.statusCode == 200;
    } on Object {
      return false;
    }
  }

  void close() => _client.close();

  // ── запрос и разбор ответа ────────────────────────────────────────

  /// Выполнить POST, превратив сбой транспорта в [SolveFailure].
  ///
  /// Обрыв соединения — такой же ожидаемый исход, как `422`: на устройстве
  /// обработчик закрывал соединение, и приложение падало необработанным
  /// `ClientException`, не показывая пользователю ничего.
  Future<http.Response> _post(Uri uri, Map<String, Object?> body) async {
    try {
      return await _client.post(
        uri,
        headers: const {'content-type': 'application/json'},
        body: jsonEncode(body),
      );
    } on Object {
      throw const SolveFailure('Нет связи с решателем');
    }
  }

  SolveFailure _failure(http.Response response, {String? fallback}) {
    try {
      final body = jsonDecode(response.body) as Map<String, dynamic>;
      final detail = body['detail'];
      if (detail is Map<String, dynamic>) {
        return SolveFailure(
          detail['message'] as String? ?? 'Задача не решена',
          explanationKey: detail['explanation'] as String?,
        );
      }
      if (detail is String) return SolveFailure(detail);
    } on Object {
      // Тело не разобралось — сообщаем код, детали не придумаем.
    }
    if (fallback != null) return SolveFailure(fallback);
    if (response.statusCode != 422) {
      return SolveFailure('Решатель ответил кодом ${response.statusCode}');
    }
    return SolveFailure('Задача не решена');
  }

  SolveResponse _parseSolve(Map<String, dynamic> body) {
    final result = body['result'];
    if (result is! Map<String, dynamic>) {
      return const SolveResponse(steps: []);
    }
    final topSolution = result['solution'];
    final methods = <SolveResponse>[];
    String? selectLabel;
    for (final group in _asList(result['groups'])) {
      if (group is! Map<String, dynamic>) continue;
      if (group['type'] != 'VERTICAL') continue;
      final select = group['selectMethodText'];
      if (select is Map<String, dynamic>) {
        selectLabel ??= _headerText(select);
      }
      for (final entry in _asList(group['entries'])) {
        if (entry is! Map<String, dynamic>) continue;
        methods.add(_parseVertical(entry['result']));
      }
    }
    if (methods.isEmpty) {
      return SolveResponse(steps: const [], solution: _node(topSolution));
    }
    final primary = methods.first;
    return SolveResponse(
      steps: primary.steps,
      solution: primary.solution ?? _node(topSolution),
      methods: methods.length > 1 ? methods : const [],
      selectMethodText: selectLabel,
    );
  }

  /// Один способ решения: шаги и его собственный ответ.
  SolveResponse _parseVertical(Object? raw) {
    if (raw is! Map<String, dynamic>) return const SolveResponse(steps: []);
    return SolveResponse(
      steps: _parseSteps(raw),
      solution: _node(raw['solutionNode']),
    );
  }

  CoreNode? _node(Object? raw) =>
      raw is Map<String, dynamic> ? CoreNode.fromJson(raw) : null;

  List<SolveStep> _parseSteps(Object? raw) {
    if (raw is! Map<String, dynamic>) return const [];
    final out = <SolveStep>[];
    for (final step in _asList(raw['steps'])) {
      if (step is! Map<String, dynamic>) continue;
      out.add(
        SolveStep(
          headers: [
            for (final h in _asList(step['headers']))
              if (h is Map<String, dynamic>) _headerText(h),
          ],
          substeps: [
            for (final s in _asList(step['substeps']))
              if (s is Map<String, dynamic>) _parseSubstep(s),
          ],
        ),
      );
    }
    return out;
  }

  Substep _parseSubstep(Map<String, dynamic> json) {
    final description = json['description'] as Map<String, dynamic>?;
    final explanation = json['explanation'] as Map<String, dynamic>?;
    final left = json['left'] as Map<String, dynamic>?;
    final right = json['right'] as Map<String, dynamic>?;
    return Substep(
      left: left == null ? null : CoreNode.fromJson(left),
      right: right == null ? null : CoreNode.fromJson(right),
      text: explanation?['text'] as String? ?? _textOf(description ?? {}),
      explanationKey:
          explanation?['key'] as String? ?? description?['type'] as String?,
      links: _parseLinks(explanation?['links']),
      detail: _parseSteps(json['subresult']),
    );
  }

  /// Ссылки внутри текста пояснения.
  List<ExplanationLink> _parseLinks(Object? raw) {
    final out = <ExplanationLink>[];
    for (final item in _asList(raw)) {
      if (item is! Map<String, dynamic>) continue;
      final label = item['label'] as String?;
      final uuid = item['uuid'] as String?;
      if (label != null && uuid != null) {
        out.add(
          ExplanationLink(
            label: label,
            uuid: uuid,
            definition: item['definition'] as String? ?? '',
          ),
        );
      }
    }
    return out;
  }

  String? _textOf(Map<String, dynamic> description) {
    final type = description['type'] as String?;
    return type == null ? null : 'step_$type';
  }

  /// Текст заголовка шага.
  ///
  /// Заголовок — тоже `CoreRichText`, и бэкенд присылает развёрнутый текст в
  /// `explanation`. Если развёртки нет, заголовок просто пустой: показывать
  /// техническое `step_eq_solve_short` пользователю незачем.
  String _headerText(Map<String, dynamic> header) {
    final explanation = header['explanation'] as Map<String, dynamic>?;
    return explanation?['text'] as String? ?? '';
  }

  // ── сериализация запроса ──────────────────────────────────────────

  Map<String, dynamic> _toJson(CoreNode node) => {
    'type': node.type.wire,
    if (node.value != null) 'value': node.value,
    if (node.children.isNotEmpty)
      'children': [for (final c in node.children) _toJson(c)],
  };

  static List<dynamic> _asList(Object? value) =>
      value is List<dynamic> ? value : const [];
}
