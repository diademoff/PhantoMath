/// Кнопка Photomath — `PhotoMathButton` оригинала, перенесена 1 в 1.
///
/// Источник: Photomath Plus 7.10.0 (SHA-256 `64c633bb…e1bfd`),
/// декод REA (`decode_android_resources`, ev_a748edcb…) + локальный декод
/// apktool того же APK:
/// `res/layout/view_photomath_button.xml`,
/// `res/drawable/photomath_button_background_default.xml`,
/// `res/drawable/ripple_rounded_corners_red_24.xml`,
/// `res/drawable/ripple_rounded_corners_gray_24.xml`,
/// `PhotoMathButton.java` (jadx).
///
/// Спецификация оригинала:
///
/// * пилюля радиусом 24dip (не прямоугольник): enabled — `primary`
///   (`photomath_red` `#BF0C34`), disabled — `photomath_gray` (`#A6A7AA`);
/// * `setMinWidth(120dip)`, внешний `setPadding(16, 2, 16, 2)`;
/// * текст 16sp `textColorPrimaryInverse` (белый), отступы `10dip`
///   сверху/снизу/справа от иконки (`button_text` margins);
/// * зазор текст–иконка 10dip, иконка `next_white` (стрелка вправо);
/// * `rotateDrawable` при `view_rotation = 0` ничего не поворачивает;
/// * `elevation=4dip` задаётся в местах использования
///   (`fragment_editor`, `view_vertical_result_controls`);
/// * в отсутствии ввода кнопка `invisible` с `alpha=0` (место сохраняется).
library;

import 'package:flutter/material.dart';


/// Кнопка Photomath: красная пилюля с текстом и стрелкой.
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
    return Semantics(liveRegion: busy, child: FilledButton(
      onPressed: enabled ? onPressed : null,
      child: Padding(padding: const EdgeInsets.symmetric(vertical: 12), child: Row(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (busy) const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2)),
          if (busy) const SizedBox(width: 12),
          Flexible(child: Text(label, textAlign: TextAlign.center)),
          if (!busy) ...[const SizedBox(width: 12), const Icon(Icons.arrow_forward, size: 20)],
        ],
      )),
    ));
  }
}
