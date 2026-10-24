/// Палитра, размеры и базовая тема приложения.
///
/// Не Material 3 с генерацией из seed-цвета, а ручная палитра: красный
/// акцент, плоские белые поверхности и три фиксированных серых для текста
/// (основной, вторичный, пояснения шагов) — генератор из seed таких серых не
/// даёт.
library;

import 'package:flutter/material.dart';

import '../i18n.dart';

/// Цвета приложения.
abstract final class PhColor {
  /// Акцент: заголовок «Решение», полоса слева, ссылки.
  static const Color red = Color(0xFFBF0C34);

  /// Основной текст и подписи клавиш.
  static const Color grayDark = Color(0xFF4C4F54);

  /// Вторичный текст, пунктир, ось графика.
  static const Color grayMedium = Color(0xFF7F7F7F);

  /// Третичный текст — пояснения шагов.
  static const Color grayLight = Color(0xFFABABAB);

  /// Подписи на графике, стрелка меню в шторке.
  static const Color gray = Color(0xFFA6A7AA);

  /// Тень над клавиатурой.
  static const Color gray30 = Color(0x48A6A7AA);

  /// Разделители.
  static const Color separatorGray = Color(0xFFEAEAEA);

  static const Color black = Color(0xFF000000);

  /// Операторы в предпросмотре решения.
  static const Color black40 = Color(0x66000000);

  static const Color white = Color(0xFFFFFFFF);

  /// Фон поверхностей.
  static const Color surface = Color(0xFFF5F5F5);

  /// Тонкие линии-разделители.
  static const Color divider = Color(0x1A000000);

  /// Светло-серый для неактивных элементов.
  static const Color light = Color(0xFFE1E1E1);

  /// Фон тулбара.
  static const Color toolbar = Color(0xFFF8F8F8);

  /// Полупрозрачная строка состояния.
  static const Color statusBar = Color(0x73000000);

  /// Подсветка совпадения при поиске.
  static const Color highlight = Color(0xFFF8E6EA);

  /// Подсветка шага при нажатии.
  static const Color resultOverlay = Color(0x95EAEAEA);

  /// Ошибки.
  static const Color error = Color(0xFFB00020);

  /// Цвета графика: оси, сетка, рамка, подписи.
  static const Color graphAxis = Color(0xFF7F7F7F);
  static const Color graphGrid = Color(0xFFEAEAEA);
  static const Color graphBorder = Color(0xFFD8D8D8);
  static const Color graphLabel = Color(0xFFA6A7AA);

  /// Клавиатура.
  ///
  /// Заливка клавиши задаётся **типом** ключа: цифры, константы, переменные и
  /// плоские знаки — белые, функции — серые, служебные — фон клавиатуры,
  /// клавиши возврата — темнее.
  static const Color keyboardBackground = Color(0xFFF0F0F0);
  static const Color keyboardNumeric = Color(0xFFFFFFFF);
  static const Color keyboardFunction = Color(0xFFE0E0E0);
  static const Color keyboardReturnHelper = Color(0xFFCBCCCD);

  /// Подписи клавиш.
  static const Color keyboardText = grayDark;
}

/// Размеры, dp.
abstract final class PhSize {
  /// Зазор между клавишами.
  static const double keyPadding = 2;

  /// Базовый кегль клавиши.
  static const double keyTextSize = 20;

  /// Доля кегля, которой рисуется математический глиф на клавише.
  static const double keyGlyphScale = 0.85;

  /// Высота строки управления (доля экрана).
  static const double controlHeightFraction = 0.08;

  /// Высота сетки клавиш (доля экрана).
  static const double keyboardHeightFraction = 0.33;

  /// Отступ подсказки долгого нажатия.
  static const double hintMargin = 6;

  /// Кегль структурного редактора.
  static const double editorInputTextSize = 20;

  /// Ширина стрелки разворачивания шага.
  static const double stepsArrowWidth = 19;

  /// Ширина боковой шторки.
  static const double drawerWidth = 320;

  /// Кегль пунктов шторки.
  static const double navigationTextSize = 16;

  /// Ширина красной полосы слева у решения и заголовка.
  static const double accentBarWidth = 6;

  /// Радиус скругления клавиши.
  static const double keyRadius = 2;
}

/// Базовая тема для `MaterialApp`.
abstract final class PhTheme {
  /// Светлая тема; тёмной у приложения нет.
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
      // Подписи кнопок без заглавных букв.
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

  /// Роли текста: заголовок решения, основной текст, пояснения, подписи.
  static TextTheme _textTheme(Brightness brightness) {
    final primary = PhColor.grayDark;
    final secondary = PhColor.grayMedium;
    final tertiary = PhColor.grayLight;
    return TextTheme(
      // Заголовок решения: 18sp, bold, акцентный цвет.
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

/// Отступы экрана решения.
///
/// Держим в одном месте, чтобы раскладка не размазывалась по виджетам.
abstract final class PhGap {
  /// Отступ текста поля ввода слева.
  static const double editorStart = 10;

  /// Верхний отступ поля ввода и блока решения.
  static const double blockTop = 16;

  /// Поля вокруг текста шага.
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

/// Общие подписи интерфейса.
abstract final class PhString {
  static String get notebook => tr('Блокнот', 'Notebook');

  /// Заголовок экрана результата.
  static String get stepsTitle => tr('Шаги по решению', 'Solution steps');
}
