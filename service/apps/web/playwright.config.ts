import { defineConfig, devices } from "@playwright/test";

/**
 * E2E (README 14.8): 백엔드 없이 동작하도록
 *  - mock 프로젝트: MSW 목업(5.7 스키마) 빌드 → 링크/상품명/이미지/차단/오류 흐름
 *  - demo 프로젝트: 발표 모드 빌드(네트워크 없음) → 전체 시연 흐름
 */
const MOCK_PORT = 3100;
const DEMO_PORT = 3200;
const reuse = !process.env.CI;

export default defineConfig({
  testDir: "./e2e",
  timeout: 60_000,
  expect: { timeout: 20_000 },
  fullyParallel: true,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { trace: "off", locale: "ko-KR", timezoneId: "Asia/Seoul" },
  projects: [
    { name: "mock", testMatch: /mock\..*\.spec\.ts/, use: { ...devices["Desktop Chrome"], baseURL: `http://localhost:${MOCK_PORT}` } },
    { name: "demo", testMatch: /demo\..*\.spec\.ts/, use: { ...devices["Desktop Chrome"], baseURL: `http://localhost:${DEMO_PORT}` } },
    { name: "mobile", testMatch: /mock\.responsive\.spec\.ts/, use: { ...devices["Pixel 7"], baseURL: `http://localhost:${MOCK_PORT}` } },
  ],
  webServer: [
    {
      command: `NEXT_PUBLIC_API_MODE=mock npx next build && npx next start -p ${MOCK_PORT}`,
      port: MOCK_PORT,
      reuseExistingServer: reuse,
      timeout: 240_000,
    },
    {
      command: `NEXT_DIST_DIR=.next-demo NEXT_PUBLIC_DEMO_MODE=true npx next build && NEXT_DIST_DIR=.next-demo npx next start -p ${DEMO_PORT}`,
      port: DEMO_PORT,
      reuseExistingServer: reuse,
      timeout: 240_000,
    },
  ],
});
