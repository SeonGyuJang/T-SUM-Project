"""발표 모드 자리표시자(placeholder) 예시 데이터 생성기.

⚠️ 여기서 만드는 상품·리뷰·판정은 모두 가상의 예시다. 실제 분석 결과가 아니다.
   - 웹 화면에는 "샘플 데이터" 배지가 붙는다(is_placeholder=true).
   - 발표 전에 오너가 고른 실제 상품(Q5)을 실제로 분석한 뒤
     `python -m realstar export-demo --analysis-id <id> --key <key>`로 교체해야 한다(docs/demo-checklist.md).
   - 숫자는 서비스와 같은 계산 함수(realstar.aggregate.stats)로 만든다.
     예시 A는 README 5.4 고정 검증 예제와 같다(★4.21 → ★4.08, −0.13, AI 비중 49.9%).

실행: python scripts/make_demo_placeholders.py
"""

from __future__ import annotations

import json
from pathlib import Path

from realstar.aggregate.stats import STARS, StarSample, compute_ratings

OUT = Path(__file__).resolve().parents[1] / "apps" / "web" / "src" / "demo" / "data"

EXAMPLES = [
    {
        "key": "vacuum",
        "product": {"product_id": "1000000001", "name": "[예시] 무선 청소기 A100 화이트", "image_url": "/demo/vacuum.svg"},
        "query": "무선 청소기 A100",
        "displayed_avg": 4.2,
        "N": {5: 1200, 4: 400, 3: 160, 2: 100, 1: 140},
        "samples": {5: (50, 50, 0), 4: (30, 70, 0), 3: (80, 20, 0), 2: (70, 30, 0), 1: (60, 40, 0)},
        "collected_at": "2026-11-12T05:20:00+00:00",
        "pages_loaded": 52,
        "reviews": {
            5: [
                ("한 달 써보고 남겨요", "처음엔 무게 때문에 고민했는데 손목에 무리가 별로 없어요. 강모드는 배터리가 금방 닳아서 평소엔 중간으로 써요. 머리카락 엉킴은 가끔 손으로 빼줘야 해요.", True, "2026-10-28"),
                (None, "원룸이라 큰 청소기는 부담이었는데 딱 좋네요 ㅎㅎ 충전 거치대가 조금 흔들리는 거 빼면 만족이에요. 먼지통 비울 때 먼지가 좀 날리긴 해요.", False, "2026-11-02"),
                (None, "부모님 댁에 하나 놔드렸어요. 버튼이 하나라 어머니도 바로 쓰시네요. 소리가 예전 유선 청소기보다 훨씬 작다고 좋아하세요.", True, "2026-10-15"),
                ("재구매", "두 번째 구매예요. 첫 번째 거 3년 쓰다가 배터리가 약해져서 같은 걸로 다시 샀어요. 필터 물세척 되는 게 제일 편해요.", False, "2026-09-30"),
                (None, "고양이 털 때문에 샀는데 카펫에서도 잘 빨아들여요. 다만 헤드에 털이 감겨서 주 1회는 가위로 잘라줘야 돼요ㅠ", True, "2026-09-21"),
            ],
            4: [
                (None, "흡입력은 만족하는데 배터리가 생각보다 짧아요. 30평 집 한 번 돌리면 거의 다 써요. 그래도 가격 생각하면 괜찮아요.", False, "2026-10-30"),
                (None, "가볍고 좋은데 거치대 고정이 약해서 벽에 박는 게 나을 것 같아요. 저는 그냥 세워 두고 써요.", False, "2026-10-11"),
                ("무난해요", "배송은 이틀 걸렸고 포장 깔끔했어요. 소음은 밤에 쓰기엔 조금 있는 편이에요.", True, "2026-09-18"),
            ],
            3: [
                (None, "기대만큼은 아니에요. 바닥 먼지는 잘 되는데 구석은 솔 툴 끼워야 하고 그게 좀 번거로워요. 가격만큼은 하는 듯.", False, "2026-10-21"),
                (None, "충전 시간이 4시간 넘게 걸려서 급할 때 못 써요. 흡입력은 보통이고 디자인은 예뻐요.", False, "2026-10-03"),
                (None, "먼지통이 작아서 자주 비워야 해요. 원룸엔 괜찮은데 넓은 집엔 비추예요.", False, "2026-09-12"),
                (None, "소음이 생각보다 커요. 아파트라 저녁엔 눈치 보여서 낮에만 돌려요. 그 외엔 그럭저럭.", False, "2026-08-29"),
            ],
            2: [
                (None, "3주 만에 강모드가 안 켜져요. AS 접수했는데 일주일째 연락이 없네요. 제품 자체는 가볍고 좋았어요.", False, "2026-10-25"),
                (None, "헤드 바퀴가 금방 뻑뻑해져서 밀 때 힘이 들어가요. 청소할 때마다 스트레스예요.", True, "2026-10-01"),
            ],
            1: [
                (None, "받자마자 충전이 안 돼서 교환했는데 교환품도 똑같아요. 결국 환불했어요. 판매자 응대는 빨랐어요.", False, "2026-10-19"),
                (None, "배터리 표시등이 계속 깜빡이고 2분 쓰면 꺼져요. 불량 같은데 교환 절차가 너무 복잡하네요.", False, "2026-09-27"),
            ],
        },
    },
    {
        "key": "tumbler",
        "product": {"product_id": "1000000002", "name": "[예시] 보온 텀블러 500ml 2개 세트", "image_url": "/demo/tumbler.svg"},
        "query": "보온 텀블러 500ml",
        "displayed_avg": 4.5,
        "N": {5: 310, 4: 62, 3: 25, 2: 12, 1: 21},
        "samples": {5: (41, 46, 13), 4: (35, 19, 8), 3: (17, 6, 2), 2: (7, 3, 2), 1: (15, 4, 2)},
        "collected_at": "2026-11-12T06:05:00+00:00",
        "pages_loaded": 31,
        "reviews": {
            5: [
                (None, "아침에 넣은 커피가 퇴근할 때까지 따뜻해요. 뚜껑 패킹 분리돼서 세척도 편하고요. 두 개라 남편이랑 하나씩 써요.", True, "2026-11-03"),
                (None, "회사 책상에 두고 쓰는데 얼음이 반나절 넘게 안 녹아요ㅋㅋ 컵홀더에도 딱 들어가요.", False, "2026-10-26"),
                ("가성비", "이 가격에 두 개면 충분히 만족이에요. 색상은 사진보다 살짝 연해요.", False, "2026-10-09"),
            ],
            4: [
                (None, "보온은 잘 되는데 입구가 좁아서 솔이 잘 안 들어가요. 세척솔 따로 사야 할 듯해요.", False, "2026-10-30"),
                (None, "생각보다 무거워요. 가방에 넣으면 묵직해요. 그래도 새는 건 없어서 만족해요.", False, "2026-10-14"),
            ],
            3: [
                (None, "하나는 괜찮은데 하나는 뚜껑이 좀 헐거워요. 뒤집으면 한두 방울 새요.", True, "2026-10-20"),
            ],
            2: [
                (None, "보온이 세 시간 정도밖에 안 가요. 상세페이지에 12시간이라고 써 있어서 기대했는데 아쉬워요.", False, "2026-10-07"),
            ],
            1: [
                (None, "받았는데 안쪽에 녹 같은 게 있어서 바로 반품했어요. 검수가 제대로 안 되는 것 같아요.", True, "2026-10-17"),
                (None, "뚜껑 고무 냄새가 너무 심해요. 몇 번 삶았는데도 안 빠져서 결국 안 써요.", False, "2026-09-30"),
            ],
        },
    },
    {
        "key": "airfryer",
        "product": {"product_id": "1000000003", "name": "[예시] 에어프라이어 5L 블랙", "image_url": "/demo/airfryer.svg"},
        "query": "에어프라이어 5L",
        "displayed_avg": 4.4,
        "N": {5: 3120, 4: 980, 3: 310, 2: 120, 1: 170},
        "samples": {5: (78, 14, 8), 4: (80, 12, 8), 3: (83, 10, 7), 2: (79, 13, 8), 1: (80, 11, 9)},
        "collected_at": "2026-11-11T23:40:00+00:00",
        "pages_loaded": 58,
        "reviews": {
            5: [
                (None, "냉동 감자튀김 12분이면 바삭하게 돼요. 바스켓 코팅이 아직 멀쩡하고 설거지도 편해요.", True, "2026-11-05"),
                (None, "5L라 통닭 반 마리 정도는 충분히 들어가요. 처음에 플라스틱 냄새 조금 났는데 공회전 두 번 하니 없어졌어요.", False, "2026-10-29"),
                (None, "다이얼 방식이라 어르신들도 쓰기 쉬워요. 소리는 선풍기 정도예요.", False, "2026-10-12"),
                ("만족", "고구마 구워 먹으려고 샀는데 오븐보다 빨라요. 겉은 쫀득하고 속은 촉촉해요 ㅎㅎ", True, "2026-10-02"),
            ],
            4: [
                (None, "크기는 좋은데 생각보다 자리를 많이 차지해요. 주방이 좁으면 사이즈 꼭 재보세요.", False, "2026-10-27"),
                (None, "타이머가 30분까지라 긴 요리는 두 번 돌려야 해요. 그 외엔 만족해요.", False, "2026-10-08"),
                (None, "바스켓 손잡이가 조금 흔들려요. 기능은 문제없어요.", False, "2026-09-25"),
            ],
            3: [
                (None, "열이 위쪽만 세서 중간에 한 번 뒤집어 줘야 골고루 익어요. 가격 생각하면 보통이에요.", False, "2026-10-18"),
                (None, "작동 중에 겉면이 꽤 뜨거워요. 아이 있는 집은 조심해야 할 것 같아요.", False, "2026-10-04"),
            ],
            2: [
                (None, "두 달 쓰니 코팅이 벗겨지기 시작했어요. 실리콘 집게만 썼는데도요.", True, "2026-10-22"),
                (None, "온도 조절이 정확하지 않은 것 같아요. 160도로 해도 겉이 타요.", False, "2026-09-29"),
            ],
            1: [
                (None, "한 달 만에 팬 소리가 덜덜거리더니 멈췄어요. AS는 택배 보내야 해서 2주 걸린대요.", False, "2026-10-15"),
            ],
        },
    },
]


def build(ex: dict) -> dict:  # type: ignore[type-arg]
    per = {s: StarSample(collected=sum(ex["samples"][s]), human=ex["samples"][s][0], ai=ex["samples"][s][1], uncertain=ex["samples"][s][2]) for s in STARS}
    rr = compute_ratings(ex["N"], per_star=per, displayed_avg=ex["displayed_avg"], bootstrap_iterations=1000, seed=20261113)
    warnings = [{"code": "placeholder", "level": "warning", "message": "가상의 예시 데이터예요. 실제 상품 분석 결과가 아니에요."}]
    warnings += [w.as_dict() for w in rr.warnings]
    top = {}
    for s in STARS:
        items = []
        for i, (title, text, photo, date) in enumerate(ex["reviews"].get(s, [])):
            p = round(0.97 - i * 0.031 - (5 - s) * 0.004, 4)
            items.append({"review_id": f"demo_{ex['key']}_{s}_{i}", "title": title, "text": text, "p_human": p, "created_at": date,
                          "has_photo": photo, "len_chars": len(text) + (len(title) + 1 if title else 0), "reason_tags": []})
        top[str(s)] = items
        if len(items) < 5:
            warnings.append({"code": "top_insufficient", "level": "info", "star": s, "message": f"{s}점에서 조건에 맞는 사람 리뷰가 {len(items)}개뿐이에요."})

    def r4(x):  # type: ignore[no-untyped-def]
        return None if x is None else round(x, 4)

    def ci(x):  # type: ignore[no-untyped-def]
        return None if x is None else [round(x[0], 4), round(x[1], 4)]

    result = {
        "analysis_id": f"demo-{ex['key']}",
        "product": {**ex["product"], "url": f"https://www.coupang.com/vp/products/{ex['product']['product_id']}"},
        "platform_stats": {"displayed_avg": ex["displayed_avg"], "total_reviews": sum(ex["N"].values()), "star_counts": {str(s): ex["N"][s] for s in STARS}},
        "sampling": {"per_star_limit": 100, "sort": "latest", "collected_at": ex["collected_at"], "pages_loaded": ex["pages_loaded"],
                     "selectors_version": "placeholder", "from_cache": False},
        "per_star": {str(s): {"total": ex["N"][s], "collected": per[s].collected, "human": per[s].human, "ai": per[s].ai, "uncertain": per[s].uncertain,
                              "human_ratio": None if per[s].human_ratio is None else round(per[s].human_ratio, 4), "ratio_substituted": False} for s in STARS},
        "ratings": {"avg_all": r4(rr.avg_all), "avg_human": r4(rr.avg_human), "diff": r4(rr.diff), "avg_human_ci95": ci(rr.avg_human_ci95),
                    "diff_ci95": ci(rr.diff_ci95), "ai_share": r4(rr.ai_share), "ai_share_ci95": ci(rr.ai_share_ci95), "corrected": None},
        "top_human_reviews": top,
        "flags": {"sponsored_count": 0, "cash_event_count": 0, "near_duplicate_groups": 0},
        "warnings": warnings,
        "model": {"version": "placeholder-example", "T_AI": None, "T_HUMAN": None, "thresholds": None, "is_dummy": False},
        "assumptions": [
            "판단 보류 리뷰는 판정된 리뷰와 사람 비율이 같다고 가정하고 계산에서 제외했어요.",
            "사람 리뷰 기준 별점은 별점별 표본에서 추정한 사람 비율을 상품 전체 별점 분포에 반영해 계산했어요.",
        ],
    }
    replay = [{"stage": "resolve"}] + [
        {"stage": "collect", "star": s, "collected": per[s].collected, "target": min(100, ex["N"][s])} for s in STARS
    ] + [{"stage": "detect"}, {"stage": "aggregate"}]
    return {
        "key": ex["key"],
        "is_placeholder": True,
        "input_examples": {"url": result["product"]["url"], "query": ex["query"]},
        "result": result,
        "replay": replay,
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for ex in EXAMPLES:
        data = build(ex)
        (OUT / f"{ex['key']}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        r = data["result"]["ratings"]
        print(ex["key"], r["avg_all"], r["avg_human"], r["diff"], r["ai_share"], r["avg_human_ci95"])


if __name__ == "__main__":
    main()
