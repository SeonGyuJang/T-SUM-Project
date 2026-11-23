from __future__ import annotations

import json
import random
from pathlib import Path

import pytest

PHRASES = {
    5: ["정말 만족해요 재구매 의사 있어요", "배송 빠르고 품질 좋아요", "가성비 최고입니다 강추", "생각보다 훨씬 좋네요 ㅎㅎ"],
    4: ["괜찮아요 쓸만합니다", "가격 대비 무난해요", "조금 아쉽지만 만족해요", "포장이 좀 아쉬웠어요 그래도 좋아요"],
    2: ["기대보다 별로예요", "마감이 아쉽네요 다시는 안 살듯", "사이즈가 안 맞아요 ㅠㅠ", "냄새가 좀 나요"],
    1: ["최악입니다 환불 원해요", "불량이 왔어요 연락도 안 돼요", "완전 쓰레기네요", "배송이 열흘 넘게 걸렸어요"],
}


@pytest.fixture()
def naver_file(tmp_path: Path) -> Path:
    rng = random.Random(0)
    p = tmp_path / "naver_shopping.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for i in range(3000):
            star = rng.choice([1, 2, 4, 5])
            text = " ".join(rng.sample(PHRASES[star], k=rng.randint(1, 3))) + f" {i}번째 구매"
            f.write(json.dumps({"review_id": f"nv-{i:05d}", "star": star, "content": text}, ensure_ascii=False) + "\n")
    return p
