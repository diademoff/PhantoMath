import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mymath_app/src/theme/phanto_theme.dart';

double contrast(Color a, Color b) {
  final x = a.computeLuminance();
  final y = b.computeLuminance();
  return ((x > y ? x : y) + .05) / ((x > y ? y : x) + .05);
}

void main() {
  for (final theme in [PhantoTheme.light(), PhantoTheme.dark()]) {
    test('AA semantic pairs ${theme.brightness}', () {
      final c = theme.colorScheme;
      expect(contrast(c.onSurface, c.surface), greaterThanOrEqualTo(4.5));
      expect(contrast(c.onSurfaceVariant, c.surface), greaterThanOrEqualTo(4.5));
      expect(contrast(c.onPrimary, c.primary), greaterThanOrEqualTo(4.5));
      expect(contrast(c.outline, c.surface), greaterThanOrEqualTo(3));
      expect(contrast(c.error, c.surface), greaterThanOrEqualTo(4.5));
    });
  }
}
