# 07. Открытые вопросы

Что не удалось установить статическим анализом и как это проверить.

## Q1. ~~Формат входной строки решателя~~ — **ЗАКРЫТ**

Восстановлен: S-выражение в фигурных скобках, словарь из 156 ключевых слов,
подтверждён таблицей литералов нативного парсера в `libPhotoMathDist.so`.
Полностью — в `08-input-protocol.md`, данные в `truth/data/input-protocol.json`.

Осталось уточнить: точная грамматика (BNF), кодировка текстовых аргументов,
поведение при ошибке разбора.

## Q2. Связь `CoreAnimationCommandResult.command` ↔ id в model.json

`command` — строка (`"ADD"`, …), а `model.json` озаглавливает потоки **id**
(`16`, `67`, `100`, …). Прямого отображения не найдено.

Гипотезы: `CoreAnimationResultType` (`ADD`…) → свой id; либо потоки
адресуются через `name`. Не проверено.

**Влияние:** только на вариант C (полный паритет анимаций). Не блокирует MVP.

## Q3. 232 ключа в arsc, которых нет в keys.txt

Все с префиксами `animation2_` / `add_rotation`. Похоже на описания
анимационных команд (тот слой, что Q2). Не критично.

## Q4. Расшифровка `.rtttl`

Модели зашифрованы; ключ в `libPhotoMathDist.so`. **Не нужно** — камера вне
scope. Отмечено, чтобы не тратить время.

## Q5. `CoreGraphResult` не разобран

Структура снята (см. `03.7`), но семантика `CoreGraphAxis`,
`CoreGraphPlotCurve`, `CoreGraphInfo`, `CoreGraphElementAnnotation` не
изучена. **Решение:** отложить, использовать `flutter_math`.

## Q6. Полиморфизм внутри `CoreColoredNode` / `CoreNode`

Адаптеры `CoreNodeDeserializer` и `CoreColoredNodeDeserializer` есть, но
признак различения в JSON не читается напрямую из декомпиляции.
Вероятно, по наличию полей `color`/`crossed`.

**Проверить:** нужен один реальный пример ответа решателя. Получить можно
только на устройстве (или эмуляторе) — см. ниже.

## Q7. Как получить эталонные ответы решателя

Для верификации нужны реальные выходы `nativeProcessExpression`. Варианты:

1. **Установить APK на эмулятор/устройство** и снять вывод через Frida
   (перехват `nativeProcessExpression` / парсинг логов).
   REA умеет `install_adb_package` и `resume_frida_session`.
   Риск: arm7-only ABI → нужен x86-эмулятор с ARM-транслятором или
   arm64-устройство. Неизвестно, работает ли.
2. **Ответить на задачи в приложении вручную** и записать вывод.
   Медленно, но надёжно.
3. **Реконструировать из arsc**: у нас есть все ключи и их арность, но нет
   самих задач.

Рекомендация: вариант 2 для корпуса из 50-100 задач (основные модули),
далее вариант 1 если нужен массовый сбор.

## Q8. Точность `normalizedInputNodeStr`

Строка канонизированного ввода. Формат неизвестен. Нужна только для
отображения «как Photomath понял ваш ввод» — косметика.

## Q9. Поведение при ошибках

`CoreAnimationCommandResult.error` — строка. `CoreResult` может иметь
`coreSolverData == null` (см. `CoreEngine.c`: результат null → колбэк с null).
Наш бэкенд должен повторить: не смог разобрать/решить → понятная ошибка,
а не 500.

## Что НЕ является открытым (закрыто)

- ✅ Структура ответа решателя — полностью
- ✅ Модель AST — полностью (143 типа)
- ✅ Модель шагов — полностью
- ✅ Словарь объяснений — 3252 ключа × 9 языков, с валидацией арности
- ✅ Набор клавиш редактора — 128 операторов
- ✅ Состав пакета APK — 510 классов приложения
- ✅ Разрешения, компоненты, SDK-версии

## Где смотреть при продолжении

```
/tmp/opencode/mymath/jadx_out/sources/com/microblink/photomath/   Java
/tmp/opencode/mymath/jadx_out/sources/c/a/a/a/u/a/               сериализация ввода
/tmp/opencode/mymath/jadx_out/sources/c/a/a/a/t/a/c.java         enum операторов
/tmp/opencode/mymath/apktool_out/AndroidManifest.xml             манифест
/tmp/opencode/mymath/resources.json                              вся таблица ресурсов
/tmp/opencode/mymath/pools.json                                  строковые пулы arsc
/home/dmff/repos/mymath/truth/data/                               извлечённые данные
```

Если `/tmp` очищен — восстановить:
```bash
unzip -q -d /tmp/opencode/mymath/apk ".truth/Photomath Plus v7.10.0 arm7.apk"
java -jar ~/tools/apktool.jar d -f -o /tmp/opencode/mymath/apktool_out ".truth/…apk"
~/tools/jadx-1.5.6/bin/jadx --no-res -d /tmp/opencode/mymath/jadx_out ".truth/…apk"
python3 truth/data/arsc_resolve.py /tmp/opencode/mymath/apk/resources.arsc resources.json
```