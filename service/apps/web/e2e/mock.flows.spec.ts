import { expect, test, type Page } from "@playwright/test";

async function collectErrors(page: Page) {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  return errors;
}

test("링크 입력 → 진행 → 결과(고정 검증 예제 숫자)", async ({ page }) => {
  const errors = await collectErrors(page);
  await page.goto("/analyze");
  await page.getByLabel("쿠팡 상품 링크").fill("https://www.coupang.com/vp/products/1000000001?itemId=111");
  await page.getByRole("button", { name: "분석하기" }).last().click();
  await expect(page).toHaveURL(/\/analyses\/mock-vacuum-\d+/);
  await expect(page.getByRole("list", { name: "진행 단계" })).toBeVisible();
  await expect(page.getByText(/점 리뷰 수집 중|대기열|판별|계산/).first()).toBeVisible();
  await expect(page.getByLabel("전체 평균 별점 4.21점")).toBeVisible({ timeout: 30_000 });
  await expect(page.getByLabel("사람 리뷰 기준 별점 4.08점")).toBeVisible();
  await expect(page.getByText("−0.13")).toBeVisible();
  await expect(page.getByText("AI 추정 리뷰를 제외하면 별점이 0.13점 낮아져요.")).toBeVisible();
  await expect(page.getByText("49.9%")).toBeVisible();
  await expect(page.getByText("사람이 쓴 것으로 보이는 리뷰 Top 5")).toBeVisible();
  // 별점 탭 키보드 이동
  await page.getByRole("tab", { name: "5점" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "4점" })).toHaveAttribute("data-state", "active");
  // 차트 대체 표
  await page.getByText("표로 보기").click();
  await expect(page.getByRole("table")).toContainText("1,200");
  expect(errors).toEqual([]);
});

test("상품명 → 후보 선택 → 결과", async ({ page }) => {
  await page.goto("/analyze");
  await page.getByRole("tab", { name: "상품명" }).click();
  await page.getByRole("searchbox", { name: "상품명" }).fill("텀블러");
  await page.getByRole("button", { name: "상품 찾기" }).click();
  await expect(page).toHaveURL(/\/analyze\/select/);
  await expect(page.getByRole("heading", { name: "이 중에 찾는 상품이 있나요?" })).toBeVisible();
  await page.getByRole("button", { name: /보온 텀블러/ }).click();
  await expect(page).toHaveURL(/\/analyses\/mock-tumbler-\d+/);
  await expect(page.getByText("표본이 부족한 별점이 있어요")).toBeVisible({ timeout: 30_000 });
});

test("이미지 업로드 → 후보 선택 → 결과", async ({ page }) => {
  await page.goto("/analyze");
  await page.getByRole("tab", { name: "이미지" }).click();
  const png = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");
  await page.getByLabel("캡처 이미지 파일").setInputFiles({ name: "capture.png", mimeType: "image/png", buffer: png });
  await expect(page.getByAltText("올린 캡처 이미지 미리보기")).toBeVisible();
  await page.getByRole("button", { name: "이미지로 찾기" }).click();
  await expect(page).toHaveURL(/\/analyze\/select/);
  await page.getByRole("button", { name: /에어프라이어/ }).click();
  await expect(page.getByLabel(/사람 리뷰 기준 별점/)).toBeVisible({ timeout: 30_000 });
});

test("차단 상태 화면", async ({ page }) => {
  await page.goto("/analyze");
  await page.getByLabel("쿠팡 상품 링크").fill("https://www.coupang.com/vp/products/9000000001");
  await page.getByRole("button", { name: "분석하기" }).last().click();
  await expect(page.getByRole("heading", { name: "지금은 리뷰를 가져올 수 없어요" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByRole("link", { name: "저장된 결과 보기" })).toBeVisible();
  await expect(page.getByText(/다시 시도 가능 시각/)).toBeVisible();
});

test("오류 상태 화면(셀렉터 깨짐)", async ({ page }) => {
  await page.goto("/analyze");
  await page.getByLabel("쿠팡 상품 링크").fill("https://www.coupang.com/vp/products/9000000002");
  await page.getByRole("button", { name: "분석하기" }).last().click();
  await expect(page.getByRole("heading", { name: "분석을 마치지 못했어요" })).toBeVisible({ timeout: 30_000 });
  await expect(page.getByText(/화면 구조가 바뀌어/)).toBeVisible();
});

test("입력 검증 오류 문구", async ({ page }) => {
  await page.goto("/analyze");
  await page.getByRole("button", { name: "분석하기" }).last().click();
  await expect(page.getByRole("alert").filter({ hasText: "쿠팡 상품 링크를 붙여 넣어 주세요." })).toBeVisible();
  await page.getByLabel("쿠팡 상품 링크").fill("https://www.11st.co.kr/products/1");
  await page.getByRole("button", { name: "분석하기" }).last().click();
  await expect(page.getByRole("alert").filter({ hasText: "지금은 쿠팡 상품 링크만 분석할 수 있어요." })).toBeVisible();
});

test("없는 분석 ID와 404 페이지", async ({ page }) => {
  await page.goto("/analyses/an_doesnotexist");
  await expect(page.getByRole("heading", { name: "분석을 마치지 못했어요" })).toBeVisible();
  const res = await page.goto("/no-such-page");
  expect(res?.status()).toBe(404);
  await expect(page.getByRole("heading", { name: "페이지를 찾을 수 없어요" })).toBeVisible();
});

test("선택 화면 빈 상태", async ({ page }) => {
  await page.goto("/analyze/select");
  await expect(page.getByRole("heading", { name: "선택할 후보가 없어요" })).toBeVisible();
});

test("모든 페이지 링크가 살아 있고 콘솔 오류가 없다", async ({ page }) => {
  const errors = await collectErrors(page);
  for (const path of ["/", "/analyze", "/how-it-works", "/faq", "/about", "/terms", "/privacy"]) {
    const res = await page.goto(path);
    expect(res?.status(), path).toBe(200);
    await expect(page.locator("h1")).toBeVisible();
    for (const href of await page.locator("a[href^='/']").evaluateAll((as) => as.map((a) => a.getAttribute("href")))) {
      const r = await page.request.get(href!);
      expect(r.status(), `${path} → ${href}`).toBeLessThan(400);
    }
  }
  expect((await page.request.get("/robots.txt")).status()).toBe(200);
  expect((await page.request.get("/sitemap.xml")).status()).toBe(200);
  expect(errors).toEqual([]);
});

test("키보드만으로 링크 입력부터 분석 시작", async ({ page }) => {
  await page.goto("/analyze");
  await page.getByLabel("쿠팡 상품 링크").focus();
  await page.keyboard.type("https://www.coupang.com/vp/products/1000000003");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/analyses\/mock-airfryer-\d+/);
});
