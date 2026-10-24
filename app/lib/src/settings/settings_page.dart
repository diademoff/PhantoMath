/// Экран настроек: десятичный разделитель, нотация биномиального
/// коэффициента, предпочитаемые методы умножения и деления.
library;

import 'package:flutter/material.dart';

import '../i18n.dart';
import 'settings.dart';

/// Экран настроек.
class SettingsPage extends StatelessWidget {
  const SettingsPage({
    super.key,
    required this.settings,
    this.onTheory,
    this.onHelp,
  });

  final AppSettings settings;

  /// Справочник теории и «Как пользоваться» (бывшие пункты боковой шторки).
  final VoidCallback? onTheory;
  final VoidCallback? onHelp;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: settings,
      builder: (context, _) => Scaffold(
        appBar: AppBar(title: Text(tr('Настройки', 'Settings'))),
        body: ListView(
          children: [
            _section(tr('Язык', 'Language')),
            RadioGroup<String>(
              groupValue: settings.locale,
              onChanged: (value) {
                if (value != null) settings.locale = value;
              },
              child: Column(
                children: [
                  RadioListTile<String>(
                    key: const ValueKey('locale:ru'),
                    title: Text('Русский'),
                    value: 'ru',
                  ),
                  const RadioListTile<String>(
                    key: ValueKey('locale:en'),
                    title: Text('English'),
                    value: 'en',
                  ),
                ],
              ),
            ),
            const Divider(),
            _section(tr('Десятичный знак', 'Decimal mark')),
            _hint(
              tr(
                'Влияет на то, как показываются и читаются числа.',
                'Affects how numbers are shown and read.',
              ),
            ),
            RadioGroup<DecimalSeparator>(
              groupValue: settings.decimalSeparator,
              onChanged: (value) {
                if (value != null) settings.decimalSeparator = value;
              },
              child: Column(
                children: [
                  for (final value in DecimalSeparator.values)
                    RadioListTile<DecimalSeparator>(
                      key: ValueKey('decimal:${value.id}'),
                      title: Text(
                        value == DecimalSeparator.point
                            ? tr('Точка (.)', 'Dot (.)')
                            : tr('Запятая (,)', 'Comma (,)'),
                      ),
                      value: value,
                    ),
                ],
              ),
            ),
            const Divider(),
            _section(tr('Биномиальный коэффициент', 'Binomial coefficient')),
            _hint(
              tr(
                'Как записывать биномиальный коэффициент.',
                'How to write the binomial coefficient.',
              ),
            ),
            RadioGroup<BinomialNotation>(
              groupValue: settings.binomialNotation,
              onChanged: (value) {
                if (value != null) settings.binomialNotation = value;
              },
              child: Column(
                children: [
                  for (final value in BinomialNotation.values)
                    RadioListTile<BinomialNotation>(
                      key: ValueKey('binomial:${value.id}'),
                      title: Text(
                        value == BinomialNotation.notationOne
                            ? tr(
                                'Этажная запись (n над k)',
                                'Stacked notation (n over k)',
                              )
                            : tr(
                                'Строчная запись C(n, k)',
                                'Inline notation C(n, k)',
                              ),
                      ),
                      value: value,
                    ),
                ],
              ),
            ),
            const Divider(),
            _section(tr('Метод умножения', 'Multiplication method')),
            _hint(
              tr(
                'Запись, которой предпочитаем умножать.',
                'The notation we prefer for multiplication.',
              ),
            ),
            RadioGroup<MultiplicationMethod>(
              groupValue: settings.multiplicationMethod,
              onChanged: (value) {
                if (value != null) settings.multiplicationMethod = value;
              },
              child: Column(
                children: [
                  for (final value in MultiplicationMethod.values)
                    RadioListTile<MultiplicationMethod>(
                      key: ValueKey('mul:${value.id}'),
                      title: Text(value.label),
                      value: value,
                    ),
                ],
              ),
            ),
            const Divider(),
            _section(tr('Метод деления', 'Division method')),
            _hint(
              tr(
                'Запись, которой предпочитаем делить.',
                'The notation we prefer for division.',
              ),
            ),
            RadioGroup<DivisionMethod>(
              groupValue: settings.divisionMethod,
              onChanged: (value) {
                if (value != null) settings.divisionMethod = value;
              },
              child: Column(
                children: [
                  for (final value in DivisionMethod.values)
                    RadioListTile<DivisionMethod>(
                      key: ValueKey('div:${value.id}'),
                      title: Text(value.label),
                      value: value,
                    ),
                ],
              ),
            ),
            const Divider(),
            _section(tr('Справка', 'Help')),
            if (onTheory case final open?)
              ListTile(
                leading: const Icon(Icons.lightbulb_outline),
                title: Text(tr('Теория', 'Theory')),
                subtitle: Text(
                  tr(
                    'правила и определения из решений',
                    'rules and definitions from solutions',
                  ),
                ),
                onTap: open,
              ),
            if (onHelp case final open?)
              ListTile(
                leading: const Icon(Icons.help_outline),
                title: Text(tr('Как пользоваться', 'How to use')),
                onTap: open,
              ),
            ListTile(
              leading: const Icon(Icons.info_outline),
              title: Text(tr('О приложении', 'About the app')),
              onTap: () => showAboutDialog(
                context: context,
                applicationName: 'PhantoMath',
                applicationLegalese: tr(
                  'Решает задачи по шагам и объясняет каждый шаг.',
                  'Solves problems step by step and explains each step.',
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _section(String title) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
    child: Text(title, style: const TextStyle(fontWeight: FontWeight.bold)),
  );

  Widget _hint(String text) => Padding(
    padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
    child: Text(text, style: const TextStyle(fontSize: 14, height: 1.4)),
  );
}
