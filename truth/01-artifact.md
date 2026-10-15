# 01. Факты об артефакте

## Идентификация

| Поле | Значение | Источник |
|---|---|---|
| Файл | `.truth/Photomath Plus v7.10.0 arm7.apk` | — |
| SHA-256 | `64c633bb7598a095b033d1f1c658a1514a1c378232988e8f2b0fd161301e1bfd` | `sha256sum`, REA `open_binary` |
| Размер | 16 967 189 байт | `ls` |
| Package | `com.microblink.photomath` | манифест |
| versionName / versionCode | `7.10.0` / `70000634` | `apktool.yml` |
| minSdk / targetSdk | 21 / 30 | `apktool.yml` |
| compileSdk | 30 (Android 11) | манифест `compileSdkVersion` |
| label | `Photomath` | манифест |
| Подпись | `META-INF/ALEX.SF` + `ALEX.RSA` | архив |
| Формат | APK (ZIP), 1259 записей | REA `inspect_artifact` |

**Наблюдение:** подпись `ALEX.*` — не Google Play. Это пересобранный/модифицированный
APK, а не официальная раздача Photomath. В `res/raw/paywall_video.mp4` лежит
недекодируемый apktool бинарник, которого нет в официальных сборках. Для нашей
задачи это неважно — мы воспроизводим поведение, а не дистрибуцию.

## REA Evidence

| Evidence ID | Операция | Что даёт |
|---|---|---|
| `ev_f65d08a78d2574544eec1b3c448bded790535a9061b9205048e4ef59c507bbcf` | `inspect_artifact` | полный граф архива |
| `ev_be7c148ff9101003c7c2e3f4638fc5634de4f657d8de52708195a156f1f12ca9` | inventory | 1237 узлов, 1260 вхождений, 1259 рёбер, **0 противоречий целостности** |
| `ev_9740cbe0dbc0cc2d222974a8ffb082c0b08ce9e8226f30e7d8ff2e89696fd763` | `inspect_analysis_view` (summary) | сводка |

Ограничения REA, зафиксированные в ответе:
- ZIP-инвентарь перечисляет только записи центрального каталога; байты вне записей
  (APK Signing Block, ZIP comment) не учтены.
- `signature_verification: not_performed` — подпись не проверялась.

Android-семейство REA (`inspect_android_package`, `search_android_classes`,
`inspect_android_class/method`, `trace_android_references`) **недоступно без
`REA_JADX_MCP_JAR`**; см. статус в `00-INDEX.md`.

## Состав архива

```
classes.dex                                  6.2 MB   весь Java/Kotlin код (один dex)
lib/armeabi-v7a/libPhotoMath.so              52 KB    JNI-мост к решателю
lib/armeabi-v7a/libPhotoMathDist.so          9.8 MB   сам решатель/движок
lib/armeabi-v7a/libpruneau.so                140 KB   Snap SDK, НЕ наше
assets/resources/model.json                  1.8 MB   визуальный скрипт анимаций
assets/resources/NodeRuntime.js              308 KB   JS-рантайм
assets/keys.txt                              76 KB    манифест ключей объяснений (3020)
assets/resources/*.rtttl                     4.6 MB   5 зашифрованных ML-моделей
assets/fonts/Roboto-{Regular,Medium,Bold}.ttf
resources.arsc                               3.2 MB   таблица ресурсов
res/                                         ~1000 XML — layouts, anims, styles
```

Архитектуры: `armeabi-v7a` (arm7) только. 64-битных и x86 ABI нет — это
существенно для выбора модели исполнения при реверсе.

## `.rtttl` — что это

Расширение нестандартное. Первые 16 байт каждого файла — высокоэнтропийные,
никакой магии (не TFLite `20 03 18 00`, не gzip `1f 8b`):

| Файл | Размер | Назначение |
|---|---|---|
| `Photomath_Ocr_general_6.2.0.rtttl` | 3.0 MB | OCR |
| `Photomath_BookpointOcr_production_5.0.7.rtttl` | 1.4 MB | OCR для учебника |
| `Photomath_Blur_general_13.0.1.rtttl` | 68 KB | детектор размытия |
| `Photomath_Filter_general_5.0.3.rtttl` | 76 KB | фильтр кадра |
| `Photomath_FontSizeEstimator_general_3.0.4.rtttl` | 8 KB | оценка кегля |

Это **зашифрованные** TensorFlow Lite-модели (ключ/расшифровка — в native).
Все пять обслуживают только камеру. По решению пользователя камера вне scope,
**модели не нужны**.

## `assets/keys.txt`

3020 строк вида `<ключ>;<арность>`. Арность = число `CoreRichText.args`,
то есть максимальный индекс `ARGn` в шаблоне (проверено: **0 расхождений**).

```
trig_angle_using_trig_table;0
trig_arcus;1
animation_algtiles_left_filled_red;2
```

Это **не** словарь локализации, а манифест грамматики объяснений: какие
сообщения решатель вправе породить и сколько у них аргументов. См. `04`.

## Инструменты разбора

Скачано в `~/tools/` (через локальный прокси `http://127.0.0.1:2080`):

| Инструмент | Версия | Путь | sha256 |
|---|---|---|---|
| jadx-headless-mcp (all-JAR) | 0.7.1 | `~/tools/rea-jadx/jadx-headless-mcp-0.7.1-all.jar` | `6e5eacf5…ff75` ✔ совпал с `.sha256` |
| jadx CLI | 1.5.6 | `~/tools/jadx-1.5.6/bin/jadx` | — |
| apktool | 2.11.1 | `~/tools/apktool.jar` | — |

Хост: OpenJDK 25.0.4.1, Linux.

Артефакты разбора лежат в `/tmp/opencode/mymath/`:
`apktool_out/` (манифест + smali + res), `jadx_out/` (Java),
`resources.json` (полная таблица ресурсов), `arsc_*.py` (скрипты).

JADX: 9304 smali-классов, 3460 для декомпиляции, **27 ошибок** из 3460 (0.8%) —
приемлемо. Пакет приложения `com.microblink.photomath` не обфусцирован
(510 классов с читаемыми именами); обфусцированы только сторонние библиотеки.

## Разрешения и компоненты

Разрешения: `CAMERA`, `VIBRATE`, `INTERNET`, `ACCESS_NETWORK_STATE`,
`WAKE_LOCK`, `FOREGROUND_SERVICE`, C2DM receive, install-referrer.

Ключевые Activity (для нас релевантны выделенные):

| Activity | Роль | Нужна? |
|---|---|---|
| `main.activity.LauncherActivity` | launcher, инициализация `CoreEngine` | аналог старта |
| `main.activity.MainActivity` | хост | ✔ |
| `editor.EditorActivity` / `EditorFragment` | **ручной ввод уравнения** | ✔ **ядро ввода** |
| `editor.keyboard.view.*` (10 кл.) | кастомная клавиатура | ✔ |
| `editor.preview.view.EditorView` | рендер ввода | ✔ |
| `resultvertical.VerticalResultActivity` | **пошаговый список** | ✔ **ядро вывода** |
| `resultanimation.AnimationResultActivity` | анимационное объяснение | ✔ |
| `graph.GraphActivity` | графики | ✔ (средний приоритет) |
| `notebook.NotebookActivity` | блокнот | опционально |
| `camera.*` (19 кл.) | камера/OCR | ✘ **вне scope** |
| `bookpoint.*`, `bookpointhomescreen.*` (103 кл.) | учебник/поиск по книгам | ✘ вне scope |
| `subscription.*` (20 кл.) | paywall/подписка | ✘ вне scope |
| `professor.*` (52 кл.) | «Professor» | ✘ вне scope |
| `authentication.*` (47 кл.) | логин/регистрация | ✘ вне scope |

`network_security_config.xml` разрешает cleartext только для `127.0.0.1`.

`com.microblink.photomath.api_key` в манифесте — 512-символьный ключ,
используется для bookpoint API. Нам не нужен.

## Что НЕ является Photomath-специфичным

Firebase (messaging/perf/analytics/remoteconfig/inappmessaging),
Facebook SDK, Snap Kit, Glide/Picasso, OkHttp, Coroutines, Material.
Итого ~8800 классов из 9304 — это библиотеки. Наш код — 510 классов.