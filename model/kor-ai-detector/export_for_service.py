"""학습한 모델을 홈페이지(service)가 읽는 아티팩트 형식으로 내보냅니다 (MODEL_DEV.md 4.12.3).

  python export_for_service.py --model models/stage2 --report reports/stage2/report.json --version det-ko-review-v1.0
  → ../artifacts/det-ko-review-v1.0/  (manifest.json + encoder/)

service 쪽 설정(service/.env):
  DETECTOR_MODE=inprocess
  MODEL_ARTIFACT_PATH=../model/artifacts/det-ko-review-v1.0
  (service 가상환경에 pip install -e ../model 과 torch·transformers 필요)

service는 realstar_model.inference.Detector로 이 폴더를 연다. Detector는 점수 = logit(AI) − logit(사람)에
보정(a=1, b=0)을 적용하므로 결과 P(AI)가 이 모델의 softmax 확률과 같고, 임계값도 report.json 값을 그대로 쓴다.
"""
import _winconsole  # noqa: F401  윈도우(cp949) 출력에서 기호 때문에 멈추지 않게
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="train.py 결과 폴더")
    ap.add_argument("--report", required=True, help="evaluate.py가 만든 report.json (임계값)")
    ap.add_argument("--version", default="det-ko-review-v1.0", help="det-ko-review-vMAJOR.MINOR")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(ROOT), "artifacts"))
    args = ap.parse_args()
    if not args.version.startswith("det-ko-review-v"):
        ap.error("--version 은 det-ko-review-v 로 시작해야 합니다(service 계약).")
    rep = json.load(open(args.report, encoding="utf-8"))
    th = rep.get("thresholds") or {"T_AI": rep["threshold"], "T_HUMAN": rep["threshold"]}
    cfg_path = os.path.join(args.model, "train_config.json")
    cfg = json.load(open(cfg_path, encoding="utf-8")) if os.path.exists(cfg_path) else {}
    newlines = cfg.get("preprocess", {}).get("newlines", "keep")
    spaces = cfg.get("preprocess", {}).get("spaces", "keep")
    if newlines != "space" or spaces != "collapse":
        print("⚠ 이 모델은 줄바꿈·연속 공백을 그대로 둔 채 학습됐는데, service 전처리(clean_review)는 둘 다 공백 하나로 바꿉니다.\n"
              "  학습 때 본 글과 서비스에서 보는 글이 달라 점수가 달라질 수 있어요. prepare_data.py 기본값(--newlines space --spaces collapse)으로\n"
              "  데이터를 다시 만들고 학습하면 같아집니다.")
    dst = os.path.join(args.out, args.version)
    enc = os.path.join(dst, "encoder")
    if os.path.exists(enc):
        shutil.rmtree(enc)
    os.makedirs(dst, exist_ok=True)
    shutil.copytree(args.model, enc, ignore=shutil.ignore_patterns("checkpoints", "*.pt", "optimizer*", "scheduler*", "rng_state*"))
    t = {"T_AI": round(float(th["T_AI"]), 6), "T_HUMAN": round(float(th["T_HUMAN"]), 6)}
    test_metrics = {name: {k: v.get(k) for k in ("auroc", "tpr", "fpr")} for name, x in rep.get("tests", {}).items()
                    for v in [x["overall"]]}
    manifest = {
        "model_version": args.version, "model_type": "encoder", "source": "kor-ai-detector",
        "created_at": datetime.now(timezone(timedelta(hours=9))).isoformat(timespec="seconds"),
        "encoder_id": cfg.get("args", {}).get("model"), "max_length": int(cfg.get("max_len") or cfg.get("args", {}).get("max_len", 256)),
        "calibration": {"a": 1.0, "b": 0.0},  # Detector: sigmoid(logit_ai - logit_human) = softmax P(AI)
        "thresholds": {"S": t, "M": t, "L": t, "ALL": t}, "min_chars": int(rep.get("min_chars", 20)),
        "target_fpr": rep.get("target_fpr"), "ai_miss": rep.get("ai_miss"), "train_preprocess": {"newlines": newlines, "spaces": spaces},
        "metrics_summary": {"val": {k: rep["val"].get(k) for k in ("auroc", "tpr", "fpr")}, "tests": test_metrics},
    }
    with open(os.path.join(dst, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"내보내기 완료 → {dst}\n  service/.env: DETECTOR_MODE=inprocess, MODEL_ARTIFACT_PATH={os.path.relpath(dst, os.path.join(os.path.dirname(os.path.dirname(ROOT)), 'service'))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
