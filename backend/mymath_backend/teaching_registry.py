"""One integration boundary for authored, mathematically checked teaching packs.

Providers never select a numerical answer. They explain an existing solver step
and must decline a case they cannot derive, rather than fabricate a calculation.
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .solver.base import Step

PACK_NAMES = ("calculus", "algebra", "discrete")


def packs() -> list[ModuleType]:
    return [import_module(f".teaching_{name}", __package__) for name in PACK_NAMES]


def templates() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for pack in packs():
        for key, value in pack.TEMPLATES.items():
            if key in out and out[key] != value:
                raise ValueError(f"conflicting teaching template: {key}")
            out[key] = value
    return out


def theory(key: str, locale: str) -> dict[str, str] | None:
    language = "ru" if locale == "ru" else "en"
    for name, pack in zip(PACK_NAMES, packs(), strict=True):
        topic = pack.RULE_TOPICS.get(key)
        if topic is not None:
            return {"id": f"{name}:{topic}", **pack.ARTICLES[topic][language]}
    return None


def enrich(step: Step) -> str | None:
    """A pack owns the first recognized rule; no broad exception swallowing."""
    for pack in packs():
        title = pack.enrich(step)
        if title is not None:
            return str(title)
    return None
