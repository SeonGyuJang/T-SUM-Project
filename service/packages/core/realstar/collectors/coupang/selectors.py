"""selectors.yaml 로더와 BeautifulSoup 보조 함수."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from bs4 import BeautifulSoup, Tag

DEFAULT_SELECTORS_PATH = Path(__file__).with_name("selectors.yaml")


class Selectors:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data

    @property
    def version(self) -> str:
        return str(self.data.get("version", "unknown"))

    def section(self, name: str) -> dict[str, Any]:
        return dict(self.data.get(name, {}))

    def get(self, section: str, key: str, default: Any = None) -> Any:
        return self.data.get(section, {}).get(key, default)

    def css_list(self, section: str, key: str) -> list[str]:
        value = self.get(section, key, [])
        if isinstance(value, str):
            return [value]
        return list(value or [])


@lru_cache(maxsize=8)
def load_selectors(path: str | None = None) -> Selectors:
    p = Path(path) if path else DEFAULT_SELECTORS_PATH
    with p.open(encoding="utf-8") as f:
        return Selectors(yaml.safe_load(f))


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


def select_first(root: Tag | BeautifulSoup, css_candidates: list[str]) -> Tag | None:
    for css in css_candidates:
        found = root.select_one(css)
        if found is not None:
            return found
    return None


def select_all(root: Tag | BeautifulSoup, css_candidates: list[str]) -> list[Tag]:
    for css in css_candidates:
        found = root.select(css)
        if found:
            return list(found)
    return []


def text_of(node: Tag | None) -> str | None:
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return re.sub(r"\s+", " ", text) if text else None


def multiline_text_of(node: Tag | None) -> str | None:
    """리뷰 본문용: <br>과 블록 경계를 줄바꿈으로 살린다(줄바꿈 처리는 model 전처리가 담당)."""
    if node is None:
        return None
    for br in node.find_all("br"):
        br.replace_with("\n")
    text = node.get_text("", strip=False)
    lines = [re.sub(r"[ \t ]+", " ", ln).strip() for ln in text.splitlines()]
    joined = "\n".join(ln for ln in lines if ln)
    return joined or None


def parse_int(text: str | None) -> int | None:
    if not text:
        return None
    m = re.search(r"\d[\d,]*", text)
    return int(m.group(0).replace(",", "")) if m else None


def parse_float(text: str | None) -> float | None:
    if not text:
        return None
    m = re.search(r"\d+(?:\.\d+)?", text.replace(",", ""))
    return float(m.group(0)) if m else None


def parse_width_percent(node: Tag | None) -> float | None:
    if node is None:
        return None
    style = str(node.get("style", ""))
    m = re.search(r"width\s*:\s*([\d.]+)\s*%", style)
    return float(m.group(1)) if m else None
