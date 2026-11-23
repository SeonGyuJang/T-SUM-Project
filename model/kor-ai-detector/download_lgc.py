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


def list_dir(d, limit=40):
    """받은 폴더 내용(진단용). 숨김 캐시 폴더는 뺀다."""
    out = []
    for dp, dns, fs in os.walk(d):
        dns[:] = [x for x in dns if not x.startswith(".")]
        for f in fs:
            p = os.path.join(dp, f)
            out.append(f"  {os.path.relpath(p, d)}  ({os.path.getsize(p) / 1e6:.1f} MB)")
    return out[:limit]


def xdac_path_from_module(d):
    """모델 카드 방식 그대로: `from XDAC_obs.xdac_encrypted import get_xdac_path; get_xdac_path()`.
    이 저장소는 LGC 데이터·XDAC-D/A 모델을 저장소 파일이 아니라 이 함수가 알려 주는 위치에 둔다(필요하면 이때 내려받음)."""
    mod_file = os.path.join(d, "xdac_encrypted.py")
    if not os.path.exists(mod_file):
        print(f"  · {mod_file} 가 없습니다(내려받기가 덜 됐을 수 있음).")
        return None
    import importlib

    parent, pkg = os.path.dirname(os.path.abspath(d)), os.path.basename(os.path.abspath(d))
    sys.path.insert(0, parent)
    try:
        mod = importlib.import_module(f"{pkg}.xdac_encrypted") if pkg.isidentifier() else None
        if mod is None:
            import importlib.util

            spec = importlib.util.spec_from_file_location("xdac_encrypted", mod_file)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
        print("  · get_xdac_path() 호출 중… (처음이면 XDAC 쪽에서 데이터·모델을 내려받아 시간이 걸릴 수 있어요)", flush=True)
        path = mod.get_xdac_path()
        print(f"  · get_xdac_path() → {path}")
        return str(path)
    except ModuleNotFoundError as e:
        print(f"  ⚠ xdac_encrypted.py를 불러오려면 패키지가 더 필요해요: {e.name}  →  pip install torch transformers captum")
    except Exception as e:  # 원인을 보여 주고 다른 위치를 계속 찾는다
        print(f"  ⚠ get_xdac_path() 실패: {type(e).__name__}: {str(e)[:300]}")
    return None


def locate_lgc(d):
    """LGC 파일 찾기: 받은 폴더 → get_xdac_path() 위치 → 캐시 폴더. 다른 곳에서 찾으면 표준 위치로 복사."""
    import glob
    import shutil

    std = os.path.join(d, LGC_REL)
    if os.path.exists(std):
        return std
    cands = []
    root = xdac_path_from_module(d)
    if root:
        cands.append(os.path.join(root, LGC_REL))
        cands += glob.glob(os.path.join(root, "**", "LGC_data_v*.json"), recursive=True)
    for base in (d, os.path.expanduser("~/.cache"), os.path.expanduser("~/XDAC_obs"), os.getcwd()):
        cands += glob.glob(os.path.join(base, "**", "LGC_data_v*.json"), recursive=True)
    found = next((c for c in cands if os.path.isfile(c)), None)
    if not found:
        print(f"\n{std} 를 찾지 못했어요. 받은 폴더({d}) 내용:")
        print("\n".join(list_dir(d)) or "  (비어 있음)")
        sys.exit("\n→ 위 목록과 오류 메시지를 보내 주세요. (LGC는 저장소 파일이 아니라 xdac_encrypted.py의 get_xdac_path()가 알려 주는 위치에 있어요)")
    os.makedirs(os.path.dirname(std), exist_ok=True)
    print(f"  · LGC 파일을 찾았어요: {found}\n  · 표준 위치로 복사: {std}")
    shutil.copy2(found, std)
    return std


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
    lgc = locate_lgc(args.dir)
    print(f"LGC 파일: {lgc} ({os.path.getsize(lgc) / 1e6:.0f} MB)")
    print(f"  prepare_data.py 에는 --lgc {os.path.relpath(lgc, ROOT)}  (kor-ai-detector 폴더 기준)\n")
    subprocess.run([sys.executable, os.path.join(ROOT, "prepare_data.py"), "--lgc", lgc, "--inspect-lgc"], check=True)


if __name__ == "__main__":
    main()
