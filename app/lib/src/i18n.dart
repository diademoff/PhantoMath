/// Язык интерфейса. Один переключатель на всё: тот же `AppSettings.locale`,
/// что выбирает язык пояснений решателя (`ru` или `en`).
String appLocale = 'ru';

/// Строка на текущем языке: `tr('Решить', 'Solve')`.
String tr(String ru, String en) => appLocale == 'en' ? en : ru;
