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
            if want != "main":
                page = "main"  # the keyboard returns to the main page by itself
        elif want == "abc":
            letter = name[4:]
            idx = ord(letter) - ord("a")
            _tap(67 + 135 * (idx % 8), ROWS[idx // 8])
            page = "main"
        else:
            ch = {"p": "p"}.get(name, name)
            ui.type_keys(ch)
        time.sleep(0.18)
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


def _text(root, rid: str) -> str:
    for n, _, _ in ui.nodes(root):
        if n.get("resource-id", "").endswith("/" + rid) and n.get("text"):
            return n.get("text")
    return ""


def _stage(name: str, root) -> dict:
    """Current stage: its description and the rows of its detail screen (if any)."""
    ids = ("/collapsed_description", "/description", "/title")
    st = {"text": _text(root, "description"), "nested": []}
    (CAP / f"{name}.png").write_bytes(ui.adb("exec-out", "screencap", "-p", binary=True))
    exp = ui.find(root, "id:substep_expand_button")
    if exp:
        ui.adb("shell", "input", "tap", str(exp[0]), str(exp[1]))
        time.sleep(2)
        nroot = ui.dump(f"{name}_d")
        st["nested"] = [n.get("text") for n, _, _ in ui.nodes(nroot)
                        if n.get("resource-id", "").endswith(ids) and n.get("text")]
        ui.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.2)
    return st


def _pages(root) -> int:
    """Pager pages of the expanded card: children of substep_bullets (1 if absent)."""
    for n in root.iter("node"):
        if n.get("resource-id", "").endswith("/substep_bullets"):
            return max(len(list(n)), 1)
    return 1


def walk(name: str) -> list[dict]:
    """Rows of the list = main steps; each row's card pages = stages.

    Row 0 is tapped, «Далее» then moves row by row; inside a row the arrow pages
    through the dots (substep_bullets). Every page may open a detail screen.
    """
    for _ in range(6):  # collect_scroll left the list scrolled down
        ui.adb("shell", "input", "swipe", "540", "700", "540", "1800", "250")
    time.sleep(0.5)
    rows = [c for n, c, _ in ui.nodes(ui.dump(f"{name}_top"))
            if n.get("resource-id", "").endswith("/collapsed_description")]
    if not rows:
        return []
    ui.adb("shell", "input", "tap", "540", str(rows[0][1] - 44))
    time.sleep(1.5)
    out = []
    for i in range(14):
        root = ui.dump(f"{name}_g{i}")
        if i:
            nxt = ui.find(root, "id:next")
            if not nxt:
                break
            ui.adb("shell", "input", "tap", str(nxt[0]), str(nxt[1]))
            time.sleep(1.5)
            root = ui.dump(f"{name}_g{i}")
        pages = _pages(root)
        stages = [_stage(f"{name}_{i}", root)]
        for k in range(pages - 1):
            nxt = ui.find(ui.dump(f"{name}_g{i}"), "id:substep_next_button")
            if not nxt:
                break
            ui.adb("shell", "input", "tap", str(nxt[0]), str(nxt[1]))
            time.sleep(1.2)
            stages.append(_stage(f"{name}_{i}_{k}", ui.dump(f"{name}_g{i}")))
        stages = [st for st in stages if st["text"]]
        if not stages:
            break
        out.append({"stages": stages})
    return out


def reset() -> None:
    """Fresh calculator screen regardless of where the previous run stopped."""
    ui.adb("shell", "am", "force-stop", "com.microblink.photomath")
    ui.adb("shell", "am", "start", "-n",
           "com.microblink.photomath/.main.activity.MainActivity")
    time.sleep(3)
    ui.adb("shell", "input", "tap", "238", "2086")
    for _ in range(10):  # first taps are lost while the keyboard animates in
        time.sleep(1)
        if ui.find(ui.dump(), "id:keyboard"):
            break
    time.sleep(1.5)


def _buttons(root) -> list[tuple[int, int, str, str]]:
    """Visible «Показать шаги по решению» buttons with the title/subtitle of their card."""
    texts_ = [(c[1], n.get("resource-id", "").split("/")[-1], n.get("text"))
              for n, c, _ in ui.nodes(root) if n.get("text")]
    out = []
    for n, c, _ in ui.nodes(root):
        if n.get("text") == "Показать шаги по решению":
            above = [(y, r, t) for y, r, t in texts_ if y < c[1]]
            title = next((t for y, r, t in reversed(above) if r == "card_title"), "")
            sub = next((t for y, r, t in reversed(above) if r == "card_subtitle"), "")
            out.append((c[0], c[1], title, sub))
    return out


def _card_steps(task_id: str, idx: int, kmap) -> dict:
    """The steps screen of the card that was just opened."""
    name = f"{task_id}_c{idx}"
    (CAP / f"{name}_steps.png").write_bytes(ui.adb("exec-out", "screencap", "-p", binary=True))
    root = ui.dump(f"{name}_top")
    methods = [n.get("text") for n, _, _ in ui.nodes(root)
               if n.get("resource-id", "").endswith("/method_name") and n.get("text")]
    steps = collect_scroll(f"{name}_steps", {"collapsed_description", "title"}, 5)
    return {
        "methods": methods,
        "steps": [{"text": t, "keys": keys_for(t, kmap)} for t in steps],
        "walk": walk(name),
    }


def crawl(task_id: str, keys: str) -> dict:
    kmap = build_keymap()
    reset()
    # Warm-up: the first taps after a fresh start are sometimes swallowed.
    ui.type_keys("1")
    time.sleep(1)
    ui.adb("shell", "input", "tap", "1005", "367")  # clear button
    time.sleep(1)
    type_task(keys)
    time.sleep(2.5)
    root = ui.dump(f"{task_id}_input")
    sol = ui.find(root, "Показать решение")
    (CAP / f"{task_id}_input.png").write_bytes(ui.adb("exec-out", "screencap", "-p", binary=True))
    res: dict = {"id": task_id, "keys": keys, "cards": []}
    if sol is None:
        res["error"] = "no solution button"
        (CAP / f"{task_id}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
        return res
    ui.adb("shell", "input", "tap", str(sol[0]), str(sol[1]))
    time.sleep(3)
    done: set[tuple[str, str]] = set()
    last_seen = None
    for _ in range(14):
        root = ui.dump(f"{task_id}_res")
        todo = [b for b in _buttons(root) if (b[2], b[3]) not in done]
        if not todo:
            seen = [(n.get("text")) for n, _, _ in ui.nodes(root) if n.get("text")]
            if seen == last_seen:
                break
            last_seen = seen
            swipe_up()
            continue
        x, y, title, sub = todo[0]
        done.add((title, sub))
        ui.adb("shell", "input", "tap", str(x), str(y))
        time.sleep(3)
        card = _card_steps(task_id, len(res["cards"]), kmap)
        card.update(title=title, subtitle=sub)
        res["cards"].append(card)
        ui.adb("shell", "input", "keyevent", "KEYCODE_BACK")
        time.sleep(1.5)
    if res["cards"]:  # compatibility with compare.py: first card is the primary solution
        res["steps"], res["walk"] = res["cards"][0]["steps"], res["cards"][0]["walk"]
    (CAP / f"{task_id}.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    return res


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "crawl":
        print(json.dumps(crawl(sys.argv[2], sys.argv[3]), ensure_ascii=False, indent=1))
    else:
        sys.exit(__doc__)
