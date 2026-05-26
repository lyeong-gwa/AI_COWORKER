/**
 * E2E: 노드 카탈로그(/nodes) 11종 defType 표시 검증.
 *
 * 사전 조건: 프론트 5174, 백엔드 8002 기동, 백엔드에 기본 11종 카탈로그가 응답.
 */
import { test, expect } from "@playwright/test";
import path from "node:path";

const SCREENSHOT_DIR = path.resolve(__dirname, "../../_참고자료/screenshots");

const DEF_TYPES = [
  "form-start",
  "api-start",
  "ai-custom",
  "ai-api-router",
  "sorter",
  "unpacker",
  "mapper",
  "api-call",
  "knowledge",
  "result",
  "markdown-viewer",
] as const;

test.describe("Node Catalog", () => {
  test("노드 카탈로그 페이지에서 11종 defType이 모두 렌더된다", async ({ page }) => {
    await page.goto("/nodes");

    // 페이지 헤더 확인
    await expect(page.locator("body")).toContainText("노드 카탈로그");

    // 백엔드에서 카탈로그가 비동기로 로드되므로 최초 카드 렌더를 기다린다
    await page.waitForLoadState("networkidle");

    for (const def of DEF_TYPES) {
      // <code> 태그 안에 defType 문자열이 표시됨
      await expect(page.locator(`code:has-text("${def}")`).first()).toBeVisible({
        timeout: 10_000,
      });
    }

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "phase3c-node-catalog.png"),
      fullPage: true,
    });
  });
});
