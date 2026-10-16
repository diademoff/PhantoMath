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

import '../theme/photomath_theme.dart';

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
    return Material(
      // `photomath_button_background_default`: красный / серый пилюли.
      color: enabled ? PhColor.red : PhColor.gray,
      elevation: 4,
      borderRadius: BorderRadius.circular(24),
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: busy ? null : onPressed,
        child: ConstrainedBox(
          // `setMinWidth(120dip)`.
          constraints: const BoxConstraints(minWidth: 120),
          child: Padding(
            // Внешний `setPadding(16, 2, 16, 2)` + внутренние отступы
            // текста `10dip` сверху/снизу.
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
            child: Padding(
              padding: const EdgeInsets.symmetric(vertical: 10),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    label,
                    style: const TextStyle(
                      // `button_text`: 16sp, белый.
                      fontSize: 16,
                      color: PhColor.white,
                    ),
                  ),
                  // Зазор текст–иконка 10dip (`layout_marginEnd` текста).
                  const SizedBox(width: 10),
                  if (busy)
                    const SizedBox(
                      width: 18,
                      height: 18,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: PhColor.white,
                      ),
                    )
                  else
                    // `next_white`: стрелка вправо, `view_rotation = 0`.
                    const Icon(
                      Icons.arrow_forward,
                      size: 20,
                      color: PhColor.white,
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}
