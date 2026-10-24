/// PhantoMath: ввод без ожидания решателя, контекстные действия и пояснения.
///
/// Главный экран:
///
/// ```
/// ┌──────────────────────────────────────────┐
/// │ ☰                          📖  ?          │  плавающие иконки
/// │ ┌ поле ввода ─────────────── ✕ ┐         │
/// │ │ 2x + 3 = 7                   │         │  редактор
/// │ ├╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤         │
/// │ ▌ x = 2                       │         │  живой ответ
/// │ ▌                              │         │
/// │           [ Показать решение ]  │         │
/// │ f ∫ <>  abc  ←  →  ⏎  ⌫         │         │  служебный ряд
/// │ ( ) 7 8 9 ÷                    │         │  клавиатура
/// └──────────────────────────────────────────┘
/// ```
///
/// Решение — отдельный экран со сворачивающимся тулбаром «Шаги по решению»
/// и карточками шагов. Боковая шторка — блокнот, теория, справка, настройки.
/// Камеры нет: задача набирается на клавиатуре.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'dart:io';
import 'dart:async';

import 'src/api/embedded_backend.dart';
import 'src/api/solver_api.dart';
import 'src/api/solver_startup.dart';
import 'src/editor/controller.dart';
import 'src/editor/editor_view.dart';
import 'src/editor/restore.dart';
import 'src/functions/function_store.dart';
import 'src/i18n.dart';
import 'src/model/core_node.dart';
import 'src/notebook/notebook.dart';
import 'src/notebook/notebook_page.dart';
import 'src/render/graph_view.dart';
import 'src/render/latex.dart';
import 'src/settings/settings.dart';
import 'src/settings/settings_page.dart';
import 'src/theme/palette.dart';
import 'src/ui/theory_index.dart';
import 'src/theme/phanto_theme.dart';
import 'src/ui/keyboard/math_keyboard.dart';
import 'src/ui/ph_button.dart';
import 'src/ui/solution_preview.dart';
import 'src/ui/vertical_result.dart';

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
  const BootstrapApp({super.key, this.start});
  final Future<void> Function()? start;

  @override
  State<BootstrapApp> createState() => _BootstrapAppState();
}

class _BootstrapAppState extends State<BootstrapApp> {
  late final String _baseUrl =
      const String.fromEnvironment('MYMATH_API').isNotEmpty
      ? const String.fromEnvironment('MYMATH_API')
      : Platform.isAndroid
      ? embeddedBaseUrl
      : defaultBaseUrl;
  late final SolverStartup _startup = SolverStartup(
    widget.start ??
        () async {
          if (Platform.isAndroid &&
              const String.fromEnvironment('MYMATH_API').isEmpty) {
            if (await startEmbeddedBackend() == null) {
              throw SolveFailure(
                tr(
                  'Не удалось запустить решатель',
                  'Could not start the solver',
                ),
              );
            }
          }
        },
  );

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _startup.ensureReady().catchError((Object _) {});
    });
  }

  @override
  void dispose() {
    _startup.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MyMathApp(baseUrl: _baseUrl, startup: _startup);
  }
}

/// Экран ожидания, пока поднимается встроенный решатель.
class SolverReadyIndicator extends StatelessWidget {
  const SolverReadyIndicator({super.key, required this.startup});
  final SolverStartup startup;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: startup,
      builder: (context, _) => Semantics(
        liveRegion: true,
        child: AnimatedSwitcher(
          duration: PhMotion.duration(context),
          child: switch (startup.status) {
            SolverStatus.starting => Text(
              tr('Подготавливаем решатель…', 'Preparing the solver…'),
              key: const ValueKey('starting'),
              style: Theme.of(context).textTheme.bodySmall,
            ),
            SolverStatus.ready => const SizedBox.shrink(key: ValueKey('ready')),
            SolverStatus.failed => TextButton.icon(
              key: const ValueKey('retry-startup'),
              onPressed: () => startup.ensureReady().catchError((Object _) {}),
              icon: const Icon(Icons.refresh),
              label: Text(tr('Повторить запуск', 'Retry launch')),
            ),
          },
        ),
      ),
    );
  }
}

/// Языки интерфейса и пояснений: русский и английский. Английский в данных
/// хранится как `default`, поэтому на бэкенд идёт `en`.
const List<String> explanationLocales = ['ru', 'en'];

class MyMathApp extends StatelessWidget {
  const MyMathApp({super.key, this.baseUrl = defaultBaseUrl, this.startup});

  final String baseUrl;
  final SolverStartup? startup;

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        systemNavigationBarColor: Colors.transparent,
      ),
      child: MaterialApp(
        title: 'PhantoMath',
        debugShowCheckedModeBanner: false,
        theme: PhantoTheme.light(),
        home: SolvePage(
          api: SolverApi(baseUrl: baseUrl),
          startup: startup,
        ),
      ),
    );
  }
}

/// Страница ввода и результата.
class SolvePage extends StatefulWidget {
  const SolvePage({super.key, required this.api, this.startup});

  final SolverApi api;
  final SolverStartup? startup;

  @override
  State<SolvePage> createState() => _SolvePageState();
}

class _SolvePageState extends State<SolvePage> {
  final _editor = EditorController();
  final _notebook = Notebook();
  final _settings = AppSettings();
  final _functions = FunctionStore();
  String? _command;

  /// Аргументы выбранной команды: второй операнд матричной шторки. Чип
  /// команды повторяет её с тем же операндом, а не теряет его.
  List<CoreNode> _commandArgs = const [];

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
  Timer? _previewTimer;
  SolveResponse? _previewAnswer;
  Future<SolveResponse>? _previewRequest;
  bool _previewBusy = false;

  /// Language of the cached answer's texts.
  late String _answerLocale;
  bool _keyboardVisible = true;
  int _requestGeneration = 0;
  Object? _lastDocument;

  /// Промежуток отбора корней: границы в виде узлов и их исходный ввод.
  CoreNode? _intervalMin;
  CoreNode? _intervalMax;
  String _intervalMinText = '';
  String _intervalMaxText = '';

  bool get _hasInterval => _intervalMin != null && _intervalMax != null;

  /// Показывается ли экран решения.
  bool get _showResult => _current != null;

  /// Текущий способ решения (основной или выбранный переключателем).
  SolveResponse? get _current {
    if (_methods.isEmpty) return _result;
    final method = _methods[_methodIndex];
    final top = _result?.solution;
    if (top == null) return method;
    // Верхний ответ может быть вердиктом (`x ∉ ℝ`); шаги остаются у способа.
    return SolveResponse(
      steps: method.steps,
      solution: top,
      methods: method.methods,
      selectMethodText: method.selectMethodText,
      header: method.header,
      alternatives: method.alternatives,
    );
  }

  /// Команды действий над выражением (совпадают с `CoreAction.command`).
  static List<(String?, String)> get _commands => [
    (null, tr('Решить', 'Solve')),
    ('factor', tr('Разложить', 'Factor')),
    ('expand', tr('Раскрыть', 'Expand')),
    ('simplify', tr('Упростить', 'Simplify')),
    ('domain', tr('Область определения', 'Domain')),
    ('range', tr('Область значений', 'Range')),
    ('restrictions', tr('ОДЗ', 'Domain restrictions')),
    ('intercepts', tr('Пересечения с осями', 'Intercepts')),
    ('inverse_function', tr('Обратная функция', 'Inverse function')),
    ('partial_fractions', tr('Простейшие дроби', 'Partial fractions')),
    ('prime_factorization', tr('Простые множители', 'Prime factors')),
    ('even_odd', tr('Чётность', 'Parity')),
    ('extrema', tr('Экстремумы', 'Extrema')),
    ('inflection', tr('Перегибы', 'Inflection points')),
    ('asymptotes', tr('Асимптоты', 'Asymptotes')),
    ('slant_asymptote', tr('Наклонная асимптота', 'Slant asymptote')),
    ('vertex', tr('Вершина', 'Vertex')),
    ('conic', tr('Тип коники', 'Conic type')),
    ('conic_details', tr('Свойства коники', 'Conic properties')),
    ('convergence', tr('Сходимость', 'Convergence')),
    ('to_fraction', tr('В дробь', 'To fraction')),
    ('to_percent', tr('В проценты', 'To percent')),
    ('to_sci', tr('10ⁿ', 'Scientific notation')),
    ('to_mixed', tr('Смешанное', 'To mixed number')),
    ('to_degrees', tr('В градусы', 'To degrees')),
    ('to_radians', tr('В радианы', 'To radians')),
    ('area', tr('Площадь', 'Area')),
    ('prove', tr('Доказать', 'Prove')),
    ('vector_length', tr('Длина', 'Length')),
    ('matrix_rank', tr('Ранг', 'Rank')),
    ('matrix_solve_left', tr('Решить A·X = B', 'Solve A·X = B')),
    ('matrix_solve_right', tr('Решить X·A = B', 'Solve X·A = B')),
  ];

  @override
  void initState() {
    super.initState();
    _notebook.load();
    _settings.load();
    // Перерисовываем при смене настроек: разделитель и нотация влияют на рендер.
    _answerLocale = _settings.locale;
    _settings.addListener(_onSettingsChanged);
    // Список определённых функций тоже обновляет экран.
    _functions.addListener(_onSettingsChanged);
    // Изменения документа отменяют устаревшую отправку, движения каретки — нет.
    _editor.addListener(_onEditorChanged);
  }

  void _onEditorChanged() {
    if (_lastDocument != _editor.document) {
      _lastDocument = _editor.document;
      _requestGeneration++;
      _busy = false;
      _error = null;
      _command = null;
      _commandArgs = const [];
      _previewAnswer = null;
      _previewRequest = null;
      _previewBusy = false;
      _previewTimer?.cancel();
      final node = _editor.toCoreNode();
      if (!_editor.isEmpty && _complete(node)) {
        _previewTimer = Timer(const Duration(milliseconds: 450), () {
          if (mounted && !_showResult) _solveWith(automatic: true);
        });
      }
    }
    if (mounted) setState(() {});
  }

  void _onSettingsChanged() {
    if (_settings.locale != _answerLocale) {
      // The cached answer carries texts in the old language: solve again.
      _answerLocale = _settings.locale;
      _requestGeneration++;
      _previewAnswer = null;
      _previewRequest = null;
      _previewBusy = false;
      if (!_showResult && !_editor.isEmpty && _complete(_editor.toCoreNode())) {
        _solveWith(automatic: true);
      }
    }
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
    _previewTimer?.cancel();
    _settings.removeListener(_onSettingsChanged);
    _functions.removeListener(_onSettingsChanged);
    _editor.removeListener(_onEditorChanged);
    _editor.dispose();
    _notebook.dispose();
    _settings.dispose();
    _functions.dispose();
    widget.api.close();
    super.dispose();
  }

  Future<void> _solve() => _solveWith(command: _command, args: _commandArgs);

  /// An operator with an empty slot: `2+`, `3x=`, `x^`, an empty matrix cell.
  static bool _missingOperand(CoreNode node) {
    const operators = {
      CoreNodeType.add,
      CoreNodeType.subtract,
      CoreNodeType.multiply,
      CoreNodeType.multiplyImplicit,
      CoreNodeType.divide,
      CoreNodeType.fraction,
      CoreNodeType.power,
      CoreNodeType.equals,
      CoreNodeType.lessThan,
      CoreNodeType.lessThanEqual,
      CoreNodeType.greaterThan,
      CoreNodeType.greaterThanEqual,
      // an empty cell of a matrix or determinant: `|3 □; 2 4|`
      CoreNodeType.matrixRow,
      CoreNodeType.determinant,
      CoreNodeType.determinant2,
      CoreNodeType.determinant3,
      CoreNodeType.determinant4,
      CoreNodeType.determinant5,
    };
    if (operators.contains(node.type) &&
        node.children.any((c) => c.type == CoreNodeType.empty)) {
      return true;
    }
    return node.children.any(_missingOperand);
  }

  Future<void> _solveWith({
    String? command,
    List<CoreNode> args = const [],
    bool automatic = false,
  }) async {
    if (_busy) return;
    _previewTimer?.cancel();
    if (_editor.isEmpty) {
      setState(() => _error = tr('Введите выражение', 'Enter an expression'));
      return;
    }
    final node = _editor.toCoreNode();
    if (_missingOperand(node)) {
      // `2+` is not finished: say so instead of showing the solver's error text
      setState(() {
        _error = automatic
            ? null
            : tr(
                'Выражение не закончено: допишите пропущенную часть',
                'Expression is incomplete: finish the missing part',
              );
        if (automatic) _previewAnswer = null;
      });
      return;
    }
    final generation = automatic ? _requestGeneration : ++_requestGeneration;
    final cached = !automatic && command == null && args.isEmpty
        ? _previewAnswer
        : null;
    final inFlight = !automatic && command == null && args.isEmpty
        ? _previewRequest
        : null;
    // `f(x) = …` — это определение функции, а не задача: запоминаем его и
    // подставляем в последующие запросы (см. `FunctionStore`).
    final definition = FunctionStore.parse(node);
    if (definition != null) {
      if (automatic) return;
      _functions.define(definition);
      setState(() {
        _result = null;
        _methods = const [];
        _error = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            tr(
              'Функция ${definition.name} определена',
              'Function ${definition.name} defined',
            ),
          ),
        ),
      );
      return;
    }
    setState(() {
      if (automatic) {
        _previewBusy = true;
      } else {
        _busy = true;
      }
      _error = null;
    });
    try {
      await widget.startup?.ensureReady();
      if (!mounted || generation != _requestGeneration) return;
      SolveResponse answer;
      if (cached != null) {
        answer = cached;
      } else {
        final request =
            inFlight ??
            widget.api.solve(
              node,
              locale: _settings.locale,
              command: command,
              args: args,
              intervalMin: _intervalMin,
              intervalMax: _intervalMax,
              definitions: _functions.contract(),
            );
        if (automatic) _previewRequest = request;
        answer = await request;
      }
      if (!mounted || generation != _requestGeneration) return;
      if (automatic) {
        setState(() => _previewAnswer = answer);
        return;
      }
      setState(() {
        _result = answer;
        _methods = answer.methods.isEmpty ? [answer] : answer.methods;
        _methodIndex = 0;
      });
      _settings.examplesSeen = true;
      unawaited(
        _notebook.add(
          NotebookEntry(
            problem: node,
            solution: answer.solution,
            savedAt: DateTime.now(),
          ),
        ),
      );
    } on SolveFailure catch (err) {
      if (!mounted || generation != _requestGeneration) return;
      setState(() {
        _error = err.message;
        _result = null;
        _methods = const [];
      });
    } catch (_) {
      if (mounted && generation == _requestGeneration) {
        setState(
          () => _error = tr(
            'Не удалось запустить решатель. Повторите попытку.',
            'Could not start the solver. Please try again.',
          ),
        );
      }
    } finally {
      if (mounted && generation == _requestGeneration) {
        setState(() {
          _busy = false;
          _previewBusy = false;
          _previewRequest = null;
        });
      }
    }
  }

  bool _complete(CoreNode node) =>
      node.type != CoreNodeType.empty &&
      node.children.every(_complete) &&
      !(node.type == CoreNodeType.constant &&
          (node.value == '.' || node.value?.endsWith('.') == true));

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
        SnackBar(
          content: Text(
            tr(
              'Введи числа через запятую',
              'Enter numbers separated by commas',
            ),
          ),
        ),
      );
      return;
    }
    final List<CoreNode> args;
    if (command == 'vector_scale') {
      if (numbers.length != 1) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              tr('Скаляр — одно число', 'A scalar is a single number'),
            ),
          ),
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
          SnackBar(
            content: Text(tr('Скаляр — число', 'Scalar must be a number')),
          ),
        );
        return;
      }
      args = [CoreNode(type: CoreNodeType.constant, value: text.trim())];
    } else if (command == 'matrix_transpose' ||
        command == 'matrix_inverse' ||
        command == 'matrix_inverse_gauss' ||
        command == 'matrix_determinant' ||
        command == 'matrix_rank') {
      args = const [];
    } else {
      final matrix = _parseMatrix(text);
      if (matrix == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              tr(
                'Матрица: строки через ;, ячейки через ,',
                'Matrix: rows separated by ;, cells by ,',
              ),
            ),
          ),
        );
        return;
      }
      args = [matrix];
    }
    Navigator.of(context).pop();
    // У трёх матричных команд есть русская подпись в `_commands`: показываем
    // её чипом, как у команд из списка действий.
    if (_commands.any((c) => c.$1 == command)) {
      setState(() {
        _command = command;
        _commandArgs = args;
      });
    }
    _solveWith(command: command, args: args);
  }

  // ─── Раскладка ──────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    final colors = Theme.of(context).colorScheme;
    return Scaffold(
      appBar: _showResult
          ? null
          : AppBar(
              titleSpacing: 16,
              title: Row(
                children: [
                  TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0, end: 1),
                    duration: PhMotion.duration(context, 360),
                    builder: (context, value, child) => Opacity(
                      opacity: value,
                      child: Transform.translate(
                        offset: Offset(0, 4 * (1 - value)),
                        child: child,
                      ),
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(7),
                      child: Image.asset('assets/logo.png', width: 28),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Flexible(
                    child: Text(
                      'PhantoMath',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: 20,
                        fontWeight: FontWeight.w600,
                        color: colors.onSurface,
                      ),
                    ),
                  ),
                ],
              ),
              actions: [
                IconButton(
                  tooltip: _keyboardVisible
                      ? tr('Скрыть клавиатуру', 'Hide keyboard')
                      : tr('Показать клавиатуру', 'Show keyboard'),
                  onPressed: () =>
                      setState(() => _keyboardVisible = !_keyboardVisible),
                  icon: Icon(
                    _keyboardVisible
                        ? Icons.keyboard_hide_outlined
                        : Icons.keyboard_outlined,
                  ),
                ),
                _topIcon(
                  tooltip: PhString.notebook,
                  icon: Icons.history_outlined,
                  onPressed: _openNotebook,
                ),
                _topIcon(
                  tooltip: tr('Настройки', 'Settings'),
                  icon: Icons.settings_outlined,
                  onPressed: _openSettings,
                ),
              ],
            ),
      body: PopScope(
        canPop: !_showResult && !_keyboardVisible,
        onPopInvokedWithResult: (didPop, _) {
          if (didPop) return;
          if (_showResult) {
            _backToInput();
          } else {
            setState(() => _keyboardVisible = false);
          }
        },
        child: SafeArea(
          top: _showResult,
          child: _showResult
              ? TweenAnimationBuilder<double>(
                  tween: Tween(begin: 0, end: 1),
                  duration: MediaQuery.disableAnimationsOf(context)
                      ? Duration.zero
                      : const Duration(milliseconds: 280),
                  curve: Curves.easeOutCubic,
                  builder: (context, value, child) => Opacity(
                    opacity: value,
                    child: Transform.translate(
                      offset: Offset(0, 18 * (1 - value)),
                      child: child,
                    ),
                  ),
                  child: _buildResult(),
                )
              : _buildEditor(),
        ),
      ),
    );
  }

  /// Верхняя иконка: 14dip отступ, как `padding=14dip` в `activity_main.xml`.
  Widget _topIcon({
    required String tooltip,
    required IconData icon,
    required VoidCallback onPressed,
  }) {
    return IconButton(
      tooltip: tooltip,
      padding: const EdgeInsets.all(14),
      icon: Icon(icon, size: 24),
      color: Theme.of(context).colorScheme.onSurfaceVariant,
      onPressed: onPressed,
    );
  }

  /// Экран ввода: поле, предпросмотр решения, команды и клавиатура.
  Widget _buildEditor() {
    return LayoutBuilder(
      builder: (context, constraints) {
        final wide = constraints.maxWidth > 650 && constraints.maxHeight < 520;
        final keyboard = MathKeyboard(
          controller: _editor,
          decimalSeparator: _settings.decimalSeparator.symbol,
          maxHeight: wide ? constraints.maxHeight : constraints.maxHeight * .58,
        );
        final content = [
          if (_hasVariable(_editor.toCoreNode()))
            TextButton.icon(
              onPressed: _busy ? null : _openGraph,
              icon: const Icon(Icons.show_chart),
              label: Text(tr('График', 'Graph')),
            ),
          _showSolutionButton(),
        ];
        final Widget workspace =
            MediaQuery.textScalerOf(context).scale(1) > 1.3 &&
                constraints.maxHeight < 580
            ? ListView(
                children: [
                  SizedBox(height: 148, child: _editorArea()),
                  ...content,
                ],
              )
            : Column(
                children: [
                  Expanded(child: _editorArea()),
                  ...content,
                ],
              );
        if (!_keyboardVisible && wide) return workspace;
        if (wide) {
          return Row(
            children: [
              Expanded(child: workspace),
              SizedBox(width: 360, child: keyboard),
            ],
          );
        }
        return Column(
          children: [
            Expanded(child: workspace),
            _slideKeyboard(keyboard),
          ],
        );
      },
    );
  }

  /// Примеры задач: одно нажатие кладёт задачу в поле ввода.
  Widget _exampleChips() {
    const examples = <(String, String)>[
      ('x² − 5x + 6 = 0', '{=({x^2-5x+6},{0})}'),
      ('2x + 3 = 7', '{=({2x+3},{7})}'),
      ('(x + 3)²', '{(x+3)^2}'),
      ('1/2 + 1/3', '{frac({1},{2})+frac({1},{3})}'),
      ('x² − 9 > 0', '{>({x^2-9},{0})}'),
      ('∫ x² dx', '{integral({x^2})}'),
      ('d/dx sin x', '{derivation_diff({x},{sin({x})})}'),
    ];
    return Padding(
      padding: const EdgeInsets.only(top: 16),
      child: Wrap(
        spacing: 8,
        runSpacing: 4,
        children: [
          for (final (label, source) in examples)
            ActionChip(
              key: ValueKey('example:$source'),
              label: Text(label),
              onPressed: () => _useExample(source),
            ),
        ],
      ),
    );
  }

  Future<void> _useExample(String source) async {
    try {
      await widget.startup?.ensureReady();
      final node = await widget.api.parse(source);
      if (!mounted) return;
      _editor.replaceDocument(coreToEditor(node));
    } on Object {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            tr('Не удалось подставить пример', 'Could not load example'),
          ),
        ),
      );
    }
  }

  /// Клавиатура выезжает снизу и уезжает обратно; без анимаций просто появляется.
  Widget _slideKeyboard(Widget keyboard) {
    final duration = PhMotion.duration(context, 260);
    final shown = _keyboardVisible
        ? keyboard
        : const SizedBox(width: double.infinity);
    return duration == Duration.zero
        ? shown
        : ClipRect(
            child: AnimatedSize(
              duration: duration,
              curve: Curves.easeOutCubic,
              alignment: Alignment.topCenter,
              child: shown,
            ),
          );
  }

  /// Поле ввода, предпросмотр решения и ошибка — `fragment_editor.xml`.
  Widget _editorArea() {
    return ListView(
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
      children: [
        Text(
          _editor.isEmpty
              ? tr('Введите задачу', 'Enter a problem')
              : _kindLabel,
          style: Theme.of(context).textTheme.bodySmall,
        ),
        const SizedBox(height: 16),
        Stack(
          children: [
            Padding(
              padding: const EdgeInsets.only(
                top: 0,
                left: 0,
                // Справа поле под кнопку очистки — `layout_marginEnd=40dip`
                // плюс сама кнопка.
                right: 40,
              ),
              child: EditorView(
                controller: _editor,
                onFocus: () => setState(() => _keyboardVisible = true),
                decimalSeparator: _settings.decimalSeparator,
              ),
            ),
            // Кнопка очистки справа сверху.
            if (!_editor.isEmpty)
              Positioned(
                top: 0,
                right: 0,
                child: IconButton(
                  tooltip: tr('Очистить', 'Clear'),
                  padding: const EdgeInsets.all(4),
                  icon: const Icon(Icons.cancel, size: 24),
                  color: Theme.of(context).colorScheme.onSurfaceVariant,
                  onPressed: () => setState(_editor.clear),
                ),
              ),
          ],
        ),
        if (_editor.isEmpty)
          Padding(
            padding: const EdgeInsets.only(top: 12),
            child: Text(
              tr(
                'Например, 2x + 3 = 7. Начните с клавиатуры ниже.',
                'For example, 2x + 3 = 7. Start with the keyboard below.',
              ),
              style: Theme.of(context).textTheme.bodySmall,
            ),
          ),
        // examples show what the app can do until the first problem is solved
        if (_editor.isEmpty && !_settings.examplesSeen) _exampleChips(),
        // Ошибка: текст 14sp третичным цветом с иконкой.
        if (_error != null) _errorRow(),
        // Предпросмотр ответа.
        if (_previewLatex case final preview?)
          SolutionPreview(
            latex: preview,
            alternatives: [
              for (final form
                  in (_current ?? _previewAnswer)?.alternatives ?? const [])
                nodeToLatex(form, _latexOptions),
            ],
          ),
        if (_previewFindsRoots) ...[
          Text(
            tr(
              'Нули выражения: приравниваем его к 0',
              'Roots of the expression: set it equal to 0',
            ),
            style: Theme.of(context).textTheme.bodySmall,
          ),
          Align(
            alignment: Alignment.centerLeft,
            child: TextButton(
              onPressed: () => _solveWith(command: 'factor'),
              child: Text(tr('Разложить на множители', 'Factor')),
            ),
          ),
        ],
        if (_previewBusy) const LinearProgressIndicator(minHeight: 2),
        _definedFunctions(),
      ],
    );
  }

  /// LaTeX текущего ответа для предпросмотра над клавиатурой.
  String? get _previewLatex {
    final result = _current ?? _previewAnswer;
    final solution = result?.solution;
    if (solution == null || solution.type == CoreNodeType.empty) {
      return result?.verdictLatex;
    }
    final latex = nodeToLatex(solution, _latexOptions);
    return latex.isEmpty ? null : latex;
  }

  bool get _previewFindsRoots {
    final source = _editor.toCoreNode();
    final solution = _previewAnswer?.solution;
    if (solution == null ||
        source.type == CoreNodeType.equals ||
        source.type == CoreNodeType.system) {
      return false;
    }
    bool equation(CoreNode node) => node.type == CoreNodeType.equals;
    return equation(solution) ||
        (solution.type == CoreNodeType.list &&
            solution.children.isNotEmpty &&
            solution.children.every(equation));
  }

  /// Строка ошибки: 14sp третичным цветом с иконкой.
  Widget _errorRow() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(PhGap.stepSide, 24, PhGap.stepSide, 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(
              Icons.error_outline,
              size: 18,
              color: Theme.of(context).colorScheme.error,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _error!,
              style: TextStyle(
                fontSize: 16,
                color: Theme.of(context).colorScheme.error,
              ),
            ),
          ),
        ],
      ),
    );
  }

  /// Определённые функции (`f(x) = …`) чипами, как подсказки над клавиатурой.
  Widget _definedFunctions() {
    if (_functions.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.fromLTRB(PhGap.stepSide, 0, PhGap.stepSide, 8),
      child: Wrap(
        spacing: 8,
        runSpacing: 4,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (final definition in _functions.definitions)
            Chip(
              label: Text(
                '${definition.name}(${definition.params.join(', ')})',
              ),
              labelStyle: const TextStyle(fontSize: 12),
              backgroundColor: Theme.of(context).colorScheme.surface,
              side: BorderSide(color: Theme.of(context).colorScheme.outline),
              onDeleted: () => _functions.remove(definition.name),
              deleteIcon: const Icon(Icons.close, size: 16),
            ),
        ],
      ),
    );
  }

  /// Команды и дополнительные действия.
  ///
  /// На поверхности — график и разложение, остальное — в листе «Другие
  /// действия», где только то, что имеет смысл для этой задачи.
  Widget _commandBar() {
    final node = _editor.toCoreNode();
    bool variable(CoreNode n) =>
        n.type == CoreNodeType.variable || n.children.any(variable);
    // Factoring means something only for a power of the unknown or a product of
    // two parts that both contain it; `2x + 3 = 7` has nothing to factor.
    bool factorable(CoreNode n) =>
        (n.type == CoreNodeType.power && n.children.any(variable)) ||
        ((n.type == CoreNodeType.multiply ||
                n.type == CoreNodeType.multiplyImplicit) &&
            n.children.where(variable).length >= 2) ||
        n.children.any(factorable);
    final more = _extraActions(node);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Wrap(
        spacing: 8,
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          if (!_editor.isEmpty && variable(node))
            TextButton.icon(
              onPressed: _busy ? null : _openGraph,
              icon: const Icon(Icons.show_chart, size: 20),
              label: Text(tr('График', 'Graph')),
            ),
          if (!_editor.isEmpty &&
              variable(node) &&
              factorable(node) &&
              !_hasCalculus(node))
            TextButton(
              onPressed: () => _solveWith(command: 'factor'),
              child: Text(tr('Разложить на множители', 'Factor')),
            ),
          if (more.isNotEmpty || _command != null)
            TextButton.icon(
              onPressed: () => _openActions(more),
              icon: const Icon(Icons.more_horiz, size: 20),
              label: Text(tr('Другие действия', 'More actions')),
            ),
          if (_command != null)
            InputChip(
              label: Text(_commands.firstWhere((c) => c.$1 == _command).$2),
              onDeleted: () => setState(() {
                _command = null;
                _commandArgs = const [];
              }),
            ),
        ],
      ),
    );
  }

  /// Что ещё можно сделать с этой задачей: `(команда, название, пояснение)`.
  ///
  /// Только осмысленное для её вида — у числа нет асимптот, у уравнения
  /// нет «раскрыть скобки»; раньше лист показывал все 30 команд всегда.
  List<(String, String, String)> _extraActions(CoreNode node) {
    bool has(CoreNode n, bool Function(CoreNode) test) =>
        test(n) || n.children.any((c) => has(c, test));
    bool variable(CoreNode n) => has(n, (m) => m.type == CoreNodeType.variable);
    final letters = <String>{};
    void collect(CoreNode n) {
      if (n.type == CoreNodeType.variable) letters.add(n.value ?? '');
      n.children.forEach(collect);
    }

    collect(node);
    const relations = {
      CoreNodeType.equals,
      CoreNodeType.lessThan,
      CoreNodeType.lessThanEqual,
      CoreNodeType.greaterThan,
      CoreNodeType.greaterThanEqual,
      CoreNodeType.system,
    };
    if (has(node, (n) => n.type == CoreNodeType.matrix)) {
      return [
        (
          'matrix',
          tr('Матрица…', 'Matrix…'),
          tr(
            'умножить, сложить или решить с другой матрицей',
            'multiply, add, or solve with another matrix',
          ),
        ),
      ];
    }
    if (_hasCalculus(node)) return const [];
    if (relations.contains(node.type)) {
      final trig = has(
        node,
        (n) =>
            n.type == CoreNodeType.sin ||
            n.type == CoreNodeType.cos ||
            n.type == CoreNodeType.tan,
      );
      return [
        if (node.type == CoreNodeType.equals &&
            letters.containsAll({'x', 'y'})) ...[
          (
            'conic',
            tr('Тип кривой', 'Curve type'),
            tr(
              'окружность, эллипс, парабола или гипербола',
              'circle, ellipse, parabola, or hyperbola',
            ),
          ),
          (
            'conic_details',
            tr('Свойства кривой', 'Curve properties'),
            tr('центр, радиус, фокусы', 'center, radius, foci'),
          ),
        ],
        if (trig && node.type == CoreNodeType.equals)
          (
            'interval',
            _hasInterval
                ? tr(
                    'Корни на [$_intervalMinText; $_intervalMaxText]',
                    'Roots on [$_intervalMinText; $_intervalMaxText]',
                  )
                : tr('Корни на промежутке', 'Roots on an interval'),
            tr(
              'отобрать корни, лежащие на отрезке',
              'filter roots within the segment',
            ),
          ),
      ];
    }
    if (!variable(node)) {
      // a vector is a LIST of numbers (`solver/vectors.py`)
      if (node.type == CoreNodeType.list) {
        return [
          (
            'vector_length',
            tr('Длина вектора', 'Vector length'),
            tr('модуль вектора', 'vector magnitude'),
          ),
          (
            'vector',
            tr('Вектор…', 'Vector…'),
            tr(
              'сложить или умножить на другой вектор',
              'add or multiply by another vector',
            ),
          ),
        ];
      }
      final value = node.type == CoreNodeType.constant ? node.value ?? '' : '';
      final integer = RegExp(r'^\d+$').hasMatch(value);
      final decimal = RegExp(r'^\d*\.\d+$').hasMatch(value);
      final fraction = node.type == CoreNodeType.fraction;
      return [
        if (integer)
          (
            'prime_factorization',
            tr('Простые множители', 'Prime factors'),
            tr(
              'разложить число на простые множители',
              'factor the number into primes',
            ),
          ),
        if (decimal)
          (
            'to_fraction',
            tr('В обыкновенную дробь', 'To common fraction'),
            tr(
              'записать десятичную дробь обыкновенной',
              'write the decimal as a common fraction',
            ),
          ),
        if (fraction)
          (
            'to_mixed',
            tr('Смешанное число', 'Mixed number'),
            tr('выделить целую часть', 'extract the whole part'),
          ),
        if (integer || decimal || fraction)
          (
            'to_percent',
            tr('В проценты', 'To percent'),
            tr('записать число в процентах', 'write the number as a percent'),
          ),
      ];
    }
    final denominatorHasX = has(
      node,
      (n) =>
          (n.type == CoreNodeType.fraction || n.type == CoreNodeType.divide) &&
          n.children.length == 2 &&
          variable(n.children[1]),
    );
    int? exponent(CoreNode n) =>
        n.type == CoreNodeType.power &&
            n.children.length == 2 &&
            variable(n.children[0])
        ? int.tryParse(n.children[1].value ?? '')
        : null;
    final degrees = <int>[];
    void powers(CoreNode n) {
      if (exponent(n) case final k?) degrees.add(k);
      n.children.forEach(powers);
    }

    powers(node);
    final quadratic =
        !denominatorHasX && degrees.contains(2) && degrees.every((k) => k <= 2);
    final invertible = has(
      node,
      (n) =>
          n.type == CoreNodeType.root2 ||
          n.type == CoreNodeType.ln ||
          n.type == CoreNodeType.log ||
          (n.type == CoreNodeType.power &&
              n.children.length == 2 &&
              variable(n.children[1])),
    );
    return [
      (
        'simplify',
        tr('Упростить', 'Simplify'),
        tr('привести подобные, сократить', 'combine like terms, reduce'),
      ),
      (
        'expand',
        tr('Раскрыть скобки', 'Expand'),
        tr(
          'умножить и привести подобные',
          'multiply out and combine like terms',
        ),
      ),
      (
        'domain',
        tr('Область определения', 'Domain'),
        tr(
          'при каких x выражение имеет смысл',
          'the values of x for which the expression is defined',
        ),
      ),
      (
        'intercepts',
        tr('Пересечения с осями', 'Intercepts'),
        tr('где график пересекает оси', 'where the graph crosses the axes'),
      ),
      if (quadratic)
        (
          'vertex',
          tr('Вершина параболы', 'Parabola vertex'),
          tr('координаты вершины', 'coordinates of the vertex'),
        ),
      if (!denominatorHasX)
        (
          'extrema',
          tr('Экстремумы', 'Extrema'),
          tr('наибольшие и наименьшие значения', 'maximum and minimum values'),
        ),
      if (denominatorHasX) ...[
        (
          'asymptotes',
          tr('Асимптоты', 'Asymptotes'),
          tr(
            'прямые, к которым приближается график',
            'lines that the graph approaches',
          ),
        ),
        (
          'partial_fractions',
          tr('Простейшие дроби', 'Partial fractions'),
          tr(
            'разложить дробь на сумму простых',
            'decompose the fraction into simpler fractions',
          ),
        ),
      ],
      if (invertible || denominatorHasX)
        (
          'inverse_function',
          tr('Обратная функция', 'Inverse function'),
          tr('выразить x через y', 'express x in terms of y'),
        ),
      (
        'even_odd',
        tr('Чётность', 'Parity'),
        tr('чётная, нечётная или общего вида', 'even, odd, or neither'),
      ),
    ];
  }

  Future<void> _openActions(List<(String, String, String)> items) async {
    final action = await showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      builder: (context) => SafeArea(
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.sizeOf(context).height * .75,
          ),
          child: ListView(
            shrinkWrap: true,
            padding: const EdgeInsets.fromLTRB(8, 0, 8, 16),
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
                child: Text(
                  tr('Что ещё можно сделать', 'What else you can do'),
                  style: Theme.of(context).textTheme.titleLarge,
                ),
              ),
              if (_command != null)
                ListTile(
                  minTileHeight: 56,
                  leading: const Icon(Icons.restart_alt),
                  title: Text(_solveLabelFor(null)),
                  subtitle: Text(
                    tr(
                      'вернуться к обычному решению',
                      'return to regular solving',
                    ),
                  ),
                  onTap: () => Navigator.pop(context, 'auto'),
                ),
              for (final (command, title, hint) in items)
                ListTile(
                  minTileHeight: 56,
                  title: Text(title),
                  subtitle: Text(hint),
                  selected: _command == command,
                  onTap: () => Navigator.pop(context, command),
                ),
            ],
          ),
        ),
      ),
    );
    if (!mounted || action == null) return;
    switch (action) {
      case 'vector':
        await _openVectorSheet();
      case 'matrix':
        await _openMatrixSheet();
      case 'interval':
        await _openIntervalDialog();
        if (mounted) await _solve();
      default:
        setState(() {
          _command = action == 'auto' ? null : action;
          _commandArgs = const [];
        });
        await _solve();
    }
  }

  String get _solveLabel => _solveLabelFor(_command);

  String _solveLabelFor(String? command) {
    if (command != null) {
      return _commands.firstWhere((c) => c.$1 == command).$2;
    }
    final node = _editor.toCoreNode();
    final type = node.type;
    // Дифференциальное уравнение (в том числе задача Коши, набранная
    // системой) — не «Решить»: у него свой ответ и свои шаги.
    if ((type == CoreNodeType.equals || type == CoreNodeType.system) &&
        _hasDerivative(node)) {
      return tr('Решить уравнение', 'Solve the equation');
    }
    return switch (type) {
      CoreNodeType.equals ||
      CoreNodeType.system ||
      CoreNodeType.lessThan ||
      CoreNodeType.lessThanEqual ||
      CoreNodeType.greaterThan ||
      CoreNodeType.greaterThanEqual => tr('Решить', 'Solve'),
      CoreNodeType.derivation ||
      CoreNodeType.derivation1 ||
      CoreNodeType.derivation1Diff ||
      CoreNodeType.derivation1Prime ||
      CoreNodeType.derivation2Prime => tr(
        'Найти производную',
        'Find the derivative',
      ),
      CoreNodeType.integral => tr('Найти интеграл', 'Find the integral'),
      CoreNodeType.integralDefinite => tr(
        'Вычислить интеграл',
        'Evaluate the integral',
      ),
      CoreNodeType.limit ||
      CoreNodeType.limitLeft ||
      CoreNodeType.limitRight => tr('Найти предел', 'Find the limit'),
      _ =>
        _hasVariable(node)
            ? tr('Упростить', 'Simplify')
            : tr('Вычислить', 'Evaluate'),
    };
  }

  /// Есть ли в узле производная `y`: штрих, `d/dx` от переменной или `y″`.
  bool _hasDerivative(CoreNode node) => switch (node.type) {
    CoreNodeType.prime ||
    CoreNodeType.derivation1Prime ||
    CoreNodeType.derivation2Prime => true,
    CoreNodeType.derivation || CoreNodeType.derivation1 =>
      node.children.length == 1 &&
          node.children.single.type == CoreNodeType.variable,
    _ => node.children.any(_hasDerivative),
  };

  /// Производная, интеграл или предел: у них свой ответ, разложение и
  /// исследование функции к ним не относятся.
  bool _hasCalculus(CoreNode node) =>
      _hasDerivative(node) ||
      const {
        CoreNodeType.integral,
        CoreNodeType.integralDefinite,
        CoreNodeType.limit,
        CoreNodeType.limitLeft,
        CoreNodeType.limitRight,
      }.contains(node.type) ||
      node.children.any(_hasCalculus);

  bool _hasVariable(CoreNode node) =>
      node.type == CoreNodeType.variable || node.children.any(_hasVariable);

  String get _kindLabel => switch (_editor.toCoreNode().type) {
    CoreNodeType.equals => tr('Уравнение', 'Equation'),
    CoreNodeType.system => tr('Система уравнений', 'System of equations'),
    CoreNodeType.lessThan ||
    CoreNodeType.lessThanEqual ||
    CoreNodeType.greaterThan ||
    CoreNodeType.greaterThanEqual => tr('Неравенство', 'Inequality'),
    CoreNodeType.derivation ||
    CoreNodeType.derivation1 => tr('Производная', 'Derivative'),
    CoreNodeType.integral ||
    CoreNodeType.integralDefinite => tr('Интеграл', 'Integral'),
    _ =>
      _hasVariable(_editor.toCoreNode())
          ? tr('Выражение с переменной', 'Expression with a variable')
          : tr('Арифметическое выражение', 'Arithmetic expression'),
  };

  /// Кнопка «Показать решение» (`PhButton`) по центру над клавиатурой,
  /// отступ снизу 20dp.
  /// Disabled и busy остаются видимыми и не сдвигают клавиатуру.
  Widget _showSolutionButton() {
    final enabled = !_editor.isEmpty && !_busy;
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 0, 16, 12),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (widget.startup case final startup?)
              SolverReadyIndicator(startup: startup),
            PhButton(
              key: const ValueKey('solve'),
              label: _busy
                  ? tr('Решаем…', 'Solving…')
                  : _previewAnswer != null
                  ? tr('Шаги решения', 'Solution steps')
                  : _solveLabel,
              onPressed: enabled ? _solve : null,
              busy: _busy,
            ),
            if (_busy)
              TextButton(
                onPressed: () => setState(() {
                  _requestGeneration++;
                  _busy = false;
                }),
                child: Text(tr('Отменить', 'Cancel')),
              ),
          ],
        ),
      ),
    );
  }

  void _backToInput() => setState(() {
    _result = null;
    _methods = const [];
    _requestGeneration++;
    _busy = false;
    _keyboardVisible = true;
  });

  /// Экран решения: сворачивающийся тулбар высотой 110dp — развёрнутый
  /// заголовок 34sp жирный слева, свёрнутый 16sp по центру на фоне `#F8F8F8`.
  /// `NestedScrollView` + `SliverAppBar`, оба вида заголовка перекрещиваются в
  /// `_CollapsingToolbarTitle`.
  Widget _buildResult() {
    final result = _current;
    if (result == null) return const SizedBox.shrink();
    return Column(
      children: [
        Expanded(
          child: NestedScrollView(
            headerSliverBuilder: (context, innerScrolled) => [
              SliverAppBar(
                pinned: true,
                expandedHeight: 110,
                collapsedHeight: kToolbarHeight,
                backgroundColor: Theme.of(context).scaffoldBackgroundColor,
                surfaceTintColor: Colors.transparent,
                // Навигационной иконки здесь нет: шторка живёт на экране
                // ввода. Иначе `Scaffold` подставит сюда
                // гамбургер поверх заголовка.
                automaticallyImplyLeading: false,
                // Заголовок живёт только в `flexibleSpace`: свой `title`
                // у `SliverAppBar` даёт второй, неубираемый заголовок.
                // При `pinned: true` Flutter считает `toolbarOpacity`
                // равным 1 (`app_bar.dart`), поэтому `FlexibleSpaceBar.title`
                // не гаснет и накладывается на `title`.
                flexibleSpace: const _CollapsingToolbarTitle(),
                // copies the answer to the clipboard
                actions: [
                  IconButton(
                    tooltip: tr('Копировать ответ', 'Copy answer'),
                    icon: const Icon(Icons.copy_outlined),
                    onPressed: _copyResult,
                  ),
                ],
              ),
            ],
            body: VerticalResult(
              result: result,
              problem: _editor.toCoreNode(),
              divisionMethod: _settings.divisionMethod,
              latexOptions: _latexOptions,
              onLink: _onLink,
              onCopy: _copyFormula,
              methodSwitcher: Column(
                children: [
                  _commandBar(),
                  if (_methods.length > 1) _methodSwitcher(),
                ],
              ),
              // back to the input with the problem kept, ready to edit
              leading: IconButton(
                tooltip: tr('Назад', 'Back'),
                style: IconButton.styleFrom(
                  backgroundColor: Theme.of(context).colorScheme.surface,
                  elevation: 3,
                  shadowColor: Colors.black26,
                  fixedSize: const Size(48, 48),
                ),
                icon: const Icon(Icons.arrow_back),
                onPressed: _backToInput,
              ),
            ),
          ),
        ),
      ],
    );
  }

  /// Переключатель способов решения — строка «Альтернативная форма».
  Widget _methodSwitcher() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(
        PhSize.accentBarWidth + PhGap.stepSide,
        PhGap.blockTop,
        PhGap.stepSide,
        0,
      ),
      child: Row(
        children: [
          Expanded(
            child: Text(
              _result?.selectMethodText ??
                  tr('Способ решения', 'Solution method'),
              style: TextStyle(
                fontSize: 16,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
          ),
          Text(
            '${_methodIndex + 1}/${_methods.length}',
            style: Theme.of(context).textTheme.bodySmall,
          ),
          IconButton(
            tooltip: tr('Другой способ', 'Another method'),
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.swap_horiz, size: 20),
            color: Theme.of(context).colorScheme.primary,
            onPressed: () => setState(
              () => _methodIndex = (_methodIndex + 1) % _methods.length,
            ),
          ),
        ],
      ),
    );
  }

  // ─── Действия ───────────────────────────────────────────────────────────

  Future<void> _openSettings() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) => SettingsPage(
          settings: _settings,
          onTheory: _openTheory,
          onHelp: _openHelp,
        ),
      ),
    );
  }

  Future<void> _openNotebook() async {
    final problem = await Navigator.of(context).push<CoreNode>(
      MaterialPageRoute<CoreNode>(
        builder: (_) =>
            NotebookPage(notebook: _notebook, latexOptions: _latexOptions),
      ),
    );
    if (!mounted || problem == null) return;
    try {
      final document = coreToEditor(problem);
      _backToInput();
      _editor.replaceDocument(document);
    } on UnsupportedError {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            tr(
              'Эта запись пока не поддерживает редактирование. Исходная задача сохранена.',
              'This entry cannot be edited yet. The original problem is saved.',
            ),
          ),
        ),
      );
    }
  }

  /// Справка: возможности приложения и настройки ввода.
  Future<void> _openTheory() async {
    await widget.startup?.ensureReady();
    if (!mounted) return;
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            TheoryIndexPage(api: widget.api, locale: _settings.locale),
      ),
    );
  }

  Future<void> _openHelp() async {
    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => const _HelpSheet(),
    );
  }

  /// Открыть график текущего выражения.
  Future<void> _openGraph() async {
    if (_editor.isEmpty) {
      setState(() => _error = tr('Введите выражение', 'Enter an expression'));
      return;
    }
    final generation = _requestGeneration;
    final node = _editor.toCoreNode();
    try {
      await widget.startup?.ensureReady();
      if (!mounted || generation != _requestGeneration) return;
      await Navigator.of(context).push(
        MaterialPageRoute<void>(
          builder: (_) => GraphPage(api: widget.api, node: node),
        ),
      );
    } on SolveFailure catch (err) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(err.message)));
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(
              tr('Не удалось запустить решатель', 'Could not start the solver'),
            ),
          ),
        );
      }
    }
  }

  /// Открыть ввод промежутка отбора корней (для тригонометрических уравнений).
  Future<void> _openIntervalDialog() async {
    final bounds = await showDialog<({String min, String max})>(
      context: context,
      builder: (context) =>
          _IntervalDialog(min: _intervalMinText, max: _intervalMaxText),
    );
    if (bounds == null) return;

    final minText = bounds.min.trim();
    final maxText = bounds.max.trim();
    if (minText.isEmpty || maxText.isEmpty) {
      setState(() {
        _previewAnswer = null;
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
        _previewAnswer = null;
        _intervalMin = minNode;
        _intervalMax = maxNode;
        _intervalMinText = minText;
        _intervalMaxText = maxText;
      });
    } on SolveFailure catch (err) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            tr(
              'Не удалось разобрать границы: ${err.message}',
              'Could not parse the bounds: ${err.message}',
            ),
          ),
        ),
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
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(tr('Скопировано', 'Copied'))));
  }

  /// Текст решения без формул: шаги и пояснения (для копирования).
  String _plainText(SolveResponse result) {
    final buffer = StringBuffer();
    for (final group in result.steps) {
      for (final header in group.headers) {
        buffer.writeln(header);
      }
      for (final substep in group.substeps) {
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
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(tr('Скопировано', 'Copied'))));
  }

  /// Нажатие на ссылку в тексте шага.
  ///
  /// Сюда попадают только ссылки с определением: без него ссылка остаётся
  /// обычным текстом (`ExplanationText`), а не ведёт в тупик «пояснение
  /// появится позже». Смена способа решения — отдельное управление
  /// «Альтернативная форма» на самом экране.
  void _onLink(ExplanationLink link) {
    showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      builder: (context) => Padding(
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              link.label,
              style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 12),
            Text(link.definition, style: const TextStyle(fontSize: 16)),
          ],
        ),
      ),
    );
  }
}

/// Заголовок сворачивающегося тулбара — `CollapsingToolbarLayout`.
///
/// Оба вида заголовка рисуются здесь, а не через `SliverAppBar.title` +
/// `FlexibleSpaceBar.title`: при `pinned: true` `toolbarOpacity` равен 1
/// (`app_bar.dart`), поэтому заголовок `FlexibleSpaceBar` не гаснет и
/// накладывается на заголовок `AppBar` — на экране остаются два текста
/// друг поверх друга. Здесь крупный вид уступает мелкому перекрёстным
/// затуханием на второй половине сворачивания.
class _CollapsingToolbarTitle extends StatelessWidget {
  const _CollapsingToolbarTitle();

  /// Высота развёрнутого тулбара — `AppBarLayout` 110dip.
  static const double _expandedHeight = 110;

  /// Доля сворачивания, на которой виды заголовка сменяют друг друга.
  static const Interval _crossfade = Interval(0.5, 1.0, curve: Curves.easeIn);

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // 0 — тулбар свёрнут, 1 — развёрнут.
        final double expanded =
            ((constraints.maxHeight - kToolbarHeight) /
                    (_expandedHeight - kToolbarHeight))
                .clamp(0.0, 1.0);
        final double showExpanded = _crossfade.transform(expanded);
        return Stack(
          fit: StackFit.expand,
          children: [
            // `ToolbarTitleTextCollapsed`: 16sp, основной цвет, по центру
            // строки тулбара (`collapsedTitleGravity=center_horizontal`).
            Opacity(
              opacity: 1 - showExpanded,
              child: Align(
                alignment: Alignment.topCenter,
                child: SizedBox(
                  height: kToolbarHeight,
                  child: Center(
                    child: Text(
                      PhString.stepsTitle,
                      style: const TextStyle(fontSize: 16),
                    ),
                  ),
                ),
              ),
            ),
            // `ToolbarTitleTextExpanded`: 34sp, жирный, чёрный, поля
            // `expandedTitleMarginStart=16dip` и `…Bottom=22dip`.
            Opacity(
              opacity: showExpanded,
              child: Align(
                alignment: Alignment.bottomLeft,
                child: Padding(
                  padding: const EdgeInsets.only(left: 16, bottom: 22),
                  child: Text(
                    PhString.stepsTitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      fontSize: 34,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

/// Лист справки «Как пользоваться»: перечень возможностей текстом.
class _HelpSheet extends StatelessWidget {
  const _HelpSheet();

  List<(IconData, String, String)> get _items => [
    (
      Icons.backspace_outlined,
      tr('Клавиатура', 'Keyboard'),
      tr(
        'Служебный ряд переключает экраны: abc — буквы, f ∫ <> — расширенная панель. Удержание клавиши открывает варианты: у π — π/2 и π/3, у x — y и z, у √ — ∛ и корень n.',
        'The function row switches screens: abc for letters, f ∫ <> for the extended panel. Long-press a key for alternatives: π/2 and π/3 for π, y and z for x, ∛ and nth root for √.',
      ),
    ),
    (
      Icons.touch_app_outlined,
      tr('Структурный ввод', 'Structural input'),
      tr(
        'Дробь, корень, степень и модуль вставляются шаблонами и поглощают предыдущий операнд. Тап по элементу в поле ставит курсор.',
        'Fractions, roots, powers, and absolute value are inserted as templates and absorb the previous operand. Tap an element in the field to place the cursor.',
      ),
    ),
    (
      Icons.functions,
      tr('Функции', 'Functions'),
      tr(
        'Введите f(x) = … — определение запомнится и подставится в следующие задачи. Из него же берётся обратная функция.',
        'Type f(x) = … — the definition will be remembered and substituted into later problems. The inverse function is also derived from it.',
      ),
    ),
    (
      Icons.show_chart,
      tr('График', 'Graph'),
      tr(
        'Кнопка «График» рисует функцию по точкам и отмечает корни, пересечения с осью y и экстремумы.',
        'The Graph button plots the function point by point and marks roots, y-axis intercepts, and extrema.',
      ),
    ),
    (
      Icons.settings_outlined,
      tr('Настройки', 'Settings'),
      tr(
        'Десятичный разделитель, нотация биномиального коэффициента и методы умножения.',
        'Decimal separator, binomial coefficient notation, and multiplication methods.',
      ),
    ),
  ];

  @override
  Widget build(BuildContext context) {
    final items = _items;
    return ConstrainedBox(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.sizeOf(context).height * 0.7,
      ),
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
        children: [
          Text(
            tr('Как пользоваться', 'How to use'),
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 16),
          for (final (icon, title, body) in items)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(
                    icon,
                    size: 24,
                    color: Theme.of(context).colorScheme.primary,
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(title, style: const TextStyle(fontSize: 16)),
                        const SizedBox(height: 4),
                        Text(
                          body,
                          style: const TextStyle(fontSize: 14, height: 1.35),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
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
    return OutlinedButton(
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
            tr('Операции с вектором', 'Vector operations'),
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _second,
            decoration: InputDecoration(
              labelText: tr(
                'Второй вектор (например 3, 4)',
                'Second vector (for example 3, 4)',
              ),
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _action('vector_add', tr('Сложить', 'Add'), _second),
              _action('vector_subtract', tr('Вычесть', 'Subtract'), _second),
              _action('vector_dot', tr('Скалярное', 'Dot product'), _second),
              _action(
                'vector_cross',
                tr('Векторное', 'Cross product'),
                _second,
              ),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _scalar,
            decoration: InputDecoration(
              labelText: tr('Скаляр', 'Scalar'),
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: _action('vector_scale', tr('× скаляр', '× scalar'), _scalar),
          ),
        ],
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
      title: Text(tr('Промежуток', 'Interval')),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          TextField(
            controller: _min,
            decoration: InputDecoration(
              labelText: tr('Левая граница', 'Left bound'),
              hintText: tr('например, 0', 'for example, 0'),
            ),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _max,
            decoration: InputDecoration(
              labelText: tr('Правая граница', 'Right bound'),
              hintText: tr('например, 2π', 'for example, 2π'),
            ),
          ),
          const SizedBox(height: 12),
          Text(
            tr(
              'Границы — числа или выражения с π. '
                  'Пустые поля убирают промежуток.',
              'Bounds are numbers or expressions with π. '
                  'Empty fields remove the interval.',
            ),
            style: const TextStyle(fontSize: 12),
          ),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: Text(tr('Отмена', 'Cancel')),
        ),
        FilledButton(
          onPressed: () =>
              Navigator.of(context).pop((min: _min.text, max: _max.text)),
          child: Text(tr('Готово', 'Done')),
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
    return OutlinedButton(
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
            tr('Операции с матрицей', 'Matrix operations'),
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 12),
          TextField(
            controller: _second,
            decoration: InputDecoration(
              labelText: tr(
                'Вторая матрица (например 5,6;7,8)',
                'Second matrix (for example 5,6;7,8)',
              ),
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _action('matrix_add', tr('Сложить', 'Add'), _second),
              _action('matrix_subtract', tr('Вычесть', 'Subtract'), _second),
              _action('matrix_multiply', tr('Умножить', 'Multiply'), _second),
              _action(
                'matrix_solve_left',
                tr('Решить A·X = B', 'Solve A·X = B'),
                _second,
              ),
              _action(
                'matrix_solve_right',
                tr('Решить X·A = B', 'Solve X·A = B'),
                _second,
              ),
            ],
          ),
          const SizedBox(height: 16),
          TextField(
            controller: _scalar,
            decoration: InputDecoration(
              labelText: tr('Скаляр', 'Scalar'),
              border: const OutlineInputBorder(),
            ),
          ),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: _action('matrix_scale', tr('× скаляр', '× scalar'), _scalar),
          ),
          const SizedBox(height: 16),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              OutlinedButton(
                onPressed: () => widget.onRun('matrix_transpose', ''),
                child: Text(tr('Транспонировать', 'Transpose')),
              ),
              OutlinedButton(
                onPressed: () => widget.onRun('matrix_inverse', ''),
                child: Text(tr('Обратная', 'Inverse')),
              ),
              OutlinedButton(
                onPressed: () => widget.onRun('matrix_inverse_gauss', ''),
                child: Text(tr('Обратная (Гаусс)', 'Inverse (Gauss)')),
              ),
              OutlinedButton(
                onPressed: () => widget.onRun('matrix_determinant', ''),
                child: Text(tr('Определитель', 'Determinant')),
              ),
              OutlinedButton(
                onPressed: () => widget.onRun('matrix_rank', ''),
                child: Text(tr('Ранг', 'Rank')),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
