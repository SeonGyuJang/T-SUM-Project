"""GPU·모델 없이 돌아가는 점검: 데이터 준비 → 분할 규칙 → 지표 → 평가 리포트.

python tests/smoke_test.py
"""
import csv
import json
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


def test_compile():
    for f in ("train.py", "evaluate.py", "xdac_baseline.py", "prepare_data.py", "metrics.py"):
        py_compile.compile(os.path.join(ROOT, f), doraise=True)
    print("✓ 문법 검사 (train.py 등)")


if __name__ == "__main__":
    test_metrics()
    test_compile()
    test_prepare_and_evaluate()
    print("\n모든 점검 통과")
