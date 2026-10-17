"""Minimal adb UI driver for black-box observation of Photomath.

Usage:
  ui.py dump [name]            -> prints clickable/text nodes, saves xml
  ui.py tap TEXT|id:RES|x,y    -> taps first matching node
  ui.py shot NAME              -> saves NAME.png
"""
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parent / "cap"
OUT.mkdir(exist_ok=True)


def adb(*args: str, binary: bool = False):
    r = subprocess.run(["adb", *args], capture_output=True, check=False)
    return r.stdout if binary else r.stdout.decode(errors="replace")


def dump(name: str = "last") -> ET.Element:
    adb("shell", "uiautomator", "dump", "/sdcard/ui.xml")
    xml = adb("shell", "cat", "/sdcard/ui.xml")
    (OUT / f"{name}.xml").write_text(xml)
    return ET.fromstring(xml)


def nodes(root: ET.Element):
    for n in root.iter("node"):
        b = [int(v) for v in re.findall(r"\d+", n.get("bounds", ""))]
        if len(b) == 4:
            yield n, ((b[0] + b[2]) // 2, (b[1] + b[3]) // 2), b


def find(root: ET.Element, sel: str):
    for n, c, _ in nodes(root):
        if sel.startswith("id:"):
            if n.get("resource-id", "").endswith(sel[3:]):
                return c
        elif sel in (n.get("text"), n.get("content-desc")):
            return c
    return None


# Main keyboard page (1080x2340), column/row centres in device pixels.
_COLS = [91, 270, 449, 628, 807, 986]
_ROWS = [1659, 1835, 2010, 2186]
KEYS = {
    "(": (0, 0), ")": (1, 0), "7": (2, 0), "8": (3, 0), "9": (4, 0), "/": (5, 0),
    "F": (0, 1), "R": (1, 1), "4": (2, 1), "5": (3, 1), "6": (4, 1), "*": (5, 1),
    "^": (0, 2), "x": (1, 2), "1": (2, 2), "2": (3, 2), "3": (4, 2), "-": (5, 2),
    "p": (0, 3), "%": (1, 3), "0": (2, 3), ",": (3, 3), "=": (4, 3), "+": (5, 3),
}
# Toolbar: < and > move the cursor, E = enter, B = backspace.
TOOLBAR = {"<": 449, ">": 628, "E": 807, "B": 986}


def type_keys(seq: str) -> None:
    for ch in seq:
        if ch in TOOLBAR:
            adb("shell", "input", "tap", str(TOOLBAR[ch]), "1486")
        else:
            c, r = KEYS[ch]
            adb("shell", "input", "tap", str(_COLS[c]), str(_ROWS[r]))


def main() -> None:
    cmd, *rest = sys.argv[1:]
    if cmd == "dump":
        root = dump(rest[0] if rest else "last")
        for n, c, _ in nodes(root):
            t, d = n.get("text"), n.get("content-desc")
            rid = n.get("resource-id", "").split("/")[-1]
            if t or d or n.get("clickable") == "true":
                print(f"{c[0]:5},{c[1]:<5} {rid:32} t={t!r} d={d!r}"
                      f"{' [c]' if n.get('clickable') == 'true' else ''}")
    elif cmd == "tap":
        sel = rest[0]
        if re.fullmatch(r"\d+,\d+", sel):
            x, y = sel.split(",")
        else:
            c = find(dump(), sel)
            if c is None:
                sys.exit(f"not found: {sel}")
            x, y = map(str, c)
        adb("shell", "input", "tap", x, y)
        print("tapped", x, y)
    elif cmd == "type":
        type_keys(rest[0])
    elif cmd == "shot":
        (OUT / f"{rest[0]}.png").write_bytes(
            adb("exec-out", "screencap", "-p", binary=True))
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main()
