/// Экран ввода и показа решения.
///
/// Сценарий: набираем выражение на своей клавиатуре (структурный редактор,
/// `src/editor/`), отправляем бэкенду AST-JSON, получаем шаги с пояснениями
/// и ответ. Камера вне объёма (решение пользователя).
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import 'src/api/embedded_backend.dart';
import 'src/api/solver_api.dart';
import 'src/editor/controller.dart';
import 'src/editor/convert.dart';
import 'src/editor/editor_view.dart';
import 'src/editor/keyboard.dart';
import 'src/model/core_node.dart';
import 'src/notebook/notebook.dart';
import 'src/notebook/notebook_page.dart';
import 'src/render/graph_view.dart';
import 'src/render/latex.dart';
import 'src/settings/settings.dart';
import 'src/settings/settings_page.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(const BootstrapApp());
}

/// Адрес бэкенда по умолчанию.
///
/// `10.0.2.2` — адрес хоста, видимый с эмулятора Android. На устройстве
/// нужен реальный IP, поэтому значение вынесено в аргумент запуска.
const String defaultBaseUrl = String.fromEnvironment(
  'MYMATH_API',
  defaultValue: 'http://10.0.2.2:8000',
);

/// Выбрать бэкенд: явный `MYMATH_API`, иначе встроенный Python (Android),
/// иначе адрес по умолчанию (эмулятор/десктоп с внешним сервером).
Future<String> resolveBaseUrl() async {
  const override = String.fromEnvironment('MYMATH_API');
  if (override.isNotEmpty) return override;
  final embedded = await startEmbeddedBackend();
  return embedded ?? defaultBaseUrl;
}

/// Оболочка запуска.
///
/// Сразу показывает окно, а встроенный Python поднимает в фоне: иначе
/// приложение висело бы без интерфейса, пока стартует интерпретатор.
class BootstrapApp extends StatefulWidget {
  const BootstrapApp({super.key});

  @override
  State<BootstrapApp> createState() => _BootstrapAppState();
}

class _BootstrapAppState extends State<BootstrapApp> {
  String? _baseUrl;

  @override
  void initState() {
    super.initState();
    _resolve();
  }

  Future<void> _resolve() async {
    final baseUrl = await resolveBaseUrl();
    if (mounted) setState(() => _baseUrl = baseUrl);
  }

  @override
  Widget build(BuildContext context) {
    final baseUrl = _baseUrl;
    if (baseUrl == null) return const _StartingScreen();
    return MyMathApp(baseUrl: baseUrl);
  }
}

/// Экран ожидания, пока поднимается встроенный решатель.
class _StartingScreen extends StatelessWidget {
  const _StartingScreen();

  @override
  Widget build(BuildContext context) {
    return const MaterialApp(
      home: Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text('Запуск решателя…'),
            ],
          ),
        ),
      ),
    );
  }
}

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
      darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF2C6BED),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
      ),
      themeMode: ThemeMode.system,
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
  final _notebook = Notebook();
  final _settings = AppSettings();
  String _locale = 'ru';
  String? _command;

  /// Настройки отрисовки: десятичный разделитель и нотация биномиального
  /// коэффициента из профиля.
  LatexOptions get _latexOptions => LatexOptions(
    decimalSeparator: _settings.decimalSeparator,
    binomialNotation: _settings.binomialNotation,
  );

  SolveResponse? _result;
  List<SolveResponse> _methods = const [];
  int _methodIndex = 0;
  String? _error;
  bool _busy = false;

  /// Промежуток отбора корней: границы в виде узлов и их исходный ввод.
  CoreNode? _intervalMin;
  CoreNode? _intervalMax;
  String _intervalMinText = '';
  String _intervalMaxText = '';

  bool get _hasInterval => _intervalMin != null && _intervalMax != null;

  /// Текущий способ решения (основной или выбранный переключателем).
  SolveResponse? get _current =>
      _methods.isEmpty ? _result : _methods[_methodIndex];

  /// Команды действий над выражением (совпадают с `CoreAction.command`).
  static const List<(String?, String)> _commands = [
    (null, 'Решить'),
    ('factor', 'Разложить'),
    ('expand', 'Раскрыть'),
    ('simplify', 'Упростить'),
    ('domain', 'Область определения'),
    ('range', 'Область значений'),
    ('restrictions', 'ОДЗ'),
    ('intercepts', 'Пересечения с осями'),
    ('inverse_function', 'Обратная функция'),
    ('partial_fractions', 'Простейшие дроби'),
    ('prime_factorization', 'Простые множители'),
    ('even_odd', 'Чётность'),
    ('extrema', 'Экстремумы'),
    ('inflection', 'Перегибы'),
    ('asymptotes', 'Асимптоты'),
    ('slant_asymptote', 'Наклонная асимптота'),
    ('vertex', 'Вершина'),
    ('conic', 'Тип коники'),
    ('conic_details', 'Свойства коники'),
    ('convergence', 'Сходимость'),
    ('to_fraction', 'В дробь'),
    ('to_percent', 'В проценты'),
    ('to_sci', '10ⁿ'),
    ('to_mixed', 'Смешанное'),
    ('to_degrees', 'В градусы'),
    ('to_radians', 'В радианы'),
    ('area', 'Площадь'),
    ('prove', 'Доказать'),
    ('vector_length', 'Длина'),
  ];

  @override
  void initState() {
    super.initState();
    _notebook.load();
    _settings.load();
    // Перерисовываем при смене настроек: разделитель и нотация влияют на рендер.
    _settings.addListener(_onSettingsChanged);
  }

  void _onSettingsChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _settings.removeListener(_onSettingsChanged);
    _editor.dispose();
    _notebook.dispose();
    _settings.dispose();
    widget.api.close();
    super.dispose();
  }

  Future<void> _solve() => _solveWith(command: _command);

  Future<void> _solveWith({
    String? command,
    List<CoreNode> args = const [],
  }) async {
    if (_editor.isEmpty) {
      setState(() => _error = 'Введите выражение');
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final node = _editor.toCoreNode();
      final answer = await widget.api.solve(
        node,
        locale: _locale,
        command: command,
        args: args,
        intervalMin: _intervalMin,
        intervalMax: _intervalMax,
      );
      if (!mounted) return;
      setState(() {
        _result = answer;
        _methods = answer.methods.isEmpty ? [answer] : answer.methods;
        _methodIndex = 0;
      });
      await _notebook.add(
        NotebookEntry(
          problem: node,
          solution: answer.solution,
          savedAt: DateTime.now(),
        ),
      );
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

  /// Второй вектор из строки «3, 4» или скаляр из «2».
  List<CoreNode>? _parseNumbers(String text) {
    final parts = text
        .split(RegExp(r'[,\s]+'))
        .where((part) => part.isNotEmpty)
        .toList();
    if (parts.isEmpty) return null;
    final nodes = <CoreNode>[];
    for (final part in parts) {
      if (double.tryParse(part) == null) return null;
      nodes.add(CoreNode(type: CoreNodeType.constant, value: part));
    }
    return nodes;
  }

  /// Шторка операций над вектором: второй операнд и выбор действия.
  Future<void> _openVectorSheet() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => _VectorSheet(onRun: _runVectorCommand),
    );
  }

  /// Выполнить векторную команду с введённым вторым операндом.
  void _runVectorCommand(String command, String text) {
    final numbers = _parseNumbers(text);
    if (numbers == null || numbers.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Введи числа через запятую')),
      );
      return;
    }
    final List<CoreNode> args;
    if (command == 'vector_scale') {
      if (numbers.length != 1) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Скаляр — одно число')),
        );
        return;
      }
      args = [numbers.first];
    } else {
      args = [CoreNode(type: CoreNodeType.list, children: numbers)];
    }
    Navigator.of(context).pop();
    _solveWith(command: command, args: args);
  }

  /// Разобрать матрицу из строки «1, 2; 3, 4» (строки через `;`, ячейки через `,`).
  CoreNode? _parseMatrix(String text) {
    final rows = text
        .split(';')
        .map((row) => row.trim())
        .where((row) => row.isNotEmpty)
        .toList();
    if (rows.isEmpty) return null;
    final matrixRows = <CoreNode>[];
    var width = -1;
    for (final rowText in rows) {
      final cells = rowText
          .split(',')
          .map((cell) => cell.trim())
          .where((cell) => cell.isNotEmpty)
          .toList();
      if (cells.isEmpty) return null;
      if (width == -1) {
        width = cells.length;
      } else if (cells.length != width) {
        return null;
      }
      final nodes = <CoreNode>[];
      for (final cell in cells) {
        if (double.tryParse(cell) == null) return null;
        nodes.add(CoreNode(type: CoreNodeType.constant, value: cell));
      }
      matrixRows.add(CoreNode(type: CoreNodeType.matrixRow, children: nodes));
    }
    return CoreNode(type: CoreNodeType.matrix, children: matrixRows);
  }

  /// Шторка операций над матрицей: второй операнд и выбор действия.
  Future<void> _openMatrixSheet() async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      showDragHandle: true,
      builder: (context) => _MatrixSheet(onRun: _runMatrixCommand),
    );
  }

  /// Выполнить матричную команду с введённым вторым операндом.
  void _runMatrixCommand(String command, String text) {
    final List<CoreNode> args;
    if (command == 'matrix_scale') {
      if (double.tryParse(text.trim()) == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Скаляр — число')),
        );
        return;
      }
      args = [CoreNode(type: CoreNodeType.constant, value: text.trim())];
    } else if (command == 'matrix_transpose' ||
        command == 'matrix_inverse' ||
        command == 'matrix_determinant') {
      args = const [];
    } else {
      final matrix = _parseMatrix(text);
      if (matrix == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Матрица: строки через ;, ячейки через ,')),
        );
        return;
      }
      args = [matrix];
    }
    Navigator.of(context).pop();
    _solveWith(command: command, args: args);
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: AppBar(
        title: const Text('mymath'),
        actions: [
          IconButton(
            tooltip: 'Копировать результат',
            icon: const Icon(Icons.copy_outlined),
            onPressed: _current == null ? null : _copyResult,
          ),
          IconButton(
            tooltip: 'Блокнот',
            icon: const Icon(Icons.book_outlined),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => NotebookPage(
                  notebook: _notebook,
                  latexOptions: _latexOptions,
                ),
              ),
            ),
          ),
          IconButton(
            tooltip: 'Настройки',
            icon: const Icon(Icons.settings_outlined),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute<void>(
                builder: (_) => SettingsPage(settings: _settings),
              ),
            ),
          ),
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
            _preview(theme),
            EditorView(
              controller: _editor,
              decimalSeparator: _settings.decimalSeparator,
            ),
            SizedBox(
              height: 40,
              child: SingleChildScrollView(
                scrollDirection: Axis.horizontal,
                padding: const EdgeInsets.symmetric(horizontal: 12),
                child: Row(children: [
                  for (final (command, label) in _commands)
                    Padding(
                      padding: const EdgeInsets.only(right: 6),
                      child: ChoiceChip(
                        label: Text(label),
                        selected: _command == command,
                        onSelected: (_) => setState(() => _command = command),
                      ),
                    ),
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ActionChip(
                      avatar: const Icon(Icons.arrow_outward, size: 16),
                      label: const Text('Вектор…'),
                      onPressed: _openVectorSheet,
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ActionChip(
                      avatar: const Icon(Icons.grid_on, size: 16),
                      label: const Text('Матрица…'),
                      onPressed: _openMatrixSheet,
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ActionChip(
                      avatar: const Icon(Icons.straighten, size: 16),
                      label: Text(
                        _hasInterval
                            ? 'Промежуток: [$_intervalMinText; $_intervalMaxText]'
                            : 'Промежуток',
                      ),
                      onPressed: _openIntervalDialog,
                    ),
                  ),
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ActionChip(
                      avatar: const Icon(Icons.show_chart, size: 16),
                      label: const Text('График'),
                      onPressed: _openGraph,
                    ),
                  ),
                ]),
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
            _SubstepCard(
              substep: substep,
              theme: theme,
              options: _latexOptions,
              onLink: _onLink,
              onCopy: _copyFormula,
            ),
        ],
        if (result.solution != null) ...[
          const SizedBox(height: 24),
          Text('Ответ', style: theme.textTheme.titleSmall),
          const SizedBox(height: 8),
          _Math(latex: nodeToLatex(result.solution!, _latexOptions)),
        ],
      ],
    );
  }

  /// Живой предпросмотр формулы: текущий ввод, собранный в LaTeX.
  ///
  /// Редактор рисует структурное дерево; здесь то же выражение показано
  /// набором (`flutter_math`) — так видно, что именно уйдёт решателю.
  Widget _preview(ThemeData theme) {
    return AnimatedBuilder(
      animation: _editor,
      builder: (context, _) {
        if (_editor.isEmpty) return const SizedBox.shrink();
        final latex = nodeToLatex(
          editorToCoreNode(_editor.document),
          _latexOptions,
        );
        return Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
          alignment: Alignment.centerLeft,
          child: Math.tex(
            latex,
            mathStyle: MathStyle.display,
            onErrorFallback: (error) => const SizedBox.shrink(),
          ),
        );
      },
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

  /// Открыть график текущего выражения.
  Future<void> _openGraph() async {
    if (_editor.isEmpty) {
      setState(() => _error = 'Введите выражение');
      return;
    }
    try {
      final data = await widget.api.graph(_editor.toCoreNode());
      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('График y = f(${data.variable})'),
          content: SizedBox(
            width: 320,
            height: 260,
            child: GraphView(data: data),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(),
              child: const Text('Закрыть'),
            ),
          ],
        ),
      );
    } on SolveFailure catch (err) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(err.message)),
      );
    }
  }

  /// Открыть ввод промежутка отбора корней (для тригонометрических уравнений).
  Future<void> _openIntervalDialog() async {
    final bounds = await showDialog<({String min, String max})>(
      context: context,
      builder: (context) => _IntervalDialog(
        min: _intervalMinText,
        max: _intervalMaxText,
      ),
    );
    if (bounds == null) return;

    final minText = bounds.min.trim();
    final maxText = bounds.max.trim();
    if (minText.isEmpty || maxText.isEmpty) {
      setState(() {
        _intervalMin = null;
        _intervalMax = null;
        _intervalMinText = '';
        _intervalMaxText = '';
      });
      return;
    }

    try {
      // Границы разбирает бэкенд — тот же протокол, что и для ввода.
      final minNode = await widget.api.parse('{$minText}');
      final maxNode = await widget.api.parse('{$maxText}');
      if (!mounted) return;
      setState(() {
        _intervalMin = minNode;
        _intervalMax = maxNode;
        _intervalMinText = minText;
        _intervalMaxText = maxText;
      });
    } on SolveFailure catch (err) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Не удалось разобрать границы: ${err.message}')),
      );
    }
  }

  /// Скопировать результат: LaTeX ответа, иначе — текст решения.
  Future<void> _copyResult() async {
    final result = _current;
    if (result == null) return;
    final text = result.solution != null
        ? nodeToLatex(result.solution!, _latexOptions)
        : _plainText(result);
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Скопировано')),
    );
  }

  /// Текст решения без формул: шаги и пояснения (для копирования).
  String _plainText(SolveResponse result) {
    final buffer = StringBuffer();
    for (final step in result.steps) {
      for (final header in step.headers) {
        buffer.writeln(header);
      }
      for (final substep in step.substeps) {
        final left = substep.left == null
            ? ''
            : nodeToLatex(substep.left!, _latexOptions);
        final right = substep.right == null
            ? ''
            : nodeToLatex(substep.right!, _latexOptions);
        if (left.isNotEmpty || right.isNotEmpty) {
          buffer.writeln('$left → $right');
        }
        if (substep.text != null && substep.text!.isNotEmpty) {
          buffer.writeln(substep.text);
        }
      }
    }
    return buffer.toString().trim();
  }

  /// Скопировать одну формулу шага.
  Future<void> _copyFormula(String latex) async {
    if (latex.isEmpty) return;
    await Clipboard.setData(ClipboardData(text: latex));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Скопировано')),
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
///
/// Если у подшага есть вложенный результат (`subresult`) — он показывается
/// раскрываемым блоком «Подробнее»: это углублённое пояснение шага.
class _SubstepCard extends StatelessWidget {
  const _SubstepCard({
    required this.substep,
    required this.theme,
    required this.options,
    required this.onLink,
    required this.onCopy,
  });

  final Substep substep;
  final ThemeData theme;
  final LatexOptions options;
  final void Function(ExplanationLink link) onLink;
  final void Function(String latex) onCopy;

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
                  Expanded(
                    child: _Math(latex: nodeToLatex(substep.left!, options)),
                  ),
                if (substep.left != null && substep.right != null)
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 8),
                    child: Icon(Icons.arrow_forward, size: 18),
                  ),
                if (substep.right != null)
                  Expanded(
                    child: _Math(latex: nodeToLatex(substep.right!, options)),
                  ),
                IconButton(
                  tooltip: 'Копировать шаг',
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.copy_outlined, size: 18),
                  onPressed: _copyText,
                ),
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
            if (substep.detail.isNotEmpty) _detail(context),
          ],
        ),
      ),
    );
  }

  /// Строка для копирования: `было → стало`.
  void _copyText() {
    final left = substep.left == null ? '' : nodeToLatex(substep.left!, options);
    final right =
        substep.right == null ? '' : nodeToLatex(substep.right!, options);
    final text = [left, right].where((part) => part.isNotEmpty).join(' → ');
    onCopy(text);
  }

  /// Раскрываемое углублённое пояснение шага (вложенные подшаги).
  Widget _detail(BuildContext context) {
    return Theme(
      data: theme.copyWith(dividerColor: Colors.transparent),
      child: ExpansionTile(
        tilePadding: EdgeInsets.zero,
        childrenPadding: const EdgeInsets.only(left: 8),
        title: Text('Подробнее', style: theme.textTheme.labelLarge),
        children: [
          for (final step in substep.detail) ...[
            for (final header in step.headers)
              Align(
                alignment: Alignment.centerLeft,
                child: Padding(
                  padding: const EdgeInsets.symmetric(vertical: 4),
                  child: Text(header, style: theme.textTheme.labelMedium),
                ),
              ),
            for (final nested in step.substeps)
              _SubstepCard(
                substep: nested,
                theme: theme,
                options: options,
                onLink: onLink,
                onCopy: onCopy,
              ),
          ],
        ],
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

/// Шторка операций над вектором: поле второго операнда и кнопки действий.
class _VectorSheet extends StatefulWidget {
  const _VectorSheet({required this.onRun});

  final void Function(String command, String text) onRun;

  @override
  State<_VectorSheet> createState() => _VectorSheetState();
}

class _VectorSheetState extends State<_VectorSheet> {
  final _second = TextEditingController();
  final _scalar = TextEditingController(text: '2');

  @override
  void dispose() {
    _second.dispose();
    _scalar.dispose();
    super.dispose();
  }

  Widget _action(String command, String label, TextEditingController input) {
    return FilledButton.tonal(
      onPressed: () => widget.onRun(command, input.text),
      child: Text(label),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Операции с вектором',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _second,
            decoration: const InputDecoration(
              labelText: 'Второй вектор (например 3, 4)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _action('vector_add', 'Сложить', _second),
              _action('vector_subtract', 'Вычесть', _second),
              _action('vector_dot', 'Скалярное', _second),
              _action('vector_cross', 'Векторное', _second),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _scalar,
            decoration: const InputDecoration(
              labelText: 'Скаляр',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: _action('vector_scale', '× скаляр', _scalar),
          ),
        ],
      ),
    );
  }
}

/// Формула с защитой от невалидного LaTeX.///
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
    return Semantics(
      label: 'Формула',
      child: Math.tex(
        latex,
        mathStyle: MathStyle.display,
        onErrorFallback: (error) => Text(
          latex,
          style: TextStyle(color: Theme.of(context).colorScheme.error),
        ),
      ),
    );
  }
}

/// Диалог ввода промежутка: левая и правая границы.
class _IntervalDialog extends StatefulWidget {
  const _IntervalDialog({required this.min, required this.max});

  final String min;
  final String max;

  @override
  State<_IntervalDialog> createState() => _IntervalDialogState();
}

class _IntervalDialogState extends State<_IntervalDialog> {
  late final TextEditingController _min = TextEditingController(
    text: widget.min,
  );
  late final TextEditingController _max = TextEditingController(
    text: widget.max,
  );

  @override
  void dispose() {
    _min.dispose();
    _max.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      title: const Text('Промежуток'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _min,
            decoration: const InputDecoration(
              labelText: 'Левая граница',
              hintText: 'например, 0',
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _max,
            decoration: const InputDecoration(
              labelText: 'Правая граница',
              hintText: 'например, 2π',
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Границы — числа или выражения с π. '
            'Пустые поля убирают промежуток.',
            style: TextStyle(fontSize: 12),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Отмена'),
        ),
        FilledButton(
          onPressed: () =>
              Navigator.of(context).pop((min: _min.text, max: _max.text)),
          child: const Text('Готово'),
        ),
      ],
    );
  }
}

/// Шторка операций над матрицей: второй операнд и выбор действия.
class _MatrixSheet extends StatefulWidget {
  const _MatrixSheet({required this.onRun});

  final void Function(String command, String text) onRun;

  @override
  State<_MatrixSheet> createState() => _MatrixSheetState();
}

class _MatrixSheetState extends State<_MatrixSheet> {
  final _second = TextEditingController(text: '5,6;7,8');
  final _scalar = TextEditingController(text: '2');

  @override
  void dispose() {
    _second.dispose();
    _scalar.dispose();
    super.dispose();
  }

  Widget _action(String command, String label, TextEditingController input) {
    return FilledButton.tonal(
      onPressed: () => widget.onRun(command, input.text),
      child: Text(label),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(
        left: 16,
        right: 16,
        bottom: MediaQuery.of(context).viewInsets.bottom + 24,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            'Операции с матрицей',
            style: Theme.of(context).textTheme.titleMedium,
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _second,
            decoration: const InputDecoration(
              labelText: 'Вторая матрица (например 5,6;7,8)',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _action('matrix_add', 'Сложить', _second),
              _action('matrix_subtract', 'Вычесть', _second),
              _action('matrix_multiply', 'Умножить', _second),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _scalar,
            decoration: const InputDecoration(
              labelText: 'Скаляр',
              border: OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: _action('matrix_scale', '× скаляр', _scalar),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              FilledButton.tonal(
                onPressed: () => widget.onRun('matrix_transpose', ''),
                child: const Text('Транспонировать'),
              ),
              FilledButton.tonal(
                onPressed: () => widget.onRun('matrix_inverse', ''),
                child: const Text('Обратная'),
              ),
              FilledButton.tonal(
                onPressed: () => widget.onRun('matrix_inverse_gauss', ''),
                child: const Text('Обратная (Гаусс)'),
              ),
              FilledButton.tonal(
                onPressed: () => widget.onRun('matrix_determinant', ''),
                child: const Text('Определитель'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
