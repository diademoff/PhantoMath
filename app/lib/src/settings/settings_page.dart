/// Экран настроек: десятичный разделитель, нотация биномиального
/// коэффициента, предпочитаемые методы умножения и деления.
///
/// Повторяет разделы профиля Photomath (`UserProfile*Activity`): в оригинале
/// они лежат в профиле пользователя, у нас — на отдельном экране. Значения —
/// из `DecimalSeparator`, `BinomialType`, `MUL_*`, `DIV_*`.
library;

import 'package:flutter/material.dart';

import 'settings.dart';

/// Экран настроек.
class SettingsPage extends StatelessWidget {
  const SettingsPage({super.key, required this.settings});

  final AppSettings settings;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: settings,
      builder: (context, _) => Scaffold(
        appBar: AppBar(title: const Text('Настройки')),
        body: ListView(
          children: [
            _section('Десятичный знак'),
            _hint('Влияет на то, как показываются и читаются числа.'),
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
                            ? 'Точка (.)'
                            : 'Запятая (,)',
                      ),
                      value: value,
                    ),
                ],
              ),
            ),
            const Divider(),
            _section('Биномиальный коэффициент'),
            _hint('Как записывать биномиальный коэффициент.'),
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
                            ? 'Этажная запись (n над k)'
                            : 'Строчная запись C(n, k)',
                      ),
                      value: value,
                    ),
                ],
              ),
            ),
            const Divider(),
            _section('Метод умножения'),
            _hint('Запись, которой предпочитаем умножать.'),
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
            _section('Метод деления'),
            _hint('Запись, которой предпочитаем делить.'),
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
