// README 14.9: 1920×1080, 1440×900, 768, 375 해상도 전 페이지 스크린샷.
// 사용: (목업 빌드 서버 실행 후) node scripts/screenshots.mjs http://localhost:3100 ../../../docs/screenshots
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

const [, , base = "http://localhost:3100", out = "screenshots"] = process.argv;
const SIZES = [
  { name: "1920", width: 1920, height: 1080 },
  { name: "1440", width: 1440, height: 900 },
  { name: "768", width: 768, height: 1024 },
  { name: "375", width: 375, height: 812 },
];
const SELECT = JSON.stringify({
  status: "needs_selection", input_type: "query", query: "텀블러", cached: false,
  candidates: [
    { product_id: "1000000002", name: "[예시] 보온 텀블러 500ml 2개 세트", image_url: "/demo/tumbler.svg", price: 23900, is_ad: false, rating: 4.5, review_count: 430, match_score: 0.92 },
    { product_id: "1000000021", name: "[예시] 보온 텀블러 350ml", image_url: null, price: 12900, is_ad: false, rating: 4.6, review_count: 410, match_score: 0.71 },
    { product_id: "1000000023", name: "[예시] 빨대 텀블러 600ml", image_url: null, price: 9900, is_ad: true, rating: 4.1, review_count: 51, match_score: 0.48 },
  ],
});
const PAGES = [
  ["01-home", "/"],
  ["02-analyze", "/analyze"],
  ["03-select", "/analyze/select", { session: SELECT }],
  ["04-progress", () => `/analyses/mock-vacuum-${Date.now() - 4000}`, { wait: 600 }],
  ["05-result", "/analyses/mock-vacuum", { wait: 1200 }],
  ["06-result-insufficient", "/analyses/mock-tumbler", { wait: 1200 }],
  ["07-blocked", () => `/analyses/mock-s9000000001-${Date.now() - 60000}`],
  ["08-error", () => `/analyses/mock-s9000000002-${Date.now() - 60000}`],
  ["09-how-it-works", "/how-it-works"],
  ["10-faq", "/faq"],
  ["11-about", "/about"],
  ["12-terms", "/terms"],
  ["13-privacy", "/privacy"],
  ["14-404", "/not-a-page"],
];

const browser = await chromium.launch();
for (const s of SIZES) {
  mkdirSync(`${out}/${s.name}`, { recursive: true });
  const ctx = await browser.newContext({ viewport: { width: s.width, height: s.height }, deviceScaleFactor: 1, locale: "ko-KR", timezoneId: "Asia/Seoul", reducedMotion: "reduce" });
  const page = await ctx.newPage();
  for (const [name, path, opt = {}] of PAGES) {
    if (opt.session) {
      await page.goto(base + "/");
      await page.evaluate((v) => sessionStorage.setItem("realstar:last-resolve", v), opt.session);
    }
    const url = typeof path === "function" ? path() : path;
    await page.goto(base + url, { waitUntil: "networkidle" });
    await page.waitForTimeout(opt.wait ?? 500);
    await page.screenshot({ path: `${out}/${s.name}/${name}.png`, fullPage: true });
  }
  await ctx.close();
  console.log("done", s.name);
}
await browser.close();
