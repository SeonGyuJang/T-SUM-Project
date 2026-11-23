"""XDAC_obs(LGC 데이터 + XDAC 모델)를 내려받고 LGC 구조를 확인합니다.

사전 준비 (한 번만):
  1) https://huggingface.co/keepsteady/XDAC_obs 에서 로그인 후 접근 조건에 동의(자동 승인)
  2) 터미널에서  huggingface-cli login   (또는 hf auth login)  → 토큰 입력

  python download_lgc.py                 # model/data/raw/XDAC_obs 에 내려받고 LGC 필드·라벨 값을 출력
  python download_lgc.py --inspect-only  # 이미 받은 파일 구조만 다시 보기
  (저장소 루트에서는: python model/kor-ai-detector/download_lgc.py)
"""
import argparse
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
# 다른 원천 데이터(네이버·쿠팡)와 같은 곳: model/data/raw/ (git에 올라가지 않음)
XDAC_DIR = os.path.join(os.path.dirname(ROOT), "data", "raw", "XDAC_obs")
LGC_REL = os.path.join("LGC_data", "LGC_data_v1.0.json")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dir", default=XDAC_DIR, help="저장 폴더 (기본 model/data/raw/XDAC_obs)")
    ap.add_argument("--inspect-only", action="store_true")
    args = ap.parse_args()

    if not args.inspect_only:
        try:
            from huggingface_hub import snapshot_download
        except ImportError:
            sys.exit("pip install huggingface_hub 가 필요합니다.")
        try:
            snapshot_download(repo_id="keepsteady/XDAC_obs", local_dir=args.dir)
        except Exception as e:  # 접근 승인·로그인 문제를 알기 쉽게
            msg = str(e)
            if "401" in msg or "403" in msg or "gated" in msg.lower() or "restricted" in msg.lower():
                sys.exit("내려받기 실패: 접근 권한이 없습니다.\n"
                         "  1) https://huggingface.co/keepsteady/XDAC_obs 에서 로그인 후 조건 동의\n"
                         "  2) huggingface-cli login 으로 토큰 등록\n"
                         f"  (원래 오류: {msg[:200]})")
            raise
    lgc = os.path.join(args.dir, LGC_REL)
    if not os.path.exists(lgc):
        found = [os.path.join(dp, f) for dp, _, fs in os.walk(args.dir) for f in fs if f.endswith((".json", ".jsonl"))]
        sys.exit(f"{lgc} 가 없습니다. 받은 JSON 파일: {found[:10]}")
    print(f"LGC 파일: {lgc} ({os.path.getsize(lgc) / 1e6:.0f} MB)")
    print(f"  prepare_data.py 에는 --lgc {os.path.relpath(lgc, ROOT)}  (kor-ai-detector 폴더 기준)\n")
    subprocess.run([sys.executable, os.path.join(ROOT, "prepare_data.py"), "--lgc", lgc, "--inspect-lgc"], check=True)


if __name__ == "__main__":
    main()
