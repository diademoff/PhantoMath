/// Экран ввода и показа решения.
///
/// Минимальный рабочий сценарий: вводим выражение, отправляем бэкенду,
/// получаем шаги с пояснениями и отве��. Камера вне объёма (решение
/// пользователя), поэтому ввода ровно два — текстовое поле и кнопка.
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import 'src/api/solver_api.dart';
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
  final _controller = TextEditingController(text: '2+3*4');
  final _localeController = TextEditingController(text: 'ru');

  SolveResponse? _result;
  String? _error;
  bool _busy = false;

  @override
  void dispose() {
    _controller.dispose();
    _localeController.dispose();
    widget.api.close();
    super.dispose();
  }

  Future<void> _solve() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // Текстовое поле принимает тот же протокол, что и редактор Photomath:
      // это снимает отдельный слой парсинга на фронте.
      final node = await widget.api.parse('{${_controller.text}}');
      final answer = await widget.api.solve(
        node,
        locale: _localeController.text.isEmpty
            ? 'default'
            : _localeController.text,
      );
      if (!mounted) return;
      setState(() => _result = answer);
    } on SolveFailure catch (err) {
      if (!mounted) return;
      setState(() => _error = err.message);
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(title: const Text('mymath')),
      body: SafeArea(
        child: Column(
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  TextField(
                    controller: _controller,
                    decoration: const InputDecoration(
                      labelText: 'Выражение',
                      hintText: '2x + 3 = 7',
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: (_) => _solve(),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      SizedBox(
                        width: 110,
                        child: TextField(
                          controller: _localeController,
                          decoration: const InputDecoration(
                            labelText: 'Язык',
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      FilledButton(
                        onPressed: _busy ? null : _solve,
                        child: _busy
                            ? const SizedBox(
                                width: 18,
                                height: 18,
                                child: CircularProgressIndicator(strokeWidth: 2),
                              )
                            : const Text('Решить'),
                      ),
                    ],
                  ),
                ],
              ),
            ),
            if (_error != null)
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Text(
                  _error!,
                  style: TextStyle(color: theme.colorScheme.error),
                ),
              ),
            const Divider(height: 1),
            Expanded(child: _buildBody(theme)),
          ],
        ),
      ),
    );
  }

  Widget _buildBody(ThemeData theme) {
    final result = _result;
    if (result == null) {
      return Center(
        child: Text(
          'Введите выражение и нажмите «Решить»',
          style: theme.textTheme.bodyMedium,
        ),
      );
    }
    if (result.steps.isEmpty) {
      return const Center(child: Text('Решатель не вернул шагов'));
    }
    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        for (final step in result.steps) ...[
          for (final header in step.headers)
            Padding(
              padding: const EdgeInsets.symmetric(vertical: 4),
              child: Text(header, style: theme.textTheme.titleSmall),
            ),
          for (final substep in step.substeps)
            _SubstepCard(substep: substep, theme: theme),
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
}

/// Карточка подшага: выражение, стрелка, выражение и пояснение.
class _SubstepCard extends StatelessWidget {
  const _SubstepCard({required this.substep, required this.theme});

  final Substep substep;
  final ThemeData theme;

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
              Text(substep.text!, style: theme.textTheme.bodyMedium),
            ],
          ],
        ),
      ),
    );
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
