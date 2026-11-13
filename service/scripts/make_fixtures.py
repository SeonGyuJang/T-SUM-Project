"""개발·테스트용 FixtureProvider 데이터 생성기.

⚠️ 여기서 만드는 상품·리뷰는 모두 가상의 예시다(실제 쿠팡 상품·리뷰가 아님).
   상품 1000000001은 README 5.4 고정 검증 예제(N_s, h_s)를 그대로 재현한다.

실행: python scripts/make_fixtures.py  (tests/fixtures/json/ 아래를 다시 만든다)
"""

from __future__ import annotations

import json
import random
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "json"

OPENERS = {
    5: ["배송 빠르고 포장도 꼼꼼했어요", "이 가격에 이 정도면 대만족입니다", "두 번째 구매예요", "부모님 선물로 샀는데 좋아하세요", "고민하다 샀는데 잘 샀네요"],
    4: ["전체적으로 괜찮아요", "가격 생각하면 만족해요", "기대했던 것과 거의 비슷해요", "쓸만합니다", "무난하게 잘 쓰고 있어요"],
    3: ["그냥 그래요", "가격만큼 하는 것 같아요", "좋은 점도 있고 아쉬운 점도 있어요", "보통이에요", "생각보다는 평범하네요"],
    2: ["조금 실망했어요", "기대보다 별로예요", "한 달 쓰고 남기는 후기인데 아쉬워요", "추천하긴 어렵네요", "상세페이지랑 좀 달라요"],
    1: ["완전 실망입니다", "환불 요청했어요", "이틀 만에 고장났어요", "돈 아까워요", "다시는 안 살 것 같아요"],
}
DETAILS = {
    5: ["소음이 생각보다 작아서 밤에도 쓸 수 있어요", "무게가 가벼워서 손목이 덜 아파요", "충전이 빨라서 편해요", "디자인이 깔끔해서 거실에 둬도 예뻐요", "흡입력이 좋아서 머리카락도 잘 빨아들여요"],
    4: ["다만 충전 거치대가 조금 흔들려요", "배터리가 30분 정도 가요", "설명서가 좀 부실하긴 해요", "먼지통 비우는 게 살짝 번거로워요", "색상이 사진보다 약간 어두워요"],
    3: ["흡입력은 보통 수준이에요", "소음이 좀 있는 편이에요", "부품 마감이 아쉬워요", "배송은 빨랐는데 제품은 평범해요", "가격이 조금만 더 쌌으면 좋겠어요"],
    2: ["배터리가 금방 닳아요", "버튼이 뻑뻑해서 누르기 힘들어요", "사용한 지 얼마 안 됐는데 소리가 커졌어요", "고객센터 연결이 어려웠어요", "냄새가 좀 나요"],
    1: ["전원이 아예 안 들어와요", "포장 뜯자마자 부품이 깨져 있었어요", "교환받은 것도 똑같이 불량이에요", "설명과 완전히 다른 제품이 왔어요", "충전이 아예 안 돼요"],
}
CLOSERS = ["참고하세요", "ㅎㅎ", "ㅠㅠ", "추천합니다", "다음에도 여기서 살게요", "", "그래도 쓸만해요", "고민되시면 사세요", "별로예요"]


def make_text(star: int, i: int, rng: random.Random) -> str:
    parts = [OPENERS[star][i % 5], DETAILS[star][(i // 5) % 5]]
    if i % 3 == 0:
        parts.append(DETAILS[star][(i + 2) % 5])
    closer = CLOSERS[(i * 7 + star) % len(CLOSERS)]
    text = ". ".join(parts) + "."
    if closer:
        text += " " + closer
    return f"{text} ({i + 1}번째 사용 기록)" if i >= 25 else text


def make_product(pid: str, name: str, counts: dict[int, int], displayed_avg: float, per_star: int = 100, seed: int = 1, **extra: object) -> dict:
    rng = random.Random(seed)
    reviews = []
    for star in (5, 4, 3, 2, 1):
        for i in range(min(per_star, counts[star])):
            month = 1 + (i % 10)
            reviews.append(
                {
                    "review_id": f"r{pid}_{star}_{i:03d}",
                    "product_id": pid,
                    "star": star,
                    "title": None if i % 4 else ["좋아요", "솔직 후기", "한 달 사용기", "구매 후기"][i % 4 // 1 % 4],
                    "content": make_text(star, i, rng),
                    "created_at": f"2026-{month:02d}-{1 + (i * 3) % 28:02d}",
                    "has_photo": i % 6 == 0,
                    "helpful_count": (i * 13) % 17,
                    "option_name": "기본형",
                    "author_hash": None,
                }
            )
    data = {
        "meta": {
            "product_id": pid,
            "name": name,
            "image_url": None,
            "url": f"https://www.coupang.com/vp/products/{pid}",
            "category": "생활가전",
            "displayed_avg": displayed_avg,
            "total_reviews": sum(counts.values()),
            "star_counts": {str(k): v for k, v in counts.items()},
        },
        "reviews": reviews,
    }
    data.update(extra)
    return data


def main() -> None:
    (OUT / "products").mkdir(parents=True, exist_ok=True)
    (OUT / "search").mkdir(parents=True, exist_ok=True)
    products = {
        # README 5.4 고정 검증 예제
        "1000000001": make_product("1000000001", "[예시] 무선 청소기 A100 화이트", {5: 1200, 4: 400, 3: 160, 2: 100, 1: 140}, 4.2),
        # 표본 부족
        "1000000002": make_product("1000000002", "[예시] 보온 텀블러 500ml 2개 세트", {5: 40, 4: 12, 3: 5, 2: 2, 1: 1}, 4.5),
        # 3점 수집 중 차단(모의)
        "1000000003": make_product("1000000003", "[예시] 에어프라이어 5L", {5: 300, 4: 120, 3: 60, 2: 30, 1: 40}, 4.3, simulate={"blocked_at_star": 3}),
        # 리뷰 없음
        "1000000004": make_product("1000000004", "[예시] 신상품 무선 이어폰 X1", {5: 0, 4: 0, 3: 0, 2: 0, 1: 0}, None),  # type: ignore[arg-type]
        # 셀렉터 깨짐(모의)
        "1000000005": make_product("1000000005", "[예시] 전기포트 1.7L", {5: 10, 4: 5, 3: 2, 2: 1, 1: 1}, 4.1, simulate={"parser_broken": True}),
    }
    for pid, data in products.items():
        (OUT / "products" / f"{pid}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    # 고정 예제 라벨: h = {5:50, 4:30, 3:80, 2:70, 1:60}, 나머지는 ai
    h = {5: 50, 4: 30, 3: 80, 2: 70, 1: 60}
    labels = {}
    for star in (5, 4, 3, 2, 1):
        for i in range(100):
            labels[f"r1000000001_{star}_{i:03d}"] = "human" if i < h[star] else "ai"
    (OUT / "labels_1000000001.json").write_text(json.dumps(labels, indent=0), encoding="utf-8")

    def cand(pid: str, name: str, price: int, ad: bool = False, rc: int = 100) -> dict:
        return {"product_id": pid, "item_id": None, "vendor_item_id": None, "name": name, "price": price, "image_url": None,
                "url": f"https://www.coupang.com/vp/products/{pid}", "is_ad": ad, "rating": 4.5, "review_count": rc}

    searches = {
        "무선 청소기 a100": [cand("1000000001", "[예시] 무선 청소기 A100 화이트", 189000, rc=2000),
                         cand("1000000011", "[예시] 무선 청소기 A200 그레이", 239000, rc=812),
                         cand("1000000012", "[예시] 핸디 청소기 미니", 49000, ad=True, rc=95)],
        "텀블러": [cand("1000000002", "[예시] 보온 텀블러 500ml 2개 세트", 23900, rc=60),
                cand("1000000021", "[예시] 보온 텀블러 350ml", 12900, rc=410),
                cand("1000000022", "[예시] 스테인리스 텀블러 750ml", 18900, rc=233),
                cand("1000000023", "[예시] 빨대 텀블러 600ml", 9900, ad=True, rc=51)],
    }
    for q, c in searches.items():
        (OUT / "search" / f"{q}.json").write_text(json.dumps({"candidates": c}, ensure_ascii=False, indent=1), encoding="utf-8")
    (OUT / "short_links.json").write_text(
        json.dumps({"https://link.coupang.com/a/demo01": "https://www.coupang.com/vp/products/1000000001?itemId=111&vendorItemId=222"}, indent=1),
        encoding="utf-8",
    )
    print(f"fixtures written to {OUT}")


if __name__ == "__main__":
    main()
