"""사람(human) 데이터 불러오기 (MODEL_DEV.md 4.2.1).

  H2  네이버 쇼핑 20만 건  model/data/raw/naver/naver_shopping.jsonl      (collect_training_data.py naver)
  H1  쿠팡 2022-11-30 이전 model/data/raw/coupang/coupang_training.json   (collect_training_data.py category|collect)

분할은 '그룹' 해시로 정한다(D-008: 같은 그룹은 한 분할에만). 쿠팡은 상품ID, 네이버는 상품 정보가 없어 리뷰ID가 그룹이다.
같은 입력이면 언제 실행해도 같은 분할이 나온다(생성 단계도 이 함수로 참고 리뷰의 분할을 맞춘다).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from realstar_model.paths import RAW_COUPANG, RAW_NAVER
from realstar_model.preprocess import clean_review

SPLITS = ("train", "val", "test")
SPLIT_RATIO = (0.8, 0.1, 0.1)


@dataclass
class Sample:
    sample_id: str
    label: int                 # 0 = human, 1 = ai
    source: str                # naver_shopping | coupang | ai:<generator>
    text: str                  # 원문(제목 없이 본문). 모델 입력은 clean_review로 만든다
    title: str | None = None
    star: int | None = None
    group: str = ""            # 분할 단위
    split: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def split_of(group: str, salt: str = "realstar-v1") -> str:
    h = int(hashlib.sha256(f"{salt}|{group}".encode()).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "train" if h < SPLIT_RATIO[0] else "val" if h < SPLIT_RATIO[0] + SPLIT_RATIO[1] else "test"


def _keep(text: str) -> bool:
    """MODEL_DEV.md 4.4-8: 한글 비율 < 0.5, 5자 미만 제외."""
    c = clean_review(None, text)
    return c.len_chars >= 5 and c.hangul_ratio >= 0.5


def load_naver(path: Path = RAW_NAVER) -> Iterator[Sample]:
    if not path.exists():
        raise FileNotFoundError(f"네이버 쇼핑 데이터가 없어요: {path}\n  저장소 루트에서 `python collect_training_data.py naver` 를 먼저 실행하세요.")
    for line in path.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if not _keep(r["content"]):
            continue
        sid = str(r["review_id"])
        yield Sample(sample_id=sid, label=0, source="naver_shopping", text=r["content"], star=int(r["star"]),
                     group=f"nv:{sid}", split=split_of(f"nv:{sid}"))


def load_coupang(path: Path = RAW_COUPANG) -> Iterator[Sample]:
    """collect_training_data.py 결과에서 2022-11-30 이전(pre_chatgpt) 리뷰만."""
    if not path.exists():
        return
    d = json.loads(path.read_text(encoding="utf-8"))
    for pid, prod in d.get("products", {}).items():
        for r in prod.get("reviews", []):
            if r.get("period") != "pre_chatgpt" or not _keep(r.get("content") or ""):
                continue
            g = f"cp:{pid}"
            yield Sample(sample_id=str(r["review_id"]), label=0, source="coupang", text=r["content"], title=r.get("title"),
                         star=r.get("star"), group=g, split=split_of(g),
                         meta={"product_id": pid, "category": r.get("category"), "created_at": r.get("created_at")})


def load_human(include_coupang: bool = True, naver_path: Path = RAW_NAVER, coupang_path: Path = RAW_COUPANG) -> list[Sample]:
    out = list(load_naver(naver_path))
    if include_coupang:
        out += list(load_coupang(coupang_path))
    seen: set[str] = set()
    uniq = []
    for s in out:  # 정확 중복 제거(4.4-7)
        key = clean_review(s.title, s.text).clean_text
        if key in seen:
            continue
        seen.add(key)
        uniq.append(s)
    return uniq


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                yield json.loads(line)


__all__ = ["SPLITS", "Sample", "load_coupang", "load_human", "load_naver", "read_jsonl", "split_of"]
