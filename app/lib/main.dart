/// Главный экран Photomath: ввод, решение и вертикальный результат.
///
/// Раскладка собрана по `res/layout/activity_main.xml`,
/// `res/layout/fragment_editor.xml`,
/// `res/layout/view_main_navigation_drawer.xml` и
/// `res/layout/activity_vertical_result.xml` (Photomath Plus 7.10.0,
/// SHA-256 `64c633bb…e1bfd`, декод REA `decode_android_resources`):
///
/// ```
/// ┌──────────────────────────────────────────┐
/// │ ☰                          📖  ?          │  плавающие иконки
/// │ ┌ поле ввода ─────────────── ✕ ┐         │
/// │ │ 2x + 3 = 7                   │         │  @id/editor_view
/// │ ├╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌┤         │  @id/solution_dotted_line
/// │ ▌ x = 2                       │         │  @id/solution_line + решение
/// │ ▌                              │         │
/// │           [ Показать решение ]  │         │  @id/solution_button
/// │ f ∫ <>  abc  ←  →  ⏎  ⌫         │         │  @id/control_layout
/// │ ( ) 7 8 9 ÷                    │         │  @id/primary_layout
/// └──────────────────────────────────────────┘
/// ```
///
/// Результат — отдельный экран со сворачивающимся тулбаром
/// «Шаги по решению» (`AppBarLayout` 110dip) и панелью
/// `@id/controls` (назад + `PhotoMathButton` «Пояснить этапы»).
/// Шторка — боковой `NavigationView` шириной 320dip.
///
/// Отличия от оригинала, вынужденные продуктом: камера вне scope
/// (решение пользователя, `truth/09-decisions.md`), поэтому вместо видоискателя
/// сразу открывается редактор; книжная полка, профессор и подписка тоже вне
/// объёма (пункт Plus в шторке — заглушка, баннера нет). Белые иконки
/// видоискателя (`menu_white`, `help_white`) заменены контурными: фон здесь
/// белый, а не тёмный видоискатель. Блокнот, справка и настройки остаются.
library;

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'src/api/embedded_backend.dart';
import 'src/api/solver_api.dart';
import 'src/editor/controller.dart';
import 'src/editor/editor_view.dart';
import 'src/functions/function_store.dart';
import 'src/model/core_node.dart';
import 'src/notebook/notebook.dart';
import 'src/notebook/notebook_page.dart';
import 'src/render/graph_view.dart';
import 'src/render/latex.dart';
import 'src/settings/settings.dart';
import 'src/settings/settings_page.dart';
import 'src/theme/photomath_theme.dart';
import 'src/ui/keyboard/photomath_keyboard.dart';
import 'src/ui/photomath_button.dart';
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
    return MaterialApp(
      theme: PhotomathTheme.light(),
      home: const Scaffold(
        body: Center(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              CircularProgressIndicator(),
              SizedBox(height: 16),
              Text(
                'Запуск решателя…',
                style: TextStyle(color: PhColor.grayDark),
              ),
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
    // Тема оригинала одна: `AppTheme` — Light, тёмной в APK нет.
    // `statusBarColor` оригинала — `#73000000` полупрозрачный чёрный.
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: PhColor.statusBar,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
      ),
      child: MaterialApp(
        title: 'mymath',
        debugShowCheckedModeBanner: false,
        theme: PhotomathTheme.light(),
        home: SolvePage(api: SolverApi(baseUrl: baseUrl)),
      ),
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
  final _functions = FunctionStore();
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

  /// Показывается ли вертикальный результат — отдельный экран, как в оригинале.
  bool get _showResult => _current != null;

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
    // Список определённых функций тоже обновляет экран.
    _functions.addListener(_onSettingsChanged);
    // Видимость `@id/solution_button` и `@id/clear_button` повторяет
    // редактор: в оригинале `EditorFragment` следит за вводом и
    // показывает/прячет кнопку решения (`invisible` + `alpha=0/1`).
    _editor.addListener(_onEditorChanged);
  }

  void _onEditorChanged() {
    if (mounted) setState(() {});
  }

  void _onSettingsChanged() {
    if (mounted) setState(() {});
  }

  @override
  void dispose() {
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

  Future<void> _solve() => _solveWith(command: _command);

  Future<void> _solveWith({
    String? command,
    List<CoreNode> args = const [],
  }) async {
    if (_editor.isEmpty) {
      setState(() => _error = 'Введите выражение');
      return;
    }
    final node = _editor.toCoreNode();
    // `f(x) = …` — это определение функции, а не задача: запоминаем его и
    // подставляем в последующие запросы (см. `FunctionStore`).
    final definition = FunctionStore.parse(node);
    if (definition != null) {
      _functions.define(definition);
      setState(() {
        _result = null;
        _methods = const [];
        _error = null;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Функция ${definition.name} определена')),
      );
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      final answer = await widget.api.solve(
        node,
        locale: _locale,
        command: command,
        args: args,
        intervalMin: _intervalMin,
        intervalMax: _intervalMax,
        definitions: _functions.contract(),
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
        _methods = const [];
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
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Скаляр — одно число')));
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
        ScaffoldMessenger.of(context)
            .showSnackBar(const SnackBar(content: Text('Скаляр — число')));
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
          const SnackBar(
            content: Text('Матрица: строки через ;, ячейки через ,'),
          ),
        );
        return;
      }
      args = [matrix];
    }
    Navigator.of(context).pop();
    _solveWith(command: command, args: args);
  }

  final _scaffoldKey = GlobalKey<ScaffoldState>();

  // ─── Раскладка ──────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: _scaffoldKey,
      backgroundColor: PhColor.white,
      // Шторка навигации оригинала (`@id/navigation_view` в
      // `activity_main.xml`): боковой `NavigationView` шириной до 320dip
      // (`drawer_width`), а не нижний лист.
      drawer: _buildDrawer(),
      body: SafeArea(
        bottom: false,
        child: Stack(
          children: [
            // Контент: результат, если он есть, иначе редактор с клавиатурой.
            Positioned.fill(
              child: _showResult ? _buildResult() : _buildEditor(),
            ),
            // Плавающие иконки принадлежат экрану ввода (`activity_main.xml`):
            // `@id/menu_icon` — шторка навигации, слева сверху
            // (`padding=12dip`, `marginTop=20dip`, `marginStart=4dip`);
            // `@id/notebook_icon` и `@id/help_icon` — справа сверху
            // (`padding=14dip`, `marginTop=18dip`, у помощи дополнительно
            // `marginEnd=8dip`, у блокнота `marginEnd=4dip` слева от помощи).
            //
            // На экране результата их нет: у него своя панель
            // (`activity_vertical_result.xml`), и в её `@id/toolbar` нет
            // навигационной иконки (`contentInsetStartWithNavigation=0dip`),
            // а `@id/share_button` и `@id/toolbar_ribbon` — `visibility=gone`.
            // Возврат оттуда — нижняя `@id/back`.
            if (!_showResult) ...[
              Positioned(top: 20, left: 4, child: _menuButton()),
              Positioned(
                top: 18,
                right: 4,
                child: Row(
                  children: [
                    _topIcon(
                      tooltip: PhString.notebook,
                      icon: Icons.menu_book_outlined,
                      onPressed: _openNotebook,
                    ),
                    const SizedBox(width: 4),
                    _topIcon(
                      tooltip: 'Справка',
                      icon: Icons.help_outline,
                      onPressed: _openHelp,
                    ),
                  ],
                ),
              ),
            ],
          ],
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
      color: PhColor.grayDark,
      onPressed: onPressed,
    );
  }

  /// Кнопка шторки — `@id/menu_icon`.
  Widget _menuButton() {
    return IconButton(
      tooltip: 'Меню',
      padding: const EdgeInsets.all(12),
      icon: const Icon(Icons.menu, size: 24),
      color: PhColor.grayDark,
      onPressed: _openDrawer,
    );
  }

  /// Экран ввода: поле, предпросмотр решения, команды и клавиатура.
  Widget _buildEditor() {
    return Column(
      children: [
        Expanded(child: _editorArea()),
        _commandBar(),
        // `@id/solution_button` — «Показать решение» над клавиатурой.
        _showSolutionButton(),
        PhotomathKeyboard(
          controller: _editor,
          decimalSeparator: _settings.decimalSeparator.symbol,
        ),
      ],
    );
  }

  /// Поле ввода, предпросмотр решения и ошибка — `fragment_editor.xml`.
  Widget _editorArea() {
    return ListView(
      padding: EdgeInsets.zero,
      children: [
        Stack(
          children: [
            Padding(
              padding: const EdgeInsets.only(
                top: PhGap.blockTop,
                left: PhGap.editorStart,
                // Справа поле под кнопку очистки — `layout_marginEnd=40dip`
                // плюс сама кнопка.
                right: 40,
              ),
              child: EditorView(
                controller: _editor,
                decimalSeparator: _settings.decimalSeparator,
              ),
            ),
            // `@id/clear_button`: галочка справа сверху.
            if (!_editor.isEmpty)
              Positioned(
                top: PhGap.blockTop,
                right: 12,
                child: IconButton(
                  tooltip: 'Очистить',
                  padding: const EdgeInsets.all(4),
                  icon: const Icon(Icons.cancel, size: 24),
                  color: PhColor.gray,
                  onPressed: () => setState(_editor.clear),
                ),
              ),
          ],
        ),
        // `@id/error`: текст 14sp тертичным с иконкой ошибки.
        if (_error != null) _errorRow(),
        // `@id/solution_container` + `@id/solution_line`: предпросмотр ответа.
        if (_previewLatex case final preview?) SolutionPreview(latex: preview),
        _definedFunctions(),
      ],
    );
  }

  /// LaTeX текущего ответа для предпросмотра над клавиатурой.
  String? get _previewLatex {
    final result = _current;
    final solution = result?.solution;
    if (solution == null) return null;
    final latex = nodeToLatex(solution, _latexOptions);
    return latex.isEmpty ? null : latex;
  }

  /// Строка ошибки — `@id/error`, 14sp `textColorTertiary` с иконкой.
  Widget _errorRow() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(PhGap.stepSide, 24, PhGap.stepSide, 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.only(top: 2),
            child: Icon(
              Icons.error_outline,
              size: 18,
              color: PhColor.grayLight,
            ),
          ),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _error!,
              style: const TextStyle(fontSize: 14, color: PhColor.grayLight),
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
              labelStyle: const TextStyle(
                fontSize: 12,
                color: PhColor.grayDark,
              ),
              backgroundColor: PhColor.surface,
              side: const BorderSide(color: PhColor.separatorGray),
              onDeleted: () => _functions.remove(definition.name),
              deleteIcon: const Icon(Icons.close, size: 16),
            ),
        ],
      ),
    );
  }

  /// Команды и дополнительные действия.
  ///
  /// В оригинале этот выбор живёт в шторке (`view_main_navigation_drawer`),
  /// здесь — горизонтальная лента, потому что шторка отдана навигации.
  /// Лента — `SingleChildScrollView` + `Row`, а не `ListView`: все чипы
  /// строятся сразу, поэтому дальние команды (`Промежуток`, `График`)
  /// находятся поиском и доступны скроллу (`ensureVisible` в тестах).
  Widget _commandBar() {
    return SizedBox(
      height: 40,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        padding: const EdgeInsets.symmetric(horizontal: 12),
        child: Row(
          children: [
          for (final (command, label) in _commands)
            Padding(
              padding: const EdgeInsets.only(right: 6),
              child: ChoiceChip(
                label: Text(label),
                labelStyle: TextStyle(
                  fontSize: 12,
                  color: _command == command ? PhColor.white : PhColor.grayDark,
                ),
                selected: _command == command,
                selectedColor: PhColor.red,
                backgroundColor: PhColor.surface,
                side: const BorderSide(color: PhColor.separatorGray),
                showCheckmark: false,
                onSelected: (_) => setState(() => _command = command),
              ),
            ),
          ActionChip(
            avatar: const Icon(
              Icons.arrow_outward,
              size: 16,
              color: PhColor.grayDark,
            ),
            label: const Text('Вектор…'),
            labelStyle: const TextStyle(fontSize: 12, color: PhColor.grayDark),
            backgroundColor: PhColor.surface,
            side: const BorderSide(color: PhColor.separatorGray),
            onPressed: _openVectorSheet,
          ),
          const SizedBox(width: 6),
          ActionChip(
            avatar: const Icon(
              Icons.grid_on,
              size: 16,
              color: PhColor.grayDark,
            ),
            label: const Text('Матрица…'),
            labelStyle: const TextStyle(fontSize: 12, color: PhColor.grayDark),
            backgroundColor: PhColor.surface,
            side: const BorderSide(color: PhColor.separatorGray),
            onPressed: _openMatrixSheet,
          ),
          const SizedBox(width: 6),
          ActionChip(
            avatar: const Icon(
              Icons.straighten,
              size: 16,
              color: PhColor.grayDark,
            ),
            label: Text(
              _hasInterval
                  ? 'Промежуток: [$_intervalMinText; $_intervalMaxText]'
                  : 'Промежуток',
            ),
            labelStyle: const TextStyle(fontSize: 12, color: PhColor.grayDark),
            backgroundColor: PhColor.surface,
            side: const BorderSide(color: PhColor.separatorGray),
            onPressed: _openIntervalDialog,
          ),
          const SizedBox(width: 6),
          ActionChip(
            avatar: const Icon(
              Icons.show_chart,
              size: 16,
              color: PhColor.grayDark,
            ),
            label: const Text('График'),
            labelStyle: const TextStyle(fontSize: 12, color: PhColor.grayDark),
            backgroundColor: PhColor.surface,
            side: const BorderSide(color: PhColor.separatorGray),
            onPressed: _openGraph,
          ),
          ],
        ),
      ),
    );
  }

  /// `@id/solution_button` — `PhotoMathButton` оригинала.
  ///
  /// Пилюля радиусом 24dip (`ripple_rounded_corners_red_24`), `minWidth=120dip`,
  /// текст 16sp белый + стрелка `next_white`, `elevation=4dip`,
  /// отступ снизу 20dip, по центру над клавиатурой
  /// (`constraintBottom_toTopOf=keyboard`, старт/конец к родителю).
  /// Без ввода — `invisible` с `alpha=0`: место сохраняется (`Opacity`),
  /// чтобы клавиатура не прыгала.
  Widget _showSolutionButton() {
    final enabled = !_editor.isEmpty && !_busy;
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Center(
        child: Opacity(
          opacity: enabled ? 1 : 0,
          child: PhButton(
            key: const ValueKey('solve'),
            label: _busy ? 'Решаем…' : PhString.showSolution,
            onPressed: enabled ? _solve : null,
            busy: _busy,
          ),
        ),
      ),
    );
  }

  /// Экран вертикального результата — `activity_vertical_result.xml`.
  ///
  /// Оригинал — `CoordinatorLayout` с `AppBarLayout` высотой 110dip и
  /// `CollapsingToolbarLayout`: развёрнутый заголовок 34sp жирный чёрный
  /// (`ToolbarTitleTextExpanded`, `textColorHeader`) с полями
  /// `expandedTitleMarginStart=16dip` / `expandedTitleMarginBottom=22dip`,
  /// свёрнутый — 16sp по центру (`ToolbarTitleTextCollapsed`,
  /// `collapsedTitleGravity=center_horizontal`), фон свёртки
  /// `toolbarColor` (`#F8F8F8`), прокрутка `scroll|exitUntilCollapsed|snap`.
  /// Здесь тот же эффект даёт `NestedScrollView` + `SliverAppBar`, а оба вида
  /// заголовка перекрещиваются в `_CollapsingToolbarTitle`.
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
                backgroundColor: PhColor.toolbar,
                surfaceTintColor: Colors.transparent,
                // В `@id/toolbar` оригинала нет навигационной иконки
                // (`contentInsetStartWithNavigation=0dip`), а шторка живёт
                // на экране ввода. Иначе `Scaffold` подставит сюда
                // гамбургер поверх заголовка.
                automaticallyImplyLeading: false,
                // Заголовок живёт только в `flexibleSpace`: свой `title`
                // у `SliverAppBar` даёт второй, неубираемый заголовок.
                // При `pinned: true` Flutter считает `toolbarOpacity`
                // равным 1 (`app_bar.dart`), поэтому `FlexibleSpaceBar.title`
                // не гаснет и накладывается на `title`.
                flexibleSpace: const _CollapsingToolbarTitle(),
              ),
            ],
            body: VerticalResult(
              result: result,
              latexOptions: _latexOptions,
              onLink: _onLink,
              onCopy: _copyFormula,
              methodSwitcher: _methods.length > 1 ? _methodSwitcher() : null,
            ),
          ),
        ),
        // `@id/back` и `@id/next` из `view_vertical_result_controls`.
        _resultControls(),
      ],
    );
  }

  /// Нижняя панель результата — `view_vertical_result_controls.xml`.
  ///
  /// `@id/controls`: `padding=8dip`, `layout_marginStart/End=24dip`,
  /// `layout_marginBottom=32dip`, `gravity=center_horizontal`.
  /// `@id/back`: 48×48dip, `padding=8dip`, белый скруглённый фон
  /// (`ripple_rounded_corners_white_24`, радиус 24dip), `elevation=4dip`,
  /// иконка `back_step`. `@id/next` — `PhotoMathButton` (`explain_steps`).
  Widget _resultControls() {
    return Padding(
      padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
      child: Row(
        children: [
          IconButton(
            tooltip: 'Назад',
            style: IconButton.styleFrom(
              backgroundColor: PhColor.white,
              elevation: 4,
              padding: const EdgeInsets.all(8),
              fixedSize: const Size(48, 48),
            ),
            icon: const Icon(Icons.arrow_back),
            onPressed: () => setState(() {
              _result = null;
              _methods = const [];
            }),
          ),
          const Spacer(),
          PhButton(
            label: _busy ? 'Решаем…' : PhString.explainSteps,
            onPressed: _busy ? null : _solve,
            busy: _busy,
          ),
        ],
      ),
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
              PhString.alternateForm,
              style: const TextStyle(fontSize: 14, color: PhColor.red),
            ),
          ),
          Text(
            '${_methodIndex + 1}/${_methods.length}',
            style: const TextStyle(fontSize: 14, color: PhColor.grayMedium),
          ),
          IconButton(
            tooltip: 'Другой способ',
            visualDensity: VisualDensity.compact,
            icon: const Icon(Icons.swap_horiz, size: 20),
            color: PhColor.red,
            onPressed: () => setState(
              () => _methodIndex = (_methodIndex + 1) % _methods.length,
            ),
          ),
        ],
      ),
    );
  }

  // ─── Действия ───────────────────────────────────────────────────────────

  /// Открыть боковую шторку (`@id/navigation_view`).
  void _openDrawer() {
    _scaffoldKey.currentState?.openDrawer();
  }

  /// Боковая шторка — `res/layout/view_main_navigation_drawer.xml` 1 в 1.
  ///
  /// Оригинал: `ScrollView` + `ConstraintLayout` (`@id/menu_items`),
  /// логотип `@id/menu_title` высотой 38dip (`marginTop=20dip`,
  /// `marginStart=24dip`), пункты меню 18sp с полями `18dip` сверху/снизу
  /// и `24dip` по бокам, зазор иконка–текст 16dip (`drawablePadding`).
  /// Профиль (`@id/profile_container`) скрыт (`visibility=gone`) без входа —
  /// здесь входа нет (решение пользователя, `truth/09-decisions.md`),
  /// поэтому показан пункт входа. Подписка и баннер вне объёма продукта:
  /// пункт Plus показывает заглушку, баннера нет.
  /// «Настройки» и «Копировать результат» — наши пункты (в оригинале
  /// настройки живут в профиле, а шаринг — в тулбаре результата);
  /// отмечены тем же стилем, чтобы ряд выглядел цельно.
  Widget _buildDrawer() {
    return Drawer(
      backgroundColor: PhColor.white,
      // `drawer_width=320dip` (`android:maxWidth` шторки).
      width: PhSize.drawerWidth,
      child: SafeArea(
        child: ListView(
          padding: EdgeInsets.zero,
          children: [
            // `@id/menu_title`: логотип, высота 38dip, отступы 20/24.
            const Padding(
              padding: EdgeInsets.only(top: 20, left: 24),
              child: SizedBox(
                height: 38,
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Text(
                    'mymath',
                    style: TextStyle(
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                      color: PhColor.red,
                    ),
                  ),
                ),
              ),
            ),
            const SizedBox(height: 25),
            _drawerItem(
              icon: Icons.login_outlined,
              label: PhString.signIn,
              onTap: () {
                Navigator.of(context).pop();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Вход вне объёма версии')),
                );
              },
            ),
            _drawerLanguageItem(),
            _drawerItem(
              icon: Icons.help_outline,
              label: PhString.helpCenter,
              onTap: () {
                Navigator.of(context).pop();
                _openHelp();
              },
            ),
            _drawerItem(
              icon: Icons.info_outline,
              label: PhString.about,
              onTap: () {
                Navigator.of(context).pop();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('mymath — решатель математики')),
                );
              },
            ),
            _drawerItem(
              icon: Icons.workspace_premium_outlined,
              label: PhString.plus,
              onTap: () {
                Navigator.of(context).pop();
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Подписка вне объёма версии')),
                );
              },
            ),
            const Divider(
              height: 1,
              indent: 24,
              endIndent: 24,
              color: PhColor.separatorGray,
            ),
            _drawerItem(
              icon: Icons.menu_book_outlined,
              label: PhString.notebook,
              onTap: () {
                Navigator.of(context).pop();
                _openNotebook();
              },
            ),
            _drawerItem(
              icon: Icons.settings_outlined,
              label: 'Настройки',
              onTap: () {
                Navigator.of(context).pop();
                Navigator.of(context).push(
                  MaterialPageRoute<void>(
                    builder: (_) => SettingsPage(settings: _settings),
                  ),
                );
              },
            ),
            _drawerItem(
              icon: Icons.copy_outlined,
              label: 'Копировать результат',
              enabled: _current != null,
              onTap: () {
                Navigator.of(context).pop();
                _copyResult();
              },
            ),
          ],
        ),
      ),
    );
  }

  /// Пункт шторки: 18sp, поля 18/24, зазор иконка–текст 16dip.
  Widget _drawerItem({
    required IconData icon,
    required String label,
    required VoidCallback? onTap,
    bool enabled = true,
  }) {
    return InkWell(
      onTap: enabled ? onTap : null,
      child: Padding(
        padding: const EdgeInsets.only(
          top: 18,
          bottom: 18,
          left: 24,
          right: 24,
        ),
        child: Row(
          children: [
            Icon(
              icon,
              size: 24,
              color: enabled ? PhColor.grayDark : PhColor.grayLight,
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Text(
                label,
                style: TextStyle(
                  fontSize: 18,
                  color: enabled ? PhColor.grayDark : PhColor.grayLight,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// Пункт языка — `@id/menu_item_language`: иконка + подпись 18sp
  /// и текущее значение 14sp под ней; здесь значение — язык пояснений
  /// (`ru`/`en`, решение пользователя).
  Widget _drawerLanguageItem() {
    return InkWell(
      onTap: () {
        setState(() => _locale = _locale == 'ru' ? 'en' : 'ru');
      },
      child: Padding(
        padding: const EdgeInsets.only(
          top: 18,
          bottom: 18,
          left: 24,
          right: 24,
        ),
        child: Row(
          children: [
            const Icon(Icons.translate, size: 24, color: PhColor.grayDark),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    PhString.language,
                    style: TextStyle(fontSize: 18, color: PhColor.grayDark),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _locale,
                    style: const TextStyle(
                      fontSize: 14,
                      color: PhColor.grayMedium,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openNotebook() async {
    await Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (_) =>
            NotebookPage(notebook: _notebook, latexOptions: _latexOptions),
      ),
    );
  }

  /// Справка: возможности приложения и настройки ввода.
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
      ScaffoldMessenger.of(context)
          .showSnackBar(SnackBar(content: Text(err.message)));
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
    ScaffoldMessenger.of(context)
        .showSnackBar(const SnackBar(content: Text('Скопировано')));
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
        .showSnackBar(const SnackBar(content: Text('Скопировано')));
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
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: PhColor.grayDark,
              ),
            ),
            const SizedBox(height: 12),
            Text(
              link.definition,
              style: const TextStyle(fontSize: 16, color: PhColor.grayDark),
            ),
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
/// затуханием на второй половине сворачивания, как в оригинале.
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
        final double expanded = ((constraints.maxHeight - kToolbarHeight) /
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
              child: const Align(
                alignment: Alignment.topCenter,
                child: SizedBox(
                  height: kToolbarHeight,
                  child: Center(
                    child: Text(
                      PhString.stepsTitle,
                      style: TextStyle(fontSize: 16, color: PhColor.grayDark),
                    ),
                  ),
                ),
              ),
            ),
            // `ToolbarTitleTextExpanded`: 34sp, жирный, чёрный, поля
            // `expandedTitleMarginStart=16dip` и `…Bottom=22dip`.
            Opacity(
              opacity: showExpanded,
              child: const Align(
                alignment: Alignment.bottomLeft,
                child: Padding(
                  padding: EdgeInsets.only(left: 16, bottom: 22),
                  child: Text(
                    PhString.stepsTitle,
                    style: TextStyle(
                      fontSize: 34,
                      fontWeight: FontWeight.bold,
                      color: PhColor.black,
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

/// Лист справки — замена экрана «Как пользоваться» оригинала.
///
/// Оригинал (`activity_how_to_use.xml`) — карусель с картинками; здесь тот же
/// перечень возможностей текстом.
class _HelpSheet extends StatelessWidget {
  const _HelpSheet();

  @override
  Widget build(BuildContext context) {
    const items = <(IconData, String, String)>[
      (
        Icons.backspace_outlined,
        'Клавиатура',
        'Служебный ряд переключает экраны: abc — буквы, f ∫ <> — расширенная панель. Удержание клавиши открывает варианты: у π — π/2 и π/3, у x — y и z, у √ — ∛ и корень n.',
      ),
      (
        Icons.touch_app_outlined,
        'Структурный ввод',
        'Дробь, корень, степень и модуль вставляются шаблонами и поглощают предыдущий операнд. Тап по элементу в поле ставит курсор.',
      ),
      (
        Icons.functions,
        'Функции',
        'Введите f(x) = … — определение запомнится и подставится в следующие задачи. Из него же берётся обратная функция.',
      ),
      (
        Icons.show_chart,
        'График',
        'Кнопка «График» рисует функцию по точкам и отмечает корни, пересечения с осью y и экстремумы.',
      ),
      (
        Icons.settings_outlined,
        'Настройки',
        'Десятичный разделитель, нотация биномиального коэффициента и методы умножения.',
      ),
    ];
    return ConstrainedBox(
      constraints: BoxConstraints(
        maxHeight: MediaQuery.sizeOf(context).height * 0.7,
      ),
      child: ListView(
        shrinkWrap: true,
        padding: const EdgeInsets.fromLTRB(24, 8, 24, 32),
        children: [
          const Text(
            'Как пользоваться',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: PhColor.grayDark,
            ),
          ),
          const SizedBox(height: 16),
          for (final (icon, title, body) in items)
            Padding(
              padding: const EdgeInsets.only(bottom: 16),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(icon, size: 24, color: PhColor.red),
                  const SizedBox(width: 16),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          title,
                          style: const TextStyle(
                            fontSize: 16,
                            color: PhColor.grayDark,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          body,
                          style: const TextStyle(
                            fontSize: 14,
                            color: PhColor.grayMedium,
                            height: 1.35,
                          ),
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
          const Text(
            'Операции с вектором',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: PhColor.grayDark,
            ),
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
          const Text(
            'Операции с матрицей',
            style: TextStyle(
              fontSize: 18,
              fontWeight: FontWeight.bold,
              color: PhColor.grayDark,
            ),
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
              OutlinedButton(
                onPressed: () => widget.onRun('matrix_transpose', ''),
                child: const Text('Транспонировать'),
              ),
              OutlinedButton(
                onPressed: () => widget.onRun('matrix_inverse', ''),
                child: const Text('Обратная'),
              ),
              OutlinedButton(
                onPressed: () => widget.onRun('matrix_inverse_gauss', ''),
                child: const Text('Обратная (Гаусс)'),
              ),
              OutlinedButton(
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
