import 'package:flutter/material.dart';

import 'palette.dart' show PhColor;

/// Semantic roles: widgets must not select colors themselves.
///
/// Palette and shapes come from `palette.dart`: red accent, flat white surfaces,
/// grey text. There is no dark theme.
abstract final class PhantoTheme {
  static ThemeData light() {
    const page = PhColor.white;
    final scheme = ColorScheme.fromSeed(seedColor: PhColor.red).copyWith(
      primary: PhColor.red,
      onPrimary: PhColor.white,
      primaryContainer: PhColor.highlight,
      onPrimaryContainer: const Color(0xFF5C0016),
      surface: PhColor.white,
      onSurface: PhColor.grayDark,
      onSurfaceVariant: const Color(0xFF65686D),
      // inactive steps lie on the light grey window background.
      surfaceContainerLow: PhColor.surface,
      surfaceContainerHighest: PhColor.separatorGray,
      outline: const Color(0xFF777A7F),
      outlineVariant: PhColor.separatorGray,
      error: PhColor.error,
    );
    final base = ThemeData(useMaterial3: true, colorScheme: scheme);
    final rounded = RoundedRectangleBorder(
      borderRadius: BorderRadius.circular(14),
    );
    return base.copyWith(
      scaffoldBackgroundColor: page,
      splashFactory: InkSparkle.splashFactory,
      pageTransitionsTheme: const PageTransitionsTheme(
        builders: {
          TargetPlatform.android: FadeForwardsPageTransitionsBuilder(),
          TargetPlatform.linux: FadeForwardsPageTransitionsBuilder(),
        },
      ),
      textTheme: base.textTheme.copyWith(
        headlineSmall: TextStyle(
          fontSize: 28,
          fontWeight: FontWeight.w600,
          color: scheme.onSurface,
          letterSpacing: -0.6,
        ),
        titleLarge: TextStyle(
          fontSize: 22,
          fontWeight: FontWeight.w600,
          color: scheme.onSurface,
        ),
        // step-screen heading: bold accent.
        titleMedium: TextStyle(
          fontSize: 18,
          fontWeight: FontWeight.bold,
          color: scheme.primary,
        ),
        bodyLarge: TextStyle(
          fontSize: 16,
          height: 1.45,
          color: scheme.onSurface,
        ),
        bodyMedium: TextStyle(
          fontSize: 16,
          height: 1.45,
          color: scheme.onSurface,
        ),
        bodySmall: TextStyle(
          fontSize: 14,
          height: 1.4,
          color: scheme.onSurfaceVariant,
        ),
        labelLarge: TextStyle(
          fontSize: 16,
          fontWeight: FontWeight.w600,
          color: scheme.onSurface,
        ),
        labelSmall: TextStyle(fontSize: 14, color: scheme.onSurfaceVariant),
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: page,
        foregroundColor: scheme.onSurface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        scrolledUnderElevation: 0,
        centerTitle: false,
      ),
      cardTheme: CardThemeData(
        color: scheme.surface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(16),
          side: BorderSide(color: scheme.outlineVariant),
        ),
      ),
      dividerTheme: DividerThemeData(color: scheme.outlineVariant, space: 1),
      snackBarTheme: SnackBarThemeData(
        behavior: SnackBarBehavior.floating,
        shape: rounded,
        backgroundColor: PhColor.grayDark,
        contentTextStyle: const TextStyle(color: PhColor.white),
      ),
      iconButtonTheme: IconButtonThemeData(
        style: IconButton.styleFrom(minimumSize: const Size(48, 48)),
      ),
      filledButtonTheme: FilledButtonThemeData(
        style: FilledButton.styleFrom(
          minimumSize: const Size(48, 52),
          shape: rounded,
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          minimumSize: const Size(48, 48),
          side: BorderSide(color: scheme.primary),
          shape: rounded,
        ),
      ),
      textButtonTheme: TextButtonThemeData(
        style: TextButton.styleFrom(minimumSize: const Size(48, 48)),
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        showDragHandle: true,
        shape: const RoundedRectangleBorder(
          borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
        ),
      ),
      dialogTheme: DialogThemeData(
        backgroundColor: scheme.surface,
        surfaceTintColor: Colors.transparent,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      ),
      inputDecorationTheme: InputDecorationTheme(
        border: OutlineInputBorder(borderRadius: BorderRadius.circular(14)),
        contentPadding: const EdgeInsets.all(16),
      ),
    );
  }
}

abstract final class PhMotion {
  static Duration duration(BuildContext context, [int milliseconds = 200]) =>
      MediaQuery.disableAnimationsOf(context)
      ? Duration.zero
      : Duration(milliseconds: milliseconds);
}
