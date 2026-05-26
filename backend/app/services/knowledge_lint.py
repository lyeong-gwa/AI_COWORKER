"""Knowledge Lint — Karpathy v2 P4 (`.omc/plans/지식-karpathy-v2.md` §9).

On-demand 위키 점검 — 정적(LLM 미호출) + 동적(LLM batch) 2단계.

설계 근거:
  - §9.1 단계별 흐름 (정적 → 동적 → 보고서)
  - §9.2 보고서 형식 (`_lint-report.md`)
  - §9.3 LLM 비용 견적
  - D3 on-demand only, D11 보고서 단일 + history 백업
  - D13 LLM temperature=0.1, batch 5건

주의:
  - 절대 자동 스케줄러 추가 금지 (D3 — on-demand only)
  - LLM 호출은 정적 검사 _후_ 에만 (lint cost 가시화)
  - `dry_run=true` 시 LLM 호출 0, 보고서/history 는 작성
  - `llm_enabled=false` 시 LLM 호출 0, dynamic 섹션은 모두 (none)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ..core.config import _BACKEND_DIR, settings
from .knowledge_file_service import KnowledgeFileDoc, list_md_files
from .knowledge_link_parser import LINK_PATTERN, parse_links
from .knowledge_schema import (
    KnowledgeSchema,
    SchemaValidationError,
    load_schema,
    validate_category,
    validate_page_type,
    validate_slug,
)

logger = logging.getLogger(__name__)


# ── 비용 견적 (plan §9.3) ─────────────────────────────────────────────────
# Sonnet 가격 가정 — in $3/M tokens, out $15/M tokens. 페어당 평균 토큰.
_AVG_DUP_TOKENS_IN = 1500
_AVG_DUP_TOKENS_OUT = 100
_AVG_CONTRADICTION_TOKENS_IN = 2000
_AVG_CONTRADICTION_TOKENS_OUT = 150
_AVG_OUTDATED_TOKENS_IN = 800
_AVG_OUTDATED_TOKENS_OUT = 50
_PRICE_IN_PER_M = 3.0
_PRICE_OUT_PER_M = 15.0

# 임계값
_DUP_COSINE_THRESHOLD = 0.92         # 의미적 중복 후보
_CONTRADICTION_COSINE_THRESHOLD = 0.85  # 모순 후보 — title 유사도 추가 필터
_OUTDATED_DATE_PATTERN = re.compile(r"20\d{2}[-./]\d{1,2}")
_LLM_BATCH_SIZE = 5

_SLUG_REGEX_DEFAULT = r"^[a-z0-9]+(-[a-z0-9]+)*$"


# ── 보고서 경로 helpers ────────────────────────────────────────────────────


def _knowledge_dir() -> str:
    d = settings.KNOWLEDGE_DIR
    if not os.path.isabs(d):
        d = os.path.join(_BACKEND_DIR, d)
    os.makedirs(d, exist_ok=True)
    return d


def _report_path() -> str:
    return os.path.join(_knowledge_dir(), "_lint-report.md")


def _history_dir() -> str:
    p = os.path.join(_knowledge_dir(), "_lint-history")
    os.makedirs(p, exist_ok=True)
    return p


def _history_path(now: datetime) -> str:
    return os.path.join(_history_dir(), now.strftime("%Y-%m-%d_%H%M%S") + ".md")


# ── 결과 구조 ──────────────────────────────────────────────────────────────


@dataclass
class LintFinding:
    """단일 위반 1건."""

    kind: str  # "duplicate" | "contradiction" | "orphan" | "outdated" | "broken_link" | "schema_violation"
    severity: str  # "error" | "warning" | "info"
    payload: Dict[str, Any] = field(default_factory=dict)


# ── 정적 검사 ──────────────────────────────────────────────────────────────


def _is_entity(doc: KnowledgeFileDoc) -> bool:
    return (doc.page_type or "").strip() == "Entity"


def _doc_min_links(doc: KnowledgeFileDoc, schema: KnowledgeSchema) -> int:
    """`_schema.yaml.page_types.{page_type}.min_links` 가 정의되어 있으면 반환.

    명시 안 되어 있으면 0 (검사 안 함). plan §8.1 의 Comparison min_links=2 등.
    """
    if not doc.page_type:
        return 0
    pt = schema.page_types.get(doc.page_type) or {}
    try:
        return int(pt.get("min_links", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _static_schema_violations(
    docs: List[KnowledgeFileDoc],
    schema: KnowledgeSchema,
) -> List[LintFinding]:
    """카테고리 enum / page_type enum / slug regex 위반 점검."""
    findings: List[LintFinding] = []
    for d in docs:
        # category
        try:
            if d.category:
                validate_category(d.category, schema=schema)
            elif schema.category_ids:
                # 카테고리 정의돼 있는데 doc.category 비어있음 → 위반
                findings.append(LintFinding(
                    kind="schema_violation",
                    severity="error",
                    payload={
                        "id": d.id,
                        "field": "category",
                        "reason": "category 가 비어 있습니다 (_schema.yaml 에 카테고리가 정의된 상태)",
                    },
                ))
        except SchemaValidationError as exc:
            findings.append(LintFinding(
                kind="schema_violation",
                severity="error",
                payload={
                    "id": d.id,
                    "field": "category",
                    "reason": str(exc),
                    "details": exc.details,
                },
            ))
        # page_type
        try:
            validate_page_type(d.page_type, schema=schema)
        except SchemaValidationError as exc:
            findings.append(LintFinding(
                kind="schema_violation",
                severity="error",
                payload={
                    "id": d.id,
                    "field": "page_type",
                    "reason": str(exc),
                    "details": exc.details,
                },
            ))
        # slug — id 가 "{category}/{slug}" 형태일 때만
        if "/" in d.id:
            _, _, slug = d.id.partition("/")
            try:
                validate_slug(slug, schema=schema)
            except SchemaValidationError as exc:
                findings.append(LintFinding(
                    kind="schema_violation",
                    severity="error",
                    payload={
                        "id": d.id,
                        "field": "slug",
                        "reason": str(exc),
                        "details": exc.details,
                    },
                ))
    return findings


def _static_broken_links(docs: List[KnowledgeFileDoc]) -> List[LintFinding]:
    """본문 `[[...]]` 가 실제 페이지에 없음 + `[[deleted:*]]` 표식 점검."""
    findings: List[LintFinding] = []
    all_ids = {d.id for d in docs}
    for d in docs:
        # link parser 가 raw target 반환. `[[deleted:foo]]` 도 target="deleted:foo" 로 캡처.
        for tgt in (d.links or []):
            if tgt.startswith("deleted:"):
                # cascade 마커 — info 수준으로 보고
                findings.append(LintFinding(
                    kind="broken_link",
                    severity="info",
                    payload={
                        "from": d.id,
                        "to": tgt.split(":", 1)[1],
                        "reason": "deleted 마커 (force delete 후 잔재)",
                    },
                ))
                continue
            if tgt not in all_ids:
                findings.append(LintFinding(
                    kind="broken_link",
                    severity="warning",
                    payload={
                        "from": d.id,
                        "to": tgt,
                        "reason": "target 페이지가 존재하지 않음",
                    },
                ))
    return findings


def _static_orphans(docs: List[KnowledgeFileDoc]) -> List[LintFinding]:
    """고아 페이지 — backlink 0 (Entity 제외)."""
    findings: List[LintFinding] = []
    backlink_count: Dict[str, int] = {d.id: 0 for d in docs}
    for d in docs:
        for tgt in (d.links or []):
            # `deleted:` prefix 제거
            real = tgt[len("deleted:"):] if tgt.startswith("deleted:") else tgt
            if real in backlink_count and real != d.id:
                backlink_count[real] += 1
    for d in docs:
        if _is_entity(d):
            continue
        if backlink_count.get(d.id, 0) == 0:
            findings.append(LintFinding(
                kind="orphan",
                severity="warning",
                payload={
                    "id": d.id,
                    "page_type": d.page_type or "",
                    "reason": "어떤 페이지도 이 페이지를 link/backlink 하지 않음",
                },
            ))
    return findings


def _static_min_links(
    docs: List[KnowledgeFileDoc],
    schema: KnowledgeSchema,
) -> List[LintFinding]:
    """page_type 최소 링크 위반 (e.g. Comparison min_links=2)."""
    findings: List[LintFinding] = []
    for d in docs:
        required = _doc_min_links(d, schema)
        if required <= 0:
            continue
        # `deleted:` 마커는 실제 link 로 카운트하지 않음
        actual_links = [t for t in (d.links or []) if not t.startswith("deleted:")]
        if len(actual_links) < required:
            findings.append(LintFinding(
                kind="schema_violation",
                severity="warning",
                payload={
                    "id": d.id,
                    "field": "links",
                    "reason": (
                        f"page_type={d.page_type} min_links={required} 인데 "
                        f"현 outgoing link 수 {len(actual_links)}"
                    ),
                    "details": {"required": required, "actual": len(actual_links)},
                },
            ))
    return findings


def run_static_checks(
    docs: List[KnowledgeFileDoc],
    schema: KnowledgeSchema,
) -> Tuple[List[LintFinding], List[LintFinding], List[LintFinding], List[LintFinding]]:
    """정적 검사 묶음 — (schema_violations, broken_links, orphans, min_links_violations).

    min_links 위반은 schema 카테고리에 합쳐서 보고하므로 별도 묶음으로 둔다.
    """
    schema_v = _static_schema_violations(docs, schema)
    broken = _static_broken_links(docs)
    orphans = _static_orphans(docs)
    min_links = _static_min_links(docs, schema)
    return schema_v, broken, orphans, min_links


# ── 동적 검사 — 임베딩 기반 페어 추출 ───────────────────────────────────


def _cosine(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _embed_docs(docs: List[KnowledgeFileDoc]) -> Dict[str, List[float]]:
    """페이지별 임베딩 1건 (제목+본문 head). ChromaDB 가 아닌 embedding service 직접 호출.

    ChromaDB 내부의 chunk 단위 embedding 은 검색 dedup 용이라 페어 비교에는
    1 페이지=1 벡터 (제목 + 본문 첫 800 문자) 가 더 안정적이다.
    """
    try:
        from .embedding import get_embedding_service
        svc = get_embedding_service()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LINT] embedding service 사용 불가 — 동적 검사 skip: %s", exc)
        return {}

    texts: List[str] = []
    ids: List[str] = []
    for d in docs:
        head = (d.content or "")[:800]
        # title 가중치 — 짧으니 2회 반복
        texts.append(f"{d.title}\n{d.title}\n{head}")
        ids.append(d.id)

    try:
        vectors = svc.embed_batch(texts, batch_size=32)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LINT] embed_batch 실패 — 동적 검사 skip: %s", exc)
        return {}

    return {doc_id: vec for doc_id, vec in zip(ids, vectors)}


def _duplicate_candidates(
    docs: List[KnowledgeFileDoc],
    embeddings: Dict[str, List[float]],
) -> List[Tuple[KnowledgeFileDoc, KnowledgeFileDoc, float]]:
    """같은 카테고리 내 코사인 > 0.92 페어."""
    pairs: List[Tuple[KnowledgeFileDoc, KnowledgeFileDoc, float]] = []
    by_cat: Dict[str, List[KnowledgeFileDoc]] = {}
    for d in docs:
        by_cat.setdefault(d.category or "_uncat_", []).append(d)

    for cat, cat_docs in by_cat.items():
        for i in range(len(cat_docs)):
            for j in range(i + 1, len(cat_docs)):
                a, b = cat_docs[i], cat_docs[j]
                va = embeddings.get(a.id)
                vb = embeddings.get(b.id)
                if not va or not vb:
                    continue
                sim = _cosine(va, vb)
                if sim > _DUP_COSINE_THRESHOLD:
                    pairs.append((a, b, sim))
    pairs.sort(key=lambda t: t[2], reverse=True)
    return pairs


def _contradiction_candidates(
    docs: List[KnowledgeFileDoc],
    embeddings: Dict[str, List[float]],
) -> List[Tuple[KnowledgeFileDoc, KnowledgeFileDoc, float]]:
    """cosine > 0.85 + title 키워드 1개 이상 공유."""
    pairs: List[Tuple[KnowledgeFileDoc, KnowledgeFileDoc, float]] = []

    def _kw(t: str) -> set:
        # 매우 단순한 키워드 — 길이 2 이상의 토큰
        tokens = re.split(r"[\s\-_/]+", (t or "").lower())
        return {tok for tok in tokens if len(tok) >= 2}

    for i in range(len(docs)):
        ka = _kw(docs[i].title)
        for j in range(i + 1, len(docs)):
            a, b = docs[i], docs[j]
            kb = _kw(b.title)
            if not (ka & kb):
                continue
            va = embeddings.get(a.id)
            vb = embeddings.get(b.id)
            if not va or not vb:
                continue
            sim = _cosine(va, vb)
            if sim > _CONTRADICTION_COSINE_THRESHOLD:
                pairs.append((a, b, sim))
    pairs.sort(key=lambda t: t[2], reverse=True)
    return pairs


def _outdated_candidates(
    docs: List[KnowledgeFileDoc],
    log_recent_ids: set,
) -> List[KnowledgeFileDoc]:
    """`_log.md` 최근 변경 없는 페이지 + 본문에 날짜 패턴 포함."""
    out: List[KnowledgeFileDoc] = []
    for d in docs:
        if d.id in log_recent_ids:
            continue
        if not _OUTDATED_DATE_PATTERN.search(d.content or ""):
            continue
        out.append(d)
    return out


def _recent_log_ids(limit: int = 50) -> set:
    """최근 `_log.md` 행에서 doc_id 추출 (출처: append_log_entry 포맷)."""
    path = os.path.join(_knowledge_dir(), "_log.md")
    if not os.path.exists(path):
        return set()
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
    except OSError:
        return set()
    pat = re.compile(r"^##\s*\[[^\]]+\]\s*\S+\s*\|\s*([^|]+?)\s*\|")
    ids: List[str] = []
    for ln in lines:
        m = pat.match(ln)
        if m:
            ids.append(m.group(1).strip())
    return set(ids[-limit:])


# ── LLM 동적 verdict ──────────────────────────────────────────────────────


def _estimate_cost_usd(llm_in_tokens: int, llm_out_tokens: int) -> float:
    cost = (
        (llm_in_tokens / 1_000_000.0) * _PRICE_IN_PER_M
        + (llm_out_tokens / 1_000_000.0) * _PRICE_OUT_PER_M
    )
    return round(cost, 6)


async def _llm_verdict_for_pairs(
    pairs: List[Tuple[KnowledgeFileDoc, KnowledgeFileDoc, float]],
    *,
    kind: str,  # "duplicate" or "contradiction"
) -> Tuple[List[Dict[str, Any]], int, int, int]:
    """LLM 에 batch (size 5) 로 페어 평가. (verdicts, llm_calls, in_tokens, out_tokens)."""
    if not pairs:
        return [], 0, 0, 0
    try:
        from .llm.registry import get_llm_handler
        handler = get_llm_handler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LINT] LLM handler 사용 불가 — %s 검사 skip: %s", kind, exc)
        # fallback: LLM 호출 없이 cosine 만으로 후보 보고
        verdicts = []
        for a, b, sim in pairs:
            verdicts.append({
                "a": a.id, "b": b.id, "cosine": round(sim, 4),
                "llm_verdict": "LLM_UNAVAILABLE",
                "llm_finding": "",
            })
        return verdicts, 0, 0, 0

    verdicts: List[Dict[str, Any]] = []
    llm_calls = 0
    in_toks = 0
    out_toks = 0

    if kind == "duplicate":
        system = (
            "당신은 위키 페이지 중복 검토 전문가입니다. "
            "두 페이지의 제목+본문이 의미적으로 중복(같은 주제·같은 정보)인지 판단하세요. "
            "각 페어에 대해 'MERGE_CANDIDATE' (병합 권장) 또는 'DIFFERENT' (다른 주제) "
            "와 한 줄 평가를 JSON 배열로 응답하세요. "
            "형식: [{\"pair\":1,\"verdict\":\"MERGE_CANDIDATE\",\"reason\":\"...\"}, ...]"
        )
    else:  # contradiction
        system = (
            "당신은 위키 페이지 모순 검토 전문가입니다. "
            "두 페이지가 같은 주제를 다루지만 _주장·결론·정책이 충돌_ 하는지 판단하세요. "
            "각 페어에 대해 'CONTRADICTION' (모순 있음) 또는 'CONSISTENT' (충돌 없음) "
            "와 한 줄 근거를 JSON 배열로 응답하세요. "
            "형식: [{\"pair\":1,\"verdict\":\"CONTRADICTION\",\"reason\":\"...\"}, ...]"
        )

    for batch_start in range(0, len(pairs), _LLM_BATCH_SIZE):
        batch = pairs[batch_start: batch_start + _LLM_BATCH_SIZE]
        prompt_parts: List[str] = []
        for idx, (a, b, sim) in enumerate(batch, start=1):
            prompt_parts.append(
                f"### 페어 {idx} (cosine={sim:.3f})\n"
                f"#### A — id={a.id}, title={a.title}, page_type={a.page_type}\n"
                f"{(a.content or '')[:600]}\n\n"
                f"#### B — id={b.id}, title={b.title}, page_type={b.page_type}\n"
                f"{(b.content or '')[:600]}"
            )
        user_prompt = "\n\n".join(prompt_parts) + "\n\n위 페어들을 평가하여 JSON 배열로만 응답하세요."

        try:
            resp = await handler.simple_chat(
                prompt=user_prompt,
                system_prompt=system,
                temperature=0.1,
                max_tokens=600,
                call_type=f"lint_{kind}",
            )
            llm_calls += 1
            in_toks += int(resp.prompt_tokens or 0)
            out_toks += int(resp.completion_tokens or 0)
            content = (resp.content or "").strip()
            # 코드펜스 제거
            if "```json" in content:
                content = content.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in content:
                content = content.split("```", 1)[1].split("```", 1)[0].strip()
            # JSON 배열 추출
            start_idx = content.find("[")
            end_idx = content.rfind("]")
            parsed: List[Dict[str, Any]] = []
            if start_idx != -1 and end_idx != -1:
                try:
                    parsed = json.loads(content[start_idx: end_idx + 1])
                except Exception:  # noqa: BLE001
                    parsed = []
            # 각 페어별 응답 매핑
            for idx, (a, b, sim) in enumerate(batch, start=1):
                match = next(
                    (p for p in parsed if int(p.get("pair", 0) or 0) == idx),
                    None,
                )
                if match is None:
                    verdicts.append({
                        "a": a.id, "b": b.id, "cosine": round(sim, 4),
                        "llm_verdict": "PARSE_ERROR",
                        "llm_finding": (resp.content or "")[:200],
                    })
                else:
                    verdicts.append({
                        "a": a.id, "b": b.id, "cosine": round(sim, 4),
                        "llm_verdict": str(match.get("verdict", "")) or "UNKNOWN",
                        "llm_finding": str(match.get("reason", "")),
                    })
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LINT] LLM %s 호출 실패: %s", kind, exc)
            for a, b, sim in batch:
                verdicts.append({
                    "a": a.id, "b": b.id, "cosine": round(sim, 4),
                    "llm_verdict": "LLM_ERROR",
                    "llm_finding": str(exc)[:160],
                })

    return verdicts, llm_calls, in_toks, out_toks


async def _llm_outdated_findings(
    candidates: List[KnowledgeFileDoc],
) -> Tuple[List[Dict[str, Any]], int, int, int]:
    """outdated 의심 페이지에 LLM 한 줄 질의."""
    if not candidates:
        return [], 0, 0, 0
    try:
        from .llm.registry import get_llm_handler
        handler = get_llm_handler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[LINT] LLM handler 사용 불가 — outdated 검사 skip: %s", exc)
        return [
            {"id": c.id, "llm_finding": "LLM_UNAVAILABLE"} for c in candidates
        ], 0, 0, 0

    findings: List[Dict[str, Any]] = []
    llm_calls = 0
    in_toks = 0
    out_toks = 0
    system = (
        "당신은 운영 문서 최신성 검토 전문가입니다. "
        "주어진 페이지 본문에 등장하는 날짜·버전이 _현재 시점에서 구식_ 인지 평가하세요. "
        "응답은 JSON 배열로만: "
        "[{\"id\":\"...\",\"verdict\":\"OUTDATED\"|\"OK\",\"reason\":\"한 줄\"}, ...]"
    )
    # batch 5 페이지씩
    for batch_start in range(0, len(candidates), _LLM_BATCH_SIZE):
        batch = candidates[batch_start: batch_start + _LLM_BATCH_SIZE]
        prompt_parts = []
        for c in batch:
            prompt_parts.append(
                f"### id={c.id}\n#### title: {c.title}\n#### body (head 400):\n"
                f"{(c.content or '')[:400]}"
            )
        user_prompt = "\n\n".join(prompt_parts) + "\n\n위 페이지들의 최신성을 JSON 배열로만 응답하세요."

        try:
            resp = await handler.simple_chat(
                prompt=user_prompt,
                system_prompt=system,
                temperature=0.1,
                max_tokens=600,
                call_type="lint_outdated",
            )
            llm_calls += 1
            in_toks += int(resp.prompt_tokens or 0)
            out_toks += int(resp.completion_tokens or 0)
            content = (resp.content or "").strip()
            if "```json" in content:
                content = content.split("```json", 1)[1].split("```", 1)[0].strip()
            elif "```" in content:
                content = content.split("```", 1)[1].split("```", 1)[0].strip()
            start_idx = content.find("[")
            end_idx = content.rfind("]")
            parsed: List[Dict[str, Any]] = []
            if start_idx != -1 and end_idx != -1:
                try:
                    parsed = json.loads(content[start_idx: end_idx + 1])
                except Exception:  # noqa: BLE001
                    parsed = []
            for c in batch:
                match = next((p for p in parsed if str(p.get("id", "")) == c.id), None)
                if match and str(match.get("verdict", "")).upper() == "OUTDATED":
                    findings.append({
                        "id": c.id,
                        "llm_finding": str(match.get("reason", ""))[:200],
                    })
        except Exception as exc:  # noqa: BLE001
            logger.warning("[LINT] LLM outdated 호출 실패: %s", exc)
    return findings, llm_calls, in_toks, out_toks


# ── 보고서 작성 ────────────────────────────────────────────────────────────


def _section_or_none(title: str, rows: List[str]) -> List[str]:
    out = [f"## {title}", ""]
    if not rows:
        out.append("(none)")
        out.append("")
    else:
        out.extend(rows)
        out.append("")
    return out


def _format_report(
    *,
    now: datetime,
    summary: Dict[str, Any],
    duplicates: List[Dict[str, Any]],
    contradictions: List[Dict[str, Any]],
    orphans: List[Dict[str, Any]],
    outdated: List[Dict[str, Any]],
    broken_links: List[Dict[str, Any]],
    schema_violations: List[Dict[str, Any]],
) -> str:
    """plan §9.2 의 형식 그대로 markdown 생성."""
    lines: List[str] = []
    lines.append(f"# Knowledge Lint Report — {now.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Errors: {summary['errors']}")
    lines.append(f"- Warnings: {summary['warnings']}")
    lines.append(f"- Info: {summary['info']}")
    lines.append(
        f"- LLM calls: {summary['llm_calls']} "
        f"(estimated cost: ${summary['estimated_cost_usd']:.2f})"
    )
    lines.append("")

    # 1. Duplicates
    dup_rows = []
    for d in duplicates:
        dup_rows.append(
            f"- [[{d['a']}]] ↔ [[{d['b']}]] (cosine={d.get('cosine', 0):.3f}, "
            f"LLM verdict: {d.get('llm_verdict', 'N/A')}"
            + (f" — {d['llm_finding']}" if d.get("llm_finding") else "")
            + ")"
        )
    lines.extend(_section_or_none("1. Duplicates (의미적 중복 후보)", dup_rows))

    # 2. Contradictions
    con_rows = []
    for c in contradictions:
        con_rows.append(
            f"- [[{c['a']}]] vs [[{c['b']}]] (LLM: {c.get('llm_finding', '')})"
        )
    lines.extend(_section_or_none("2. Contradictions (모순)", con_rows))

    # 3. Orphans
    orph_rows = []
    for o in orphans:
        orph_rows.append(
            f"- [[{o['id']}]] — page_type={o.get('page_type', '')}, {o.get('reason', '')}"
        )
    lines.extend(_section_or_none("3. Orphans (고아 페이지)", orph_rows))

    # 4. Outdated
    out_rows = []
    for o in outdated:
        out_rows.append(
            f"- [[{o['id']}]] — {o.get('llm_finding', '최신성 검토 권고')}"
        )
    lines.extend(_section_or_none("4. Outdated (구식 의심)", out_rows))

    # 5. Broken Cross-References
    bl_rows = []
    for b in broken_links:
        bl_rows.append(
            f"- [[{b['to']}]] in [[{b['from']}]] — {b.get('reason', '')}"
        )
    lines.extend(_section_or_none("5. Broken Cross-References (깨진 링크)", bl_rows))

    # 6. Schema Violations
    sv_rows = []
    for s in schema_violations:
        sv_rows.append(
            f"- `{s['id']}` — field={s.get('field', '?')}, {s.get('reason', '')}"
        )
    lines.extend(_section_or_none("6. Schema Violations", sv_rows))

    return "\n".join(lines).rstrip() + "\n"


def _write_report(content: str, *, now: datetime) -> Tuple[str, str]:
    """`_lint-report.md` 덮어쓰기 + `_lint-history/{ts}.md` 백업.

    Returns:
        (report_path, history_path) - 둘 다 backend/ 기준 상대경로.
    """
    rp = _report_path()
    hp = _history_path(now)
    with open(rp, "w", encoding="utf-8") as f:
        f.write(content)
    with open(hp, "w", encoding="utf-8") as f:
        f.write(content)

    # backend 기준 상대경로로 반환 (응답 가독성)
    def _rel(p: str) -> str:
        try:
            return os.path.relpath(p, _BACKEND_DIR).replace("\\", "/")
        except ValueError:
            return p.replace("\\", "/")
    return _rel(rp), _rel(hp)


# ── 메인 API ───────────────────────────────────────────────────────────────


def _severity_summary(
    schema_violations: List[Dict[str, Any]],
    broken_links: List[Dict[str, Any]],
    orphans: List[Dict[str, Any]],
    duplicates: List[Dict[str, Any]],
    contradictions: List[Dict[str, Any]],
    outdated: List[Dict[str, Any]],
) -> Tuple[int, int, int]:
    """error/warning/info 카운트.

    분류 규칙:
      - errors: schema_violation (field in {category, page_type, slug})
      - warnings: broken_link (warning), orphans, duplicates (MERGE_CANDIDATE),
                 contradictions (CONTRADICTION), schema_violations(min_links)
      - info: broken_link (info — deleted 마커), outdated, 기타
    """
    errors = 0
    warnings = 0
    info = 0

    for sv in schema_violations:
        if sv.get("field") in {"category", "page_type", "slug"}:
            errors += 1
        else:
            warnings += 1

    for bl in broken_links:
        if bl.get("severity") == "info":
            info += 1
        else:
            warnings += 1

    warnings += len(orphans)

    for d in duplicates:
        v = (d.get("llm_verdict") or "").upper()
        if v == "MERGE_CANDIDATE":
            warnings += 1
        else:
            info += 1

    for c in contradictions:
        v = (c.get("llm_verdict") or "").upper()
        if v == "CONTRADICTION":
            warnings += 1
        else:
            info += 1

    info += len(outdated)

    return errors, warnings, info


async def run_lint(
    categories: Optional[List[str]] = None,
    dry_run: bool = False,
    llm_enabled: bool = True,
) -> Dict[str, Any]:
    """on-demand lint 실행.

    Args:
        categories: 검사 대상 카테고리 필터. ``None`` 또는 빈 리스트면 전체.
        dry_run:    ``True`` 면 정적 검사만 수행, LLM 호출 0. 보고서·history 는 작성.
        llm_enabled: ``False`` 면 LLM 호출 0 (dynamic 섹션 모두 (none)).
                     ``dry_run`` 이 ``True`` 면 이 값과 무관하게 LLM 호출 0.

    Returns:
        plan §6.1 의 응답 구조.
    """
    now = datetime.utcnow()
    schema = load_schema()
    all_docs = list_md_files()
    if categories:
        cat_set = set(categories)
        docs = [d for d in all_docs if (d.category or "") in cat_set]
    else:
        docs = list(all_docs)

    # ── 1. 정적 검사 (LLM 미호출) ────────────────────────────────────────
    schema_v_findings, broken_findings, orphan_findings, min_link_findings = run_static_checks(
        docs, schema,
    )

    # min_links 위반은 schema_violations 섹션에 합쳐서 출력
    schema_violations: List[Dict[str, Any]] = []
    for f in schema_v_findings:
        schema_violations.append({**f.payload, "severity": f.severity})
    for f in min_link_findings:
        schema_violations.append({**f.payload, "severity": f.severity})

    broken_links: List[Dict[str, Any]] = [
        {**f.payload, "severity": f.severity} for f in broken_findings
    ]
    orphans: List[Dict[str, Any]] = [
        {**f.payload, "severity": f.severity} for f in orphan_findings
    ]

    # ── 2. 동적 검사 (LLM) ─────────────────────────────────────────────────
    duplicates: List[Dict[str, Any]] = []
    contradictions: List[Dict[str, Any]] = []
    outdated: List[Dict[str, Any]] = []
    llm_calls = 0
    llm_in = 0
    llm_out = 0

    do_llm = (not dry_run) and llm_enabled

    if do_llm and docs:
        embeddings = _embed_docs(docs)
        if embeddings:
            dup_pairs = _duplicate_candidates(docs, embeddings)
            con_pairs = _contradiction_candidates(docs, embeddings)

            dup_results, c1, in1, out1 = await _llm_verdict_for_pairs(
                dup_pairs, kind="duplicate",
            )
            duplicates = dup_results
            llm_calls += c1
            llm_in += in1
            llm_out += out1

            con_results, c2, in2, out2 = await _llm_verdict_for_pairs(
                con_pairs, kind="contradiction",
            )
            # contradiction 은 CONTRADICTION 만 노출
            contradictions = [
                r for r in con_results
                if (r.get("llm_verdict") or "").upper() == "CONTRADICTION"
            ]
            llm_calls += c2
            llm_in += in2
            llm_out += out2

        # outdated
        recent_ids = _recent_log_ids(limit=50)
        outdated_cands = _outdated_candidates(docs, recent_ids)
        outdated_results, c3, in3, out3 = await _llm_outdated_findings(outdated_cands)
        outdated = outdated_results
        llm_calls += c3
        llm_in += in3
        llm_out += out3

    # ── 3. summary 집계 ──────────────────────────────────────────────────
    errors, warnings, info = _severity_summary(
        schema_violations, broken_links, orphans, duplicates, contradictions, outdated,
    )

    # 비용 추정 — 실제 토큰 기반. LLM 호출 0 이면 0.
    estimated_cost = _estimate_cost_usd(llm_in, llm_out)

    summary = {
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "llm_calls": llm_calls,
        "estimated_cost_usd": estimated_cost,
    }

    # ── 4. 보고서 생성 ───────────────────────────────────────────────────
    report_md = _format_report(
        now=now,
        summary=summary,
        duplicates=duplicates,
        contradictions=contradictions,
        orphans=orphans,
        outdated=outdated,
        broken_links=broken_links,
        schema_violations=schema_violations,
    )
    report_path, history_path = _write_report(report_md, now=now)

    return {
        "summary": summary,
        "duplicates": duplicates,
        "contradictions": contradictions,
        "orphans": orphans,
        "outdated": outdated,
        "broken_links": broken_links,
        "schema_violations": schema_violations,
        "report_path": report_path,
        "history_path": history_path,
    }


__all__ = [
    "run_lint",
    "run_static_checks",
    "LintFinding",
]
