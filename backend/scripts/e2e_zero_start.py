"""
e2e_zero_start.py — 제로 스타트 E2E 검증 스크립트

AI 업무도우미 Phase 2c 산출물.
wipe 후 백엔드 기동 상태에서 실행하면 a~i 단계를 순서대로 검증한다.

사용법:
  cd backend
  python scripts/e2e_zero_start.py [--base-url http://localhost:8002]

전제: 백엔드(포트 8002)가 기동 중이어야 한다.
"""

import argparse
import json
import time
import uuid
import urllib.request
import urllib.error
import sys

DEFAULT_BASE = "http://localhost:8002"


def req(base: str, method: str, path: str, body=None):
    url = base + path
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    r = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(r) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def check(label: str, cond: bool, detail: str = ""):
    status = "PASS" if cond else "FAIL"
    print(f"  [{status}] {label}" + (f" - {detail}" if detail else ""))
    return cond


def main():
    parser = argparse.ArgumentParser(description="E2E 제로 스타트 검증")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    args = parser.parse_args()
    base = args.base_url
    api = base + "/api/v1"

    def r(method, path, body=None):
        return req(api, method, path, body)

    results = {}
    print(f"\n=== AI 업무도우미 E2E 제로 스타트 검증 ({base}) ===\n")

    # ── a) 워크플로우 목록 → 빈 리스트 ──────────────────────────────────
    print("a) GET /workflows")
    s, b = r("GET", "/workflows")
    ok = s == 200 and isinstance(b, list) and len(b) == 0
    check("200 + 빈 리스트", ok, f"status={s}, count={len(b) if isinstance(b, list) else b}")
    results["a"] = ok

    # ── b) 노드 카탈로그 → 13개 (11종 + 인스턴스DB Phase A 2종) ─────────
    print("\nb) GET /nodes/catalog")
    s, b = r("GET", "/nodes/catalog")
    ok = s == 200 and isinstance(b, list) and len(b) == 13
    check("200 + 13종 반환", ok, f"status={s}, count={len(b) if isinstance(b, list) else b}")
    results["b"] = ok

    # ── c) API 명세 등록 ─────────────────────────────────────────────────
    print("\nc) POST /api-definitions")
    run_id = uuid.uuid4().hex[:8]
    s, b = r("POST", "/api-definitions", {
        "name": f"httpbin-get-{run_id}",
        "urlTemplate": "https://httpbin.org/get",
        "method": "GET",
        "description": "httpbin GET 테스트",
    })
    api_def_id = b.get("id", "")
    ok = s == 200 and bool(api_def_id)
    check("200 + id 반환", ok, f"status={s}, id={api_def_id}")
    results["c"] = ok

    # ── d) 지식문서 등록 ─────────────────────────────────────────────────
    print("\nd) POST /knowledge")
    knowledge_suffix = uuid.uuid4().hex[:8]
    s, b = r("POST", "/knowledge", {
        "title": f"VPN 접속 문제 처리 가이드 {knowledge_suffix}",
        "category": "인프라",
        "tags": ["VPN", "인프라"],
        "content": "## VPN 접속 오류\n\n비밀번호 초기화 후에도 인증 실패 시 IT팀 티켓 발행.",
    })
    doc_id = b.get("id", "")
    ok = s in (200, 201) and bool(doc_id)
    check("201 + id 반환", ok, f"status={s}, id={doc_id}")
    results["d"] = ok

    # ── e) 커스텀 AI 노드 등록 ───────────────────────────────────────────
    print("\ne) POST /nodes")
    s, b = r("POST", "/nodes", {
        "name": f"티켓분류기-{run_id}",
        "description": "IT 지원 티켓 분류",
        "systemPrompt": "당신은 IT 지원 티켓을 분류하는 전문가입니다.",
        "userPromptTemplate": "다음 문의글을 분류하세요: {{input}}",
        "inputSchema": {"type": "object", "properties": {"input": {"type": "string"}}},
        "outputSchema": {"type": "object", "properties": {"category": {"type": "string"}}},
        "tags": ["분류", "IT지원"],
    })
    ai_node_id = b.get("id", "")
    ok = s in (200, 201) and bool(ai_node_id)
    check("201 + id 반환", ok, f"status={s}, id={ai_node_id}")
    results["e"] = ok

    # ── f) 워크플로우 생성 ───────────────────────────────────────────────
    print("\nf) POST /workflows")
    n1 = "wn-" + uuid.uuid4().hex[:8]
    n2 = "wn-" + uuid.uuid4().hex[:8]
    c1 = "wc-" + uuid.uuid4().hex[:8]
    s, b = r("POST", "/workflows", {
        "name": "E2E 테스트 워크플로우",
        "description": "제로 스타트 E2E 검증",
        "status": "active",
        "nodes": [
            {"id": n1, "nodeId": n1, "definitionType": "form-start", "name": "시작",
             "config": {"fields": [{"name": "query", "label": "질문", "type": "string", "required": True}]},
             "orderIndex": 0},
            {"id": n2, "nodeId": n2, "definitionType": "result", "name": "결과",
             "config": {}, "orderIndex": 1},
        ],
        "connections": [
            {"id": c1, "sourceNodeId": n1, "targetNodeId": n2,
             "sourceHandle": "output", "targetHandle": "input"},
        ],
    })
    wf_id = b.get("id", "")
    # status가 draft로 생성되면 PATCH로 활성화
    if s in (200, 201) and b.get("status") == "draft":
        r("PATCH", f"/workflows/{wf_id}", {"status": "active"})
    ok = s in (200, 201) and bool(wf_id)
    check("201 + id 반환", ok, f"status={s}, id={wf_id}")
    results["f"] = ok

    # ── g) 워크플로우 실행 ───────────────────────────────────────────────
    print("\ng) POST /workflows/{id}/run")
    if not wf_id:
        print("  [SKIP] 워크플로우 ID 없음 (f 단계 실패)")
        results["g"] = False
    else:
        s, b = r("POST", f"/workflows/{wf_id}/run", {"inputData": {"query": "테스트"}})
        instance_id = b.get("instanceId", "")
        ok = s == 202 and bool(instance_id)
        check("202 + instanceId 반환", ok, f"status={s}, instanceId={instance_id}")
        results["g"] = ok

    # ── h) 인스턴스 조회 ─────────────────────────────────────────────────
    print("\nh) GET /warehouse/instances/{id}")
    if not results.get("g"):
        print("  [SKIP] g 단계 실패")
        results["h"] = False
    else:
        time.sleep(3)  # 백그라운드 실행 대기
        s, b = r("GET", f"/warehouse/instances/{instance_id}")
        exec_status = b.get("status", "")
        ok = s == 200 and exec_status in ("completed", "running", "failed", "pending")
        check(f"200 + status 반환", ok, f"status={s}, execStatus={exec_status}")
        results["h"] = ok

    # ── i) 지식 프로모션 ─────────────────────────────────────────────────
    print("\ni) POST /knowledge/from-instance")
    if not results.get("h"):
        print("  [SKIP] h 단계 실패")
        results["i"] = False
    else:
        unique_suffix = uuid.uuid4().hex[:8]
        s, b = r("POST", "/knowledge/from-instance", {
            "instanceId": instance_id,
            "title": f"E2E 검증 결과 프로모션 {unique_suffix}",
            "category": "테스트",
            "tags": ["e2e", "검증"],
        })
        promo_id = b.get("id", "")
        ok = s in (200, 201) and bool(promo_id)
        check("201 + id 반환", ok, f"status={s}, id={promo_id}")
        results["i"] = ok

    # ── 요약 ─────────────────────────────────────────────────────────────
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    pct = int(passed / total * 100)
    print(f"\n=== 결과: {passed}/{total} 단계 성공 ({pct}%) ===")
    for step, ok in results.items():
        print(f"  {step}) {'PASS' if ok else 'FAIL'}")

    if pct >= 80:
        print("\nPhase 2c E2E 통과 기준(80%) 충족.")
        sys.exit(0)
    else:
        print("\nPhase 2c E2E 통과 기준(80%) 미달.")
        sys.exit(1)


if __name__ == "__main__":
    main()
