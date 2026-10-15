# 02. Архитектура

## Главное

Приложение — **тонкая оболочка над нативным движком**. Вся математика в
`libPhotoMathDist.so` (9.8 MB, arm32). Java-слой:

1. рисует интерфейс (Android Views, Material),
2. сериализует ввод в строку,
3. зовёт JNI,
4. получает JSON,
5. десериализует в `CoreSolverData` через Gson,
6. рисует результат.

Это **идеальная граница для нашей переписки**: контракт между Java и native —
JSON. Нам нужно реализовать ровно этот JSON с другой стороны.

## Слои

```
┌───────────────────────────────────────────────────────────────┐
│ UI (Android Views)                                            │
│  resultvertical · resultanimation · graph · editor · notebook │
├───────────────────────────────────────────────────────────────┤
│ Модель данных  com.microblink.photomath.core.results          │
│  CoreResult → CoreSolverData → CoreSolverResult → groups[]   │
│  ветки: vertical/ · animation/ · graph/                        │
├───────────────────────────────────────────────────────────────┤
│ CoreEngine (JNI)  libPhotoMath.so (52 KB)                      │
│  nativeProcessExpression / nativeProcessFrame /                │
│  nativeCommandToNodeActionJson / nativeExtractSolve           │
├───────────────────────────────────────────────────────────────┤
│ Движок  libPhotoMathDist.so (9.8 MB)                          │
│  решатель · OCR (TFLite, модели .rtttl) · визуальный скрипт    │
├───────────────────────────────────────────────────────────────┤
│ Ассеты                                                            │
│  model.json (51 визуальный поток) · keys.txt (3020 ключей)     │
│  NodeRuntime.js · *.rtttl (шифрованные модели)                │
└───────────────────────────────────────────────────────────────┘
```

## Карта пакетов приложения

`com/microblink/photomath/` — 510 классов (не обфусцированы):

| Пакет | Классов | Назначение |
|---|---|---|
| `core` | 103 | модель результата, рендер, анимации, графы |
| `bookpoint` | 73 | распознавание задач из учебника (вне scope) |
| `professor` | 52 | режим «Professor» (вне scope) |
| `authentication` | 47 | логин/профиль (вне scope) |
| `common` | 38 | `PhotoMathResult`, `MathTextView`, метаданные |
| `bookpointhomescreen` | 30 | (вне scope) |
| `subscription` | 20 | paywall (вне scope) |
| `solution` | 20 | рендер «SolutionView» |
| `resultvertical` | 19 | пошаговый список |
| `camera` | 19 | камера/OCR (вне scope) |
| `manager` | 15 | логи, sharing, firebase |
| `editor` | 15 | ввод + клавиатура |
| `resultanimation` | 12 | анимации |
| `graph` | 11 | графики |
| `notebook` | 9 | блокнот |
| `main` | 9 | Launcher/Main |
| `howtouse`, `feedback`, `about`, `intro`, `help` | 17 | экраны |

## Поток данных (ввод → результат)

Найдено в `c/a/a/w/s/a.java`:

```java
public final class a {                       // UseCase: SolveExpression
    boolean b()  { return remoteConfig.isCloudSolverEnabled(); }

    Object c(String expressionString, Callback<CoreResult> cb) {
        if (b()) {                          // CLOUD_SOLVER
            InternalCoreInput in = coreEngine.a(str);       // command -> {node, action}
            pwsapi.h(in, ...);                              // POST на сервер Photomath
        } else {                            // LOCAL_SOLVER  ← наш случай
            coreEngine.c(str, result -> ...);
        }
    }
}
```

Два режима, переключаются Firebase Remote Config:

| Режим | Путь | Нам нужен |
|---|---|---|
| `LOCAL_SOLVER` | `CoreEngine.nativeProcessExpression(ctx, str)` → JSON | **да** |
| `CLOUD_SOLVER` | `CoreEngine.nativeCommandToNodeActionJson(ctx, str)` → `InternalCoreInput` → `PWSAPI.h(...)` | нет |

Для переписки берём **LOCAL_SOLVER**: он офлайн и детерминирован.

## Инициализация

`main/activity/LauncherActivity.java:340-370`:

```java
Log.d("STARTUP_INITIALIZATION", "Initializing CoreEngine");
CoreEngine.b();                                   // System.loadLibrary("PhotoMath")
if (!CoreEngine.nativeIsProcessorSupported()) { ... }
coreEngine2.g = CoreEngine.nativeInitialize(appContext);   // → long handle
```

Версии движка доступны через `nativeGetSolverVersion()` / `nativeGetOcrVersion()`
и показываются в экране «About».

Вся работа идёт на `HandlerThread("Processing")`; результат доставляется на
главный поток. В Python это не релевантно.

## Граница, которую мы пересекаем

Мы **не** переносим:
- `.rtttl` модели и OCR (камера вне scope),
- `libPhotoMathDist.so` целиком (это и есть то, что заменяем),
- bookpoint / professor / subscription / auth.

Мы **переносим**:
- формат AST (`CoreNode` / `CoreNodeType`) → наш тип выражения,
- формат шагов (`CoreSolverVerticalStep/Substep`) → наш результат,
- базу объяснений (3252 шаблона × 9 языков) → наш словарь,
- рендер → Flutter.

Подробности контракта — `03-solver-contract.md`.