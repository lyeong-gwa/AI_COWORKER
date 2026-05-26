"""
Phase 4 마이그레이션 — 66 페이지 일괄 재태깅 (multi-service v3).

목적:
  1. 모든 페이지에 ``service`` 필드를 부여한다 (현재는 사실상 ``codeeyes`` 단일).
  2. 4종 legacy 카테고리(``codeeyes`` / ``ito-portal-operations`` /
     ``plugin-troubleshooting`` / ``faq``) 페이지를 신 8종 enum 중 하나로 재분류한다.
  3. category 변경 시 id 가 변경되므로 본문 내 ``[[old_cat/slug]]`` 형식 링크를
     mapping table 로 일괄 치환한다.

설계 근거:
  - `.omc/plans/지식-multi-service.md` §7.2 (마이그레이션 절차)
  - P1/P2 가 이미 service 필드/필터/API 검증을 완료한 상태.
  - PUT 라우터(``app/api/routes/knowledge.py:886``) 가 category 변경 시 file rename +
    `_index-{cat}.md` 갱신 + ChromaDB 동기화를 자동으로 수행한다.

호출:
  python scripts/migrate_to_multi_service.py --dry-run   # 보고서만, PUT 호출 없음
  python scripts/migrate_to_multi_service.py             # 실제 적용

가드:
  - LLM 응답이 enum 외 값이면 fallback (``service=codeeyes``, ``category=operations-guide``).
  - LLM 호출 실패 → 해당 페이지 skip, 보고에 명시.
  - PUT 실패 → 보고에 명시, 다음 페이지 계속.
  - 멱등성: 이미 신 카테고리 + service != "unknown" 인 페이지는 skip.

8002 서버는 가동 중이어야 한다 (마이그레이션은 PUT API 경유).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

# backend/ 를 sys.path 에 추가 (scripts/ 에서 직접 실행)
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

# .env 로드 (DEFAULT_LLM_PROVIDER 등)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(os.path.join(_BACKEND_DIR, ".env"))
except Exception:
    pass

import httpx  # noqa: E402

from app.services.llm import get_llm_handler, LLMRequest, LLMMessage  # noqa: E402
from app.services.knowledge_schema import load_schema  # noqa: E402

# ── 상수 / 설정 ──────────────────────────────────────────────────────────────

API_BASE = os.environ.get("KNOWLEDGE_API_BASE", "http://localhost:8002/api/v1/knowledge")

# 신 8종 카테고리 enum (P1 _schema.yaml). 변경 시 _schema.yaml 과 동기화 필요.
NEW_CATEGORIES = {
    "overview",
    "operations-guide",
    "troubleshooting",
    "faq",
    "integration",
    "member-management",
    "policy",
    "installation",
}

# legacy 카테고리 집합 (재분류 대상). faq 는 신·구 동명이라 그대로 두는 게 기본.
LEGACY_CATEGORIES = {"codeeyes", "ito-portal-operations", "plugin-troubleshooting"}

# legacy → fallback 신 카테고리 (LLM 실패 시 사용)
LEGACY_FALLBACK = {
    "codeeyes": "overview",
    "ito-portal-operations": "operations-guide",
    "plugin-troubleshooting": "troubleshooting",
    "faq": "faq",
}

# service enum (현재 2종). LLM 이 codeeyes 또는 unknown 중 선택.
ALLOWED_SERVICES = {"codeeyes", "unknown"}
DEFAULT_SERVICE = "codeeyes"

# 본문 첫 N 자만 LLM 에 전달 (토큰 절약)
CONTENT_PREVIEW_CHARS = 1000

REPORT_PATH = os.path.join(
    _BACKEND_DIR, "data", "knowledge", "_migration-multi-service-report.md"
)

# 페이지간 PUT 요청 간격 (rate limit / 부하 완화)
PUT_DELAY_SEC = 0.05


# ── 데이터 모델 ──────────────────────────────────────────────────────────────


@dataclass
class PageRecord:
    """API 에서 받은 한 페이지의 마이그레이션 결과."""

    old_id: str
    title: str
    old_category: str
    old_service: str

    # LLM/fallback 결정 결과
    new_service: str = ""
    new_category: str = ""
    new_id: str = ""
    llm_reason: str = ""
    llm_status: str = ""  # "ok" | "fallback" | "skip-already-new" | "error"
    llm_tokens_in: int = 0
    llm_tokens_out: int = 0

    # PUT 결과
    put_status: str = "pending"  # "pending" | "ok" | "skipped" | "error" | "dry-run"
    put_error: str = ""

    # 링크 보정 — 이 페이지가 다른 페이지에서 받는 인링크 수
    inlink_count: int = 0


@dataclass
class LinkPatchRecord:
    """본문 내 옛 id 링크 치환 결과 (cross-page 보정)."""

    owner_id: str  # 본문을 수정한 페이지 (마이그레이션 후 신 id 기준)
    replacements: List[Tuple[str, str]] = field(default_factory=list)  # [(old_id, new_id), ...]
    put_status: str = "pending"
    put_error: str = ""


# ── HTTP 유틸 ───────────────────────────────────────────────────────────────


async def fetch_all_pages(client: httpx.AsyncClient) -> List[Dict[str, Any]]:
    """현재 페이지 전부 조회."""
    resp = await client.get(API_BASE, timeout=30.0)
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, list):
        return data
    # envelope 형태일 경우 대응
    if isinstance(data, dict):
        if "items" in data:
            return data["items"]
    raise RuntimeError(f"unexpected /knowledge response shape: {type(data)}")


async def put_page(
    client: httpx.AsyncClient,
    doc_id: str,
    body: Dict[str, Any],
) -> Tuple[bool, str, Dict[str, Any]]:
    """PUT /knowledge/{id}. Returns (ok, error_msg, response_json)."""
    url = f"{API_BASE}/{doc_id}"
    try:
        resp = await client.put(url, json=body, timeout=60.0)
        if resp.status_code >= 400:
            return False, f"HTTP {resp.status_code}: {resp.text[:500]}", {}
        return True, "", resp.json()
    except Exception as e:  # noqa: BLE001
        return False, f"exception: {e}", {}


# ── LLM 분류 ────────────────────────────────────────────────────────────────


_LLM_SYSTEM_PROMPT = (
    "당신은 사내 지식 위키 페이지의 분류 보조자입니다. "
    "주어진 페이지의 제목과 본문 발췌, 그리고 (legacy) 카테고리를 보고 "
    "1) 어떤 service 인지, 2) 어떤 (신) category 가 가장 적합한지 JSON 으로만 답합니다.\n"
    "출력은 다음 JSON 한 객체뿐이며, 그 외 텍스트는 절대 포함하지 않습니다:\n"
    '{"service": "...", "category": "...", "reasoning": "한 문장 한국어"}'
)


def _build_user_prompt(title: str, content_preview: str, old_category: str) -> str:
    return (
        f"# 분류 작업\n\n"
        f"## 후보 service (이 중 하나만 선택)\n"
        f"- codeeyes : CodeEyes (소스코드 정적 분석) 서비스 관련 페이지\n"
        f"- unknown  : 명백히 다른 서비스이거나 판단 불가\n"
        f"  (참고: 현재 위키에는 CodeEyes 외 서비스가 없으므로 사실상 거의 모두 codeeyes)\n\n"
        f"## 후보 (신) category (이 중 하나만 선택)\n"
        f"- overview          : 서비스/시스템 전반 소개\n"
        f"- operations-guide  : 운영 절차/플로우/일상 운영 가이드\n"
        f"- troubleshooting   : 오류/장애/해결법\n"
        f"- faq               : 자주 묻는 질문\n"
        f"- integration       : 외부 시스템 연동/방화벽/API 통합 (GitHub, LDAP 등)\n"
        f"- member-management : 사용자/팀/권한 운영\n"
        f"- policy            : 권한/규칙/승인 기준 등 정책류\n"
        f"- installation      : 설치/구성/환경 셋업\n\n"
        f"## legacy → 신 카테고리 매핑 힌트 (강제는 아니나 우선 고려)\n"
        f"- 기존 codeeyes              → overview / operations-guide / integration\n"
        f"- 기존 ito-portal-operations → operations-guide / member-management / integration / policy 중 적합한 것\n"
        f"- 기존 plugin-troubleshooting → troubleshooting (대부분) / installation (설치 관련만)\n"
        f"- 기존 faq                   → faq\n\n"
        f"## 분류 대상\n"
        f"- 기존 category: {old_category}\n"
        f"- title: {title}\n"
        f"- 본문(첫 {CONTENT_PREVIEW_CHARS}자):\n{content_preview}\n\n"
        f'반드시 다음 JSON 한 객체로만 답하세요: {{"service":"...","category":"...","reasoning":"..."}}'
    )


def _extract_json_obj(text: str) -> Optional[Dict[str, Any]]:
    """모델이 ```json ... ``` 같은 코드펜스로 감쌌어도 첫 JSON 객체를 추출."""
    if not text:
        return None
    # 코드펜스 제거
    t = re.sub(r"```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    t = t.replace("```", "")
    # 첫 { ... } 매칭 (가장 외곽)
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


async def classify_page_with_llm(
    handler,
    title: str,
    content: str,
    old_category: str,
) -> Tuple[Optional[Dict[str, Any]], int, int, str]:
    """LLM 1회 호출 → (parsed_json|None, in_tokens, out_tokens, raw_or_err)."""
    preview = (content or "")[:CONTENT_PREVIEW_CHARS]
    user_prompt = _build_user_prompt(title, preview, old_category)
    req = LLMRequest(
        messages=[
            LLMMessage(role="system", content=_LLM_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt),
        ],
        temperature=0.0,
        max_tokens=300,
        call_type="migrate_multi_service",
    )
    # JSON 강제 (OpenAI response_format 호환). 핸들러가 무시하면 그냥 텍스트 파싱으로 fallback.
    req.extra = {"response_format": {"type": "json_object"}}

    try:
        resp = await handler.chat(req)
    except Exception as e:  # noqa: BLE001
        return None, 0, 0, f"llm-error: {e}"

    parsed = _extract_json_obj(resp.content or "")
    return parsed, resp.prompt_tokens, resp.completion_tokens, resp.content or ""


def _normalize_decision(
    decision: Optional[Dict[str, Any]],
    old_category: str,
) -> Tuple[str, str, str, str]:
    """LLM 응답 → (service, category, reasoning, status).

    status : "ok" | "fallback"
    """
    if not decision:
        # 완전 실패 → fallback
        fb_cat = LEGACY_FALLBACK.get(old_category, "operations-guide")
        return DEFAULT_SERVICE, fb_cat, "LLM 응답 파싱 실패 → 휴리스틱 fallback", "fallback"

    svc_raw = str(decision.get("service", "")).strip().lower()
    cat_raw = str(decision.get("category", "")).strip().lower()
    reason = str(decision.get("reasoning", "")).strip()

    svc = svc_raw if svc_raw in ALLOWED_SERVICES else DEFAULT_SERVICE
    cat = cat_raw if cat_raw in NEW_CATEGORIES else LEGACY_FALLBACK.get(old_category, "operations-guide")

    if svc_raw not in ALLOWED_SERVICES or cat_raw not in NEW_CATEGORIES:
        return svc, cat, f"{reason} (enum 보정 적용)".strip(), "fallback"
    return svc, cat, reason, "ok"


# ── 링크 보정 ───────────────────────────────────────────────────────────────


_LINK_PATTERN = re.compile(r"\[\[([^\[\]\n]+?)\]\]")


def patch_links(content: str, id_mapping: Dict[str, str]) -> Tuple[str, List[Tuple[str, str]]]:
    """본문 내 ``[[old_id]]`` 를 ``[[new_id]]`` 로 치환.

    id_mapping 키는 정확히 ``{old_cat}/{slug}`` 형태이며 변경된 페이지만 포함한다.
    Returns (new_content, replacements).
    """
    replacements: List[Tuple[str, str]] = []

    def _sub(m: re.Match) -> str:
        inner = m.group(1).strip()
        # `[[deleted:...]]` 등 비id 마커는 유지
        if inner.startswith("deleted:"):
            return m.group(0)
        # 정확 일치 우선
        if inner in id_mapping:
            new = id_mapping[inner]
            replacements.append((inner, new))
            return f"[[{new}]]"
        return m.group(0)

    new_content = _LINK_PATTERN.sub(_sub, content)
    return new_content, replacements


# ── 메인 마이그레이션 ───────────────────────────────────────────────────────


async def run_migration(dry_run: bool) -> Dict[str, Any]:
    started_at = datetime.now().isoformat()
    timings = {"started_at": started_at}

    # 1) schema sanity check
    schema = load_schema(force=True)
    schema_cat_ids = schema.category_ids
    schema_svc_ids = schema.service_ids
    missing_cats = [c for c in NEW_CATEGORIES if c not in schema_cat_ids]
    if missing_cats:
        raise RuntimeError(
            f"_schema.yaml 에 신 카테고리 누락: {missing_cats} — P1 schema 갱신 필요"
        )
    if "codeeyes" not in schema_svc_ids:
        raise RuntimeError("_schema.yaml services 에 'codeeyes' 미정의 — P1 schema 갱신 필요")

    # 2) 페이지 전체 로드
    async with httpx.AsyncClient() as client:
        pages = await fetch_all_pages(client)

    print(f"[INFO] 로드 페이지 수: {len(pages)}", flush=True)

    # 3) LLM 핸들러 준비
    handler = get_llm_handler()  # .env 기준 OpenAI
    print(f"[INFO] LLM provider: {handler.provider}, model: {handler.default_model}", flush=True)

    # 4) 분류 단계
    records: List[PageRecord] = []
    id_mapping: Dict[str, str] = {}  # 변경된 페이지만 (old_id -> new_id)
    total_in_tokens = 0
    total_out_tokens = 0

    # 인링크 count 계산 (보고용)
    inlink_counter: Dict[str, int] = {p["id"]: 0 for p in pages}
    for p in pages:
        for raw_target in p.get("links", []) or []:
            if raw_target in inlink_counter and raw_target != p["id"]:
                inlink_counter[raw_target] += 1

    classify_t0 = time.perf_counter()
    for idx, p in enumerate(pages, 1):
        old_id = p["id"]
        old_cat = p.get("category", "") or ""
        old_svc = p.get("service", "") or "unknown"
        title = p.get("title", old_id)
        content = p.get("content", "") or ""

        rec = PageRecord(
            old_id=old_id,
            title=title,
            old_category=old_cat,
            old_service=old_svc,
            inlink_count=inlink_counter.get(old_id, 0),
        )

        # 멱등성 check: 이미 신 카테고리 + service != "unknown" 이면 skip
        if old_cat in NEW_CATEGORIES and old_svc in ALLOWED_SERVICES and old_svc != "unknown":
            rec.new_service = old_svc
            rec.new_category = old_cat
            rec.new_id = old_id
            rec.llm_reason = "이미 신 분류 적용된 페이지 — LLM 호출 생략"
            rec.llm_status = "skip-already-new"
            rec.put_status = "skipped"
            records.append(rec)
            continue

        # LLM 호출
        try:
            parsed, ti, to, _raw = await classify_page_with_llm(handler, title, content, old_cat)
        except Exception as e:  # noqa: BLE001
            parsed, ti, to = None, 0, 0
            rec.llm_status = "error"
            rec.llm_reason = f"LLM 예외: {e}"

        total_in_tokens += ti
        total_out_tokens += to

        svc, new_cat, reason, status = _normalize_decision(parsed, old_cat)
        rec.new_service = svc
        rec.new_category = new_cat
        rec.llm_reason = reason or rec.llm_reason
        rec.llm_status = rec.llm_status or status
        rec.llm_tokens_in = ti
        rec.llm_tokens_out = to

        # 신 id
        if "/" in old_id:
            slug = old_id.split("/", 1)[1]
        else:
            slug = old_id
        rec.new_id = f"{new_cat}/{slug}"

        if rec.new_id != old_id:
            id_mapping[old_id] = rec.new_id

        records.append(rec)

        if idx % 5 == 0 or idx == len(pages):
            print(
                f"[CLASSIFY] {idx}/{len(pages)}  in_tok={total_in_tokens} out_tok={total_out_tokens}",
                flush=True,
            )

    classify_elapsed = time.perf_counter() - classify_t0
    timings["classify_sec"] = round(classify_elapsed, 1)
    timings["llm_tokens_in"] = total_in_tokens
    timings["llm_tokens_out"] = total_out_tokens

    # 5) PUT 단계 (dry-run 이면 skip)
    put_t0 = time.perf_counter()
    put_ok = 0
    put_skipped = 0
    put_failed = 0

    if not dry_run:
        async with httpx.AsyncClient() as client:
            for rec in records:
                if rec.put_status == "skipped":
                    put_skipped += 1
                    continue
                body = {
                    "service": rec.new_service,
                    "category": rec.new_category,
                    "operator": "migration:multi-service-v3",
                }
                ok, err, _resp = await put_page(client, rec.old_id, body)
                if ok:
                    rec.put_status = "ok"
                    put_ok += 1
                else:
                    rec.put_status = "error"
                    rec.put_error = err
                    put_failed += 1
                await asyncio.sleep(PUT_DELAY_SEC)
    else:
        for rec in records:
            if rec.put_status == "skipped":
                put_skipped += 1
                continue
            rec.put_status = "dry-run"

    put_elapsed = time.perf_counter() - put_t0
    timings["put_sec"] = round(put_elapsed, 1)

    # 6) 링크 보정 단계 — 페이지 다시 로드 (id 가 바뀌었을 수 있음)
    link_patches: List[LinkPatchRecord] = []
    link_t0 = time.perf_counter()

    if not dry_run:
        async with httpx.AsyncClient() as client:
            pages_after = await fetch_all_pages(client)
            # 본문에서 옛 id 패턴 찾아 치환 후 PUT
            for p in pages_after:
                cur_id = p["id"]
                content = p.get("content", "") or ""
                if not content:
                    continue
                new_content, repls = patch_links(content, id_mapping)
                if not repls:
                    continue
                patch_rec = LinkPatchRecord(owner_id=cur_id, replacements=repls)
                body = {
                    "content": new_content,
                    "operator": "migration:multi-service-v3-linkfix",
                }
                ok, err, _resp = await put_page(client, cur_id, body)
                if ok:
                    patch_rec.put_status = "ok"
                else:
                    patch_rec.put_status = "error"
                    patch_rec.put_error = err
                link_patches.append(patch_rec)
                await asyncio.sleep(PUT_DELAY_SEC)
    else:
        # dry-run 도 어느 페이지가 영향받을지 simulate
        async with httpx.AsyncClient() as client:
            pages_again = await fetch_all_pages(client)
        for p in pages_again:
            cur_id = p["id"]
            content = p.get("content", "") or ""
            if not content:
                continue
            _, repls = patch_links(content, id_mapping)
            if repls:
                link_patches.append(
                    LinkPatchRecord(owner_id=cur_id, replacements=repls, put_status="dry-run")
                )

    link_elapsed = time.perf_counter() - link_t0
    timings["link_patch_sec"] = round(link_elapsed, 1)

    # 7) 결과 보고서 작성
    summary = {
        "dry_run": dry_run,
        "page_count": len(pages),
        "renamed_count": len(id_mapping),
        "put_ok": put_ok,
        "put_skipped": put_skipped,
        "put_failed": put_failed,
        "link_patch_pages": len(link_patches),
        "link_patch_total_replacements": sum(len(lp.replacements) for lp in link_patches),
        **timings,
        "finished_at": datetime.now().isoformat(),
    }
    write_report(summary, records, link_patches)
    return {"summary": summary, "records": records, "link_patches": link_patches}


# ── 보고서 ──────────────────────────────────────────────────────────────────


def write_report(
    summary: Dict[str, Any],
    records: List[PageRecord],
    link_patches: List[LinkPatchRecord],
) -> None:
    lines: List[str] = []
    lines.append("# Multi-Service v3 마이그레이션 보고서\n")
    lines.append(f"- mode: **{'DRY-RUN' if summary['dry_run'] else 'APPLY'}**")
    lines.append(f"- 시작: {summary.get('started_at')}")
    lines.append(f"- 종료: {summary.get('finished_at')}")
    lines.append(f"- 총 페이지: {summary['page_count']}")
    lines.append(f"- 카테고리 변경 (id rename): {summary['renamed_count']}")
    lines.append(
        f"- PUT 결과: ok={summary['put_ok']}, skipped={summary['put_skipped']}, failed={summary['put_failed']}"
    )
    lines.append(
        f"- 링크 보정: 페이지={summary['link_patch_pages']}, 치환 합계={summary['link_patch_total_replacements']}"
    )
    lines.append(
        f"- LLM 토큰: in={summary.get('llm_tokens_in',0)} / out={summary.get('llm_tokens_out',0)}"
    )
    lines.append(
        f"- 시간(초): classify={summary.get('classify_sec')}, put={summary.get('put_sec')}, link_patch={summary.get('link_patch_sec')}"
    )

    # 카테고리 분포
    from collections import Counter

    new_cat_dist = Counter(r.new_category for r in records)
    new_svc_dist = Counter(r.new_service for r in records)
    lines.append("\n## 마이그레이션 후 분포 (계획)\n")
    lines.append("### 서비스")
    for k, v in sorted(new_svc_dist.items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")
    lines.append("\n### 카테고리")
    for k, v in sorted(new_cat_dist.items(), key=lambda x: -x[1]):
        lines.append(f"- {k}: {v}")

    # 페이지별 표
    lines.append("\n## 페이지별 결정\n")
    lines.append("| # | old_id | new_id | old_cat → new_cat | service | LLM 상태 | PUT 상태 | reason |")
    lines.append("|---|---|---|---|---|---|---|---|")
    for i, r in enumerate(records, 1):
        reason_short = (r.llm_reason or "").replace("|", "/").replace("\n", " ")[:120]
        lines.append(
            f"| {i} | `{r.old_id}` | `{r.new_id}` | `{r.old_category}` → `{r.new_category}` "
            f"| {r.new_service} | {r.llm_status} | {r.put_status} | {reason_short} |"
        )

    # 실패 페이지 별도 섹션
    fails = [r for r in records if r.put_status == "error" or r.llm_status == "error"]
    if fails:
        lines.append("\n## 실패 페이지\n")
        for r in fails:
            lines.append(f"- `{r.old_id}` — llm_status={r.llm_status} put_status={r.put_status}")
            if r.put_error:
                lines.append(f"  - put_error: `{r.put_error}`")
            if r.llm_status == "error":
                lines.append(f"  - llm_reason: `{r.llm_reason}`")

    # 링크 보정 상세
    if link_patches:
        lines.append("\n## 링크 보정 상세\n")
        lines.append("| # | owner | 치환 수 | 상태 | 샘플 (old → new) |")
        lines.append("|---|---|---|---|---|")
        for i, lp in enumerate(link_patches, 1):
            sample = ", ".join(f"`{a}` → `{b}`" for a, b in lp.replacements[:3])
            if len(lp.replacements) > 3:
                sample += f" (+{len(lp.replacements)-3} more)"
            lines.append(
                f"| {i} | `{lp.owner_id}` | {len(lp.replacements)} | {lp.put_status} | {sample} |"
            )

    # 멱등성 안내
    lines.append("\n## 재실행 안내\n")
    lines.append(
        "- 이 스크립트는 멱등 설계입니다 (이미 신 분류된 페이지는 LLM 호출 없이 skip)."
    )
    lines.append(
        "- 실패만 다시 돌리려면: 페이지 카테고리/서비스를 수동으로 되돌린 후 재실행."
    )

    os.makedirs(os.path.dirname(REPORT_PATH), exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[OK] 보고서: {REPORT_PATH}", flush=True)


# ── CLI ─────────────────────────────────────────────────────────────────────


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Phase 4 멀티-서비스 마이그레이션")
    p.add_argument("--dry-run", action="store_true", help="보고서만, PUT 호출 없음")
    return p.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    try:
        result = asyncio.run(run_migration(dry_run=args.dry_run))
    except Exception as e:  # noqa: BLE001
        print(f"[FATAL] {e}", file=sys.stderr)
        return 2

    s = result["summary"]
    mode = "DRY-RUN" if s["dry_run"] else "APPLY"
    print(
        f"[DONE] mode={mode} pages={s['page_count']} renamed={s['renamed_count']} "
        f"put_ok={s['put_ok']} put_skipped={s['put_skipped']} put_failed={s['put_failed']} "
        f"link_patch_pages={s['link_patch_pages']} link_replacements={s['link_patch_total_replacements']} "
        f"llm_in={s.get('llm_tokens_in')} llm_out={s.get('llm_tokens_out')}",
        flush=True,
    )
    if s["put_failed"] > 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
