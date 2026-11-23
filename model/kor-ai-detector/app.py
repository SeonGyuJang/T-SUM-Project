"""학습한 모델이 제대로 동작하는지 브라우저에서 확인하는 간단한 웹페이지 (설치 추가 없음: 파이썬 표준 라이브러리).

  python app.py --model models/stage2 --report reports/stage2/report.json
  → http://127.0.0.1:7860

- 리뷰를 넣으면 P(AI)와 판정(사람 / AI / 판단 보류)을 보여 줍니다. 여러 개는 한 줄에 하나씩.
- 테스트셋(data/processed/*.jsonl)에서 무작위로 뽑아 정답과 판정을 나란히 볼 수 있습니다.
- 임계값은 evaluate.py가 만든 report.json에서 읽습니다. 없으면 0.5 하나로 판정하고 화면에 경고를 띄웁니다.
"""
import argparse
import glob
import json
import os
import random
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
MAX_TEXTS, MAX_CHARS = 200, 5000

PAGE = r"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI 리뷰 탐지 모델 점검</title>
<style>
:root{--bg:#f7f8fa;--card:#fff;--text:#1d2330;--muted:#6b7280;--line:#e5e7eb;--primary:#2c5be6;--human:#15803d;--ai:#c2410c;--hold:#6b7280;--bar:#eef0f4}
@media (prefers-color-scheme:dark){:root{--bg:#12151c;--card:#1b2029;--text:#e7eaf0;--muted:#9aa3b2;--line:#2b3240;--primary:#7aa2ff;--human:#4ade80;--ai:#fb923c;--hold:#9aa3b2;--bar:#262c38}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Apple SD Gothic Neo","Malgun Gothic",sans-serif}
main{max-width:980px;margin:0 auto;padding:24px 16px 64px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0 0 12px}
.muted{color:var(--muted)}.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:18px;margin-top:16px}
textarea{width:100%;min-height:120px;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);color:var(--text);font:inherit;resize:vertical}
button,select,input{font:inherit}button{background:var(--primary);color:#fff;border:0;border-radius:8px;padding:9px 16px;cursor:pointer;font-weight:600}
button.ghost{background:transparent;color:var(--primary);border:1px solid var(--line)}button:disabled{opacity:.5;cursor:wait}
.row{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:10px}
.res{border-top:1px solid var(--line);padding:12px 0}.res:first-child{border-top:0}
.badge{display:inline-block;padding:2px 10px;border-radius:999px;font-weight:700;font-size:13px;color:#fff}
.b-사람{background:var(--human)}.b-AI{background:var(--ai)}.b-판단보류{background:var(--hold)}
.bar{position:relative;height:10px;background:var(--bar);border-radius:999px;margin:8px 0 2px}
.fill{position:absolute;left:0;top:0;bottom:0;border-radius:999px;background:var(--primary)}
.tick{position:absolute;top:-4px;bottom:-4px;width:2px}.t-ai{background:var(--ai)}.t-h{background:var(--human)}
.txt{white-space:pre-wrap;word-break:break-all;margin-top:6px}
table{width:100%;border-collapse:collapse;font-size:14px}th,td{border-bottom:1px solid var(--line);padding:7px 6px;text-align:left;vertical-align:top}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap}td.nw,th{white-space:nowrap}.ok{color:var(--human);font-weight:700}.bad{color:var(--ai);font-weight:700}
.kv{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:4px 16px;font-size:14px}.kv div{min-width:0;overflow-wrap:anywhere}
#tbl{overflow-x:auto}select{max-width:100%}code{overflow-wrap:anywhere}.warn{background:#fff4e5;color:#7a4b00;border-radius:8px;padding:10px 12px;margin-top:10px}
@media (prefers-color-scheme:dark){.warn{background:#3a2a10;color:#ffd38a}}
.legend{font-size:13px}.legend span{margin-right:12px}
@media (max-width:600px){.hide-sm{display:none}}
</style></head><body><main>
<h1>AI 리뷰 탐지 모델 점검</h1>
<p class="muted">학습한 모델이 리뷰를 어떻게 판정하는지 확인하는 페이지예요. 판정은 참고용이에요.</p>

<section class="card" id="info"><h2>모델 정보</h2><div class="kv" id="kv">불러오는 중…</div><div id="warn"></div></section>

<section class="card"><h2>리뷰 판별</h2>
<textarea id="input" placeholder="리뷰를 붙여 넣으세요. 여러 개를 확인하려면 아래 '한 줄에 하나씩'을 켜세요."></textarea>
<div class="row"><label><input type="checkbox" id="multi"> 한 줄에 하나씩 여러 개</label></div>
<div class="row"><button id="go">판별하기</button>
<button class="ghost" data-ex="h">사람 같은 예시</button><button class="ghost" data-ex="a">AI 같은 예시</button><button class="ghost" id="clear">지우기</button></div>
<p class="legend muted"><span>막대 = P(AI)</span><span style="color:var(--human)">┃ 사람 기준(T_HUMAN)</span><span style="color:var(--ai)">┃ AI 기준(T_AI)</span></p>
<div id="out"></div></section>

<section class="card"><h2>테스트셋에서 무작위로 확인</h2>
<p class="muted">data/processed 의 평가용 파일에서 뽑아 정답과 판정을 비교해요. 판단 보류는 정답·오답에서 뺍니다.</p>
<div class="row"><select id="file"></select><select id="n"><option>20</option><option>50</option><option selected>100</option><option>300</option></select>
<button id="sample">무작위 확인</button></div>
<div id="sum" class="row"></div><div id="tbl"></div></section>
</main>
<script>
const EX = {h:["배송 빨라요 ㅎㅎ 근데 포장이 좀 허술했어요","생각보다 작아서 좀 실망ㅠ 그래도 가격대비 괜찮음","세번째 재구매에요 애들이 잘먹어요"],
 a:["이 제품은 가성비가 뛰어나며 품질 또한 매우 만족스럽습니다. 배송도 빠르고 포장도 꼼꼼하여 신뢰가 갑니다. 재구매 의사가 있습니다.",
    "전반적으로 만족스러운 구매였습니다. 디자인이 세련되고 마감 처리도 깔끔하여 선물용으로도 손색이 없을 것 같습니다.",
    "사용해 보니 기대 이상이었습니다. 다만 사이즈가 생각보다 커서 공간을 고려하시는 것이 좋겠습니다."]};
let INFO = {};
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const pct = x => (x*100).toFixed(1) + "%";
async function api(path, body){const r = await fetch(path, body ? {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(body)} : {});
  const j = await r.json(); if(!r.ok) throw new Error(j.error || r.status); return j;}
function bar(p){return `<div class="bar"><div class="fill" style="width:${p*100}%"></div>
  <div class="tick t-h" style="left:${INFO.T_HUMAN*100}%"></div><div class="tick t-ai" style="left:${INFO.T_AI*100}%"></div></div>`;}
function badge(v){return `<span class="badge b-${v.replace(/ /g,"")}">${v}</span>`;}
async function loadInfo(){
  INFO = await api("/api/info");
  const rows = [["모델 폴더", INFO.model_dir], ["기반 모델", INFO.base_model || "-"], ["장치", INFO.device],
    ["AI 기준 T_AI", `${INFO.T_AI.toFixed(4)} (P(AI)가 이보다 크면 AI)`], ["사람 기준 T_HUMAN", `${INFO.T_HUMAN.toFixed(4)} (이하이면 사람, 사이는 판단 보류)`],
    ["기준 정한 방법", INFO.target_fpr != null ? `검증셋 사람 오탐 ${pct(INFO.target_fpr)} · AI 놓침 ${pct(INFO.ai_miss ?? 0.05)}` : "-"],
    ["줄바꿈 처리", INFO.newlines === "space" ? "공백으로 바꿈(학습과 같게)" : "그대로"], ["최대 토큰", INFO.max_len]];
  for (const [k,v] of Object.entries(INFO.val_metrics || {})) if (/auroc|tpr/.test(k)) rows.push([`검증 ${k.replace("eval_","")}`, Number(v).toFixed(4)]);
  $("#kv").innerHTML = rows.map(([k,v]) => `<div class="muted">${k}</div><div>${esc(v)}</div>`).join("");
  $("#warn").innerHTML = INFO.calibrated ? "" : `<div class="warn">report.json이 없어 임계값 0.5로 판정해요. <code>evaluate.py</code>로 만든 report.json을 <code>--report</code>로 지정하세요.</div>`;
  $("#file").innerHTML = INFO.files.length ? INFO.files.map(f => `<option>${esc(f)}</option>`).join("") : "<option value=''>data/processed 에 파일 없음</option>";
}
$("#go").onclick = async () => {
  const raw = $("#input").value.trim(); if(!raw) return;
  const texts = $("#multi").checked ? raw.split("\n").map(s => s.trim()).filter(Boolean) : [raw];
  $("#go").disabled = true; $("#out").innerHTML = "<p class='muted'>판별 중…</p>";
  try { const {results} = await api("/api/predict", {texts});
    $("#out").innerHTML = results.map(r => `<div class="res">${badge(r.verdict)} <b>P(AI) ${pct(r.p_ai)}</b>
      <span class="muted">· ${r.chars}자${r.chars < 20 ? " (20자 미만은 판단 보류)" : ""}</span>${bar(r.p_ai)}<div class="txt">${esc(r.text)}</div></div>`).join("");
  } catch(e){ $("#out").innerHTML = `<div class="warn">${esc(e.message)}</div>`; } finally { $("#go").disabled = false; }
};
document.querySelectorAll("[data-ex]").forEach(b => b.onclick = () => { $("#multi").checked = true; $("#input").value = EX[b.dataset.ex].join("\n"); });
$("#clear").onclick = () => { $("#input").value = ""; $("#out").innerHTML = ""; };
$("#sample").onclick = async () => {
  if(!$("#file").value) return; $("#sample").disabled = true; $("#tbl").innerHTML = "<p class='muted'>판별 중…</p>"; $("#sum").innerHTML = "";
  try { const j = await api("/api/sample", {file: $("#file").value, n: +$("#n").value});
    const s = j.summary;
    $("#sum").innerHTML = `<span>정답률 <b>${s.decided ? pct(s.correct/s.decided) : "-"}</b> (${s.correct}/${s.decided})</span>
      <span class="muted">· 판단 보류 ${s.hold}건 · 사람을 AI로 ${s.fp}건 · AI를 사람으로 ${s.fn}건</span>`;
    $("#tbl").innerHTML = `<table><thead><tr><th>정답</th><th>판정</th><th>P(AI)</th><th class="hide-sm">출처</th><th>리뷰</th></tr></thead><tbody>${
      j.rows.map(r => { const ok = r.verdict === "판단 보류" ? "" : ((r.verdict === "AI") === (r.label === 1) ? "ok" : "bad");
        return `<tr><td class="nw">${r.label ? "AI" : "사람"}</td><td class="nw ${ok}">${r.verdict}</td><td class="num">${pct(r.p_ai)}</td>
          <td class="hide-sm muted">${esc(r.generator)}${r.prompt_type ? " · " + esc(r.prompt_type) : ""}</td><td class="txt">${esc(r.text)}</td></tr>`;}).join("")}</tbody></table>`;
  } catch(e){ $("#tbl").innerHTML = `<div class="warn">${esc(e.message)}</div>`; } finally { $("#sample").disabled = false; }
};
loadInfo().catch(e => { $("#kv").innerHTML = `<div class="warn">${esc(e.message)}</div>`; });
</script></body></html>"""


def make_handler(pred, data_dir):
    def files():
        # 학습 파일은 제외. 리뷰 테스트(stage2_test…)를 먼저, 댓글(stage1)·검증 파일은 뒤로
        names = [os.path.basename(p) for p in glob.glob(os.path.join(data_dir, "*.jsonl")) if "train" not in os.path.basename(p)]
        return sorted(names, key=lambda n: (not n.startswith("stage2_test"), n.startswith("stage1"), n))

    class H(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):  # 조용히
            pass

        def send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}") if n < 5_000_000 else {}

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                return self.send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
            if self.path == "/api/info":
                return self.send(200, {**pred.info(), "files": files()})
            self.send(404, {"error": "없는 주소예요"})

        def do_POST(self):
            try:
                req = self.body()
                if self.path == "/api/predict":
                    texts = [str(t)[:MAX_CHARS] for t in (req.get("texts") or []) if str(t).strip()][:MAX_TEXTS]
                    if not texts:
                        return self.send(400, {"error": "리뷰를 입력해 주세요."})
                    return self.send(200, {"results": pred.judge(texts)})
                if self.path == "/api/sample":
                    name = os.path.basename(str(req.get("file") or ""))
                    path = os.path.join(data_dir, name)
                    if name not in files():
                        return self.send(400, {"error": f"평가용 파일이 아니에요: {name}"})
                    with open(path, encoding="utf-8") as f:
                        recs = [json.loads(x) for x in f if x.strip()]
                    n = max(1, min(int(req.get("n") or 100), 1000))
                    pick = random.sample(recs, min(n, len(recs)))
                    res = pred.judge([r["text"] for r in pick])
                    rows, s = [], {"correct": 0, "decided": 0, "hold": 0, "fp": 0, "fn": 0}
                    for r, j in zip(pick, res):
                        rows.append({**j, "label": int(r["label"]), "generator": r.get("generator", ""), "prompt_type": r.get("prompt_type", "")})
                        if j["verdict"] == "판단 보류":
                            s["hold"] += 1
                            continue
                        s["decided"] += 1
                        is_ai = j["verdict"] == "AI"
                        s["correct"] += int(is_ai == (r["label"] == 1))
                        s["fp"] += int(is_ai and r["label"] == 0)
                        s["fn"] += int(not is_ai and r["label"] == 1)
                    return self.send(200, {"rows": rows, "summary": s})
                self.send(404, {"error": "없는 주소예요"})
            except Exception as e:  # 화면에 원인을 보여 준다
                self.send(500, {"error": f"{type(e).__name__}: {e}"})

    return H


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", required=True, help="train.py 결과 폴더 (예: models/stage2)")
    ap.add_argument("--report", default=None, help="evaluate.py가 만든 report.json (임계값)")
    ap.add_argument("--data", default=os.path.join(ROOT, "data", "processed"), help="테스트 파일 폴더")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=7860)
    args = ap.parse_args()
    from predictor import Predictor

    print("모델을 불러오는 중…", flush=True)
    pred = Predictor(args.model, report=args.report)
    srv = ThreadingHTTPServer((args.host, args.port), make_handler(pred, args.data))
    print(f"열렸어요 → http://{args.host}:{args.port}  (장치 {pred.device}, T_AI {pred.t_ai:.4f}, T_HUMAN {pred.t_human:.4f})  · 끄려면 Ctrl+C")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
