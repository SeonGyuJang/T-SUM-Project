import { expect, test } from "@playwright/test";

test("발표 모드: 네트워크 없이 입력 → 진행 재생 → 결과", async ({ page, context }) => {
  // 외부 네트워크 차단: 같은 서버의 정적 파일 외 요청이 나가면 실패
  const external: string[] = [];
  await context.route(/^https?:\/\/(?!localhost)/, (r) => { external.push(r.request().url()); return r.abort(); });
  await page.goto("/");
  await expect(page.getByText("발표 모드 · 미리 분석해 저장한 예시 상품 결과를 보여드려요")).toBeVisible();
  await page.getByRole("button", { name: /무선 청소기 A100/ }).click();
  await page.getByRole("button", { name: "분석하기" }).last().click();
  await expect(page).toHaveURL(/\/analyses\/demo-vacuum-\d+/);
  await expect(page.getByRole("list", { name: "진행 단계" })).toBeVisible();
  const t0 = Date.now();
  await expect(page.getByLabel("전체 평균 별점 4.21점")).toBeVisible({ timeout: 30_000 });
  const replay = Date.now() - t0;
  expect(replay).toBeGreaterThan(8_000); // 저장된 단계를 10~15초로 재생
  await expect(page.getByText("저장된 분석 결과").first()).toBeVisible();
  await expect(page.getByText(/수집 시각 2026년 11월 12일/)).toBeVisible();
  expect(external).toEqual([]);
});

test("발표 모드: 예시 외 상품은 안내", async ({ page }) => {
  await page.goto("/analyze");
  await page.getByLabel("쿠팡 상품 링크").fill("https://www.coupang.com/vp/products/12345");
  await page.getByRole("button", { name: "분석하기" }).last().click();
  await expect(page.getByRole("alert").filter({ hasText: "발표 모드에서는 예시 상품만 분석할 수 있어요." })).toBeVisible();
});

test("발표 모드: 상품명 → 선택 화면", async ({ page }) => {
  await page.goto("/analyze");
  await page.getByRole("tab", { name: "상품명" }).click();
  await page.getByRole("searchbox", { name: "상품명" }).fill("에어프라이어");
  await page.getByRole("button", { name: "상품 찾기" }).click();
  await expect(page).toHaveURL(/\/analyze\/select/);
  await page.getByRole("button", { name: /에어프라이어/ }).click();
  await expect(page).toHaveURL(/\/analyses\/demo-airfryer-\d+/);
});

test("발표 모드: 리뷰 직접 확인은 네트워크 없이 예시 판정", async ({ page, context }) => {
  const external: string[] = [];
  await context.route(/^https?:\/\/(?!localhost)/, (r) => { external.push(r.request().url()); return r.abort(); });
  await page.goto("/check");
  await page.getByLabel("판별할 리뷰").fill("배송 빨라요 근데 생각보다 사이즈가 작아서 좀 아쉽 ㅠㅠ 그래도 이 가격이면 쓸만해요");
  await page.getByRole("button", { name: "판별하기" }).click();
  await expect(page.getByText("발표 모드: 실제 AI 판별 모델이 아니라 예시 규칙으로 판정한 결과예요.")).toBeVisible();
  await expect(page.getByRole("meter", { name: "AI가 썼을 확률" })).toBeVisible();
  expect(external).toEqual([]);
});
