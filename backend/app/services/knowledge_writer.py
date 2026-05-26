"""Knowledge `_log.md` / `_index-{category}.md` 자동 관리 helper — Karpathy v2 (P2).

설계 근거: `.omc/plans/지식-karpathy-v2.md` §6.2, §5.3.

본 모듈은 POST/PUT/DELETE 모두에서 호출되어:
  - `_log.md` 에 변경 1줄 append (append-only)
  - 영향받은 카테고리의 `_index-{category}.md` 를 재생성 (id ASC 정렬 GFM 표)

`_log.md` 포맷 (사람 가독, parse 가능):

    ## [YYYY-MM-DD HH:MM:SS] {change_type} | {doc_id} | v{version} | by {operator}

`_index-{category}.md` 포맷:

    # Index — {category}

    | id | title | page_type | tags |
    |----|-------|-----------|------|
    | category/slug | 제목 | Summary | tag1, tag2 |
    | ... |

비어 있을 때:

    # Index — {category}

    *비어 있음*
"""

from __future__ import annotations

import os
from datetime import datetime
from typing import Optional, List

from ..core.config import settings, _BACKEND_DIR


# ── 경로 helpers ──────────────────────────────────────────────────────────


def _knowledge_dir() -> str:
    d = settings.KNOWLEDGE_DIR
    if not os.path.isabs(d):
        d = os.path.join(_BACKEND_DIR, d)
    os.makedirs(d, exist_ok=True)
    return d


def _log_path() -> str:
    return os.path.join(_knowledge_dir(), "_log.md")


def _index_path(category: str) -> str:
    return os.path.join(_knowledge_dir(), category, f"_index-{category}.md")


def _category_dir(category: str) -> str:
    p = os.path.join(_knowledge_dir(), category)
    os.makedirs(p, exist_ok=True)
    return p


# ── _log.md ────────────────────────────────────────────────────────────────


def append_log_entry(
    operator: str,
    change_type: str,
    doc_id: str,
    version: Optional[int] = None,
) -> None:
    """`_log.md` 끝에 1 줄 append. 파일 미존재 시 헤더와 함께 새로 생성.

    포맷: ``## [YYYY-MM-DD HH:MM:SS] {change_type} | {doc_id} | v{version} | by {operator}``
    version 이 None 이면 ``v?`` 로 기록.
    """
    path = _log_path()
    ts = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    ver_part = f"v{version}" if version is not None else "v?"
    line = f"## [{ts}] {change_type} | {doc_id} | {ver_part} | by {operator}\n"

    # 파일이 없거나 빈 파일이면 헤더부터 시작
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        with open(path, "w", encoding="utf-8") as f:
            f.write("# Knowledge Log\n\n")
            f.write(line)
        return

    # append
    with open(path, "a", encoding="utf-8") as f:
        # 마지막에 줄바꿈이 없으면 보강
        try:
            with open(path, "rb") as rf:
                rf.seek(-1, os.SEEK_END)
                last = rf.read(1)
            if last != b"\n":
                f.write("\n")
        except OSError:
            pass
        f.write(line)


# ── _index-{category}.md ───────────────────────────────────────────────────


def _escape_md_cell(value: str) -> str:
    """GFM 표 셀 안에 들어가도 안전하게: 파이프(`|`) 이스케이프, 줄바꿈 제거."""
    if value is None:
        return ""
    s = str(value)
    return s.replace("|", "\\|").replace("\n", " ").replace("\r", " ").strip()


def rebuild_index(category: str) -> str:
    """해당 카테고리 디렉토리를 스캔하여 `_index-{category}.md` 를 재작성.

    Returns:
        생성된 index 파일의 절대경로.
    """
    cat_dir = _category_dir(category)
    index_path = _index_path(category)

    # 같은 카테고리 디렉토리의 .md 파일들을 읽어 frontmatter 추출.
    # 메타 파일(`_index-*.md`, `_*.md`) 은 제외.
    from .knowledge_file_service import parse_frontmatter

    rows: List[dict] = []
    for entry in sorted(os.listdir(cat_dir)):
        if entry.startswith("_") or entry.startswith("."):
            continue
        if not entry.endswith(".md"):
            continue
        slug = entry[:-3]
        full = os.path.join(cat_dir, entry)
        try:
            with open(full, "r", encoding="utf-8") as f:
                raw = f.read()
        except OSError:
            continue
        metadata, _ = parse_frontmatter(raw)
        title = metadata.get("title") or slug
        page_type = metadata.get("page_type") or "Summary"
        tags_raw = metadata.get("tags") or []
        if isinstance(tags_raw, str):
            tags_list = [t.strip() for t in tags_raw.split(",") if t.strip()]
        elif isinstance(tags_raw, list):
            tags_list = [str(t) for t in tags_raw]
        else:
            tags_list = []
        rows.append({
            "id": f"{category}/{slug}",
            "title": str(title),
            "page_type": str(page_type),
            "tags": tags_list,
        })

    # id ASC
    rows.sort(key=lambda r: r["id"])

    lines: List[str] = []
    lines.append(f"# Index — {category}")
    lines.append("")
    if not rows:
        lines.append("*비어 있음*")
        lines.append("")
    else:
        lines.append("| id | title | page_type | tags |")
        lines.append("|----|-------|-----------|------|")
        for r in rows:
            tags_str = ", ".join(_escape_md_cell(t) for t in r["tags"])
            lines.append(
                f"| {_escape_md_cell(r['id'])} | {_escape_md_cell(r['title'])} "
                f"| {_escape_md_cell(r['page_type'])} | {tags_str} |"
            )
        lines.append("")

    with open(index_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return index_path


__all__ = [
    "append_log_entry",
    "rebuild_index",
]
