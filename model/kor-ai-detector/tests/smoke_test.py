"""GPU·모델 없이 돌아가는 점검: 데이터 준비 → 분할 규칙 → 지표 → 평가 리포트.

python tests/smoke_test.py
"""
import csv
import json
from collections import Counter
import os
import py_compile
import random
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from metrics import auroc, binary_report, threshold_at_fpr  # noqa: E402

PY = sys.executable
rng = random.Random(0)


def run(*args):
    r = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout, r.stderr)
        raise SystemExit(f"실패: {' '.join(args)}")
    return r.stdout


def load(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(x) for x in f if x.strip()]


def test_metrics():
    assert auroc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
    assert auroc([0, 0, 1, 1], [0.9, 0.8, 0.2, 0.1]) == 0.0
    assert auroc([0, 1], [0.5, 0.5]) == 0.5
    assert abs(auroc([0, 1, 0, 1], [0.1, 0.4, 0.5, 0.8]) - 0.75) < 1e-9
    human = [i / 100 for i in range(100)]
    thr = threshold_at_fpr(human, 0.01)
    rep = binary_report([0] * 100, human, thr)
    assert rep["fp"] <= 1, rep
    print("✓ metrics")


def make_raw(d):
    # LGC 흉내: 필드명이 기본값과 다르고 라벨이 문자열
    lgc = []
    for i in range(400):
        ai = i % 2 == 1
        lgc.append({"comment": ("이 기사에 대해 다양한 의견이 있을 것 같습니다. " if ai else "ㅋㅋㅋ 이게 말이 되냐 ") + str(i),
                    "type": "LLM" if ai else "HUMAN", "model": "gpt" if ai else "", "article": f"a{i // 8}"})
    lgc.append({"comment": "중복 댓글", "type": "HUMAN", "model": "", "article": "dup"})
    lgc.append({"comment": "중복 댓글", "type": "HUMAN", "model": "", "article": "dup"})
    with open(os.path.join(d, "lgc.json"), "w", encoding="utf-8") as f:
        json.dump(lgc, f, ensure_ascii=False)

    def write_csv(name, rows):
        with open(os.path.join(d, name), "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)

    naver = [{"text": f"배송 빨라요 ㅎㅎ 상품{i} 좋네요" + "!" * (i % 3), "product_id": f"p{i // 5}",
              "platform": "naver", "date": "2021-05-01" if i % 10 else "2024-01-01", "rating": 5}
             for i in range(300)]
    coupang = [{"text": f"쿠팡 로켓배송 굿 {i}", "product_id": f"c{i // 5}", "platform": "coupang",
                "date": "2021-03-03", "rating": 4} for i in range(60)]
    write_csv("naver_human.csv", naver)
    write_csv("coupang_human.csv", coupang)

    for gen in ("chatgpt", "claude", "gemini"):
        rows = []
        for i in range(120):
            pid = f"p{i // 4}" if i < 100 else f"c{i}"
            text = f"이 제품은 품질이 우수하며 상품{i} 가격 대비 만족스럽습니다 ({gen})"
            if i == 0:
                text = "물론입니다! 다음은 리뷰입니다:\n\n" + text
            if i == 1:
                text = "죄송하지만, AI 언어 모델로서 그 요청은 작성할 수 없습니다."
            rows.append({"text": text, "product_id": pid, "generator": gen,
                         "platform": "coupang" if pid.startswith("c") else "naver", "prompt_type": "scratch"})
        with open(os.path.join(d, f"ai_{gen}.jsonl"), "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")


def test_prepare_and_evaluate():
    with tempfile.TemporaryDirectory() as d:
        make_raw(d)
        out = os.path.join(d, "processed")
        stdout = run("prepare_data.py",
                     "--lgc", os.path.join(d, "lgc.json"),
                     "--lgc-text-field", "comment", "--lgc-label-field", "type", "--lgc-ai-values", "llm",
                     "--lgc-generator-field", "model", "--lgc-group-field", "article",
                     "--human-reviews", os.path.join(d, "naver_human.csv"), os.path.join(d, "coupang_human.csv"),
                     "--ai-reviews", *[os.path.join(d, f"ai_{g}.jsonl") for g in ("chatgpt", "claude", "gemini")],
                     "--human-before", "2022-12-01",
                     "--holdout-generators", "gemini", "--test-only-platforms", "coupang",
                     "--out", out)
        print(stdout)
        s = {k: load(os.path.join(out, f"{k}.jsonl")) for k in
             ("stage1_train", "stage1_val", "stage1_test", "stage2_train", "stage2_val", "stage2_test",
              "stage2_test_unseen_gen", "stage2_test_xplatform")}

        # 1단계: 라벨 매핑, 중복 제거, 기사 단위 분할
        assert {r["label"] for r in s["stage1_train"]} == {0, 1}
        assert sum(r["text"] == "중복 댓글" for k in ("stage1_train", "stage1_val", "stage1_test") for r in s[k]) == 1
        g = {k: {r["group"] for r in s[k]} for k in ("stage1_train", "stage1_val", "stage1_test")}
        assert not (g["stage1_train"] & g["stage1_val"]) and not (g["stage1_train"] & g["stage1_test"])

        # 2단계: 상품 단위 분할, holdout 모델·플랫폼 격리, 날짜 필터, AI 메타 문구 정리
        g2 = {k: {r["group"] for r in s[k]} for k in ("stage2_train", "stage2_val", "stage2_test")}
        assert not (g2["stage2_train"] & g2["stage2_val"]) and not (g2["stage2_train"] & g2["stage2_test"])
        for k in ("stage2_train", "stage2_val", "stage2_test"):
            assert all(r["generator"] != "gemini" for r in s[k]), k
            assert all(r["platform"] != "coupang" for r in s[k]), k
        unseen_ai = [r for r in s["stage2_test_unseen_gen"] if r["label"] == 1]
        assert unseen_ai and all(r["generator"] == "gemini" for r in unseen_ai)
        assert not ({r["group"] for r in unseen_ai} & (g2["stage2_train"] | g2["stage2_val"]))
        assert s["stage2_test_xplatform"] and all(r["platform"] == "coupang" for r in s["stage2_test_xplatform"])
        all_rev = [r for k in s if k.startswith("stage2") for r in s[k]]
        assert all(r.get("date", "2000") < "2022-12-01" for r in all_rev if r["label"] == 0)
        assert not any("물론입니다" in r["text"] or "AI 언어 모델" in r["text"] for r in all_rev)
        assert "길이" in stdout and "지름길" in stdout
        print("✓ prepare_data (분할·격리·정제 규칙)")

        # 평가: 외부 점수 CSV 경로 (모델 없이 지표·리포트 생성 확인)
        scores = os.path.join(d, "scores.csv")
        with open(scores, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "score"])
            for k in ("stage2_val", "stage2_test", "stage2_test_unseen_gen", "stage2_test_xplatform"):
                for r in s[k]:
                    base = 0.75 if r["label"] == 1 else 0.25
                    w.writerow([r["id"], min(1, max(0, base + rng.uniform(-0.3, 0.3)))])
        rep_dir = os.path.join(d, "reports")
        run("evaluate.py", "--scores-csv", scores, "--val", os.path.join(out, "stage2_val.jsonl"),
            "--test", *[os.path.join(out, f"{k}.jsonl") for k in
                        ("stage2_test", "stage2_test_unseen_gen", "stage2_test_xplatform")],
            "--out", rep_dir)
        rep = json.load(open(os.path.join(rep_dir, "report.json"), encoding="utf-8"))
        assert set(rep["tests"]) == {"stage2_test", "stage2_test_unseen_gen", "stage2_test_xplatform"}
        assert rep["tests"]["stage2_test"]["overall"]["auroc"] > 0.8
        assert os.path.exists(os.path.join(rep_dir, "report.md"))
        print("✓ evaluate (--scores-csv, 임계값·세부 지표·리포트)")


def test_thresholds_and_verdict():
    from predictor import thresholds_from_val, verdict

    labels = [0] * 200 + [1] * 200
    scores = [i / 400 for i in range(200)] + [0.3 + i / 300 for i in range(200)]
    t_ai, t_h = thresholds_from_val(labels, scores, 0.01, 0.05)
    fp = sum(1 for s, y in zip(scores, labels) if y == 0 and s > t_ai)
    miss = sum(1 for s, y in zip(scores, labels) if y == 1 and s <= t_h)
    assert fp <= 2 and miss <= 10 and t_h <= t_ai, (t_ai, t_h, fp, miss)
    # 판정은 점수 순서와 일관돼야 한다(예전 0.4~0.7 고정 보류 구간의 모순 방지)
    order = {"사람": 0, "판단 보류": 1, "AI": 2}
    vs = [verdict(p / 100, t_ai, t_h, 50) for p in range(101)]
    assert all(order[a] <= order[b] for a, b in zip(vs, vs[1:])), vs
    assert verdict(0.99, t_ai, t_h, 5) == "판단 보류"  # 20자 미만
    print("✓ 임계값 2개(T_AI·T_HUMAN)와 판정 일관성")


def test_newlines_auto():
    with tempfile.TemporaryDirectory() as d:
        human = [{"text": f"한줄짜리 사람 리뷰 {i} 좋아요", "product_id": f"p{i}", "platform": "naver", "date": "2020-01-01"}
                 for i in range(200)]
        ai = [{"text": f"첫 문단입니다 {i}.\n\n두 번째 문단이에요.", "product_id": f"p{i}", "generator": "claude"} for i in range(200)]
        for name, rows in (("h.jsonl", human), ("a.jsonl", ai)):
            with open(os.path.join(d, name), "w", encoding="utf-8") as f:
                f.writelines(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
        out = os.path.join(d, "p")
        stdout = run("prepare_data.py", "--human-reviews", os.path.join(d, "h.jsonl"), "--ai-reviews", os.path.join(d, "a.jsonl"),
                     "--out", out)
        rows = [r for k in ("train", "val", "test") for r in load(os.path.join(out, f"stage2_{k}.jsonl"))]
        assert not any("\n" in r["text"] for r in rows) and "공백으로 바꿉니다" in stdout
        assert json.load(open(os.path.join(out, "data_summary.json"), encoding="utf-8"))["cleaning_stats"]["newlines_mode"] == "space"
        stdout = run("prepare_data.py", "--human-reviews", os.path.join(d, "h.jsonl"), "--ai-reviews", os.path.join(d, "a.jsonl"),
                     "--newlines", "keep", "--out", out)
        assert "줄바꿈 수" in stdout and "⚠ 줄바꿈 수" in stdout  # 유지하면 지름길 경고
    print("✓ 줄바꿈 자동 처리(한쪽에만 있으면 공백으로) + 지름길 경고")


def test_inspect_lgc():
    with tempfile.TemporaryDirectory() as d:
        make_raw(d)
        out = run("prepare_data.py", "--lgc", os.path.join(d, "lgc.json"), "--inspect-lgc")
        assert "필드: ['comment', 'type', 'model', 'article']" in out and "'LLM': 200" in out
    print("✓ LGC 구조 확인(--inspect-lgc)")


def test_lgc_ai_only():
    """XDAC 공개 LGC(AI 댓글만, 라벨 필드 없음) → 1단계 없이 lgc_ai_test.jsonl만."""
    with tempfile.TemporaryDirectory() as d:
        recs = [{"idx": i, "llm_model_family": ["GPT", "Claude", "Gemma"][i % 3], "temperature": 0.3,
                 "generated_comment": f"이 소식 듣고 기분이 좋네요 {i}"} for i in range(30)]
        with open(os.path.join(d, "lgc.json"), "w", encoding="utf-8") as f:
            json.dump(recs, f, ensure_ascii=False)
        out = run("prepare_data.py", "--lgc", os.path.join(d, "lgc.json"), "--inspect-lgc")
        assert "--lgc-all-ai" in out and "1단계(댓글) 학습은 할 수 없습니다" in out, out
        o = os.path.join(d, "out")
        out = run("prepare_data.py", "--lgc", os.path.join(d, "lgc.json"), "--lgc-all-ai",
                  "--lgc-text-field", "generated_comment", "--lgc-generator-field", "llm_model_family", "--out", o)
        rows = load(os.path.join(o, "lgc_ai_test.jsonl"))
        assert len(rows) == 30 and all(r["label"] == 1 for r in rows), rows[:2]
        assert {r["generator"] for r in rows} == {"gpt", "claude", "gemma"}
        assert not os.path.exists(os.path.join(o, "stage1_train.jsonl"))
    print("✓ AI 댓글만 있는 LGC → lgc_ai_test.jsonl")


def test_convert_and_tasks():
    with tempfile.TemporaryDirectory() as d:
        nv = os.path.join(d, "naver.jsonl")
        with open(nv, "w", encoding="utf-8") as f:
            for i in range(50):
                f.write(json.dumps({"review_id": f"nv-{i:04d}", "star": [1, 2, 4, 5][i % 4], "content": f"리뷰 내용 {i} 배송 좋아요"},
                                   ensure_ascii=False) + "\n")
        nv_txt = os.path.join(d, "naver_shopping.txt")  # bab2min 원본 형식: 별점<TAB>리뷰
        with open(nv_txt, "w", encoding="utf-8") as f:
            f.write("5\t배송 빠르고 좋아요\n1\t최악이에요\n")
        # AI Hub 속성기반 감정분석 흉내: 구분 폴더 안 JSON 배열
        ah = os.path.join(d, "AI_hub", "pre", "TL_쇼핑몰_01.패션_1-1.여성의류")
        os.makedirs(ah)
        recs = [{"Index": str(i), "RawText": f"사이즈가 작아요 {i}", "Source": "쇼핑몰", "Domain": "패션", "MainCategory": "여성의류",
                 "ProductName": "OO 스** 티셔츠 4종세트" if i < 6 else "OO 니트 라** 세트", "ReviewScore": ["20", "100", "70", "90"][i % 4],
                 "RDate": "20221215" if i == 9 else "20211010", "GeneralPolarity": "-1", "Aspects": []} for i in range(10)]
        recs += [{"Index": "s1", "RawText": "#데일리룩 오늘의 코디 공유해요", "Source": "SNS", "Domain": "패션",
                  "MainCategory": "여성의류", "ProductName": "", "Aspects": []},
                 {"Index": "nd", "RawText": "날짜 없는 쇼핑몰 리뷰", "Source": "쇼핑몰", "Domain": "패션",
                  "MainCategory": "여성의류", "ProductName": "OO 니트", "ReviewScore": "100", "Aspects": []}]
        json.dump(recs, open(os.path.join(ah, "a.json"), "w", encoding="utf-8"), ensure_ascii=False)
        raw = os.path.join(d, "raw")
        merged = os.path.join(raw, "human_reviews.jsonl")
        out = run("convert_sources.py", "--aihub", os.path.join(d, "AI_hub", "pre"), "--naver", nv, "--out", merged)
        run("convert_sources.py", "--aihub", os.path.join(d, "none"), "--naver", nv_txt, "--out", os.path.join(raw, "txt.jsonl"))
        txt_rows = load(os.path.join(raw, "txt.jsonl"))
        assert [(r["rating"], r["text"]) for r in txt_rows] == [(5, "배송 빠르고 좋아요"), (1, "최악이에요")], txt_rows
        rows_all = load(merged)
        n = [r for r in rows_all if r["platform"] == "naver"]
        a = [r for r in rows_all if r["platform"] == "aihub"]
        assert len(n) == 50 and n[0]["product_id"] == "nv-0000" and n[0]["date"] == "2020-07-31"
        assert len(a) == 9, a                                   # 2022-12-15·날짜 없음·SNS는 제외
        assert "SNS: 1건 [제외" in out and "날짜 없음 1건" in out, out
        assert {r["rating"] for r in a} == {1, 5, 4} and a[0]["date"] == "2021-10-10"
        assert a[0]["category"] == "패션 > 여성의류" and a[0]["product_name"] == "티셔츠 4종세트"
        assert len({r["product_id"] for r in a}) == 2           # 상품명별로 묶임
        assert "합친 사람 리뷰" in out
        tasks = os.path.join(d, "tasks")
        run("make_ai_tasks.py", "make", "--human", merged,
            "--n", "12", "--generators", "chatgpt", "claude", "--out", tasks)
        path = os.path.join(tasks, "tasks_claude.csv")
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
        assert len(rows) == 12 and all(r["prompt"] and r["product_id"] for r in rows)
        assert {r["prompt_type"] for r in rows} <= {"scratch", "style", "rewrite"}
        for i, r in enumerate(rows):  # 사람이 채운 것처럼
            r["text"] = f"생성된 리뷰 {i}입니다" if i % 3 else ""
            r["model_version"] = "claude-test"
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        run("make_ai_tasks.py", "merge", path, "--out", raw)
        ai = load(os.path.join(raw, "ai_claude.jsonl"))
        assert len(ai) == 8 and all(r["generator"] == "claude" and r["product_id"] for r in ai)
        # 채운 작업표는 덮어쓰지 않음 → --batch 로 새 묶음, 이전 기준 리뷰는 피함
        r = subprocess.run([PY, "make_ai_tasks.py", "make", "--human", merged,
                            "--n", "5", "--generators", "claude", "--out", tasks], cwd=ROOT, capture_output=True, text=True)
        assert r.returncode != 0 and "덮어쓰지 않습니다" in (r.stdout + r.stderr), r.stdout + r.stderr
        run("make_ai_tasks.py", "make", "--human", merged,
            "--n", "5", "--generators", "claude", "--batch", "b2", "--out", tasks)
        b2 = list(csv.DictReader(open(os.path.join(tasks, "tasks_claude_b2.csv"), encoding="utf-8-sig")))
        assert len(b2) == 5 and b2[0]["task_id"].startswith("claude-b2-")
        assert not {x["anchor_id"] for x in b2} & {x["anchor_id"] for x in rows}
        assert len(load(os.path.join(raw, "ai_claude.jsonl"))) == 8  # 원래 작업표는 그대로
    print("✓ convert_sources(AI Hub·네이버 → 파일 하나) + make_ai_tasks(작업표 만들기·합치기·추가 묶음)")


def test_fill_ai_tasks():
    """API 대신 가짜 응답기로: 빈 칸 채우기·모델 번갈아·거절 기록·이어서 하기·merge 호환."""
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "tasks_claude.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["task_id", "generator", "product_id", "prompt", "text", "model_version"])
            for i in range(9):
                prompt = "이건 거절해 줘" if i == 4 else ("말로 거절하는 경우" if i == 7 else f"리뷰 써 줘 {i}")
                w.writerow([f"claude-{i:05d}", "claude", f"p{i}", prompt,
                            "이미 채움" if i == 0 else ("가짜 리뷰라 도와드리기 어렵습니다" if i == 8 else ""), "m0" if i in (0, 8) else ""])
        out = run("fill_ai_tasks.py", path, "--provider", "fake", "--models", "a", "b", "--limit", "5", "--save-every", "2")
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
        assert rows[0]["text"] == "이미 채움" and rows[0]["model_version"] == "m0"   # 채운 칸은 건드리지 않음
        filled = [r for r in rows[1:6] if r["text"]]
        assert len(filled) == 4 and rows[4]["api_note"].startswith("refusal"), rows   # 4번은 거절로 기록
        assert {r["model_version"] for r in filled} == {"a", "b"}                     # 모델 번갈아
        assert all(not r["text"] for r in rows[6:])                                   # --limit 5
        assert rows[8]["api_note"] == "text_refusal"                                  # 예전에 저장된 거절 문구는 비움
        assert "거절 문구가 저장된 1행" in out
        run("fill_ai_tasks.py", path, "--provider", "fake", "--models", "a", "b")     # 이어서: 나머지만
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
        assert sum(1 for r in rows if r["text"]) == 6 and not rows[4]["text"], "남은 빈 칸 = 거절 3건"
        assert rows[7]["api_note"] == "text_refusal" and not rows[7]["text"]          # 말로 한 거절은 리뷰로 저장 안 함
        run("make_ai_tasks.py", "merge", path, "--out", d)
        assert len(load(os.path.join(d, "ai_claude.jsonl"))) == 6
        assert "실제 답한 모델" in out
    # 붐비는 모델은 2번 연달아 실패하면 이번 실행에서 건너뛰고, 다른 모델은 계속
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "tasks_gemini.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["task_id", "generator", "product_id", "prompt", "text"])
            for i in range(12):
                w.writerow([f"gemini-{i:05d}", "gemini", f"p{i}", f"리뷰 써 줘 {i}", ""])
        os.environ["FILL_RETRY_BASE_S"] = "0.01"
        try:
            # 붐비는 모델을 앞에 둬도(시험 요청이 그 모델로 가도) 멈추지 않고 다른 모델로 계속
            out = run("fill_ai_tasks.py", path, "--provider", "fake", "--models", "busy-model", "ok-model", "--concurrency", "1")
        finally:
            os.environ.pop("FILL_RETRY_BASE_S", None)
        rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
        ok = [r for i, r in enumerate(rows) if i % 2 == 1]
        busy = [r for i, r in enumerate(rows) if i % 2 == 0]
        assert all(r["text"] for r in ok), ok                                         # 다른 모델은 끝까지 채움
        assert not any(r["text"] for r in busy) and all(r["api_note"] for r in busy)  # 붐비는 모델 행은 기록만
        assert "⏸ busy-model" in out and "--retry-failed" in out, out
    # 요청 한도(429): 속도를 줄여 결국 모두 채움 / 하루 한도 소진 모델은 빼고 다른 모델이 대신
    with tempfile.TemporaryDirectory() as d:
        def sheet(name, n):
            path = os.path.join(d, name)
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f)
                w.writerow(["task_id", "generator", "product_id", "prompt", "text"])
                for i in range(n):
                    w.writerow([f"gemini-{i:05d}", "gemini", f"p{i}", f"리뷰 써 줘 {i}", ""])
            return path
        os.environ["FILL_RETRY_BASE_S"] = "0.01"
        try:
            lim = sheet("lim.csv", 10)
            out = run("fill_ai_tasks.py", lim, "--provider", "fake", "--models", "limited-model")
            rows = list(csv.DictReader(open(lim, encoding="utf-8-sig")))
            assert all(r["text"] for r in rows), (out, rows)                          # 429가 와도 빠짐없이
            day = sheet("day.csv", 8)
            out = run("fill_ai_tasks.py", day, "--provider", "fake", "--models", "daily-model", "ok-model", "--reassign-busy")
            rows = list(csv.DictReader(open(day, encoding="utf-8-sig")))
            assert rows[0]["api_note"] == "quota_day" and all(r["text"] for r in rows[1:]), (out, rows)
            assert {r["model_version"] for r in rows[1:]} == {"ok-model"} and "하루 한도" in out
        finally:
            os.environ.pop("FILL_RETRY_BASE_S", None)
    print("✓ fill_ai_tasks(빈 칸만 채우기·모델 번갈아·거절 기록·이어서 하기·붐비는 모델 건너뛰기·요청 한도·하루 한도)")



def test_anchor_mix_and_matching():
    """쿠팡 몫을 카테고리마다 고르게 + 사람 리뷰를 AI와 같은 플랫폼·카테고리에서 뽑기."""
    with tempfile.TemporaryDirectory() as d:
        raw = os.path.join(d, "raw")
        os.makedirs(raw)
        with open(os.path.join(raw, "naver_human.jsonl"), "w", encoding="utf-8") as f:
            for i in range(2000):
                f.write(json.dumps({"text": f"네이버 리뷰 {i} 좋아요 배송 빨라요", "product_id": f"nv-{i}", "platform": "naver",
                                    "date": "2020-07-31", "rating": 1 + i % 5, "source_id": f"nv-{i}"}, ensure_ascii=False) + "\n")
        with open(os.path.join(raw, "coupang_human.jsonl"), "w", encoding="utf-8") as f:
            for i in range(300):
                cat = "건강식품" if i < 270 else "주방"  # 건강식품이 90%
                f.write(json.dumps({"text": f"{cat} 리뷰 {i} 괜찮네요 재구매 의사 있어요", "product_id": f"cp-{i // 10}", "platform": "coupang",
                                    "date": "2021-05-01", "rating": 1 + i % 5, "category": cat, "product_name": f"{cat} 상품",
                                    "source_id": f"cp-{i}"}, ensure_ascii=False) + "\n")
        tasks = os.path.join(d, "tasks")
        out = run("make_ai_tasks.py", "make", "--human", os.path.join(raw, "naver_human.jsonl"), os.path.join(raw, "coupang_human.jsonl"),
                  "--n", "400", "--generators", "claude", "--out", tasks)
        rows = list(csv.DictReader(open(os.path.join(tasks, "tasks_claude.csv"), encoding="utf-8-sig")))
        plat = Counter(r["platform"] for r in rows)
        cats = Counter(r["category"] for r in rows if r["platform"] == "coupang")
        assert 100 < plat["coupang"] < 200, plat          # 기본 50%지만 주방(30건)이 상한에 걸려 일부는 네이버로
        assert 5 <= cats["주방"] <= 25, cats               # 사람 리뷰 30건의 절반(15) 근처까지만
        assert cats["건강식품"] > 100, cats                # 넘친 몫은 여유 있는 카테고리로
        assert "몫을 줄인 출처" in out, out
        for i, r in enumerate(rows):
            r["text"] = f"AI가 쓴 {r['category'] or '네이버'} 리뷰 {i} 정말 만족스러워요"
        with open(os.path.join(tasks, "tasks_claude.csv"), "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        run("make_ai_tasks.py", "merge", os.path.join(tasks, "tasks_claude.csv"), "--out", raw)
        o = os.path.join(d, "p")
        run("prepare_data.py", "--human-reviews", os.path.join(raw, "naver_human.jsonl"), os.path.join(raw, "coupang_human.jsonl"),
            "--ai-reviews", os.path.join(raw, "ai_claude.jsonl"), "--out", o)
        allrows = [x for k in ("train", "val", "test") for x in load(os.path.join(o, f"stage2_{k}.jsonl"))]
        hp = Counter((x["platform"], x.get("category", "")) for x in allrows if x["label"] == 0)
        ap_ = Counter((x["platform"], x.get("category", "")) for x in allrows if x["label"] == 1)
        for k, n in ap_.items():  # 사람 쪽 출처 분포가 AI 쪽과 거의 같아야 함
            assert abs(hp[k] - n) <= max(5, 0.15 * n), (k, hp[k], n, hp, ap_)
    print("✓ 기준 리뷰 출처 고르게(쿠팡 카테고리별) + 사람 리뷰를 AI와 같은 출처에서 뽑기")


def test_compile():
    for f in ("train.py", "evaluate.py", "xdac_baseline.py", "prepare_data.py", "metrics.py", "predictor.py", "app.py",
              "convert_sources.py", "make_ai_tasks.py", "fill_ai_tasks.py", "export_for_service.py", "download_lgc.py"):
        py_compile.compile(os.path.join(ROOT, f), doraise=True)
    print("✓ 문법 검사 (train.py 등)")


if __name__ == "__main__":
    test_metrics()
    test_thresholds_and_verdict()
    test_compile()
    test_inspect_lgc()
    test_lgc_ai_only()
    test_newlines_auto()
    test_convert_and_tasks()
    test_anchor_mix_and_matching()
    test_fill_ai_tasks()
    test_prepare_and_evaluate()
    print("\n모든 점검 통과")
