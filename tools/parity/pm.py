"""Black-box crawler for the installed Photomath 7.10.0 (adb + uiautomator).

Types a task with the on-screen keyboard, walks the result cards and the step
lists, and maps every visible step text back to dictionary keys via the Russian
templates in truth/data/explanations.json.

  pm.py crawl TASK_ID "<keys>"      -> cap/TASK_ID.json (+ screenshots)

Keys: plain chars (0-9 x + - * / ( ) = , % ^ p), or <token>; see TOKENS.
"""
import json
import re
import sys
import time
from pathlib import Path

import ui

ROOT = Path(__file__).resolve().parents[2]
EXPL = ROOT / "truth" / "data" / "explanations.json"
CAP = ui.OUT

COLS6 = ui._COLS
ROWS = ui._ROWS
# page 2 (f ∫ <>), same grid as the main page
PAGE2 = {
    "lt": (0, 0), "gt": (1, 0), "fx": (2, 0), "sum": (3, 0), "mat": (4, 0), "log10": (5, 0),
    "int": (0, 1), "ddx": (1, 1), "inf": (2, 1), "i": (3, 1), "sin": (4, 1), "cos": (5, 1),
    "abs": (0, 2), "nPr": (1, 2), "e": (2, 2), "deg": (3, 2), "tan": (4, 2), "cot": (5, 2),
    "lim": (0, 3), "sub": (1, 3), "fact": (2, 3), "sign": (3, 3), "sec": (4, 3), "csc": (5, 3),
}
PAGE1 = {"frac": (0, 1), "sqrt": (1, 1), "sq": (0, 2), "pi": (0, 3)}
TOOLBAR_Y = 1486
FN_TAB_X, ABC_TAB_X = 91, 270
ARROW = {"L": 449, "R": 628, "E": 807, "B": 986}


def _tap(x: int, y: int) -> None:
    ui.adb("shell", "input", "tap", str(x), str(y))


def _page(which: str) -> None:
    """Switch keyboard page: 'main' (tap active tab again), 'fn', 'abc'."""
    _tap(FN_TAB_X if which == "fn" else ABC_TAB_X, TOOLBAR_Y)
    time.sleep(0.25)


def _key(grid: dict[str, tuple[int, int]], name: str) -> None:
    c, r = grid[name]
    _tap(COLS6[c], ROWS[r])


def type_task(keys: str) -> None:
    """Type a task. State: keyboard page is tracked so tokens can mix pages."""
    page = "main"
    for tok in re.findall(r"<[^>]+>|.", keys):
        name = tok[1:-1] if tok.startswith("<") else tok
        if name in ARROW:
            _tap(ARROW[name], TOOLBAR_Y)
            continue
        want, grid = "main", None
        if name in PAGE2:
            want, grid = "fn", PAGE2
        elif name in PAGE1:
            grid = PAGE1
        elif name.startswith("abc:"):
            want = "abc"
        if want != page:
            if page != "main":
                _page(page)  # toggle current tab off -> main
            if want != "main":
                _page(want)
            page = want
        if grid is not None:
            _key(grid, name)
        elif want == "abc":
            letter = name[4:]
            idx = ord(letter) - ord("a")
            _tap(67 + 135 * (idx % 8), ROWS[idx // 8])
        else:
            ch = {"p": "p"}.get(name, name)
            ui.type_keys(ch)
        time.sleep(0.12)
    if page != "main":
        _page(page)


# ---- reverse map: visible text -> dictionary keys -------------------------

def _tpl_regex(t: str) -> str:
    t = re.sub(r"\[([^|\]]*)\|[^\]]*\]", r"\1", t)
    parts = re.split(r"ARG\d+", t)
    return "^" + ".+?".join(re.escape(p.strip()) for p in parts) + "$"


def build_keymap() -> list[tuple[re.Pattern[str], str, int]]:
    d = json.loads(EXPL.read_text(encoding="utf-8"))
    out = []
    for k, v in d.items():
        t = v["templates"].get("ru")
        if t:
            out.append((re.compile(_tpl_regex(t), re.S), k, len(re.findall(r"ARG\d+", t))))
    # most specific (longest literal text, fewer wildcards) first
    out.sort(key=lambda r: (r[2], -len(r[0].pattern)))
    return out


def keys_for(text: str, kmap) -> list[str]:
    s = re.sub(r"\s+", " ", text).strip()
    return [k for rx, k, _ in kmap if rx.match(s)]


# ---- screen reading ----------------------------------------------------------

def texts(root, ids=("collapsed_description", "description", "card_title", "card_subtitle",
                     "title", "method_name", "button_text")) -> list[tuple[int, str, str]]:
    out = []
    for n, c, _ in ui.nodes(root):
        rid = n.get("resource-id", "").split("/")[-1]
        t = n.get("text")
        if t and rid in ids:
            out.append((c[1], rid, t))
    return sorted(out)


def swipe_up() -> None:
    ui.adb("shell", "input", "swipe", "540", "1700", "540", "900", "350")
    time.sleep(0.6)


def merge(acc: list, new: list) -> list:
    for k in range(min(len(acc), len(new)), -1, -1):
        if acc[len(acc) - k:] == new[:k]:
            return acc + new[k:]
    return acc + new


def collect_scroll(name: str, rid_filter, max_swipes: int = 6) -> list[str]:
    acc: list[str] = []
    for i in range(max_swipes):
        root = ui.dump(f"{name}_{i}")
        cur = [t for _, r, t in texts(root) if r in rid_filter]
        merged = merge(acc, cur)
        if merged == acc and i:
            break
        acc = merged
        swipe_up()
    return acc


def crawl(task_id: str, keys: str) -> dict:
    kmap = build_keymap()
    ui.adb("shell", "input", "tap", "1005", "367")  # clear
    time.sleep(0.5)
    type_task(keys)
    time.sleep(2.5)
    ui.OUT.mkdir(exist_ok=True)
    ui.adb("shell", "input", "tap", "628", "1312")  # dismiss tip if any
    root = ui.dump(f"{task_id}_input")
    sol = ui.find(root, "Показать решение")
    (CAP / f"{task_id}_input.png").write_bytes(ui.adb("exec-out", "screencap", "-p", binary=True))
    res: dict = {"id": task_id, "keys": keys, "cards": [], "steps": []}
    if sol is None:
        res["error"] = "no solution button"
        return res
    ui.adb("shell", "input", "tap", str(sol[0]), str(sol[1]))
    time.sleep(3)
    cards = collect_scroll(f"{task_id}_cards", {"card_title", "card_subtitle", "method_name"}, 3)
    res["cards"] = cards
    root = ui.dump(f"{task_id}_cardsroot")
    btn = ui.find(root, "Показать шаги по решению")
    if btn:
        ui.adb("shell", "input", "tap", str(btn[0]), str(btn[1]))
        time.sleep(3)
        (CAP / f"{task_id}_steps.png").write_bytes(
            ui.adb("exec-out", "screencap", "-p", binary=True))
        steps = collect_scroll(f"{task_id}_steps", {"collapsed_description", "title"}, 5)
        res["steps"] = [{"text": t, "keys": keys_for(t, kmap)} for t in steps]
    for _ in range(3):
        ui.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(0.7)
    (CAP / f"{task_id}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return res


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "crawl":
        print(json.dumps(crawl(sys.argv[2], sys.argv[3]), ensure_ascii=False, indent=1))
    else:
        sys.exit(__doc__)
