/// Тема и палитра Photomath — перенесены из APK 1 в 1.
///
/// Источник: Photomath Plus 7.10.0 (SHA-256 `64c633bb…e1bfd`), файлы
/// `res/values/colors.xml`, `res/values/styles.xml`, `res/values/dimens.xml`.
/// Ресурсы прочитаны через REA (`decode_android_resources`) и сверены с
/// локальным декодом apktool того же APK.
///
/// Оригинал — не Material 3, а `Theme.MaterialComponents.Light.NoActionBar`
/// с ручной палитрой; роли текста заданы явно:
///
/// | роль оригинала              | ресурс APK                  | цвет      |
/// |-----------------------------|-----------------------------|-----------|
/// | `android:textColorPrimary`   | `photomath_gray_dark`       | `#4C4F54` |
/// | `android:textColorSecondary` | `photomath_gray_medium`     | `#7F7F7F` |
/// | `android:textColorTertiary`  | `photomath_gray_light`      | `#ABABAB` |
/// | `backgroundColor`            | `white`                     | `#FFFFFF` |
/// | `colorSurface`               | `photomath_window_background_light_gray` | `#F5F5F5` |
/// | `dividerColor`               | `photomath_divider_gray`    | `#1A000000` |
/// | `warningColor`, `colorError` | `photomath_red`             | `#BF0C34` |
///
/// Поэтому палитра собрана вручную, а не через `ColorScheme.fromSeed`:
/// генератор из seed-цвета не даёт нужных серых (в оригинале это не тони,
/// а фиксированные значения).
library;

import 'package:flutter/material.dart';

/// Цвета Photomath. Значения — из `res/values/colors.xml` без преобразований.
abstract final class PhColor {
  /// `photomath_red`: акцент, заголовок «Решение», полоса слева, ссылки.
  static const Color red = Color(0xFFBF0C34);

  /// `photomath_gray_dark`: основной текст и подписи клавиш.
  static const Color grayDark = Color(0xFF4C4F54);

  /// `photomath_gray_medium`: вторичный текст, пунктир, ось графика.
  static const Color grayMedium = Color(0xFF7F7F7F);

  /// `photomath_gray_light`: третичный текст — пояснения шагов.
  static const Color grayLight = Color(0xFFABABAB);

  /// `photomath_gray`: подписи на графике, стрелка меню в шторке.
  static const Color gray = Color(0xFFA6A7AA);

  /// `photomath_gray_30`: тень над клавиатурой.
  static const Color gray30 = Color(0x48A6A7AA);

  /// `photomath_separator_gray` / `photomath_gray_ultra_light`.
  static const Color separatorGray = Color(0xFFEAEAEA);

  /// `photomath_black`.
  static const Color black = Color(0xFF000000);

  /// `photomath_black_40`: операторы в предпросмотре решения.
  static const Color black40 = Color(0x66000000);

  /// `white`.
  static const Color white = Color(0xFFFFFFFF);

  /// `photomath_window_background_light_gray` = `colorSurface`.
  static const Color surface = Color(0xFFF5F5F5);

  /// `photomath_divider_gray` = `dividerColor`.
  static const Color divider = Color(0x1A000000);

  /// `photomath_light` = `colorAccent`, `primaryLight`.
  static const Color light = Color(0xFFE1E1E1);

  /// `toolbar_background_color`.
  static const Color toolbar = Color(0xFFF8F8F8);

  /// `status_bar_color`.
  static const Color statusBar = Color(0x73000000);

  /// `photomath_highlight_light` — подсветка совпадения при поиске.
  static const Color highlight = Color(0xFFF8E6EA);

  /// `vertical_result_overlay_color` — подсветка шага при нажатии.
  static const Color resultOverlay = Color(0x95EAEAEA);

  /// `errorColor`.
  static const Color error = Color(0xFFB00020);

  /// Цвета графика: `photomath_graph_axis`, `_grid`, `_border`, `_label`.
  static const Color graphAxis = Color(0xFF7F7F7F);
  static const Color graphGrid = Color(0xFFEAEAEA);
  static const Color graphBorder = Color(0xFFD8D8D8);
  static const Color graphLabel = Color(0xFFA6A7AA);

  /// Клавиатура.
  ///
  /// Заливка клавиши задаётся **типом** ключа (`c.a.a.a.t.a.e.a`):
  /// цифры, константы, переменные и плоские знаки — белые, функции —
  /// `keyboard_function_keys_color`, служебные — `keyboard_default_background`,
  /// клавиши возврата — `keyboard_return_helper_keys_color`.
  static const Color keyboardBackground = Color(0xFFF0F0F0);
  static const Color keyboardNumeric = Color(0xFFFFFFFF);
  static const Color keyboardFunction = Color(0xFFE0E0E0);
  static const Color keyboardReturnHelper = Color(0xFFCBCCCD);

  /// `keyboard_button_text_color` = `photomath_gray_dark`.
  static const Color keyboardText = grayDark;
}

/// Размеры из `res/values/dimens.xml` и атрибутов раскладок.
abstract final class PhSize {
  /// `keyboard_column_padding` и `keyboard_row_padding`.
  static const double keyPadding = 2;

  /// `keyboard_button_text_size`: базовый кегль клавиши (20dip).
  static const double keyTextSize = 20;

  /// Доля клавиши, на которой рисуется математический глиф
  /// (`KeyboardKeyView.c`: `new MathTextView(context, text, textSize * 0.85f)`).
  static const double keyGlyphScale = 0.85;

  /// `control_height_percentage`: высота строки управления.
  static const double controlHeightFraction = 0.08;

  /// `keyboard_height_percentage`: высота сетки клавиш.
  static const double keyboardHeightFraction = 0.33;

  /// `keyboard_hint_margin`: отступ подсказки долгого нажатия.
  static const double hintMargin = 6;

  /// `editor_input_text_size`: кегль структурного редактора.
  static const double editorInputTextSize = 20;

  /// `steps_arrow_width`: ширина стрелки разворачивания шага.
  static const double stepsArrowWidth = 19;

  /// `drawer_width`.
  static const double drawerWidth = 320;

  /// `navigation_text_size`.
  static const double navigationTextSize = 16;

  /// Ширина красной полосы слева (`@id/solution_line`, `@id/title`).
  static const double accentBarWidth = 6;

  /// Радиус скругления клавиши (`drawable/keyboard_button_background`).
  static const double keyRadius = 2;
}

/// Тема Photomath для `MaterialApp`.
abstract final class PhotomathTheme {
  /// Светлая тема. Оригинал тёмную не имеет (`AppTheme` — Light, а
  /// `color-night/` в APK касается только таймпикера Material).
  static ThemeData light() => _base(Brightness.light);

  static ThemeData _base(Brightness brightness) {
    final scheme = const ColorScheme.light(
      primary: PhColor.red,
      onPrimary: PhColor.white,
      secondary: PhColor.grayDark,
      onSecondary: PhColor.white,
      surface: PhColor.surface,
      onSurface: PhColor.grayDark,
      error: PhColor.error,
      onError: PhColor.white,
    );
    final text = _textTheme(brightness);
    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: scheme,
      scaffoldBackgroundColor: PhColor.white,
      canvasColor: PhColor.white,
      dividerColor: PhColor.divider,
      textTheme: text,
      primaryTextTheme: text,
      splashFactory: InkRipple.splashFactory,
      appBarTheme: const AppBarTheme(
        backgroundColor: PhColor.toolbar,
        foregroundColor: PhColor.grayDark,
        elevation: 0,
        centerTitle: false,
        surfaceTintColor: Colors.transparent,
      ),
      iconTheme: const IconThemeData(color: PhColor.grayDark, size: 24),
      snackBarTheme: const SnackBarThemeData(
        backgroundColor: PhColor.grayDark,
        contentTextStyle: TextStyle(color: PhColor.white, fontSize: 14),
        behavior: SnackBarBehavior.floating,
      ),
      bottomSheetTheme: const BottomSheetThemeData(
        backgroundColor: PhColor.white,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(16)),
        ),
      ),
      dialogTheme: const DialogThemeData(
        backgroundColor: PhColor.white,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.all(Radius.circular(4)),
        ),
      ),
      // `buttonStyle` оригинала — `NoCapsButton`: заглавных нет нигде.
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          backgroundColor: PhColor.red,
          foregroundColor: PhColor.white,
          elevation: 0,
          textStyle: const TextStyle(fontSize: 16),
          shape: const RoundedRectangleBorder(),
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(
          foregroundColor: PhColor.red,
          textStyle: const TextStyle(fontSize: 16),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: PhColor.red,
          side: const BorderSide(color: PhColor.red),
          textStyle: const TextStyle(fontSize: 16),
        ),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(foregroundColor: PhColor.grayDark),
      ),
      dividerTheme: const DividerThemeData(
        color: PhColor.divider,
        thickness: 1,
        space: 1,
      ),
      listTileTheme: const ListTileThemeData(
        iconColor: PhColor.grayDark,
        textColor: PhColor.grayDark,
      ),
    );
  }

  /// Роли текста повторяют `AppTheme` оригинала.
  static TextTheme _textTheme(Brightness brightness) {
    final primary = PhColor.grayDark;
    final secondary = PhColor.grayMedium;
    final tertiary = PhColor.grayLight;
    return TextTheme(
      // Заголовок решения: 18sp, bold, `photomath_red`.
      titleMedium: const TextStyle(
        fontSize: 18,
        fontWeight: FontWeight.bold,
        color: PhColor.red,
        height: 1.2,
      ),
      // Основной текст и подписи кнопок: 16sp.
      bodyLarge: TextStyle(fontSize: 16, color: primary),
      bodyMedium: TextStyle(fontSize: 16, color: primary),
      // Пояснение шага: 16sp, `textColorTertiary`.
      bodySmall: TextStyle(fontSize: 16, color: tertiary, height: 1.35),
      titleSmall: TextStyle(fontSize: 14, color: secondary),
      labelLarge: TextStyle(fontSize: 14, color: primary),
      labelMedium: TextStyle(fontSize: 12, color: secondary),
      labelSmall: TextStyle(fontSize: 11, color: secondary),
    );
  }
}

/// Раскладка строк APK, повторяющая `constraint`-атрибуты один в один.
///
/// Держим в одном месте, чтобы раскладка читалась как в `res/layout`, а не
/// размазывалась по виджетам.
abstract final class PhGap {
  /// Отступ текста поля ввода слева (`editor_view` `layout_marginStart`).
  static const double editorStart = 10;

  /// Верхний отступ поля ввода и блока решения (`16dip`).
  static const double blockTop = 16;

  /// Поля вокруг текста шага (`collapsed_description`, `left_equation`).
  static const double stepSide = 16;

  /// Отступ между стрелкой и текстом в раскрытом шаге.
  static const double stepArrowGutter = 24;

  /// Отступ под шагом перед разделителем.
  static const double stepBottom = 16;

  /// Верхний отступ раскрытой части шага.
  static const double stepExpandedTop = 16;

  /// Отступ описания под формулой раскрытого шага.
  static const double stepDescriptionTop = 8;
}

/// Строки интерфейса, взятые из `res/values/strings.xml` и `values-ru`.
///
/// Локализация интерфейса в приложении не делается (решение пользователя,
/// `truth/09-decisions.md`), поэтому строки живут здесь, а не в
/// `flutter_localizations`: язык пояснений (`ru`/`en`) выбирается отдельно и
/// на эти подписи не влияет.
abstract final class PhString {
  /// `@string/solution`.
  static const String solution = 'Решение';

  /// `@string/show_solution_capitalized`.
  static const String showSolution = 'Показать решение';

  /// `@string/alternate_form`.
  static const String alternateForm = 'Альтернативная форма';

  /// `@string/explain_steps`.
  static const String explainSteps = 'Пояснить этапы';

  /// `@string/calculator` — подпись под иконкой калькулятора на главном.
  static const String calculator = 'Калькулятор';

  /// `@string/notebook`.
  static const String notebook = 'Блокнот';

  /// `@string/steps_why`.
  static const String stepsWhy = 'Почему';

  /// `@string/steps_explain_how`.
  static const String stepsExplainHow = 'Как это получилось';

  /// `@string/title_activity_steps` (ru): заголовок экрана результата.
  static const String stepsTitle = 'Шаги по решению';

  /// `@string/language` (ru).
  static const String language = 'Язык';

  /// `@string/authentication_create_profile` (ru).
  static const String signIn = 'Войти в Photomath';

  /// `@string/title_activity_help_center` (ru).
  static const String helpCenter = 'Справочный центр';

  /// `@string/navigation_about_photomath` (ru).
  static const String about = 'О нас';

  /// `@string/subscription_plus`.
  static const String plus = 'Photomath Plus';
}
