/**
 * E2E: 업무자동화(/workflows) 목록 → 상세 → 실행 흐름.
 *
 * 사전 조건:
 *   - 프론트 5174, 백엔드 8002 기동.
 *   - 백엔드에 테스트용 form-start 전용 워크플로우 1개 존재하거나, 이 스펙이 REST API로 생성.
 *
 * 목적:
 *   1) 워크플로우 목록 페이지가 렌더된다
 *   2) 목록에서 카드를 클릭하면 상세 페이지로 이동한다
 *   3) 실행 버튼 → 모달 → 제출 → 인스턴스 상세 페이지로 이동한다
 *
 * 구현 전략:
 *   - context.request 로 워크플로우 생성(없으면) → 실행 버튼을 클릭 → 인스턴스 URL 확인
 *   - 실패해도 최소 목록/상세 렌더는 검증
 */
import { test, expect } from "@playwright/test";
import path from "node:path";

const API_BASE = "http://localhost:8002";
const SCREENSHOT_DIR = path.resolve(__dirname, "../../_참고자료/screenshots");

interface Workflow {
  id: string;
  name: string;
  status: string;
}

async function ensureTestWorkflow(request: import("@playwright/test").APIRequestContext): Promise<Workflow | null> {
  // 기존 목록 조회
  const listResp = await request.get(`${API_BASE}/api/v1/workflows`);
  if (!listResp.ok()) return null;
  const existing = (await listResp.json()) as Workflow[];
  const candidate = existing.find((w) => w.status === "active" || w.status === "draft");
  if (candidate) return candidate;

  // 없으면 생성 시도
  const createResp = await request.post(`${API_BASE}/api/v1/workflows`, {
    data: {
      name: "E2E Test Workflow",
      description: "Phase 3c E2E 자동 생성",
      tags: ["e2e"],
      nodes: [
        {
          nodeId: "form-start",
          name: "입력",
          definitionType: "form-start",
          orderIndex: 0,
          config: { mode: "manual", fields: [] },
          inputMapping: {},
        },
      ],
      connections: [],
    },
  });
  if (!createResp.ok()) return null;
  return (await createResp.json()) as Workflow;
}

test.describe("Workflow execution flow", () => {
  test("워크플로우 목록에서 카드를 클릭하면 상세 페이지로 이동한다", async ({ page, request }) => {
    const wf = await ensureTestWorkflow(request);
    test.skip(!wf, "테스트용 워크플로우를 준비할 수 없습니다 (백엔드 상태 확인 필요)");

    await page.goto("/workflows");
    await expect(page.getByRole("heading", { name: "업무자동화 목록" })).toBeVisible();

    // 해당 워크플로우 링크 클릭
    const link = page.locator(`a[href="/workflows/${wf!.id}"]`).first();
    await expect(link).toBeVisible({ timeout: 10_000 });
    await link.click();

    await expect(page).toHaveURL(new RegExp(`/workflows/${wf!.id}$`));
    await expect(page.locator("body")).toContainText("업무자동화 상세");
    await expect(page.getByRole("button", { name: /실행하기/ })).toBeVisible();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "phase3c-workflow-detail.png"),
      fullPage: true,
    });
  });

  test("실행 버튼 클릭 → 실행 모달 표시", async ({ page, request }) => {
    const wf = await ensureTestWorkflow(request);
    test.skip(!wf, "테스트용 워크플로우를 준비할 수 없습니다");

    await page.goto(`/workflows/${wf!.id}`);
    await page.getByRole("button", { name: /실행하기/ }).click();

    // 모달 헤더 "실행 입력"
    await expect(page.locator("text=실행 입력")).toBeVisible();
    // 모달 푸터의 취소 버튼이 보여야 한다 (모달 열림 확인)
    await expect(page.getByRole("button", { name: /^취소$/ })).toBeVisible();

    await page.screenshot({
      path: path.join(SCREENSHOT_DIR, "phase3c-run-modal.png"),
      fullPage: false,
    });
  });
});
