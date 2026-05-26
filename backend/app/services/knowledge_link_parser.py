"""Knowledge `[[link]]` 파서 — Karpathy v2 (`.omc/plans/지식-karpathy-v2.md` §6.2, §8.1).

지식 페이지 본문에서 `[[...]]` 패턴을 추출하여 outgoing link 목록을 구성한다.

지원 형식 (link_policy 의 D6 결정):
  - id 기반 (권장):     ``[[category/slug]]``
  - 제목 기반 (호환):   ``[[Title]]`` — lint 가 id 정규화 권고
  - 깨진 링크 마커:     ``[[deleted:category/slug]]`` (DELETE force 가 자동 삽입)

본 모듈은 정규화 없이 raw target 문자열 리스트를 반환한다 (deduplicated, 순서 보존).
의미적 검증 (대상 페이지 존재 여부) 은 P4 lint 의 몫.
"""

from __future__ import annotations

import re
from typing import List, Iterable


# `[[...]]` 패턴 — 닫는 ]] 까지 non-greedy 매칭. ] 가 본문에 단독으로 있으면 제외.
LINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


def parse_links(content: str) -> List[str]:
    """본문에서 `[[...]]` 의 raw target 문자열 목록을 추출.

    - 공백 trim
    - 중복 제거 (첫 등장 순서 보존)
    - 비어 있는 capture (``[[]]``) 무시

    Returns:
        list[str]: 등장 순서로 dedup 된 target 문자열들.
                   예) ``"[[a/b]] x [[a/b]] y [[c/d]]"`` → ``["a/b", "c/d"]``
    """
    if not content:
        return []

    seen: set[str] = set()
    out: List[str] = []
    for raw in LINK_PATTERN.findall(content):
        target = raw.strip()
        if not target:
            continue
        if target in seen:
            continue
        seen.add(target)
        out.append(target)
    return out


def has_link_to(content: str, target_id: str) -> bool:
    """`content` 안에 ``[[{target_id}]]`` (정확 일치) 가 등장하는지.

    DELETE 시 backlink 계산 (`[[doc_id]]` 검색) 에 사용. 공백·접미사 변형 무시,
    정확 일치만 검사. ``[[deleted:{target_id}]]`` 는 별개 패턴이므로 매치되지 않는다.
    """
    if not content or not target_id:
        return False
    needle = f"[[{target_id}]]"
    return needle in content


def replace_link_with_deleted(content: str, target_id: str) -> str:
    """본문 내 ``[[{target_id}]]`` 를 ``[[deleted:{target_id}]]`` 로 치환.

    DELETE force=true 처리에서 backlink 보유 페이지를 수정할 때 사용.
    이미 ``[[deleted:...]]`` 인 것은 건드리지 않는다 (정확 일치 치환).
    """
    if not content or not target_id:
        return content
    needle = f"[[{target_id}]]"
    replacement = f"[[deleted:{target_id}]]"
    return content.replace(needle, replacement)


def filter_known_targets(targets: Iterable[str], known_ids: Iterable[str]) -> List[str]:
    """target 문자열 중 기존 id 와 일치하는 것만 남긴다 (id 정규화 보조).

    Title-link 처리·미존재 페이지 제거에 사용. 본 P2 에서는 호출하지 않으나
    P4 lint·검색 노드 확장에서 재사용 가능하도록 export.
    """
    known = set(known_ids)
    return [t for t in targets if t in known]


__all__ = [
    "LINK_PATTERN",
    "parse_links",
    "has_link_to",
    "replace_link_with_deleted",
    "filter_known_targets",
]
