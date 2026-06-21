"""UIAutomator hierarchy parsing — drive an Android UI by accessibility label, not pixels.

Pixel coordinates break across screens; the UIAutomator XML hierarchy is robust. This module is the
pure half (parse the dump, find a node, compute its tap center); :mod:`untether_bt.android` drives
the device. The loop is always **dump → find node → act → re-dump** (the tree is a snapshot).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from xml.etree import ElementTree

_BOUNDS = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")


def _parse_bounds(s: str | None) -> tuple[int, int, int, int] | None:
    if not s:
        return None
    m = _BOUNDS.match(s)
    return (int(m[1]), int(m[2]), int(m[3]), int(m[4])) if m else None


def _truthy(s: str | None) -> bool:
    return s == "true"


@dataclass(frozen=True)
class UiNode:
    text: str
    desc: str            # content-desc (often the only label on icon-only buttons)
    resource_id: str
    cls: str
    package: str
    bounds: tuple[int, int, int, int] | None
    clickable: bool
    checked: bool | None  # None if the attr was absent

    @property
    def center(self) -> tuple[int, int] | None:
        if self.bounds is None:
            return None
        x1, y1, x2, y2 = self.bounds
        return (x1 + x2) // 2, (y1 + y2) // 2

    def matches(self, query: str, fields: tuple[str, ...] = ("text", "desc", "resource_id")) -> bool:
        q = query.lower()
        for f in fields:
            if q in getattr(self, f, "").lower():
                return True
        return False


def parse_ui_dump(xml: str) -> list[UiNode]:
    """Parse a ``uiautomator dump`` XML into a flat list of nodes."""
    root = ElementTree.fromstring(xml)
    out: list[UiNode] = []
    for el in root.iter("node"):
        checked_attr = el.get("checked")
        out.append(
            UiNode(
                text=el.get("text", ""),
                desc=el.get("content-desc", ""),
                resource_id=el.get("resource-id", ""),
                cls=el.get("class", ""),
                package=el.get("package", ""),
                bounds=_parse_bounds(el.get("bounds")),
                clickable=_truthy(el.get("clickable")),
                checked=(None if checked_attr is None else _truthy(checked_attr)),
            )
        )
    return out


def find_node(
    nodes: list[UiNode],
    query: str,
    *,
    fields: tuple[str, ...] = ("text", "desc", "resource_id"),
    clickable_only: bool = False,
) -> UiNode | None:
    """First node matching ``query`` (substring, case-insensitive) in any of ``fields``."""
    for node in nodes:
        if clickable_only and not node.clickable:
            continue
        if node.matches(query, fields):
            return node
    return None
