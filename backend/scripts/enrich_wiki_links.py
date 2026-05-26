"""enrich_wiki_links.py — 옵시디언화 LLM 교차참조 삽입 스크립트 (일회용)

Karpathy v2 위키의 모든 페이지를 순회하면서, 각 페이지 본문에
같은 카테고리 다른 페이지로의 `[[category/slug]]` 인용을 LLM 으로 자동 삽입한다.

설계 (계획서 §§19, 본 작업 지시):
  - GET /api/v1/knowledge?limit=500 으로 페이지 전수 로딩 (DB 직조회 불필요 — REST 충분)
  - 카테고리별로 페이지 그룹화 (cross-category 인용은 일단 보류)
  - 각 페이지 P 마다 1 LLM 호출 → 본문 재작성 결과 받음 → PUT 으로 갱신
  - LLM 응답 검증:
      * 빈 응답/원본과 동일 → skip
      * 동일 페이지 자기참조 [[P.category/P.slug]] 등장 → 제거
      * 5 개 초과 신규 링크 → 처음 5 개만 유지
      * 같은 link 중복 → 첫 등장 1 회만
  - 실패한 페이지는 skip 하고 다른 페이지 계속

운영 원칙:
  - 백엔드 (8002) 재기동 금지 — PUT 호출만으로 모든 state 갱신 (changelog, _log, _index, ChromaDB sync)
  - LLM 호출은 agent_service 와 동일하게 `get_llm_handler()` 재사용
  - graphify graph.json 의 edges 를 _힌트_ 로만 활용 (label fuzzy match)

사용법:
  cd backend
  python scripts/enrich_wiki_links.py --dry-run   # LLM 호출 없이 페이지 그룹·힌트만 출력
  python scripts/enrich_wiki_links.py             # 실제 실행
  python scripts/enrich_wiki_links.py --only-category codeeyes  # 특정 카테고리만
  python scripts/enrich_wiki_links.py --limit 5   # 처음 5 페이지만
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# backend/ 를 sys.path 에 추가 — `from app.services...` 임포트 가능하게
_BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

# .env 자동 로드 (settings 초기화 전에)
try:
    from dotenv import load_dotenv  # type: ignore
    load_dotenv(_BACKEND_DIR / ".env")
except Exception:
    pass

# stdout UTF-8 강제 (Windows cp949 회피)
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("enrich_wiki_links")
# 모듈 자체 로그는 INFO 만, 라이브러리 노이즈는 줄임
for noisy in ("httpx", "httpcore", "openai", "anthropic"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

API_BASE = os.environ.get("ENRICH_API_BASE", "http://localhost:8002/api/v1")

# Sonnet 가정 가격 (knowledge_lint / knowledge_restore 와 동일)
_PRICE_IN_PER_M = 3.0
_PRICE_OUT_PER_M = 15.0

_MAX_NEW_LINKS_PER_PAGE = 5
_LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


# ── HTTP helpers ──────────────────────────────────────────────────────────


def _http_get_json(url: str, *, timeout: float = 30.0) -> Any:
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_put_json(url: str, body: Dict[str, Any], *, timeout: float = 30.0) -> Tuple[int, Any]:
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body_raw = exc.read().decode("utf-8", errors="replace")
        try:
            body_parsed: Any = json.loads(body_raw)
        except Exception:
            body_parsed = body_raw
        return exc.code, body_parsed


# ── graphify 힌트 로딩 ────────────────────────────────────────────────────


def _load_graphify_hints() -> Dict[str, List[str]]:
    """graph.json 의 edges 를 page label fuzzy match 로 변환.

    반환: {source_label: [target_label, ...]} — 매칭 안 되면 빈 dict.
    실패 시 무음 fallback (LLM 단독 사용).
    """
    graph_path = _BACKEND_DIR.parent / "graphify-out" / "graph.json"
    if not graph_path.exists():
        return {}
    try:
        with open(graph_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as exc:
        logger.warning("graphify graph.json 로드 실패 — 힌트 없이 진행: %s", exc)
        return {}

    nodes = data.get("nodes", []) or []
    edges = data.get("links", []) or data.get("edges", []) or []
    id_to_label = {n.get("id"): n.get("label", "") for n in nodes if n.get("id")}

    hints: Dict[str, List[str]] = defaultdict(list)
    for e in edges:
        src = e.get("source") or e.get("from")
        tgt = e.get("target") or e.get("to")
        if src in id_to_label and tgt in id_to_label:
            sl = id_to_label[src]
            tl = id_to_label[tgt]
            if sl and tl and tl not in hints[sl]:
                hints[sl].append(tl)
    return dict(hints)


def _match_hint_to_pages(
    page_title: str,
    hints: Dict[str, List[str]],
    title_to_id: Dict[str, str],
) -> List[str]:
    """graphify 힌트 라벨 → 위키 페이지 id (단어 단위 fuzzy contains)."""
    out: List[str] = []
    # exact label match
    candidates = hints.get(page_title, [])
    # title containment match (fallback)
    if not candidates:
        for src_label, tgts in hints.items():
            if src_label and (src_label in page_title or page_title in src_label):
                candidates = tgts
                break
    for tgt_label in candidates:
        # 위키에서 같은 title 의 페이지 찾기
        if tgt_label in title_to_id:
            out.append(title_to_id[tgt_label])
            continue
        # contains match
        for t, pid in title_to_id.items():
            if t and (t in tgt_label or tgt_label in t):
                out.append(pid)
                break
    # dedup 순서 보존
    seen: Set[str] = set()
    deduped: List[str] = []
    for x in out:
        if x not in seen:
            seen.add(x)
            deduped.append(x)
    return deduped


# ── LLM enrichment ───────────────────────────────────────────────────────


def _build_prompt(
    page: Dict[str, Any],
    siblings: List[Dict[str, Any]],
    hint_ids: List[str],
) -> Tuple[str, str]:
    """LLM 시스템/사용자 프롬프트 생성.

    Returns: (system_prompt, user_prompt)
    """
    cat = page["category"]
    own_id = page["id"]
    title = page["title"]
    content = page["content"]

    sibling_block_lines: List[str] = []
    for s in siblings:
        if s["id"] == own_id:
            continue
        summary = (s.get("content") or "").strip().replace("\n", " ")[:160]
        sibling_block_lines.append(f"- [[{s['id']}]] {s['title']}: {summary}")
    sibling_block = "\n".join(sibling_block_lines) if sibling_block_lines else "(없음)"

    hint_line = ""
    if hint_ids:
        hint_line = (
            "\n\n### 자동 분석 힌트 (참고용 — 본문 의미상 적합할 때만 인용)\n"
            + "\n".join(f"- [[{h}]]" for h in hint_ids[:8])
        )

    system = (
        "당신은 위키(옵시디언 스타일) 큐레이터입니다. "
        "주어진 페이지 본문에서 같은 카테고리 다른 페이지를 자연스럽게 인용해야 할 위치를 찾아 "
        "`[[category/slug]]` 형식의 인라인 링크를 본문에 추가합니다. "
        "엄격한 규칙:\n"
        " 1. 본문의 의미, 문장 순서, 문단 구조를 보존하라. 새 링크만 추가한다.\n"
        " 2. 동일 페이지 내 같은 링크는 최대 1회.\n"
        " 3. 의미적으로 진짜 관련 있는 곳만 — 억지 인용·중복 인용·자기 참조 절대 금지.\n"
        f" 4. 최대 {_MAX_NEW_LINKS_PER_PAGE} 개 링크만 추가하라.\n"
        " 5. 결과는 본문 markdown 만 출력 (frontmatter, 코드펜스, 설명 없이).\n"
        " 6. 기존 본문에 이미 있는 `[[...]]` 링크는 그대로 두라.\n"
        " 7. 카테고리 enum 외 슬러그 절대 금지 — 반드시 아래 후보 목록의 id 만 사용."
    )

    user = (
        f"### 페이지 정보\n"
        f"- id: `{own_id}`\n"
        f"- title: {title}\n"
        f"- category: {cat}\n"
        f"- page_type: {page.get('pageType')}\n\n"
        f"### 같은 카테고리 `{cat}` 의 다른 페이지 후보 ({len(sibling_block_lines)} 건)\n"
        f"{sibling_block}"
        f"{hint_line}\n\n"
        f"### 본문 (마크다운)\n{content}\n\n"
        "위 본문에 위 후보 페이지 중 의미적으로 진짜 관련 있는 곳에 "
        f"`[[{cat}/슬러그]]` 형식의 인라인 링크를 최대 {_MAX_NEW_LINKS_PER_PAGE} 개까지 자연스럽게 추가하여, "
        "수정된 본문 markdown 만 출력하라. 다른 설명·머리말·코드펜스는 출력하지 말 것."
    )
    return system, user


def _parse_llm_output(raw: str) -> str:
    """LLM 출력에서 markdown 본문만 추출 (코드펜스/frontmatter 제거)."""
    if not raw:
        return ""
    s = raw.strip()
    # 코드펜스 ```markdown ... ``` 제거
    if s.startswith("```"):
        # 첫 줄 (``` 또는 ```markdown)
        first_nl = s.find("\n")
        if first_nl != -1:
            s = s[first_nl + 1 :]
        # 마지막 ``` 제거
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3].rstrip()
    # frontmatter 가 실수로 포함되면 제거
    if s.startswith("---"):
        end = s.find("---", 3)
        if end != -1:
            s = s[end + 3 :].lstrip()
    return s.strip()


def _validate_and_clean(
    new_content: str,
    *,
    original_content: str,
    own_id: str,
    valid_ids: Set[str],
) -> Tuple[str, List[str], List[str]]:
    """LLM 결과 검증·정리.

    Returns:
        (cleaned_content, added_links, warnings)
        added_links: 원본에 없었고 새로 등장한 (정상) 링크 id 목록
        warnings: 문제 진단 메시지
    """
    warnings: List[str] = []
    if not new_content or not new_content.strip():
        warnings.append("LLM 응답 비어 있음")
        return original_content, [], warnings

    # 1) 원본 기존 링크
    old_links = [m.group(1).strip() for m in _LINK_PATTERN.finditer(original_content)]
    old_set = set(old_links)

    # 2) 신규 링크 등장 순서 수집
    new_links_in_order: List[str] = []
    seen_new: Set[str] = set()
    for m in _LINK_PATTERN.finditer(new_content):
        link = m.group(1).strip()
        if link in seen_new:
            continue
        seen_new.add(link)
        # 자기참조 제거 마커
        if link == own_id:
            continue
        # 신규 only
        if link in old_set:
            continue
        new_links_in_order.append(link)

    # 3) 유효성 — valid_ids 에 없는 링크는 제거 (broken 방지)
    allowed_new: List[str] = []
    for link in new_links_in_order:
        if link in valid_ids:
            allowed_new.append(link)
        else:
            warnings.append(f"미존재 페이지 인용 무시: [[{link}]]")
        if len(allowed_new) >= _MAX_NEW_LINKS_PER_PAGE:
            break

    # 4) 출력 본문에서 제거해야 할 링크 (자기참조 + invalid + 5개 초과분)
    new_links_full = []
    for m in _LINK_PATTERN.finditer(new_content):
        new_links_full.append(m.group(1).strip())

    bad_links = []
    seen_kept: Set[str] = set()
    for link in new_links_full:
        if link in old_set:
            continue  # 원본 링크는 그대로 둠
        if link == own_id:
            bad_links.append(link)
            continue
        if link not in valid_ids:
            bad_links.append(link)
            continue
        if link in seen_kept:
            # 동일 새 링크 두 번째 등장 → 모두 제거 (중복 방지)
            # 이미 1회 등장한 링크가 또 나오면 그 추가 등장만 삭제
            bad_links.append(f"DUPLICATE:{link}")
            continue
        # 5 초과 새 링크는 제거
        if link not in allowed_new:
            bad_links.append(link)
            continue
        seen_kept.add(link)

    cleaned = new_content
    # 중복분 (DUPLICATE 마크된 것) 은 두 번째 이후만 제거
    for bad in bad_links:
        if bad.startswith("DUPLICATE:"):
            link = bad.split(":", 1)[1]
            needle = f"[[{link}]]"
            # 첫 번째 등장은 살리고 두 번째 등장부터 제거
            idx1 = cleaned.find(needle)
            if idx1 < 0:
                continue
            idx2 = cleaned.find(needle, idx1 + len(needle))
            while idx2 >= 0:
                cleaned = cleaned[:idx2] + cleaned[idx2 + len(needle) :]
                idx2 = cleaned.find(needle, idx1 + len(needle))
        else:
            needle = f"[[{bad}]]"
            cleaned = cleaned.replace(needle, "")

    # 5) 원본과 동일하면 변화 없음
    if cleaned.strip() == original_content.strip():
        warnings.append("정리 후 본문이 원본과 동일 — 변경 없음")
        return original_content, [], warnings

    if not allowed_new:
        warnings.append("신규 링크 0건 — 변경 없음 처리")
        return original_content, [], warnings

    return cleaned, allowed_new, warnings


async def _call_llm(
    handler,
    *,
    system: str,
    user: str,
    max_tokens: int,
) -> Tuple[Optional[str], int, int]:
    """LLM 호출. (content|None, in_tokens, out_tokens)."""
    try:
        resp = await handler.simple_chat(
            prompt=user,
            system_prompt=system,
            temperature=0.2,
            max_tokens=max_tokens,
            call_type="enrich_wiki_links",
        )
    except Exception as exc:
        logger.warning("LLM 호출 실패: %s", exc)
        return None, 0, 0
    return (
        resp.content or "",
        int(resp.prompt_tokens or 0),
        int(resp.completion_tokens or 0),
    )


# ── 메인 ──────────────────────────────────────────────────────────────────


def _estimate_cost(in_t: int, out_t: int) -> float:
    return round((in_t / 1_000_000) * _PRICE_IN_PER_M + (out_t / 1_000_000) * _PRICE_OUT_PER_M, 6)


def _fetch_all_pages() -> List[Dict[str, Any]]:
    docs = _http_get_json(f"{API_BASE}/knowledge?limit=500", timeout=30.0)
    if not isinstance(docs, list):
        raise RuntimeError(f"GET /knowledge 응답이 리스트가 아님: {type(docs)}")
    return docs


async def main_async(args: argparse.Namespace) -> int:
    t0 = time.perf_counter()
    pages = _fetch_all_pages()
    logger.info("총 %d 페이지 조회됨", len(pages))

    # 필터: 카테고리 enum 외 / 제외 카테고리
    if args.only_category:
        pages = [p for p in pages if p.get("category") == args.only_category]
        logger.info("--only-category=%s 적용 → %d 페이지", args.only_category, len(pages))

    by_cat: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for p in pages:
        c = p.get("category") or ""
        if c:
            by_cat[c].append(p)

    title_to_id = {p.get("title", ""): p["id"] for p in pages if p.get("title")}
    valid_ids = {p["id"] for p in pages}

    hints = _load_graphify_hints()
    logger.info("graphify 힌트 라벨 %d 건 로드", len(hints))

    if args.dry_run:
        logger.info("DRY RUN — LLM 호출하지 않음. 페이지 그룹·힌트 매핑만 출력")
        for cat, lst in sorted(by_cat.items()):
            logger.info("  카테고리 %s: %d 페이지", cat, len(lst))
            for p in lst[: args.limit or 5]:
                hint_ids = _match_hint_to_pages(p.get("title", ""), hints, title_to_id)
                logger.info(
                    "    - %s (%s) hints=%s",
                    p["id"], p.get("pageType"),
                    hint_ids[:3] if hint_ids else "(none)",
                )
        return 0

    from app.services.llm.registry import get_llm_handler  # noqa: E402
    handler = get_llm_handler()
    logger.info("LLM handler 준비됨: provider=%s", getattr(handler, "provider", None))

    # 대상 페이지 선정
    targets: List[Dict[str, Any]] = []
    for cat in sorted(by_cat.keys()):
        targets.extend(by_cat[cat])
    if args.limit and args.limit > 0:
        targets = targets[: args.limit]

    logger.info("enrich 대상: %d 페이지", len(targets))

    enriched_count = 0
    skipped_count = 0
    failed_count = 0
    total_in = 0
    total_out = 0
    total_new_links = 0
    per_page_report: List[Dict[str, Any]] = []

    for idx, page in enumerate(targets, 1):
        own_id = page["id"]
        cat = page["category"]
        siblings = by_cat.get(cat, [])
        if len(siblings) <= 1:
            skipped_count += 1
            per_page_report.append({"id": own_id, "status": "skip", "reason": "no siblings"})
            logger.info("[%d/%d] %s → skip (카테고리 내 다른 페이지 없음)", idx, len(targets), own_id)
            continue

        hint_ids = _match_hint_to_pages(page.get("title", ""), hints, title_to_id)
        # hint 중 own_id, 다른 category 제거
        hint_ids = [h for h in hint_ids if h != own_id and h in valid_ids and h.startswith(f"{cat}/")]

        system_prompt, user_prompt = _build_prompt(page, siblings, hint_ids)
        content = page.get("content", "") or ""
        max_out = max(800, min(2500, int(len(content) / 2) + 600))

        new_raw, in_t, out_t = await _call_llm(
            handler, system=system_prompt, user=user_prompt, max_tokens=max_out
        )
        total_in += in_t
        total_out += out_t

        if new_raw is None:
            failed_count += 1
            per_page_report.append({"id": own_id, "status": "fail", "reason": "LLM error"})
            logger.warning("[%d/%d] %s → LLM 실패", idx, len(targets), own_id)
            continue

        parsed = _parse_llm_output(new_raw)
        cleaned, added, warns = _validate_and_clean(
            parsed,
            original_content=content,
            own_id=own_id,
            valid_ids=valid_ids,
        )

        if not added or cleaned == content:
            skipped_count += 1
            reason = "; ".join(warns) if warns else "no diff"
            per_page_report.append({"id": own_id, "status": "skip", "reason": reason, "added": []})
            logger.info("[%d/%d] %s → skip (%s)", idx, len(targets), own_id, reason)
            continue

        # PUT 호출
        put_url = f"{API_BASE}/knowledge/{own_id}"
        status, resp_body = _http_put_json(
            put_url,
            {"content": cleaned, "operator": "system:enrich-wiki-links"},
            timeout=60.0,
        )
        if status != 200:
            failed_count += 1
            per_page_report.append({
                "id": own_id, "status": "fail",
                "reason": f"PUT {status}", "added": added,
                "resp": resp_body if isinstance(resp_body, str) else str(resp_body)[:200],
            })
            logger.warning("[%d/%d] %s → PUT 실패 status=%s", idx, len(targets), own_id, status)
            continue

        enriched_count += 1
        total_new_links += len(added)
        new_ver = resp_body.get("version") if isinstance(resp_body, dict) else None
        per_page_report.append({
            "id": own_id, "status": "enriched",
            "added": added, "version": new_ver,
        })
        logger.info(
            "[%d/%d] %s → enriched (+%d links, v%s) added=%s",
            idx, len(targets), own_id, len(added), new_ver,
            ", ".join(f"[[{a}]]" for a in added),
        )

    elapsed = time.perf_counter() - t0
    avg_added = (total_new_links / enriched_count) if enriched_count else 0.0
    cost = _estimate_cost(total_in, total_out)

    logger.info("=" * 60)
    logger.info("ENRICH 완료 — %.1fs", elapsed)
    logger.info("  enriched : %d", enriched_count)
    logger.info("  skipped  : %d", skipped_count)
    logger.info("  failed   : %d", failed_count)
    logger.info("  total new links : %d (avg %.2f / enriched page)", total_new_links, avg_added)
    logger.info("  LLM tokens : in=%d out=%d  cost=$%.4f", total_in, total_out, cost)

    # 보고서 파일 (knowledge dir 안에 _enrich-report.md)
    try:
        knowledge_dir = _BACKEND_DIR / "data" / "knowledge"
        report_path = knowledge_dir / "_enrich-report.md"
        lines = [
            f"# Wiki Link Enrich Report — {time.strftime('%Y-%m-%d %H:%M:%S')}",
            "",
            "## Summary",
            f"- targets: {len(targets)}",
            f"- enriched: {enriched_count}",
            f"- skipped: {skipped_count}",
            f"- failed: {failed_count}",
            f"- total_new_links: {total_new_links}",
            f"- avg_new_links_per_enriched: {avg_added:.2f}",
            f"- llm_in_tokens: {total_in}",
            f"- llm_out_tokens: {total_out}",
            f"- estimated_cost_usd: ${cost:.4f}",
            f"- elapsed_sec: {elapsed:.1f}",
            "",
            "## Per-Page",
            "",
            "| id | status | added | reason |",
            "|----|--------|-------|--------|",
        ]
        for item in per_page_report:
            added = item.get("added") or []
            added_str = ", ".join(f"[[{a}]]" for a in added) if added else ""
            reason = (item.get("reason") or "").replace("|", "\\|")
            lines.append(
                f"| `{item['id']}` | {item['status']} | {added_str} | {reason} |"
            )
        report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        logger.info("  보고서 → %s", report_path)
    except Exception as exc:
        logger.warning("보고서 작성 실패: %s", exc)

    return 0 if failed_count == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(
        description="LLM 으로 위키 페이지에 [[category/slug]] 교차참조 자동 삽입"
    )
    parser.add_argument("--dry-run", action="store_true", help="LLM 호출 없이 미리보기")
    parser.add_argument("--only-category", type=str, default=None,
                        help="특정 카테고리만 (예: codeeyes)")
    parser.add_argument("--limit", type=int, default=0,
                        help="처리할 페이지 최대 수 (0 = 전체)")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
