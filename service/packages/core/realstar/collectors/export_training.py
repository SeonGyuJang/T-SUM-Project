"""학습용 과거 리뷰 내보내기: service → model 데이터 계약 (MODEL_DEV.md 4.2.3, 4.12.1).

- 서비스 수집과 별도로, 더 낮은 속도(TRAINING_DELAY_*)와 별도 일일 상한(TRAINING_MAX_PAGES_PER_DAY)으로 돈다.
- 차단 규칙은 동일하다: BlockedError가 나면 즉시 멈추고 쿨다운에 들어간다.
- 작성일이 TRAINING_CUTOFF_DATE(기본 2022-11-30) 이전인 리뷰만, 상품·별점당 최대 TRAINING_PER_STAR_LIMIT(30)건.
- 작성자 식별 정보는 내보내지 않는다.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from realstar import SCRAPER_VERSION
from realstar.collectors.base import STARS, RawReview, ReviewProvider
from realstar.errors import BlockedError

log = logging.getLogger(__name__)
KST = ZoneInfo("Asia/Seoul")


@dataclass
class TrainingTarget:
    product_id: str
    category: str | None = None


def read_targets(path: Path) -> list[TrainingTarget]:
    """한 줄에 `product_id[,category]`. #으로 시작하면 주석."""
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        pid, _, cat = line.partition(",")
        out.append(TrainingTarget(pid.strip(), cat.strip() or None))
    return out


def to_contract_row(r: RawReview, *, category: str | None, product_name: str, collected_at: str) -> dict[str, object]:
    return {
        "review_id": r.review_id,
        "product_id": r.product_id,
        "category": category,
        "product_name": product_name,
        "star": r.star,
        "title": r.title,
        "content": r.content,
        "created_at": r.created_at,
        "has_photo": r.has_photo,
        "helpful_count": r.helpful_count,
        "collected_at": collected_at,
        "source": "coupang_scraper",
        "scraper_version": SCRAPER_VERSION,
    }


def filter_before(reviews: Iterable[RawReview], cutoff: str, limit: int) -> list[RawReview]:
    picked = [r for r in reviews if r.created_at and r.created_at < cutoff]
    return picked[:limit]


def export_training_batch(
    provider: ReviewProvider,
    targets: list[TrainingTarget],
    out_dir: Path,
    *,
    batch: str,
    cutoff: str,
    per_star_limit: int,
    scan_limit: int = 150,
    sort: str = "best",
) -> tuple[Path, int, str]:
    """반환: (파일 경로, 내보낸 건수, outcome[ok/blocked])."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{datetime.now(KST):%Y%m%d}_{batch}.jsonl"
    n = 0
    outcome = "ok"
    with path.open("a", encoding="utf-8") as f:
        try:
            for t in targets:
                meta = provider.get_product_meta(t.product_id)
                counts = meta.resolved_star_counts() if meta.total_reviews else dict.fromkeys(STARS, 0)
                collected_at = datetime.now(KST).isoformat(timespec="seconds")
                for star in STARS:
                    if counts.get(star, 0) == 0:
                        continue
                    reviews = provider.get_reviews(t.product_id, star, scan_limit, sort=sort)  # type: ignore[arg-type]
                    for r in filter_before(reviews, cutoff, per_star_limit):
                        row = to_contract_row(r, category=t.category or meta.category, product_name=meta.name, collected_at=collected_at)
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                        n += 1
                f.flush()
        except BlockedError:
            log.warning("training export blocked; stopping batch")
            outcome = "blocked"
    return path, n, outcome
