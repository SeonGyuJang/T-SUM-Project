// OG 이미지(1200×630)를 자체 HTML로 렌더링해 public/og.png로 저장한다. 실행: npm run og
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

const font = readFileSync(fileURLToPath(new URL("../node_modules/pretendard/dist/web/variable/woff2/PretendardVariable.woff2", import.meta.url))).toString("base64");
const html = `<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:P;src:url(data:font/woff2;base64,${font}) format("woff2");font-weight:100 900}
body{margin:0;width:1200px;height:630px;font-family:P;background:#f7f8fa;display:flex;align-items:center}
.w{padding:0 96px;width:100%}.logo{display:flex;align-items:center;gap:16px;font-size:40px;font-weight:800;color:#111827}
h1{font-size:72px;line-height:1.2;font-weight:800;letter-spacing:-2px;color:#111827;margin:48px 0 24px}
p{font-size:30px;color:#4b5563;margin:0}.n{color:#1e3a8a}
</style></head><body><div class="w"><div class="logo"><svg viewBox="0 0 24 24" width="56" height="56"><rect width="24" height="24" rx="7" fill="#1e3a8a"/><path d="M12 5.2l2 4.1 4.5.6-3.3 3.1.8 4.5-4-2.2-4 2.2.8-4.5L5.5 9.9l4.5-.6z" fill="#fff"/></svg>리얼별점</div>
<h1>AI가 쓴 리뷰를 걸러낸<br><span class="n">진짜 별점</span></h1><p>쿠팡 상품 리뷰를 분석해 사람 리뷰 기준 별점을 보여드려요</p></div></body></html>`;
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 1200, height: 630 } });
await p.setContent(html);
await p.screenshot({ path: fileURLToPath(new URL("../public/og.png", import.meta.url)) });
await b.close();
console.log("public/og.png written");
