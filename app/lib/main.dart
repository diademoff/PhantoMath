/// Экран ввода и показа решения.
///
/// Сценарий: набираем выражение на своей клавиатуре (структурный редактор,
/// `src/editor/`), отправляем бэкенду AST-JSON, получаем шаги с пояснениями
/// и ответ. Камера вне объёма (решение пользователя).
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import 'src/api/solver_api.dart';
import 'src/editor/controller.dart';
import 'src/editor/editor_view.dart';
import 'src/editor/keyboard.dart';
import 'src/render/latex.dart';

void main() {
  runApp(const MyMathApp());
}

/// Адрес бэкенда по умолчанию.
///
/// `10.0.2.2` — адрес хоста, видимый с эмулятора Android. На устройстве
/// нужен реальный IP, поэтому значение вынесено в аргумент запуска.
const String defaultBaseUrl = String.fromEnvironment(
  'MYMATH_API',
  defaultValue: 'http://10.0.2.2:8000',
);

/// Языки пояснений. Продукт поддерживает только русский и английский
/// (решение пользователя, `truth/09-decisions.md`). Английский в данных
/// хранится как `default`, поэтому на бэкенд идёт `en`.
const List<String> explanationLocales = ['ru', 'en'];

class MyMathApp extends StatelessWidget {
  const MyMathApp({super.key, this.baseUrl = defaultBaseUrl});

  final String baseUrl;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'mymath',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF2C6BED)),
        useMaterial3: true,
      ),
      home: SolvePage(api: SolverApi(baseUrl: baseUrl)),
    );
  }
}

/// Страница ввода и результата.
class SolvePage extends StatefulWidget {
  const SolvePage({super.key, required this.api});

  final SolverApi api;

  @override
  State<SolvePage> createState() => _SolvePageState();
}

class _SolvePageState extends State<SolvePage> {
  final _editor = EditorController();
  String _locale = 'ru';
  String? _command;

  SolveResponse? _result;
  List<SolveResponse> _methods = const [];
  int _methodIndex = 0;
  String? _error;
  bool _busy = false;

  /// Текущий способ решения (основной или выбранный переключателем).
  SolveResponse? get _current =>
      _methods.isEmpty ? _result : _methods[_methodIndex];

  /// Команды действий над выражением (совпадают с `CoreAction.command`).
  static const List<(String?, String)> _commands = [
    (null, 'Решить'),
    ('factor', 'Разложить'),
    ('expand', 'Раскрыть'),
    ('simplify', 'Упростить'),
    ('vector_length', 'Длина'),
  ];

  @override
  void dispose() {
    _editor.dispose();
    widget.api.close();
    super.dispose();
  }

  Future<void> _solve() async {
    if (_editor.isEmpty) {
      setState(() => _error = 'Введите выражение');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final answer = await widget.api.solve(
        _editor.toCoreNode(),
        locale: _locale,
        command: _command,
      );
      if (!mounted) return;
      setState(() {
        _result = answer;
        _methods = answer.methods.isEmpty ? [answer] : answer.methods;
        _methodIndex = 0;
      });
    } on SolveFailure catch (err) {
      if (!mounted) return;
      setState(() {
        _error = err.message;
        _result = null;
      });
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('mymath'),
        actions: [
          PopupMenuButton<String>(
            tooltip: 'Язык пояснений',
            initialValue: _locale,
            onSelected: (value) => setState(() => _locale = value),
            itemBuilder: (context) => [
              for (final locale in explanationLocales)
                PopupMenuItem(value: locale, child: Text(locale)),
            ],
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Center(child: Text(_locale)),
            ),
          ),
        ],
      ),
      body: SafeArea(
        child: Column(
          children: [
            if (_error != null)
              Container(
                width: double.infinity,
                color: theme.colorScheme.errorContainer,
                padding: const EdgeInsets.symmetric(
                  horizontal: 16,
                  vertical: 8,
                ),
                child: Text(
                  _error!,
                  style: TextStyle(color: theme.colorScheme.onErrorContainer),
                ),
              ),
            Expanded(child: _buildBody(theme)),
            const Divider(height: 1),
            EditorView(controller: _editor),
            SizedBox(
              height: 40,
              child: ListView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                children: [
                  for (final (command, label) in _commands)
                    Padding(
                      padding: const EdgeInsets.only(right: 6),
                      child: ChoiceChip(
                        label: Text(label),
                        selected: _command == command,
                        onSelected: (_) => setState(() => _command = command),
                      ),
                    ),
                ],
              ),
            ),
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
              child: SizedBox(
                width: double.infinity,
                child: FilledButton.icon(
                  key: const ValueKey('solve'),
                  onPressed: _busy ? null : _solve,
                  icon: _busy
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.check),
                  label: const Text('Решить'),
                ),
              ),
            ),
            MathKeyboard(controller: _editor),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(ThemeData theme) {
    final result = _current;
    if (result == null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            'Наберите выражение на клавиатуре и нажмите «Решить»',
            style: theme.textTheme.bodyMedium,
            textAlign: TextAlign.center,
          ),
        ),
      );
    }
    if (result.steps.isEmpty) {
      return const Center(child: Text('Решатель не вернул шагов'));
    }
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        if (_methods.length > 1) _methodSwitcher(theme),
        for (final step in result.steps) ...[
          for (final header in step.headers)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Text(header, style: theme.textTheme.titleSmall),
            ),
          for (final substep in step.substeps)
            _SubstepCard(substep: substep, theme: theme, onLink: _onLink),
        ],
        if (result.solution != null) ...[
          const SizedBox(height: 24),
          Text('Ответ', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          _Math(latex: nodeToLatex(result.solution!)),
        ],
      ],
    );
  }

  /// Переключатель способов решения.
  Widget _methodSwitcher(ThemeData theme) {
    return Row(
      children: [
        Text(
          'Способ ${_methodIndex + 1} из ${_methods.length}',
          style: theme.textTheme.labelMedium,
        ),
        const Spacer(),
        TextButton(
          onPressed: () =>
              setState(() => _methodIndex = (_methodIndex + 1) % _methods.length),
          child: Text(_result?.selectMethodText ?? 'Другой способ'),
        ),
      ],
    );
  }

  /// Нажатие на ссылку в тексте шага.
  ///
  /// Если у понятия есть определение — открываем карточку. Иначе, когда
  /// решатель предложил несколько способов, ссылка переключает на следующий;
  /// в остальных случаях показываем, что понятие пока не раскрыто.
  void _onLink(ExplanationLink link) {
    if (link.definition.isNotEmpty) {
      showModalBottomSheet<void>(
        context: context,
        showDragHandle: true,
        builder: (context) => Padding(
          padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(link.label, style: Theme.of(context).textTheme.titleMedium),
              const SizedBox(height: 12),
              Text(link.definition, style: Theme.of(context).textTheme.bodyLarge),
            ],
          ),
        ),
      );
      return;
    }
    if (_methods.length > 1) {
      setState(() => _methodIndex = (_methodIndex + 1) % _methods.length);
      return;
    }
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text('«${link.label}»: пояснение понятия появится позже')),
    );
  }
}

/// Карточка подшага: выражение, стрелка, выражение и пояснение.
class _SubstepCard extends StatelessWidget {
  const _SubstepCard({
    required this.substep,
    required this.theme,
    required this.onLink,
  });

  final Substep substep;
  final ThemeData theme;
  final void Function(ExplanationLink link) onLink;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.symmetric(vertical: 4),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                if (substep.left != null)
                  Expanded(child: _Math(latex: nodeToLatex(substep.left!))),
                if (substep.left != null && substep.right != null)
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 8),
                    child: Icon(Icons.arrow_forward, size: 18),
                  ),
                if (substep.right != null)
                  Expanded(child: _Math(latex: nodeToLatex(substep.right!))),
              ],
            ),
            if (substep.text != null && substep.text!.isNotEmpty) ...[
              const SizedBox(height: 8),
              _ExplanationText(
                substep: substep,
                style: theme.textTheme.bodyMedium ?? const TextStyle(),
                onLink: onLink,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Текст пояснения со ссылками.
///
/// Ссылки приходят как метки (текст уже содержит их), поэтому метки
/// отыскиваются в строке по порядку следования и становятся нажимаемыми.
class _ExplanationText extends StatelessWidget {
  const _ExplanationText({
    required this.substep,
    required this.style,
    required this.onLink,
  });

  final Substep substep;
  final TextStyle style;
  final void Function(ExplanationLink link) onLink;

  @override
  Widget build(BuildContext context) {
    final text = substep.text ?? '';
    final linkStyle = TextStyle(
      color: Theme.of(context).colorScheme.primary,
      decoration: TextDecoration.underline,
    );
    final spans = <InlineSpan>[];
    var cursor = 0;
    for (final link in substep.links) {
      final index = text.indexOf(link.label, cursor);
      if (index < 0) continue;
      if (index > cursor) {
        spans.add(TextSpan(text: text.substring(cursor, index)));
      }
      spans.add(
        WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: GestureDetector(
            onTap: () => onLink(link),
            child: Text(link.label, style: linkStyle),
          ),
        ),
      );
      cursor = index + link.label.length;
    }
    if (cursor < text.length) {
      spans.add(TextSpan(text: text.substring(cursor)));
    }
    return Text.rich(TextSpan(children: spans), style: style);
  }
}

/// Формула с защитой от невалидного LaTeX.
///
/// `flutter_math` падает на кривом вводе; пользовательский ввод не должен
/// ронять экран, поэтому ошибка показывается как есть.
class _Math extends StatelessWidget {
  const _Math({required this.latex});

  final String latex;

  @override
  Widget build(BuildContext context) {
    if (latex.isEmpty) {
      return const SizedBox.shrink();
    }
    return Math.tex(
      latex,
      mathStyle: MathStyle.display,
      onErrorFallback: (error) => Text(
        latex,
        style: TextStyle(color: Theme.of(context).colorScheme.error),
      ),
    );
  }
}
