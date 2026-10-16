/// Экран вертикального результата — `res/layout/view_vertical_result_layout.xml`,
/// `item_vertical_result_solution.xml` и `item_vertical_result_step.xml`,
/// перенесены 1 в 1.
///
/// Что взято из раскладок оригинала:
///
/// | элемент            | атрибут/ресурс оригинала                     | здесь            |
/// |--------------------|----------------------------------------------|------------------|
/// | заголовок «Решение»| 18sp, bold, `photomath_red`, `marginTop=16`, `marginStart=16` | `_SolutionHeader`|
/// | полоса слева       | 6dip, `photomath_red`, на всю высоту блока   | `accentBarWidth` |
/// | формула решения    | 28sp, bold, операторы `textColorTertiary`, `marginTop=8`, `marginStart=16`, `marginEnd=52`, `paddingBottom=16` | `_SolutionHeader`|
/// | «Альт. форма» (результат) | 14sp, `photomath_red`, `marginStart=16` | `_SolutionHeader`|
/// | альт. формула (результат) | `textColorPrimary`, `marginTop=3`, `marginBottom=16`, `marginStart=16` | `_SolutionHeader`|
/// | формула шага       | `EquationViewGroup`, `marginTop=16`, `marginBottom=16`, `marginStart=16`, `showPreview` | `_Step` |
/// | пояснение шага     | 16sp, `textColorTertiary` (`#ABABAB`), `marginTop=8`, `marginBottom=16`, `marginStart=16`, `marginEnd=10` | `_Step` |
/// | стрелка разворота   | `steps_down`, `marginTop=16`, `marginEnd=21` | `_Chevron` |
/// | разделитель         | 1dip, `colorSurface` (`#F5F5F5`), `marginTop=16`, `marginStart/End=16` | `_StepDivider` |
/// | нижний отступ       | `bottom_margin_dummy_view`, высота 18dip    | `_Step` |
/// | подсветка нажатия   | `verticalResultOverlayColor` (`#95EAEAEA`)   | тема `resultOverlay` |
///
/// Заголовок групп — `CoreSolverVerticalResult.title`/`headers`
/// контракта; переключатель способов решения в оригинале показан
/// строкой «Альтернативная форма», поэтому он здесь на её месте.
library;

import 'package:flutter/material.dart';
import 'package:flutter_math_fork/flutter_math.dart';

import '../api/solver_api.dart';
import '../render/latex.dart';
import '../theme/photomath_theme.dart';

/// Вертикальный результат: группы шагов, ответ и пояснения.
class VerticalResult extends StatelessWidget {
  const VerticalResult({
    super.key,
    required this.result,
    required this.latexOptions,
    required this.onLink,
    required this.onCopy,
    this.methodSwitcher,
    this.onBack,
  });

  final SolveResponse result;

  /// Разделитель и нотация из профиля (`DecimalSeparator`, `BinomialType`).
  final LatexOptions latexOptions;

  /// Нажатие на ссылку в пояснении.
  final void Function(ExplanationLink link) onLink;

  /// Копирование формулы шага.
  final void Function(String latex) onCopy;

  /// Переключатель способов решения, если их несколько.
  final Widget? methodSwitcher;

  /// Возврат к вводу (`@id/back` в `view_vertical_result_controls`).
  final VoidCallback? onBack;

  @override
  Widget build(BuildContext context) {
    return ListView(
      // `@id/steps_container` — `paddingBottom=20dip`.
      padding: const EdgeInsets.only(bottom: 20),
      children: [
        ?methodSwitcher,
        for (final group in result.steps) ...[
          if (group.headers.isNotEmpty) _GroupHeader(headers: group.headers),
          for (final substep in group.substeps)
            _Step(
              substep: substep,
              latexOptions: latexOptions,
              onLink: onLink,
              onCopy: onCopy,
            ),
        ],
        if (result.solution != null)
          _SolutionHeader(
            latex: nodeToLatex(result.solution!, latexOptions),
            onCopy: onCopy,
          ),
      ],
    );
  }
}

/// Заголовок группы шагов — `CoreSolverVerticalResult.headers`.
///
/// В оригинале у вертикальной ветки есть заголовок «Решение» красным
/// 18sp; у вложенных групп заголовков нет, поэтому здесь он выводится
/// только у первой группы верхнего уровня.
class _GroupHeader extends StatelessWidget {
  const _GroupHeader({required this.headers});

  final List<String> headers;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(
        top: PhGap.blockTop,
        left: PhGap.stepSide,
        right: PhGap.stepSide,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (final header in headers)
            Text(
              header,
              style: const TextStyle(
                fontSize: 18,
                fontWeight: FontWeight.bold,
                color: PhColor.red,
                height: 1.2,
              ),
            ),
        ],
      ),
    );
  }
}

/// Блок «Решение»: полоса слева, заголовок, формула ответа.
///
/// `item_vertical_result_solution.xml`: заголовок `marginTop=16`,
/// `marginStart=16`; формула `marginTop=8`, `marginStart=16`,
/// `marginEnd=52` (место под `close_button`), `paddingBottom=16`.
class _SolutionHeader extends StatelessWidget {
  const _SolutionHeader({required this.latex, required this.onCopy});

  final String latex;
  final void Function(String latex) onCopy;

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const ColoredBox(
            color: PhColor.red,
            child: SizedBox(width: PhSize.accentBarWidth),
          ),
          Expanded(
            child: Padding(
              padding: const EdgeInsets.only(top: PhGap.blockTop),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(left: PhGap.stepSide),
                    child: Text(
                      PhString.solution,
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.bold,
                        color: PhColor.red,
                        height: 1.2,
                      ),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Padding(
                    // Формула: отступы оригинала, справа 52dip под кнопку
                    // закрытия; снизу 16dip.
                    padding: const EdgeInsets.only(
                      left: PhGap.stepSide,
                      right: 52,
                      bottom: PhGap.stepBottom,
                    ),
                    child: _Equation(
                      latex: latex,
                      fontSize: 28,
                      bold: true,
                      trailing: IconButton(
                        tooltip: 'Копировать ответ',
                        visualDensity: VisualDensity.compact,
                        icon: const Icon(Icons.copy_outlined, size: 18),
                        color: PhColor.grayLight,
                        onPressed: () => onCopy(latex),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}

/// Один подшаг — `item_vertical_result_step.xml`.
///
/// Слева формула «было», под ней пояснение серым, справа стрелка разворота;
/// раскрытый шаг показывает формулу «стало» и вложенные подшаги.
class _Step extends StatelessWidget {
  const _Step({
    required this.substep,
    required this.latexOptions,
    required this.onLink,
    required this.onCopy,
  });

  final Substep substep;
  final LatexOptions latexOptions;
  final void Function(ExplanationLink link) onLink;
  final void Function(String latex) onCopy;

  @override
  Widget build(BuildContext context) {
    final left = substep.left;
    final right = substep.right;
    final detail = substep.detail;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        ExpansionTile(
      // `@id/left_equation` — формула «было»: `marginTop=16`,
      // `marginBottom=16`, `marginStart=16`.
      tilePadding: const EdgeInsets.only(
        left: PhGap.stepSide,
        // `@id/expand_button`: `marginEnd=21dip`.
        right: 21,
        top: PhGap.stepBottom,
      ),
      childrenPadding: const EdgeInsets.only(left: PhGap.stepSide),
      // Своя стрелка `@id/expand_button` (вместо стандартной) приходит
      // через `trailing`. `trailing` рисуется только при
      // `showTrailingIcon: true` — при `false` `ExpansionTile` отбрасывает
      // его целиком, и шаг разворачивался тапом по строке без стрелки.
      // `@id/collapsed_description`: пояснение серым под формулой —
      // `marginTop=8`, `marginBottom=16`, `marginStart=16`, `marginEnd=10`.
      subtitle: substep.text == null || substep.text!.isEmpty
          ? null
          : Padding(
              padding: const EdgeInsets.only(
                top: PhGap.stepDescriptionTop,
                bottom: PhGap.stepBottom,
                right: 10,
              ),
              child: ExplanationText(
                text: substep.text!,
                links: substep.links,
                onLink: onLink,
              ),
            ),
      // `@id/expand_button`: `steps_down`, отступ справа 21dip.
      trailing: const _Chevron(),
      iconColor: PhColor.grayLight,
      collapsedIconColor: PhColor.grayLight,
      expandedAlignment: Alignment.centerLeft,
      backgroundColor: Colors.transparent,
      title: Padding(
        // Нижний отступ формулы 16dip (`marginBottom` левого уравнения).
        padding: const EdgeInsets.only(bottom: PhGap.stepBottom),
        child: Row(
        children: [
          if (left != null)
            Expanded(
              child: _Equation(
                latex: nodeToLatex(left, latexOptions),
                fontSize: 20,
                trailing: IconButton(
                  tooltip: 'Копировать шаг',
                  visualDensity: VisualDensity.compact,
                  icon: const Icon(Icons.copy_outlined, size: 18),
                  color: PhColor.grayLight,
                  onPressed: () => onCopy(nodeToLatex(left, latexOptions)),
                ),
              ),
            )
          else
            const Spacer(),
        ],
        ),
      ),
      children: [
        Padding(
          padding: const EdgeInsets.only(bottom: PhGap.stepBottom),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // `@id/right_equation`: формула «стало» в раскрытом шаге.
              if (right != null)
                _Equation(
                  latex: nodeToLatex(right, latexOptions),
                  fontSize: 20,
                ),
              for (final group in detail) ...[
                if (group.headers.isNotEmpty)
                  _GroupHeader(headers: group.headers),
                for (final nested in group.substeps)
                  _Step(
                    substep: nested,
                    latexOptions: latexOptions,
                    onLink: onLink,
                    onCopy: onCopy,
                  ),
              ],
            ],
          ),
        ),
      ],
        ),
        // `@id/bottom_divider`: 1dip, `colorSurface`, поля 16dip,
        // верхний отступ 16dip.
        const _StepDivider(),
        // `@id/bottom_margin_dummy_view`: высота 18dip.
        const SizedBox(height: 18),
      ],
    );
  }
}

/// Разделитель под шагом — `@id/bottom_divider` из
/// `item_vertical_result_step.xml`.
class _StepDivider extends StatelessWidget {
  const _StepDivider();

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 1,
      margin: const EdgeInsets.only(
        top: PhGap.stepBottom,
        left: PhGap.stepSide,
        right: PhGap.stepSide,
      ),
      color: PhColor.surface,
    );
  }
}

/// Стрелка разворота шага — `@id/expand_button` со `steps_down`.
class _Chevron extends StatelessWidget {
  const _Chevron();

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: PhSize.stepsArrowWidth,
      height: PhSize.stepsArrowWidth,
      child: Icon(
        Icons.keyboard_arrow_down,
        size: PhSize.stepsArrowWidth,
        color: PhColor.grayLight,
      ),
    );
  }
}

/// Формула шага: `EquationView` оригинала.
class _Equation extends StatelessWidget {
  const _Equation({
    required this.latex,
    required this.fontSize,
    this.bold = false,
    this.trailing,
  });

  final String latex;
  final double fontSize;
  final bool bold;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    if (latex.isEmpty) return const SizedBox.shrink();
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Math.tex(
            latex,
            mathStyle: MathStyle.display,
            textStyle: TextStyle(
              fontSize: fontSize,
              fontWeight: bold ? FontWeight.bold : FontWeight.normal,
              color: PhColor.grayDark,
            ),
            onErrorFallback: (error) => Text(
              latex,
              style: TextStyle(fontSize: fontSize, color: PhColor.error),
            ),
          ),
        ),
        ?trailing,
      ],
    );
  }
}

/// Пояснение со ссылками — порт `MathTextView` с разметкой `[label|uuid]`.
///
/// Ссылки приходят метками: текст уже содержит их, поэтому метки отыскиваются
/// в строке по порядку следования и становятся нажимаемыми.
///
/// Нажимаемой становится только та ссылка, у которой есть определение в
/// глоссарии: без него тап вёл в тупик «пояснение понятия появится позже»
/// (в английской локали таких ссылок 266 из 327). Метка при этом остаётся в
/// тексте дословно, меняется только её вид.
class ExplanationText extends StatelessWidget {
  const ExplanationText({
    super.key,
    required this.text,
    required this.links,
    required this.onLink,
  });

  final String text;
  final List<ExplanationLink> links;
  final void Function(ExplanationLink link) onLink;

  @override
  Widget build(BuildContext context) {
    final linkStyle = TextStyle(
      fontSize: 16,
      color: PhColor.red,
      decoration: TextDecoration.underline,
    );
    final spans = <InlineSpan>[];
    var cursor = 0;
    for (final link in links) {
      if (link.definition.isEmpty) continue;
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
    return Text.rich(
      TextSpan(children: spans),
      // `@id/collapsed_description`: 16sp, `textColorTertiary`.
      style: const TextStyle(
        fontSize: 16,
        color: PhColor.grayLight,
        height: 1.35,
      ),
    );
  }
}
