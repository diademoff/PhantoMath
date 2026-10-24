/// Основная кнопка приложения: красная пилюля с текстом и стрелкой.
///
/// * радиус 24dp; включена — акцентный цвет, выключена — серая;
/// * минимальная ширина 120dp, внешние поля 16×2dp;
/// * текст 16sp белый, зазор текст–иконка 10dp, иконка — стрелка вправо;
/// * без ввода кнопка невидима, но место за ней сохраняется.
library;

import 'package:flutter/material.dart';

/// Основная кнопка: красная пилюля с текстом и стрелкой.
class PhButton extends StatelessWidget {
  const PhButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.busy = false,
  });

  final String label;
  final VoidCallback? onPressed;
  final bool busy;

  @override
  Widget build(BuildContext context) {
    final enabled = onPressed != null && !busy;
    return Semantics(
      liveRegion: busy,
      child: FilledButton(
        onPressed: enabled ? onPressed : null,
        child: Padding(
          padding: const EdgeInsets.symmetric(vertical: 12),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              if (busy)
                const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              if (busy) const SizedBox(width: 12),
              Flexible(child: Text(label, textAlign: TextAlign.center)),
              if (!busy) ...[
                const SizedBox(width: 12),
                const Icon(Icons.arrow_forward, size: 20),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
