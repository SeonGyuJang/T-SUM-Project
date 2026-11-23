"""B0 베이스라인용 표면 특징(길이·줄바꿈·문장부호). 이 특징만으로 잘 맞히면 데이터 지름길을 의심한다(4.11.3)."""

from __future__ import annotations

import re

import numpy as np

from realstar_model.preprocess import CleanResult

_EMOJI = re.compile("[\U0001f300-\U0001faff☀-➿]")
FEATURES = ["len_chars", "len_eojeol", "newline_count", "period", "comma", "exclaim", "question", "tilde", "ellipsis",
            "emoji", "kk", "hh", "tt", "digit_ratio", "hangul_ratio", "space_ratio"]


def surface(c: CleanResult) -> list[float]:
    t, n = c.clean_text, max(1, c.len_chars)
    return [
        c.len_chars, c.len_eojeol, c.newline_count, t.count(".") / n, t.count(",") / n, t.count("!") / n, t.count("?") / n,
        t.count("~") / n, (t.count("...") + t.count("…")) / n, len(_EMOJI.findall(t)) / n, t.count("ㅋ") / n, t.count("ㅎ") / n,
        (t.count("ㅠ") + t.count("ㅜ")) / n, sum(ch.isdigit() for ch in t) / n, c.hangul_ratio, t.count(" ") / n,
    ]


def surface_matrix(cleaned: list[CleanResult]) -> np.ndarray:
    return np.asarray([surface(c) for c in cleaned], dtype=float)
