"""AI 리뷰 작업표(make_ai_tasks.py make)의 빈 text 칸을 API로 채웁니다. 손으로 붙여 넣는 대신.

  pip install anthropic            # Claude      (키: ANTHROPIC_API_KEY)
  pip install openai               # ChatGPT     (키: OPENAI_API_KEY)
  pip install google-genai         # Gemini      (키: GEMINI_API_KEY)

  python fill_ai_tasks.py data/ai_tasks/tasks_claude.csv  --dry-run          # 프롬프트 2개만 보기 (API 호출 없음)
  python fill_ai_tasks.py data/ai_tasks/tasks_claude.csv  --limit 20         # 시험 20건
  python fill_ai_tasks.py data/ai_tasks/tasks_claude.csv                     # 나머지 전부 (기본 claude-opus-5-5)
  python fill_ai_tasks.py data/ai_tasks/tasks_chatgpt.csv --models <OpenAI 모델> [<모델2> …]
  python fill_ai_tasks.py data/ai_tasks/tasks_gemini.csv  --models <Gemini 모델> [<모델2> …]
  → 다 되면 python make_ai_tasks.py merge data/ai_tasks/tasks_*.csv

- 어느 API를 쓸지는 작업표의 generator 칸(chatgpt·claude·gemini)으로 정합니다.
- 행마다 새 대화로 하나씩 요청합니다(여러 개를 한 번에 받으면 비슷해짐). --models 를 여러 개 주면 행을 번갈아 나눠 맡깁니다
  (가벼운 모델과 상위 모델을 섞으면 탐지 모델이 특정 모델 말투만 외우는 것을 줄입니다).
- 실제로 답한 모델명을 model_version 칸에 적습니다. 거절·오류는 api_note 칸에 적고 다음 행으로 넘어갑니다.
- 몇 건마다 작업표에 바로 저장합니다. 중간에 끊겨도(Ctrl+C 포함) 다시 실행하면 빈 칸만 이어서 채웁니다.
  거절·오류로 넘어간 행까지 다시 시도하려면 --retry-failed.
- 요청 한도(429)·서버 오류(5xx)는 기다렸다 다시 시도하고, 키·모델명 오류(401·403·404·400)는 바로 멈춥니다.
"""
import argparse
import csv
import os
import re
import sys
import threading
import time
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait

PROVIDER_OF = {"chatgpt": "openai", "gpt": "openai", "openai": "openai", "claude": "anthropic", "gemini": "google"}
DEFAULT_MODELS = {"anthropic": ["claude-opus-5-5"]}  # OpenAI·Gemini는 쓸 모델을 --models 로 직접 정합니다
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "google": "GEMINI_API_KEY"}
INSTALL = {"anthropic": "anthropic", "openai": "openai", "google": "google-genai"}
# 서버 쪽 거절 시 다른 모델로 이어 주는 기능(fallbacks)을 받는 Claude 모델
CLAUDE_FALLBACK_MODELS = {"claude-fable-5-2", "claude-fable-5-1", "claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5"}
FATAL_STATUS = {400, 401, 403, 404}
RETRY_BASE_S = float(os.environ.get("FILL_RETRY_BASE_S", "10"))  # 재시도 대기(초). 테스트에서만 줄임
BUSY_NOTES = {"error(503)", "error(429)", "error(504)", "error(500)", "error(502)"}
TIMEOUT_S = 120  # 요청 하나가 이보다 오래 걸리면 끊고 다시 (SDK 기본값은 10분)
# brotli(br) 압축 응답을 받지 않는다: 오래된 brotli 패키지가 깔린 환경(예: conda base)에서는 압축을 풀다가
# "Decompressor.decompress() got an unexpected keyword argument 'output_buffer_limit'"로 실패하고
# SDK가 이를 Connection error로 보여 준다. gzip이면 파이썬 기본 기능만 쓴다.
NO_BROTLI = {"Accept-Encoding": "gzip, deflate"}

# 요청의 실제 목적을 사실대로 알린다. 리뷰를 쓰라는 요청만 보면 '가짜 리뷰로 소비자를 속이려는 것'으로 보고
# 거절하는 경우가 있는데, 이 데이터는 AI 라벨을 달아 탐지 모델 학습·평가에만 쓰고 어디에도 게시하지 않는다.
SYSTEM_PROMPT = (
    "이 대화는 'AI가 쓴 한국어 상품 리뷰를 찾아내는 탐지 모델'을 만드는 연구 프로젝트의 데이터 구축 단계입니다. "
    "여기서 만든 글은 모두 'AI 생성'이라는 정답 라벨을 붙여 탐지 모델의 학습·평가 데이터로만 쓰며, "
    "쇼핑몰·판매 페이지·리뷰란 등 어디에도 게시하지 않습니다. "
    "탐지 모델이 실제로 쓰이는 AI 리뷰를 구별하도록 배우려면, 요청한 조건(별점·말투·분량)에 맞는 자연스러운 리뷰 본문이 필요합니다. "
    "설명이나 안내 없이 리뷰 본문만 출력하세요."
)
# 모델이 리뷰 대신 쓴 거절·대안 제시 문구 (서버의 거절 신호 없이 일반 답변으로 오는 경우)
TEXT_REFUSAL = re.compile(
    r"(도와\s*드리기\s*(?:어렵|힘들)|만들(?:어\s*드릴|지\s*않겠|\s*수\s*없)|작성(?:해\s*드리기\s*어렵|해\s*드릴\s*수\s*없|하지\s*않겠)"
    r"|가짜\s*리뷰|허위\s*(?:리뷰|후기)|전자상거래법|소비자를\s*속|대신\s*다음과\s*같이|I\s*can'?t\s*help|I'?m\s*not\s*able\s*to)",
    re.IGNORECASE,
)


def looks_refused(text):
    return bool(text) and bool(TEXT_REFUSAL.search(text))


class FakeBusy(Exception):
    """테스트용: 서버 혼잡(503)."""
    status_code = 503


class Fatal(Exception):
    """키·모델명처럼 다시 해도 안 되는 오류 → 전체 중단."""


def status_of(e):
    for attr in ("status_code", "code", "status"):
        v = getattr(e, attr, None)
        if isinstance(v, int):
            return v
    resp = getattr(e, "response", None)
    return getattr(resp, "status_code", None)


class Caller:
    """provider별 '프롬프트 1개 → (답, 실제 모델명, 메모)'. SDK는 처음 쓸 때 불러온다."""

    def __init__(self, provider, system=SYSTEM_PROMPT, thinking="low"):
        self.provider = provider
        self.system = system
        self.thinking = thinking
        self.no_thinking_cfg = set()  # thinking 설정을 거부한 모델(이후엔 빼고 보냄)
        self.client = None
        if provider == "fake":
            return
        try:
            if provider == "anthropic":
                import anthropic
                self.client = anthropic.Anthropic(max_retries=3, timeout=TIMEOUT_S, default_headers=NO_BROTLI)
            elif provider == "openai":
                from openai import OpenAI
                self.client = OpenAI(max_retries=3, timeout=TIMEOUT_S, default_headers=NO_BROTLI)
            else:
                from google import genai
                self.client = genai.Client(http_options={"timeout": TIMEOUT_S * 1000, "headers": NO_BROTLI})  # 밀리초
        except ImportError:
            sys.exit(f"pip install {INSTALL[provider]}  이 필요합니다.")
        except Exception as e:  # 키가 없으면 클라이언트 생성에서 바로 실패하는 SDK가 있다
            sys.exit(f"{provider} 클라이언트를 만들지 못했어요: {e}\n→ 환경 변수 {KEY_ENV[provider]} 에 API 키를 넣었는지 확인하세요.")

    def __call__(self, model, prompt):
        text, served, note = self._raw(model, prompt)
        if looks_refused(text):  # 거절 문구를 리뷰로 저장하지 않는다
            return None, served, "text_refusal"
        return text, served, note

    def _raw(self, model, prompt):
        if self.provider == "fake":  # 테스트용
            if model == "busy-model":
                raise FakeBusy()
            if "말로 거절" in prompt:
                return "이 요청은 가짜 리뷰를 만드는 일이라 도와드리기 어렵습니다.", model, ""
            if "거절" in prompt:
                return None, model, "refusal"
            return f"[{model}] 생성 리뷰 {abs(hash(prompt)) % 1000}", model, ""
        if self.provider == "anthropic":
            return self._claude(model, prompt)
        if self.provider == "openai":
            msgs = ([{"role": "system", "content": self.system}] if self.system else []) + [{"role": "user", "content": prompt}]
            r = self.client.chat.completions.create(model=model, messages=msgs)
            ch = r.choices[0]
            if ch.finish_reason == "content_filter" or not (ch.message.content or "").strip():
                return None, r.model, f"empty({ch.finish_reason})"
            return ch.message.content.strip(), r.model, ""
        r = self._gemini(model, prompt)
        text = (getattr(r, "text", None) or "").strip()
        served = getattr(r, "model_version", None) or model
        if not text:
            fb = getattr(r, "prompt_feedback", None)
            return None, served, f"empty({getattr(fb, 'block_reason', None) or 'no text'})"
        return text, served, ""

    def gemini_thinking(self, model):
        """짧은 리뷰라 '생각' 단계를 최소로: 2.x는 thinking_budget(pro는 0이 안 돼 최소 128), 3.x 이후는 thinking_level=low.
        Gemini의 생각 단계가 응답을 수십 초씩 늦추는 주원인이다."""
        if self.thinking != "low" or model in self.no_thinking_cfg:
            return None
        if model.startswith("gemini-2"):
            return {"thinking_budget": 128 if "pro" in model else 0}
        return {"thinking_level": "low"}

    def _gemini(self, model, prompt):
        cfg = {}
        if self.system:
            cfg["system_instruction"] = self.system
        th = self.gemini_thinking(model)
        if th:
            cfg["thinking_config"] = th
        try:
            return self.client.models.generate_content(model=model, contents=prompt, config=cfg or None)
        except Exception as e:  # 이 모델이 thinking 설정을 안 받으면 빼고 다시(이후 계속 뺌)
            if th and status_of(e) == 400 and "think" in str(e).lower():
                self.no_thinking_cfg.add(model)
                cfg.pop("thinking_config", None)
                return self.client.models.generate_content(model=model, contents=prompt, config=cfg or None)
            raise

    def _claude(self, model, prompt):
        kwargs = {"model": model, "max_tokens": 16000, "output_config": {"effort": "low"},  # 짧은 리뷰라 low
                  "messages": [{"role": "user", "content": prompt}]}
        if self.system:
            kwargs["system"] = self.system
        if model in CLAUDE_FALLBACK_MODELS:  # 안전 분류기가 거절하면 서버가 다른 모델로 이어서 답함
            r = self.client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **kwargs)
        else:
            r = self.client.messages.create(**kwargs)
        if r.stop_reason == "refusal":
            cat = getattr(getattr(r, "stop_details", None), "category", None)
            return None, r.model, f"refusal({cat})"
        if r.stop_reason == "max_tokens":
            return None, r.model, "max_tokens"
        text = "".join(b.text for b in r.content if b.type == "text").strip()
        return (text or None), r.model, "" if text else "empty"


def root_cause(e):
    """SDK의 'Connection error.' 뒤에 숨은 실제 원인(SSL 인증서·DNS·프록시 등)."""
    seen = set()
    while (e.__cause__ or e.__context__) is not None and id(e) not in seen:
        seen.add(id(e))
        e = e.__cause__ or e.__context__
    return e


def describe(e):
    code = status_of(e)
    msg = f"{type(e).__name__}{f' ({code})' if code else ''}: {str(e)[:200]}"
    root = root_cause(e)
    if root is not e:
        msg += f"  ← 원인: {type(root).__name__}: {str(root)[:200]}"
    return msg


def retryable(e):
    """요청 한도·서버 오류·연결/시간 초과만 다시 해 볼 만하다. 키 없음(TypeError)·모델명 오류(4xx) 등은 아님."""
    code = status_of(e)
    if code is not None:
        return code == 429 or code >= 500 or code in (408, 409)
    name = type(e).__name__.lower()
    return any(k in name for k in ("connection", "timeout", "timedout", "servererror", "unavailable"))


def call_with_retry(caller, model, prompt, tries=3, log=print, tag=""):
    """SDK 자체 재시도 뒤에도 429·5xx·연결 오류면 조금 더 기다렸다 다시. 그 밖의 오류는 Fatal(전체 중단)."""
    for attempt in range(tries):
        try:
            return caller(model, prompt)
        except Exception as e:
            if not retryable(e):
                raise Fatal(describe(e)) from e
            if attempt == tries - 1:
                log(f"  ✗ {tag} {describe(e)[:160]} → 건너뜀")
                return None, model, f"error({status_of(e) or type(e).__name__})"
            wait_s = min(60, RETRY_BASE_S * 2 ** attempt)
            log(f"  ↻ {tag} {describe(e)[:120]} → {wait_s}초 뒤 다시")
            time.sleep(wait_s)
    return None, model, "error"


def hint(provider):
    env = KEY_ENV.get(provider, "")
    return (f"→ 확인할 것: ① 이 터미널에 키가 있는지  echo ${env}  (새 터미널·conda 환경을 바꾸면 export를 다시 해야 함)\n"
            f"           ② 모델 ID 철자  ③ 계정에 결제·사용 한도가 남아 있는지")


def network_hint(caller):
    base = str(getattr(caller.client, "base_url", "") or "")
    proxies = [k for k in os.environ if k.lower() in ("http_proxy", "https_proxy", "all_proxy", "no_proxy")]
    over = [k for k in os.environ if k.endswith("_BASE_URL")]
    lines = ["→ 연결 문제 확인:",
             f"  · 접속 주소: {base or '(기본)'}" + ("  ← 환경 변수 " + ", ".join(over) + " 가 주소를 바꾸고 있어요" if over else ""),
             f"  · 프록시 환경 변수: {', '.join(proxies) if proxies else '없음'}",
             "  · 원인에 decompress·output_buffer_limit 가 있으면 오래된 brotli 패키지 →  pip install -U brotli brotlicffi",
             "  · 원인에 CERTIFICATE_VERIFY_FAILED 가 있으면 인증서 문제 →  pip install -U certifi  (python.org 파이썬이면 '/Applications/Python 3.x/Install Certificates.command' 실행)",
             "  · 원인에 nodename/Name or service/getaddrinfo 가 있으면 DNS·인터넷 문제 → VPN·와이파이·방화벽 확인",
             "  · 터미널에서 직접:  curl -sS -o /dev/null -w '%{http_code}\\n' https://api.anthropic.com/v1/messages   (숫자가 나오면 연결은 됨)"]
    return "\n".join(lines)


def save(path, fieldnames, rows):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8-sig", newline="") as f:  # 엑셀에서 한글이 깨지지 않게 BOM
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", help="make_ai_tasks.py가 만든 작업표 (tasks_<모델>.csv)")
    ap.add_argument("--models", nargs="+", help="쓸 모델 ID (여러 개면 행을 번갈아). Claude 기본 claude-opus-5-5")
    ap.add_argument("--provider", choices=["anthropic", "openai", "google", "fake"], help="보통 generator 칸으로 자동 결정")
    ap.add_argument("--limit", type=int, default=0, help="이번에 채울 최대 행 수 (시험용)")
    ap.add_argument("--concurrency", type=int, default=3,
                    help="모델마다 동시 요청 수 (요청 한도에 걸리면 줄이세요). 느린 모델이 빠른 모델을 막지 않게 모델별로 따로 셈")
    ap.add_argument("--save-every", type=int, default=10)
    ap.add_argument("--retry-failed", action="store_true", help="거절·오류로 넘어간 행(api_note 있음)도 다시 시도")
    ap.add_argument("--max-errors", type=int, default=20, help="오류가 이만큼 연달아 나면 멈춤")
    ap.add_argument("--thinking", choices=["low", "default"], default="low",
                    help="Gemini의 '생각' 단계: low(기본, 빠름) / default(모델 기본값, 느림). Claude는 늘 effort low")
    ap.add_argument("--busy-limit", type=int, default=2, help="한 모델이 붐빔(503·429·504)으로 이만큼 연달아 실패하면 이번 실행에서 그 모델은 건너뜀")
    ap.add_argument("--dry-run", action="store_true", help="API 호출 없이 프롬프트 2개만 출력")
    ap.add_argument("--no-system", action="store_true",
                    help="연구 목적 안내(시스템 프롬프트)를 빼고 보냄 — 손으로 채팅창에 붙여 넣는 것과 같은 조건")
    args = ap.parse_args()

    with open(args.csv, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
        fieldnames = list(reader.fieldnames or [])
    for extra in ("model_version", "api_note"):
        if extra not in fieldnames:
            fieldnames.append(extra)
    if not rows:
        sys.exit("작업표가 비어 있습니다.")
    gens = {(r.get("generator") or "").strip().lower() for r in rows}
    provider = args.provider or (PROVIDER_OF.get(gens.pop()) if len(gens) == 1 else None)
    if not provider:
        sys.exit(f"generator 칸으로 API를 정할 수 없어요({sorted(gens)}). --provider 를 주세요.")
    models = args.models or DEFAULT_MODELS.get(provider) or (["fake-model"] if provider == "fake" else None)
    if not models:
        sys.exit(f"{provider}는 쓸 모델을 --models 로 지정하세요 (해당 서비스 문서의 모델 ID).")

    # 예전 실행에서 거절 문구가 리뷰로 저장된 행을 비운다(다시 채우려면 --retry-failed)
    bad = [r for r in rows if looks_refused((r.get("text") or "").strip())]
    for r in bad:
        r["text"], r["api_note"] = "", "text_refusal"
    if bad:
        save(args.csv, fieldnames, rows)
        print(f"  · 이전에 리뷰 대신 거절 문구가 저장된 {len(bad)}행을 비웠어요 ({', '.join(r['task_id'] for r in bad[:5])}"
              f"{' …' if len(bad) > 5 else ''})")
    todo = [i for i, r in enumerate(rows)
            if not (r.get("text") or "").strip() and (args.retry_failed or not (r.get("api_note") or "").strip())]
    if args.limit:
        todo = todo[:args.limit]
    done = sum(1 for r in rows if (r.get("text") or "").strip())
    print(f"{args.csv}: 전체 {len(rows):,}행 · 채워짐 {done:,} · 이번에 채울 {len(todo):,} · {provider} {models}")
    if args.dry_run:
        if not args.no_system:
            print(f"\n[시스템 안내]\n{SYSTEM_PROMPT}")
        for i in todo[:2]:
            print(f"\n--- {rows[i]['task_id']} → {models[i % len(models)]}\n{rows[i]['prompt']}")
        return
    if not todo:
        print("채울 행이 없습니다.")
        return
    if provider != "fake" and not os.environ.get(KEY_ENV[provider]):
        # Claude는 `ant auth login` 프로필로도 되므로 경고만, 나머지는 키가 꼭 필요
        msg = f"환경 변수 {KEY_ENV[provider]} 가 비어 있어요. 이 터미널에서 export {KEY_ENV[provider]}=... 를 먼저 실행하세요."
        if provider != "anthropic":
            sys.exit(msg)
        print(f"  ⚠ {msg} (ant auth login 으로 로그인했다면 그대로 진행)")

    caller = Caller(provider, system=None if args.no_system else SYSTEM_PROMPT, thinking=args.thinking)
    stats, served = Counter(), Counter()
    state = {"since_save": 0, "streak": 0, "fatal": None}
    stop = threading.Event()

    def record(i, text, model, note):
        r = rows[i]
        if text:
            r["text"], r["model_version"], r["api_note"] = text, model, ""
            stats["ok"] += 1
            served[model] += 1
            state["streak"] = 0
        else:
            r["api_note"] = note
            stats[note.split("(")[0]] += 1
            state["streak"] = state["streak"] + 1 if note.startswith("error") and note not in BUSY_NOTES else 0
        state["since_save"] += 1
        if state["since_save"] >= args.save_every:
            save(args.csv, fieldnames, rows)
            state["since_save"] = 0

    # 1) 첫 행은 혼자 먼저 보내 본다: 키·모델명·네트워크 문제를 바로 보여 주기 위해
    first, todo = todo[0], todo[1:]
    model0 = models[first % len(models)]
    print(f"  첫 요청 시험 중… ({model0}, 최대 {TIMEOUT_S}초)", flush=True)
    t1 = time.time()
    try:
        text, served_model, note = call_with_retry(caller, model0, rows[first]["prompt"], tag=rows[first]["task_id"])
    except Fatal as e:
        if "(404)" in str(e) or "NOT_FOUND" in str(e):
            sys.exit(f"  ✗ 첫 요청 실패: {e}\n→ 키는 정상이에요. 모델 {model0} 을(를) 이 계정에서 쓸 수 없어요(이름이 틀렸거나, 신규 사용자에게 막힌 모델).\n"
                     f"  --models 에서 이 모델을 빼거나 다른 모델로 바꿔 다시 실행하세요. 이미 채운 행은 그대로 남아요.")
        sys.exit(f"  ✗ 첫 요청 실패: {e}\n{hint(provider)}")
    except KeyboardInterrupt:
        sys.exit("\n중단했어요.")
    if note in ("error(503)", "error(429)", "error(500)", "error(502)", "error(504)"):
        # 서버 혼잡·요청 한도: 네트워크 문제가 아니다. 아직 채운 게 없으니 모델 순서를 바꿔도 된다
        sys.exit(f"  ✗ 첫 요청이 {note}로 실패해서 멈춥니다. {model0} 서버가 지금 붐비거나(503) 요청 한도에 걸렸어요(429).\n"
                 f"  → 몇 분 뒤 같은 명령으로 다시 하거나, 다른 모델을 앞에 두고 시작하세요(예: --models {' '.join(models[1:] + models[:1])})."
                 f"\n    중간에 붐비는 행은 건너뛰고 api_note에 남으니, 나중에 --retry-failed 로 채우면 됩니다.")
    if note.startswith("error"):  # 연결이 안 되면 나머지를 보내 봐야 똑같다 → 진단을 보여 주고 멈춤
        sys.exit(f"  ✗ 첫 요청이 {note}로 실패해서 멈춥니다. 위 '원인'을 보세요.\n{network_hint(caller)}")
    record(first, text, served_model, note)
    save(args.csv, fieldnames, rows)
    shown = (text or note or "")[:60].replace("\n", " ")
    print(f"  ✓ {time.time() - t1:.1f}초 · {served_model} · {shown!r}", flush=True)

    # 2) 나머지는 동시에
    # 모델별 '붐빔' 차단기: 한 모델이 503·429·504로 연달아 실패하면 이번 실행에서는 그 모델 행을 바로 건너뛴다.
    # (붐비는 모델 행이 동시 요청 칸을 몇 분씩 붙잡아 다른 모델까지 멈추는 것을 막음. 건너뛴 행은 나중에 --retry-failed)
    busy_streak, paused, inflight = Counter(), set(), Counter()
    plock = threading.Lock()

    def work(i):
        if stop.is_set():
            return i, None, None, "skipped"
        model = models[i % len(models)]  # 행 번호로 번갈아 → 다시 실행해도 같은 행은 같은 모델
        if model in paused:
            return i, None, model, f"busy({model})"
        with plock:
            inflight[model] += 1
        try:
            tries = 1 if busy_streak[model] else 3  # 이미 붐비는 중이면 재시도로 시간을 쓰지 않는다
            res = call_with_retry(caller, model, rows[i]["prompt"], tries=tries, tag=rows[i]["task_id"])
        except Fatal as e:
            stop.set()
            state["fatal"] = str(e)
            return i, None, model, "fatal"
        finally:
            with plock:
                inflight[model] -= 1
        note = res[2]
        with plock:
            if note in BUSY_NOTES:
                busy_streak[model] += 1
                if busy_streak[model] >= args.busy_limit and model not in paused:
                    paused.add(model)
                    print(f"  ⏸ {model} 이(가) 계속 붐벼서(503·429·504) 이번 실행에서는 이 모델 행을 건너뜁니다."
                          f" 다른 모델은 계속해요. 나중에 --retry-failed 로 채우세요.", flush=True)
            elif res[0]:
                busy_streak[model] = 0
        return (i, *res)

    t0 = time.time()
    total = len(todo)
    n = 0
    # 모델마다 실행기를 따로 둔다: 느리거나 붐비는 모델이 요청 자리를 붙잡아도 다른 모델은 제 속도로 진행
    executors = {m: ThreadPoolExecutor(max_workers=max(1, args.concurrency)) for m in models}
    interrupted = False
    try:
        pending = {executors[models[i % len(models)]].submit(work, i) for i in todo}
        while pending:
            finished, pending = wait(pending, timeout=15, return_when=FIRST_COMPLETED)
            if not finished:  # 15초 동안 하나도 안 끝남 → 살아 있다고 알림
                with plock:
                    busy_now = ", ".join(f"{m} {c}" for m, c in inflight.items() if c)
                print(f"  … 응답 기다리는 중 ({n:,}/{total:,} 완료, 경과 {time.time() - t0:.0f}초"
                      + (f" · 진행 중: {busy_now}" if busy_now else "") + ")", flush=True)
                continue
            for fut in finished:
                i, text, model, note = fut.result()
                if note in ("skipped", "fatal"):
                    continue
                n += 1
                record(i, text, model, note)
                if note.startswith("busy("):
                    state["streak"] = 0  # 멈춘 모델 건너뛰기는 '연속 오류'로 세지 않음
                if n <= 3 or n % 10 == 0 or n == total:
                    rate = n / max(1e-9, time.time() - t0)
                    print(f"  {n:,}/{total:,} · {dict(stats)} · {rate * 60:.0f}건/분", flush=True)
                if state["streak"] >= args.max_errors and not stop.is_set():
                    print(f"  ⚠ 오류가 {state['streak']}번 연달아 나서 멈춥니다(네트워크·요청 한도 확인). 다시 실행하면 이어서 해요.")
                    stop.set()
            if stop.is_set():
                for f in pending:
                    f.cancel()
    except KeyboardInterrupt:
        stop.set()
        interrupted = True
        print("\n중단했어요. 지금까지 받은 답을 저장하고 바로 끝냅니다(보내 둔 요청의 답은 버림)…", flush=True)
    finally:
        for ex in executors.values():
            ex.shutdown(wait=not interrupted, cancel_futures=True)  # 아직 시작 안 한 요청은 버림
        save(args.csv, fieldnames, rows)
    if interrupted:  # 진행 중인 요청(최대 120초)을 기다리지 않고 바로 종료
        print(f"저장 → {args.csv} · 이번에 {dict(stats)} · 같은 명령으로 다시 실행하면 이어서 해요.", flush=True)
        os._exit(130)

    if paused:
        skipped_busy = sum(1 for r in rows if (r.get("api_note") or "").startswith(("busy(", "error(5", "error(429")))
        print(f"\n  ⏸ 붐벼서 건너뛴 모델: {sorted(paused)} · 건너뛴 행 {skipped_busy:,}건 → 나중에 같은 명령에 --retry-failed")
    left = sum(1 for r in rows if not (r.get("text") or "").strip())
    print(f"\n저장 → {args.csv} · 이번에 {dict(stats)} · 실제 답한 모델 {dict(served)} · 남은 빈 칸 {left:,}")
    if state["fatal"]:
        sys.exit(f"⚠ 멈춤: {state['fatal']}\n{hint(provider)}")
    if stats.get("refusal") or stats.get("empty") or stats.get("text_refusal"):
        print("  거절(refusal·text_refusal)·빈 답은 text를 비워 두고 api_note에 적었어요(학습 데이터에 안 들어감).\n"
              "  몇 % 이내면 그대로 두세요. 다시 시도: --retry-failed  /  다른 모델에 맡기기: --retry-failed --models <모델>")


if __name__ == "__main__":
    main()
