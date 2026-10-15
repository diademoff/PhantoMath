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
class SolveResponse {
  const SolveResponse({required this.steps, this.solution});

  /// Шаги решения по порядку следования.
  final List<SolveStep> steps;

  /// Итоговый ответ, если бэкенд его посчитал.
  final CoreNode? solution;
}

/// Шаг решения: список подшагов под общим заголовком.
class SolveStep {
  const SolveStep({this.headers = const [], this.substeps = const []});

  final List<String> headers;
  final List<Substep> substeps;
}

/// Подшаг: «было → стало» с пояснением.
class Substep {
  const Substep({this.left, this.right, this.text, this.explanationKey});

  final CoreNode? left;
  final CoreNode? right;

  /// Готовый текст пояснения; `null`, если запрос шёл без развёртки.
  final String? text;

  /// Ключ словаря объяснений — нужен для ссылок «показать другой способ».
  final String? explanationKey;
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
  }) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/api/v1/solve'),
      headers: const {'content-type': 'application/json'},
      body: jsonEncode({
        'node': _toJson(node),
        'locale': locale,
        'render': render,
      }),
    );

    if (response.statusCode == 422) {
      throw _failure(response);
    }
    if (response.statusCode != 200) {
      throw SolveFailure('Бэкенд ответил кодом ${response.statusCode}');
    }
    return _parseSolve(jsonDecode(response.body) as Map<String, dynamic>);
  }

  /// Разобрать строку протокола Photomath в дерево.
  ///
  /// Нужен для отладки ввода: показывает, что именно бэкенд понял.
  Future<CoreNode> parse(String source) async {
    final response = await _client.post(
      Uri.parse('$baseUrl/api/v1/parse'),
      headers: const {'content-type': 'application/json'},
      body: jsonEncode({'source': source}),
    );
    if (response.statusCode != 200) {
      throw SolveFailure('Не удалось разобрать выражение');
    }
    final body = jsonDecode(response.body) as Map<String, dynamic>;
    return CoreNode.fromJson(body['node'] as Map<String, dynamic>);
  }

  Future<bool> isHealthy() async {
    try {
      final response = await _client.get(
        Uri.parse('$baseUrl/api/v1/health'),
      );
      return response.statusCode == 200;
    } on Object {
      return false;
    }
  }

  void close() => _client.close();

  // ── разбор ответа ─────────────────────────────────────────────────

  SolveFailure _failure(http.Response response) {
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
    return SolveFailure('Задача не решена');
  }

  SolveResponse _parseSolve(Map<String, dynamic> body) {
    final result = body['result'] as Map<String, dynamic>?;
    if (result == null) {
      return const SolveResponse(steps: []);
    }
    final solutionNode = result['solution'] as Map<String, dynamic>?;
    final steps = <SolveStep>[];
    for (final group in _asList(result['groups'])) {
      if (group is! Map<String, dynamic>) continue;
      if (group['type'] != 'VERTICAL') continue;
      for (final entry in _asList(group['entries'])) {
        if (entry is! Map<String, dynamic>) continue;
        steps.addAll(_parseSteps(entry['result']));
      }
    }
    return SolveResponse(
      steps: steps,
      solution: solutionNode == null
          ? null
          : CoreNode.fromJson(solutionNode),
    );
  }

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
    );
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
