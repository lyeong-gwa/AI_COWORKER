/**
 * E2E: 대시보드(/) 기본 렌더 검증.
 *
 * 사전 조건: 프론트 5174, 백엔드 8002 기동.
 * 목적: 요약 카드 4종이 보이고, 워크플로우 섹션이 로딩/빈 상태/데이터 중 하나로 렌더되는지 확인.
 */
import { test, expect } from "@playwright/test";
import path from "node:path";

// 루트 `_참고자료/screenshots/` 디렉터리 (AI 업무도우미/e2e 기준 상위 2단계)
const SCREENSHOT_DIR = path.resolve(__dirname, "../../_참고자료/screenshots");

test.describe("Dashboard", () => {
  test("대시보드 랜딩 페이지가 요약 카드를 렌더한다", async ({ page }) => {
    await page.goto("/");

    // Header
    await expect(page.getByRole("heading", { name: /실행 현황/ })).toBeVisible();

    // Summary cards — 라벨 기준
    await expect(page.getByText("오늘 실행")).toBeVisible();
    await expect(page.getByText("진행 중")).toBeVisible();
    await expect(page.getByText("최근 실패")).toBeVisible();
    await expect(page.getByText("최근 성공")).toBeVisible();

    // 업무자동화 섹션 헤더
    await expect(
      page.getByRole("heading", { name: "업무자동화 목록" })
    ).toBeVisible();

    // 스크린샷 저장 (루트 메모리 규칙: _참고자료/screenshots/)
    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "phase3c-dashboard-landing.png"),
      fullPage: true,
    });
  });

  test("사이드바에 5개 네비게이션 항목이 있다", async ({ page }) => {
    await page.goto("/");
    const nav = page.locator("nav");
    await expect(nav.getByText("대시보드")).toBeVisible();
    await expect(nav.getByText("업무자동화")).toBeVisible();
    await expect(nav.getByText("지식")).toBeVisible();
    await expect(nav.getByText("API 명세")).toBeVisible();
    await expect(nav.getByText("노드 카탈로그")).toBeVisible();
  });
});
