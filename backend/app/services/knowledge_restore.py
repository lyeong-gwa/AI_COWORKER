"""Knowledge Archive Restore — Karpathy v2 P6 (`.omc/plans/지식-karpathy-v2.md` §6.1, §10.1 step 7).

`data/knowledge-archive/` 의 .md 파일들을 _신정책_ (page_type + category enum + 영문 kebab-case slug)
형식으로 변환·재등록하는 서비스 모듈.

설계 근거:
  - §6.1 POST /knowledge/restore-from-archive
  - §10.1 step 7 — 운영자 결정 후 호출, default dry_run=true (안전)
  - §10.2 가역성 — archive 원본은 _보존_, restore 는 신규 등록만 수행
  - §14 한글 slug 강제 회피 — LLM 으로 한글 제목 → 영문 kebab-case 변환

핵심 보장:
  - archive 원본 파일은 _삭제하지 않는다_ (복사가 아닌 신규 등록).
  - dry_run=True 가 기본. 운영자가 보고서 확인 후 dry_run=False 실행.
  - llm_enabled=False 시 휴리스틱 fallback (cost=0 가시화).
  - 등록 결과는 schema 위반 시 failed 로 분류, restored 와 분리.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ..core.config import _BACKEND_DIR, settings
from .knowledge_file_service import (
    KnowledgeFileDoc,
    compute_hash,
    parse_frontmatter,
    read_md_file,
    write_md_file,
)
from .knowledge_link_parser import parse_links
from .knowledge_schema import (
    ALLOWED_PAGE_TYPES,
    KnowledgeSchema,
    SchemaValidationError,
    load_schema,
    validate_category,
    validate_page_type,
    validate_slug,
)
from .knowledge_writer import append_log_entry, rebuild_index

logger = logging.getLogger(__name__)


# 한글 slug 금지 — D5/§14 한글 제목은 LLM 으로 영문 변환. fallback 휴리스틱은 영문만.
_DEFAULT_PAGE_TYPE = "Summary"

# 휴리스틱 카테고리 매핑 — 파일명 키워드 기반 fallback. LLM 미사용 시 사용.
_CATEGORY_HEURISTIC_RULES: List[Tuple[str, str]] = [
    # (substring, category_id)
    ("codeeyes", "codeeyes"),
    ("plugin", "plugin-troubleshooting"),
    ("faq", "faq"),
    ("ito", "ito-portal-operations"),
    ("member", "ito-portal-operations"),
    ("branch", "ito-portal-operations"),
    ("dev-space", "ito-portal-operations"),
    ("github", "ito-portal-operations"),
    ("configuration", "ito-portal-operations"),
    ("permission", "ito-portal-operations"),
    ("권한", "ito-portal-operations"),
    ("형상", "ito-portal-operations"),
    ("수용", "ito-portal-operations"),
    ("예외", "codeeyes"),
    ("통합UI", "ito-portal-operations"),
    ("표준", "ito-portal-operations"),
    ("질문", "faq"),
]

# Sonnet 가격 가정 (in $3/M, out $15/M) — knowledge_lint 와 동일
_PRICE_IN_PER_M = 3.0
_PRICE_OUT_PER_M = 15.0

# LLM 한 페이지당 평균 토큰 (예상치)
_AVG_LLM_IN = 1000
_AVG_LLM_OUT = 80


# ── 경로 helpers ──────────────────────────────────────────────────────────


def _archive_dir() -> str:
    base = settings.KNOWLEDGE_DIR
    if not os.path.isabs(base):
        base = os.path.join(_BACKEND_DIR, base)
    # data/knowledge → data/knowledge-archive (sibling)
    parent = os.path.dirname(base)
    return os.path.join(parent, "knowledge-archive")


def _knowledge_dir() -> str:
    d = settings.KNOWLEDGE_DIR
    if not os.path.isabs(d):
        d = os.path.join(_BACKEND_DIR, d)
    os.makedirs(d, exist_ok=True)
    return d


def _restore_report_path() -> str:
    return os.path.join(_knowledge_dir(), "_restore-report.md")


# ── 파일 스캔 ──────────────────────────────────────────────────────────────


@dataclass
class ArchiveFile:
    """archive 내 1 개 .md 파일."""

    abs_path: str           # 절대경로
    rel_path: str           # archive 디렉토리 기준 상대경로 (예: "소스코드검증-운영가이드/foo.md")
    filename: str           # 확장자 포함
    body: str               # 본문 (frontmatter 제외)
    frontmatter: Dict[str, Any] = field(default_factory=dict)


def _scan_archive(subpath: Optional[str]) -> List[ArchiveFile]:
    """archive 디렉토리에서 .md 파일 수집.

    Args:
        subpath: ``None`` 이면 archive 전체 재귀. 문자열이면 그 서브폴더만 (1단계).

    Returns:
        ArchiveFile 목록. 본문/frontmatter 까지 파싱 완료.
    """
    base = _archive_dir()
    if not os.path.isdir(base):
        return []

    if subpath:
        scan_root = os.path.join(base, subpath)
        if not os.path.isdir(scan_root):
            return []
    else:
        scan_root = base

    out: List[ArchiveFile] = []
    for root, dirs, files in os.walk(scan_root):
        # 정렬 — 결과의 deterministic 함을 보장
        dirs.sort()
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            if fname.startswith("_") or fname.startswith("."):
                continue
            abs_path = os.path.join(root, fname)
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    raw = f.read()
            except OSError as exc:
                logger.warning("[RESTORE] archive 파일 읽기 실패: %s — %s", abs_path, exc)
                continue
            metadata, body = parse_frontmatter(raw)
            rel = os.path.relpath(abs_path, base).replace("\\", "/")
            out.append(ArchiveFile(
                abs_path=abs_path,
                rel_path=rel,
                filename=fname,
                body=body or "",
                frontmatter=metadata if isinstance(metadata, dict) else {},
            ))
    return out


# ── 휴리스틱 (LLM 미사용) ──────────────────────────────────────────────────


def _slugify_heuristic(filename: str, fallback_idx: int = 0) -> str:
    """파일명 → 영문 kebab-case slug.

    한글이면 transliterate 불가하므로 ``doc-{idx}`` 또는 ``page-{stem-hash}`` fallback.
    의미 없는 짧은 slug (`1`, `a` 등) 도 hash fallback 으로 보강.
    """
    stem = filename[:-3] if filename.endswith(".md") else filename
    # NFKD 정규화 후 ASCII 추출
    nfkd = unicodedata.normalize("NFKD", stem)
    ascii_only = nfkd.encode("ascii", "ignore").decode("ascii")
    # 비영문자 제거, 공백/언더스코어 → 하이픈
    s = re.sub(r"[^a-zA-Z0-9\-]+", "-", ascii_only)
    s = re.sub(r"-+", "-", s).strip("-").lower()

    # 의미 없는 결과 — 알파벳이 1자 미만이거나 비어있으면 hash fallback
    alpha_count = sum(1 for ch in s if ch.isalpha())
    if alpha_count < 2:
        import hashlib
        h = hashlib.md5(filename.encode("utf-8")).hexdigest()[:8]
        s = f"page-{h}" if not s else f"page-{h}-{s}"
        # 결과가 다시 너무 길어지지 않게 잘라냄
        s = s[:64].rstrip("-")

    # 길이 제한 (schema default 64)
    if len(s) > 64:
        s = s[:64].rstrip("-")
    # slug regex 마지막 검증 — 결과가 숫자로만 시작해도 regex 허용 (`^[a-z0-9]+`)
    if not s:
        return f"doc-{fallback_idx}"
    return s


def _classify_heuristic(
    archive: ArchiveFile,
    schema: KnowledgeSchema,
    category_hint: Optional[str],
) -> str:
    """파일명 + frontmatter tags + body 키워드 기반 카테고리 추정.

    category_hint 가 valid 면 우선. 그 외엔 매핑 규칙 → 첫 enum fallback.
    """
    if category_hint and category_hint in schema.category_ids:
        return category_hint

    keys = (archive.filename + " " + " ".join(
        str(t) for t in (archive.frontmatter.get("tags") or [])
    ) + " " + archive.body[:200]).lower()

    for needle, cat in _CATEGORY_HEURISTIC_RULES:
        if needle.lower() in keys and cat in schema.category_ids:
            return cat

    # fallback: 첫 카테고리 (deterministic)
    if schema.category_ids:
        return sorted(schema.category_ids)[0]
    return ""


# ── LLM (옵션) ─────────────────────────────────────────────────────────────


async def _llm_classify_one(
    archive: ArchiveFile,
    schema: KnowledgeSchema,
    category_hint: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], int, int]:
    """LLM 호출 1회 — JSON 응답 파싱 → (verdict_dict|None, in_tokens, out_tokens).

    verdict_dict: {"category": str, "page_type": str, "slug": str, "rationale": str}
    실패 시 (None, 0, 0).
    """
    try:
        from .llm.registry import get_llm_handler
        handler = get_llm_handler()
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RESTORE] LLM handler 사용 불가 — %s", exc)
        return None, 0, 0

    allowed_cats = sorted(schema.category_ids) or ["codeeyes", "ito-portal-operations", "plugin-troubleshooting", "faq"]
    allowed_pts = sorted(schema.page_types.keys() or ALLOWED_PAGE_TYPES)
    cat_hint_line = (
        f"운영자가 선호하는 카테고리 힌트: {category_hint!r} (가능하면 따르되, 본문이 명백히 다르면 다른 enum 선택).\n"
        if category_hint else ""
    )
    body_head = (archive.body or "")[:1200]
    fm_title = archive.frontmatter.get("title") or archive.filename[:-3]
    fm_tags = archive.frontmatter.get("tags") or []

    system = (
        "당신은 위키 페이지 분류 전문가입니다. 주어진 마크다운 페이지를 "
        f"다음 카테고리 enum 중 정확히 하나로 분류하세요: {allowed_cats}. "
        f"그리고 다음 page_type enum 중 하나를 선택하세요: {allowed_pts}. "
        "또한 페이지 제목을 영문 kebab-case slug (소문자, 숫자, 하이픈만 허용, "
        "정규식 '^[a-z0-9]+(-[a-z0-9]+)*$' 통과, 최대 64자) 로 변환하세요. "
        "응답은 다음 JSON 1건만 코드펜스 없이 출력하세요:\n"
        '{"category":"...","page_type":"...","slug":"...","rationale":"한 줄 근거"}'
    )
    user_prompt = (
        f"### 파일명\n{archive.filename}\n\n"
        f"### 원본 카테고리 (legacy frontmatter)\n{archive.frontmatter.get('category', '')}\n\n"
        f"### 제목\n{fm_title}\n\n"
        f"### 태그\n{', '.join(str(t) for t in fm_tags)}\n\n"
        f"{cat_hint_line}"
        f"### 본문 (head 1200자)\n{body_head}\n\n"
        "위 페이지에 적합한 category, page_type, slug 를 JSON 으로만 출력하세요."
    )

    try:
        resp = await handler.simple_chat(
            prompt=user_prompt,
            system_prompt=system,
            temperature=0.1,
            max_tokens=300,
            call_type="restore_classify",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RESTORE] LLM 호출 실패: %s — %s", archive.rel_path, exc)
        return None, 0, 0

    in_toks = int(resp.prompt_tokens or 0)
    out_toks = int(resp.completion_tokens or 0)
    content = (resp.content or "").strip()
    # 코드펜스 제거
    if "```json" in content:
        content = content.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in content:
        content = content.split("```", 1)[1].split("```", 1)[0].strip()
    # JSON 객체 추출
    start = content.find("{")
    end = content.rfind("}")
    if start == -1 or end == -1:
        return None, in_toks, out_toks
    try:
        verdict = json.loads(content[start: end + 1])
    except Exception:  # noqa: BLE001
        return None, in_toks, out_toks
    if not isinstance(verdict, dict):
        return None, in_toks, out_toks
    return verdict, in_toks, out_toks


# ── 분류 통합 (LLM + 휴리스틱 fallback) ──────────────────────────────────


@dataclass
class _Classification:
    category: str
    page_type: str
    slug: str
    rationale: str
    llm_used: bool


def _normalize_slug_candidate(raw_slug: str, schema: KnowledgeSchema, archive: ArchiveFile, idx: int) -> str:
    """LLM 응답 slug 를 schema 규칙으로 정규화.

    위반 시 휴리스틱 fallback. 본 함수는 _validate_ 가 아니라 sanitize 목적.
    """
    if not raw_slug or not isinstance(raw_slug, str):
        return _slugify_heuristic(archive.filename, fallback_idx=idx)
    s = raw_slug.strip().lower()
    s = re.sub(r"[^a-z0-9\-]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    max_len = schema.max_slug_length
    if not s:
        return _slugify_heuristic(archive.filename, fallback_idx=idx)
    if len(s) > max_len:
        s = s[:max_len].rstrip("-")
    return s


async def _classify(
    archive: ArchiveFile,
    schema: KnowledgeSchema,
    *,
    category_hint: Optional[str],
    llm_enabled: bool,
    used_slugs_by_category: Dict[str, Set[str]],
    idx: int,
) -> Tuple[_Classification, int, int]:
    """1개 archive 파일을 분류. (Classification, in_tokens, out_tokens)."""
    if llm_enabled:
        verdict, in_t, out_t = await _llm_classify_one(archive, schema, category_hint)
        if verdict is not None:
            cat = str(verdict.get("category") or "").strip()
            pt = str(verdict.get("page_type") or "").strip()
            slug = _normalize_slug_candidate(str(verdict.get("slug") or ""), schema, archive, idx)
            rationale = str(verdict.get("rationale") or "")[:240]

            # category fallback
            if cat not in schema.category_ids:
                cat = _classify_heuristic(archive, schema, category_hint)
                rationale += " [category fallback to heuristic]"
            # page_type fallback
            allowed_pts = set(schema.page_types.keys() or ALLOWED_PAGE_TYPES)
            if pt not in allowed_pts:
                pt = _DEFAULT_PAGE_TYPE
                rationale += " [page_type fallback to Summary]"

            # 중복 slug 회피 (같은 카테고리 내)
            slug = _dedupe_slug(slug, used_slugs_by_category.setdefault(cat, set()))
            used_slugs_by_category[cat].add(slug)
            return _Classification(category=cat, page_type=pt, slug=slug, rationale=rationale, llm_used=True), in_t, out_t

        # LLM 실패 → 휴리스틱 fallback
        cat = _classify_heuristic(archive, schema, category_hint)
        slug = _slugify_heuristic(archive.filename, fallback_idx=idx)
        slug = _dedupe_slug(slug, used_slugs_by_category.setdefault(cat, set()))
        used_slugs_by_category[cat].add(slug)
        return _Classification(
            category=cat,
            page_type=_DEFAULT_PAGE_TYPE,
            slug=slug,
            rationale="LLM 응답 파싱 실패 — 휴리스틱 fallback",
            llm_used=False,
        ), in_t, out_t

    # llm_enabled=False — 휴리스틱만
    cat = _classify_heuristic(archive, schema, category_hint)
    slug = _slugify_heuristic(archive.filename, fallback_idx=idx)
    slug = _dedupe_slug(slug, used_slugs_by_category.setdefault(cat, set()))
    used_slugs_by_category[cat].add(slug)
    return _Classification(
        category=cat,
        page_type=_DEFAULT_PAGE_TYPE,
        slug=slug,
        rationale="LLM 미사용 (휴리스틱) — page_type=Summary, slug=파일명 ascii-fold",
        llm_used=False,
    ), 0, 0


def _dedupe_slug(base_slug: str, used: Set[str]) -> str:
    """같은 카테고리 내에서 slug 충돌 회피. ``-2``, ``-3`` ...

    이미 file system 에 존재하는 페이지 id 와도 충돌하지 않아야 한다 — 호출자가
    ``used`` 에 기존 페이지 slug 도 미리 채워둔다.
    """
    if base_slug not in used:
        return base_slug
    n = 2
    while True:
        cand = f"{base_slug}-{n}"
        if cand not in used and len(cand) <= 64:
            return cand
        n += 1
        if n > 999:  # 안전 한계
            return f"{base_slug[:50]}-{n}"


# ── 비용 추정 ──────────────────────────────────────────────────────────────


def _estimate_cost_usd(in_tokens: int, out_tokens: int) -> float:
    return round(
        (in_tokens / 1_000_000.0) * _PRICE_IN_PER_M
        + (out_tokens / 1_000_000.0) * _PRICE_OUT_PER_M,
        6,
    )


# ── 보고서 작성 ────────────────────────────────────────────────────────────


def _write_report(
    *,
    now: datetime,
    dry_run: bool,
    summary: Dict[str, Any],
    would_or_restored: List[Dict[str, Any]],
    failed: List[Dict[str, Any]],
) -> str:
    """`_restore-report.md` 덮어쓰기. dry_run 이면 'would_restore' / 실제면 'restored' 섹션.

    Returns:
        backend/ 기준 상대경로.
    """
    path = _restore_report_path()
    lines: List[str] = []
    mode = "DRY RUN" if dry_run else "REAL RUN"
    lines.append(f"# Knowledge Archive Restore Report — {now.strftime('%Y-%m-%d %H:%M:%S')} ({mode})")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- total: {summary['total']}")
    if dry_run:
        lines.append(f"- would_restore_count: {summary.get('would_restore_count', 0)}")
    else:
        lines.append(f"- restored_count: {summary.get('restored_count', 0)}")
    lines.append(f"- failed_count: {summary['failed_count']}")
    lines.append(f"- llm_calls: {summary['llm_calls']}")
    lines.append(f"- estimated_cost_usd: ${summary['estimated_cost_usd']:.4f}")
    lines.append("")

    section_title = "Would Restore" if dry_run else "Restored"
    lines.append(f"## {section_title}")
    lines.append("")
    if not would_or_restored:
        lines.append("(none)")
    else:
        lines.append("| archive_path | new_id | category | page_type | rationale |")
        lines.append("|--------------|--------|----------|-----------|-----------|")
        for item in would_or_restored:
            rat = (item.get("rationale") or "").replace("|", "\\|").replace("\n", " ")
            lines.append(
                f"| `{item.get('archive_path','')}` "
                f"| `{item.get('new_id','')}` "
                f"| {item.get('category','')} "
                f"| {item.get('page_type','')} "
                f"| {rat} |"
            )
    lines.append("")
    lines.append("## Failed")
    lines.append("")
    if not failed:
        lines.append("(none)")
    else:
        lines.append("| archive_path | reason |")
        lines.append("|--------------|--------|")
        for f in failed:
            rsn = (f.get("reason") or "").replace("|", "\\|").replace("\n", " ")
            lines.append(f"| `{f.get('archive_path','')}` | {rsn} |")
    lines.append("")

    content = "\n".join(lines).rstrip() + "\n"
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)
    try:
        return os.path.relpath(path, _BACKEND_DIR).replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


# ── 메인 API ──────────────────────────────────────────────────────────────


async def restore_from_archive(
    *,
    category_hint: Optional[str] = None,
    archive_subpath: Optional[str] = None,
    dry_run: bool = True,
    max_files: int = 200,
    llm_enabled: bool = True,
    db=None,
) -> Dict[str, Any]:
    """archive .md → 신정책 위키 페이지 재등록.

    Args:
        category_hint: 우선 카테고리 (schema enum). None 이면 LLM/휴리스틱 판단.
        archive_subpath: ``"소스코드검증-운영가이드"`` 등. None 이면 archive 전체 재귀.
        dry_run: True 면 분류 결과만 보고, 실제 등록 안 함 (default — 안전).
        max_files: 비용 가드 (default 200).
        llm_enabled: False 면 LLM 호출 0 (휴리스틱만).
        db: AsyncSession (실제 등록 시 changelog 적재용). dry_run 이면 무시 가능.

    Returns:
        dry_run=true: {"would_restore": [...], "failed": [...], "summary": {...}, "report_path": "..."}
        dry_run=false: {"restored": [...], "failed": [...], "summary": {...}, "report_path": "..."}
    """
    now = datetime.utcnow()
    schema = load_schema()
    archives = _scan_archive(archive_subpath)
    if max_files and max_files > 0:
        archives = archives[:max_files]

    failed: List[Dict[str, Any]] = []
    candidates: List[Tuple[ArchiveFile, _Classification]] = []
    total_in_tokens = 0
    total_out_tokens = 0
    llm_calls = 0

    # 기존 페이지의 slug 를 카테고리별로 수집 → 신규 slug 충돌 회피
    used_slugs_by_category: Dict[str, Set[str]] = {}
    try:
        from .knowledge_file_service import list_md_files
        existing = list_md_files()
        for d in existing:
            if "/" in d.id:
                cat, _, slug = d.id.partition("/")
                used_slugs_by_category.setdefault(cat, set()).add(slug)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RESTORE] 기존 페이지 슬러그 수집 실패 — 진행: %s", exc)

    # 1) 본문 검증 + 분류
    for idx, archive in enumerate(archives):
        if not (archive.body or "").strip():
            failed.append({
                "archive_path": archive.rel_path,
                "reason": "본문이 비어 있습니다",
            })
            continue

        try:
            classification, in_t, out_t = await _classify(
                archive,
                schema,
                category_hint=category_hint,
                llm_enabled=llm_enabled,
                used_slugs_by_category=used_slugs_by_category,
                idx=idx,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[RESTORE] 분류 단계 실패: %s", archive.rel_path)
            failed.append({
                "archive_path": archive.rel_path,
                "reason": f"분류 실패: {exc}",
            })
            continue

        if classification.llm_used:
            llm_calls += 1
        total_in_tokens += in_t
        total_out_tokens += out_t

        # schema 진위 검증 — 위반 시 failed
        try:
            validate_category(classification.category, schema=schema)
            validate_page_type(classification.page_type, schema=schema)
            validate_slug(classification.slug, schema=schema)
        except SchemaValidationError as exc:
            failed.append({
                "archive_path": archive.rel_path,
                "reason": f"schema 위반 ({exc.field}): {exc}",
            })
            continue

        # id 충돌 점검 (현재 wiki 에 이미 있으면 skip)
        new_id = f"{classification.category}/{classification.slug}"
        if read_md_file(new_id) is not None:
            failed.append({
                "archive_path": archive.rel_path,
                "reason": f"대상 id {new_id} 가 wiki 에 이미 존재합니다 (충돌)",
            })
            continue

        candidates.append((archive, classification))

    # dry_run 응답 작성
    if dry_run:
        would: List[Dict[str, Any]] = []
        for archive, c in candidates:
            new_id = f"{c.category}/{c.slug}"
            would.append({
                "archive_path": archive.rel_path,
                "new_id": new_id,
                "category": c.category,
                "page_type": c.page_type,
                "slug": c.slug,
                "rationale": c.rationale,
                "llm_used": c.llm_used,
            })
        summary = {
            "total": len(archives),
            "would_restore_count": len(would),
            "failed_count": len(failed),
            "llm_calls": llm_calls,
            "llm_in_tokens": total_in_tokens,
            "llm_out_tokens": total_out_tokens,
            "estimated_cost_usd": _estimate_cost_usd(total_in_tokens, total_out_tokens),
        }
        report_path = _write_report(
            now=now,
            dry_run=True,
            summary=summary,
            would_or_restored=would,
            failed=failed,
        )
        return {
            "would_restore": would,
            "failed": failed,
            "summary": summary,
            "report_path": report_path,
        }

    # 2) 실제 등록 — write_md_file + ChromaDB sync + changelog + log/index
    restored: List[Dict[str, Any]] = []
    affected_categories: Set[str] = set()

    # changelog/sync 임포트 — 실패 시 best-effort
    add_changelog = None
    if db is not None:
        try:
            from .knowledge_changelog_service import add_changelog as _ac
            add_changelog = _ac
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RESTORE] changelog 모듈 로드 실패 — skip: %s", exc)

    try:
        from .embedding import get_vector_db
        _vector_db_avail = True
    except Exception:  # noqa: BLE001
        _vector_db_avail = False

    operator = "system:restore"

    for archive, c in candidates:
        new_id = f"{c.category}/{c.slug}"
        # 기존 frontmatter 에서 title/tags/source 보존
        fm = archive.frontmatter or {}
        title = str(fm.get("title") or archive.filename[:-3]).strip() or archive.filename[:-3]
        tags_raw = fm.get("tags") or []
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        elif isinstance(tags_raw, list):
            tags = [str(t).strip() for t in tags_raw if str(t).strip()]
        else:
            tags = []
        # source 는 archive 의 원본 source 또는 archive 경로
        source = str(fm.get("source") or f"archive:{archive.rel_path}")

        # links 자동 파싱
        links = parse_links(archive.body)

        try:
            doc = write_md_file(
                doc_id=new_id,
                title=title,
                content=archive.body,
                category=c.category,
                tags=tags,
                source=source,
                extra_metadata={
                    "restored_from": archive.rel_path,
                    "restored_at": now.isoformat(),
                    "restore_rationale": c.rationale,
                },
                page_type=c.page_type,
                version=1,
                links=links,
                raw_source_id=None,
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("[RESTORE] 파일 작성 실패: %s", new_id)
            failed.append({
                "archive_path": archive.rel_path,
                "reason": f"파일 작성 실패: {exc}",
            })
            continue

        # changelog (best-effort)
        if add_changelog is not None and db is not None:
            try:
                await add_changelog(
                    db,
                    knowledge_id=new_id,
                    version=1,
                    change_type="create",
                    operator=operator,
                    diff_summary=f"restore from archive {archive.rel_path}",
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[RESTORE] changelog 적재 실패 — 파일 보존됨: %s", exc)

        # _log + index (best-effort)
        try:
            append_log_entry(operator=operator, change_type="create", doc_id=new_id, version=1)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RESTORE] _log 갱신 실패: %s", exc)
        affected_categories.add(c.category)

        # ChromaDB sync (best-effort)
        if _vector_db_avail:
            try:
                vector_db = get_vector_db()
                content_hash = compute_hash(archive.body)
                vector_db.add_document(
                    doc_id=new_id,
                    content=archive.body,
                    metadata={
                        "title": title,
                        "category": c.category,
                        "source": source,
                        "content_hash": content_hash,
                        "page_type": c.page_type,
                        "version": 1,
                        "links": list(links),
                        "restored_from": archive.rel_path,
                    },
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning("[RESTORE] ChromaDB sync 실패 — 파일 보존됨: %s", exc)

        restored.append({
            "archive_path": archive.rel_path,
            "new_id": new_id,
            "category": c.category,
            "page_type": c.page_type,
            "slug": c.slug,
            "rationale": c.rationale,
            "llm_used": c.llm_used,
            "version": 1,
        })

    # 각 affected 카테고리 인덱스 재생성
    for cat in affected_categories:
        try:
            rebuild_index(cat)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RESTORE] index rebuild %s 실패: %s", cat, exc)

    summary = {
        "total": len(archives),
        "restored_count": len(restored),
        "failed_count": len(failed),
        "llm_calls": llm_calls,
        "llm_in_tokens": total_in_tokens,
        "llm_out_tokens": total_out_tokens,
        "estimated_cost_usd": _estimate_cost_usd(total_in_tokens, total_out_tokens),
    }
    report_path = _write_report(
        now=now,
        dry_run=False,
        summary=summary,
        would_or_restored=restored,
        failed=failed,
    )

    return {
        "restored": restored,
        "failed": failed,
        "summary": summary,
        "report_path": report_path,
    }


__all__ = [
    "restore_from_archive",
]
