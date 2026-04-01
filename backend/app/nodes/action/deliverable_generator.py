"""GitHub 마일스톤 기반 개발/코드리뷰 산출물 자동 생성 노드 핸들러

form-start 노드로부터 github_url, milestone_number, github_token을 받아
GitHub API를 호출하고, 개발산출물 + 코드리뷰산출물 마크다운을 생성합니다.
"""
import logging
import re
import urllib.parse
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..registry import NodeHandlerRegistry
from ..base import NodeHandler, ExecutionContext

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# 리뷰 코멘트 분류
# ──────────────────────────────────────────────

REVIEW_CATEGORIES = {
    "REVIEW-BUG": "버그/결함",
    "REVIEW-PERF": "성능",
    "REVIEW-SEC": "보안",
    "REVIEW-STYLE": "코드스타일",
    "REVIEW-LOGIC": "로직오류",
    "REVIEW-SUGGEST": "개선제안",
    "REVIEW-QUESTION": "질의",
    "REVIEW": "일반리뷰",
}

REVIEW_TAG_PATTERN = re.compile(
    r"^\[(REVIEW-BUG|REVIEW-PERF|REVIEW-SEC|REVIEW-STYLE|REVIEW-LOGIC"
    r"|REVIEW-SUGGEST|REVIEW-QUESTION|REVIEW)\]\s*"
)

# 키워드 기반 자동 분류
_AUTO_CLASSIFY_RULES: List[Tuple[List[str], str]] = [
    (["bug", "fix", "error", "NPE", "null", "버그", "결함", "오류"], "버그/결함"),
    (["security", "injection", "XSS", "auth", "보안", "인증"], "보안"),
    (["performance", "cache", "index", "slow", "성능", "캐시"], "성능"),
    (["naming", "style", "indent", "format", "네이밍", "스타일", "포맷"], "코드스타일"),
    (["logic", "condition", "boundary", "로직", "조건", "경계"], "로직오류"),
    (["suggest", "consider", "better", "improve", "제안", "개선"], "개선제안"),
    (["?", "?", "why", "what", "how", "왜", "어떻게"], "질의"),
]


def classify_comment(body: str) -> Tuple[str, str]:
    """코멘트 본문에서 리뷰 분류를 추출한다.

    1. [REVIEW-*] 태그가 있으면 해당 분류 사용
    2. 태그가 없으면 키워드 기반 자동 분류
    3. 아무것도 매치 안 되면 '일반리뷰'
    """
    if not body:
        return "일반리뷰", body or ""

    m = REVIEW_TAG_PATTERN.match(body)
    if m:
        tag = m.group(1)
        content = body[m.end():].strip()
        return REVIEW_CATEGORIES.get(tag, "일반리뷰"), content

    # 키워드 자동 분류
    body_lower = body.lower()
    for keywords, category in _AUTO_CLASSIFY_RULES:
        if any(kw.lower() in body_lower for kw in keywords):
            return category, body

    return "일반리뷰", body


# ──────────────────────────────────────────────
# URL 파싱
# ──────────────────────────────────────────────

def parse_github_url(url: str) -> Tuple[str, str, Optional[int]]:
    """GitHub URL에서 owner, repo, milestone_number를 추출한다."""
    url = url.strip().rstrip("/")
    if "://" not in url:
        parts = url.split("/")
        if len(parts) >= 2:
            return parts[0], parts[1], None
        raise ValueError(f"URL 형식을 인식할 수 없습니다: {url}")

    parsed = urllib.parse.urlparse(url)
    path_parts = [p for p in parsed.path.strip("/").split("/") if p]
    if len(path_parts) < 2:
        raise ValueError(f"URL에서 owner/repo를 추출할 수 없습니다: {url}")

    owner = path_parts[0]
    repo = path_parts[1]
    milestone_num = None
    if len(path_parts) >= 4 and path_parts[2] in ("milestone", "milestones"):
        try:
            milestone_num = int(path_parts[3])
        except ValueError:
            pass
    return owner, repo, milestone_num


# ──────────────────────────────────────────────
# 유틸리티
# ──────────────────────────────────────────────

def _format_date(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


def _format_date_short(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "-"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:10] if len(iso_str) >= 10 else iso_str


def _escape_pipe(text: str) -> str:
    """마크다운 테이블에서 파이프 문자를 이스케이프한다."""
    return text.replace("\n", " ").replace("|", "\\|")


# ──────────────────────────────────────────────
# PR Body 파싱
# ──────────────────────────────────────────────

def _parse_pr_body(body: Optional[str]) -> Dict[str, Any]:
    """PR body에서 컨벤션에 따라 필드를 추출한다."""
    if not body:
        return {}

    result: Dict[str, Any] = {}

    m = re.search(r"과제번호\s*[:：]\s*(.+)", body)
    if m:
        result["task_id"] = m.group(1).strip()

    m = re.search(r"기술스택\s*[:：]\s*(.+)", body)
    if m:
        result["tech_stack"] = m.group(1).strip()

    m = re.search(r"분류\s*[:：]\s*(.+)", body)
    if m:
        result["category"] = m.group(1).strip()

    m = re.search(r"담당[자]?\s*[:：]\s*(.+)", body)
    if m:
        result["assignee"] = m.group(1).strip()

    m = re.search(r"리뷰(?:어|요청|)\s*[:：]\s*(.+)", body)
    if m:
        result["reviewers"] = m.group(1).strip()

    m = re.search(r"###\s*요약\s*\n([\s\S]*?)(?=\n###|\n##|$)", body)
    if m:
        result["summary"] = m.group(1).strip()

    m = re.search(r"###\s*상세\s*\n([\s\S]*?)(?=\n##|$)", body)
    if m:
        lines = m.group(1).strip().split("\n")
        result["details"] = [
            line.strip().lstrip("-").strip()
            for line in lines
            if line.strip().startswith("-")
        ]

    # 컨벤션이 없는 경우 fallback
    if "summary" not in result and "details" not in result:
        m = re.search(r"##\s*개요\s*\n([\s\S]*?)(?=\n##|$)", body)
        if m:
            result["summary"] = m.group(1).strip()
        m = re.search(r"##\s*작업\s*내용\s*\n([\s\S]*?)(?=\n##|$)", body)
        if m:
            lines = m.group(1).strip().split("\n")
            result["details"] = [
                line.strip().lstrip("-").strip()
                for line in lines
                if line.strip().startswith("-")
            ]

    if "assignee" not in result:
        m = re.search(r"##\s*담당자\s*\n-?\s*(.+)", body)
        if m:
            result["assignee"] = m.group(1).strip()

    return result


# ──────────────────────────────────────────────
# GitHub API 클라이언트
# ──────────────────────────────────────────────

class GitHubClient:
    """httpx 기반 비동기 GitHub REST/GraphQL 클라이언트"""

    API_BASE = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        headers: Dict[str, str] = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._headers = headers

    async def _get(self, endpoint: str) -> Any:
        """단일 GET 요청. 페이지네이션이 있으면 전체 결과를 합쳐 반환한다."""
        url = f"{self.API_BASE}/{endpoint}"
        all_items: list = []
        async with httpx.AsyncClient(timeout=30, headers=self._headers) as client:
            while url:
                resp = await client.get(url)
                if resp.status_code == 403:
                    remaining = resp.headers.get("X-RateLimit-Remaining", "?")
                    logger.error("GitHub API rate limit (remaining=%s): %s", remaining, url)
                    raise RuntimeError(
                        f"GitHub API 요청 제한에 도달했습니다 (remaining={remaining}). "
                        "잠시 후 다시 시도하거나 토큰을 사용하세요."
                    )
                resp.raise_for_status()
                data = resp.json()

                # 페이지네이션 처리
                if isinstance(data, list):
                    all_items.extend(data)
                    link = resp.headers.get("Link", "")
                    next_url = None
                    for part in link.split(","):
                        if 'rel="next"' in part:
                            next_url = part.split("<")[1].split(">")[0]
                    url = next_url
                else:
                    return data  # 단일 객체

        return all_items

    async def _graphql(self, query: str) -> Optional[Dict]:
        """GraphQL API 호출"""
        url = f"{self.API_BASE}/graphql"
        async with httpx.AsyncClient(timeout=30, headers=self._headers) as client:
            resp = await client.post(url, json={"query": query})
            if resp.status_code != 200:
                logger.warning("GraphQL 호출 실패: %s", resp.status_code)
                return None
            return resp.json()

    # --- 편의 메서드 ---

    async def fetch_milestone(self, owner: str, repo: str, number: int) -> Dict:
        return await self._get(f"repos/{owner}/{repo}/milestones/{number}")

    async def fetch_milestone_items(self, owner: str, repo: str, number: int) -> List:
        return await self._get(
            f"repos/{owner}/{repo}/issues?milestone={number}&state=all&per_page=100"
        )

    async def fetch_pull(self, owner: str, repo: str, number: int) -> Dict:
        return await self._get(f"repos/{owner}/{repo}/pulls/{number}")

    async def fetch_pull_files(self, owner: str, repo: str, number: int) -> List:
        return await self._get(
            f"repos/{owner}/{repo}/pulls/{number}/files?per_page=100"
        )

    async def fetch_pull_comments(self, owner: str, repo: str, number: int) -> List:
        return await self._get(
            f"repos/{owner}/{repo}/pulls/{number}/comments?per_page=100"
        )

    async def fetch_issue_comments(self, owner: str, repo: str, number: int) -> List:
        return await self._get(
            f"repos/{owner}/{repo}/issues/{number}/comments?per_page=100"
        )

    async def fetch_pull_reviews(self, owner: str, repo: str, number: int) -> List:
        return await self._get(f"repos/{owner}/{repo}/pulls/{number}/reviews")

    async def fetch_review_thread_status(
        self, owner: str, repo: str, pr_number: int
    ) -> Dict[int, Dict[str, bool]]:
        """GraphQL로 review thread resolved/outdated 상태 조회"""
        query = """
{
  repository(owner: "%s", name: "%s") {
    pullRequest(number: %d) {
      reviewThreads(first: 100) {
        nodes {
          isResolved
          isOutdated
          comments(first: 1) {
            nodes {
              body
              path
              databaseId
            }
          }
        }
      }
    }
  }
}
""" % (owner, repo, pr_number)

        data = await self._graphql(query)
        if not data:
            return {}

        threads = (
            data.get("data", {})
            .get("repository", {})
            .get("pullRequest", {})
            .get("reviewThreads", {})
            .get("nodes", [])
        )
        result: Dict[int, Dict[str, bool]] = {}
        for thread in threads:
            comments = thread.get("comments", {}).get("nodes", [])
            if comments:
                db_id = comments[0].get("databaseId")
                if db_id:
                    result[db_id] = {
                        "isResolved": thread.get("isResolved", False),
                        "isOutdated": thread.get("isOutdated", False),
                    }
        return result


# ──────────────────────────────────────────────
# 데이터 수집
# ──────────────────────────────────────────────

async def _collect_data(
    gh: GitHubClient, owner: str, repo: str, milestone_number: int
) -> Dict[str, Any]:
    """마일스톤 기준으로 모든 PR 데이터를 수집한다."""

    logger.info("마일스톤 정보 조회: %s/%s #%d", owner, repo, milestone_number)
    milestone = await gh.fetch_milestone(owner, repo, milestone_number)

    logger.info("마일스톤 항목 조회...")
    items = await gh.fetch_milestone_items(owner, repo, milestone_number)
    if not items:
        raise ValueError("마일스톤에 항목이 없습니다.")

    # PR만 필터링
    prs = [item for item in items if "pull_request" in item]
    prs.sort(key=lambda x: x["number"])
    logger.info("PR %d건 발견", len(prs))

    pr_data_list: List[Dict[str, Any]] = []
    for item in prs:
        num = item["number"]
        logger.info("PR #%d: %s", num, item["title"])

        pr_detail = await gh.fetch_pull(owner, repo, num)
        pr_files = await gh.fetch_pull_files(owner, repo, num) or []
        pr_comments = await gh.fetch_pull_comments(owner, repo, num) or []
        issue_comments = await gh.fetch_issue_comments(owner, repo, num) or []
        pr_reviews = await gh.fetch_pull_reviews(owner, repo, num) or []

        # GraphQL review thread 상태 (토큰이 있을 때만 가능)
        try:
            thread_status = await gh.fetch_review_thread_status(owner, repo, num)
        except Exception:
            thread_status = {}

        parsed_body = _parse_pr_body(pr_detail.get("body", ""))
        pr_author = pr_detail.get("user", {}).get("login", "")

        dev_comments: List[Dict] = []
        review_comments: List[Dict] = []

        for c in pr_comments:
            comment_author = c.get("user", {}).get("login", "")
            comment_id = c.get("id")

            status_info = thread_status.get(comment_id, {})
            is_resolved = status_info.get("isResolved", False)
            is_outdated = status_info.get("isOutdated", False)

            if is_resolved:
                status = "resolved"
            elif is_outdated:
                status = "outdated"
            else:
                status = "active"

            comment_data: Dict[str, Any] = {
                "author": comment_author,
                "body": c.get("body", ""),
                "path": c.get("path", ""),
                "line": c.get("line") or c.get("original_line") or c.get("position", ""),
                "created_at": c.get("created_at", ""),
                "diff_hunk": c.get("diff_hunk", ""),
                "status": status,
            }

            if comment_author == pr_author:
                dev_comments.append(comment_data)
            else:
                category, content = classify_comment(comment_data["body"])
                comment_data["category"] = category
                comment_data["content"] = content
                review_comments.append(comment_data)

        # 리뷰어 목록
        reviewers = list(set(
            r.get("user", {}).get("login", "")
            for r in pr_reviews
            if r.get("state") in ("APPROVED", "CHANGES_REQUESTED", "COMMENTED")
            and r.get("user", {}).get("login", "") != pr_author
        ))

        # 최종 리뷰 상태
        review_states = [
            r.get("state")
            for r in pr_reviews
            if r.get("user", {}).get("login", "") != pr_author
        ]
        final_review_state = review_states[-1] if review_states else "없음"

        pr_data_list.append({
            "number": num,
            "title": item["title"],
            "author": pr_author,
            "merged_at": pr_detail.get("merged_at", ""),
            "additions": pr_detail.get("additions", 0),
            "deletions": pr_detail.get("deletions", 0),
            "changed_files": pr_detail.get("changed_files", 0),
            "head_sha": pr_detail.get("head", {}).get("sha", "")[:7],
            "body_raw": pr_detail.get("body", ""),
            "parsed_body": parsed_body,
            "files": pr_files,
            "dev_comments": dev_comments,
            "review_comments": review_comments,
            "issue_comments": issue_comments,
            "reviewers": reviewers,
            "final_review_state": final_review_state,
            "labels": [lbl.get("name", "") for lbl in item.get("labels", [])],
        })

    return {"milestone": milestone, "prs": pr_data_list}


# ──────────────────────────────────────────────
# 마크다운 생성
# ──────────────────────────────────────────────

def _generate_dev_deliverable(
    data: Dict[str, Any], owner: str, repo: str
) -> Tuple[str, int, int, int]:
    """개발산출물 마크다운을 생성한다. (md_text, pr_count, additions, deletions) 반환"""
    ms = data["milestone"]
    prs = data["prs"]
    ms_number = ms["number"]

    lines: List[str] = []
    lines.append(f"# [{ms_number:04d}] 개발 산출물\n")

    # 배포 정보
    lines.append("## 배포 정보\n")
    lines.append("| 항목 | 내용 |")
    lines.append("|------|------|")
    lines.append(f"| 마일스톤 | {ms['title']} |")
    if ms.get("description"):
        lines.append(f"| 설명 | {_escape_pipe(ms['description'])} |")
    lines.append(f"| 배포 예정일 | {_format_date_short(ms.get('due_on'))} |")
    lines.append(f"| 상태 | {ms['state']} |")
    total = ms.get("open_issues", 0) + ms.get("closed_issues", 0)
    closed = ms.get("closed_issues", 0)
    pct = round(closed / total * 100) if total > 0 else 0
    lines.append(f"| 진행률 | {closed}/{total} ({pct}%) |")
    lines.append("")
    lines.append("---\n")

    # 과제별 개발 내역
    lines.append("## 과제별 개발 내역\n")

    total_additions = 0
    total_deletions = 0
    total_files = 0
    total_dev_comments = 0
    all_authors: set = set()

    for pr in prs:
        parsed = pr["parsed_body"]
        lines.append(f"### PR #{pr['number']}: {pr['title']}\n")
        lines.append("| 항목 | 내용 |")
        lines.append("|------|------|")
        lines.append(
            f"| PR | [#{pr['number']}]"
            f"(https://github.com/{owner}/{repo}/pull/{pr['number']}) |"
        )
        assignee = parsed.get("assignee", pr["author"])
        lines.append(f"| 담당 | {assignee} |")
        all_authors.add(assignee)

        if parsed.get("task_id"):
            lines.append(f"| 과제번호 | {parsed['task_id']} |")
        if parsed.get("tech_stack"):
            lines.append(f"| 기술스택 | {parsed['tech_stack']} |")
        if parsed.get("category"):
            lines.append(f"| 분류 | {parsed['category']} |")
        lines.append(f"| 병합일시 | {_format_date(pr['merged_at'])} |")
        lines.append(f"| 커밋 SHA | {pr['head_sha']} |")
        lines.append("")

        if parsed.get("summary"):
            lines.append(f"**작업내용 요약:** {parsed['summary']}\n")
        if parsed.get("details"):
            lines.append("**작업내용 상세:**")
            for d in parsed["details"]:
                lines.append(f"- {d}")
            lines.append("")

        file_count = len(pr["files"])
        pr_additions = sum(f.get("additions", 0) for f in pr["files"])
        pr_deletions = sum(f.get("deletions", 0) for f in pr["files"])
        total_additions += pr_additions
        total_deletions += pr_deletions
        total_files += file_count

        lines.append(f"**변경 파일 ({file_count}개, +{pr_additions} -{pr_deletions}):**\n")
        lines.append("| 파일 | 추가 | 삭제 |")
        lines.append("|------|------|------|")
        for f in pr["files"]:
            lines.append(
                f"| {f['filename']} | +{f.get('additions', 0)} | -{f.get('deletions', 0)} |"
            )
        lines.append("")

        if pr["dev_comments"]:
            total_dev_comments += len(pr["dev_comments"])
            lines.append(f"**개발자 코멘트 ({len(pr['dev_comments'])}건):**\n")
            for c in pr["dev_comments"]:
                fname = c["path"].split("/")[-1] if c["path"] else "-"
                body = c["body"].strip()
                status_icon = {
                    "resolved": "Resolved",
                    "outdated": "Outdated",
                    "active": "Active",
                }.get(c.get("status", "active"), "Active")
                lines.append(f"- **{fname}:L{c['line']}** ({status_icon})\n")
                for body_line in body.split("\n"):
                    lines.append(f"  > {body_line}")
                lines.append("")
            lines.append("")

        lines.append("---\n")

    # 개발 통계
    lines.append("## 개발 통계\n")
    lines.append("| 항목 | 수치 |")
    lines.append("|------|------|")
    lines.append(f"| 총 PR 수 | {len(prs)}개 |")
    lines.append(f"| 총 변경 파일 | {total_files}개 |")
    lines.append(f"| 총 추가 라인 | +{total_additions} |")
    lines.append(f"| 총 삭제 라인 | -{total_deletions} |")
    lines.append(
        f"| 참여 개발자 | {len(all_authors)}명 ({', '.join(sorted(all_authors))}) |"
    )
    lines.append(f"| 개발자 코멘트 | {total_dev_comments}건 |")
    lines.append("")

    return "\n".join(lines), len(prs), total_additions, total_deletions


def _generate_review_deliverable(
    data: Dict[str, Any], owner: str, repo: str
) -> Tuple[str, int]:
    """코드리뷰산출물 마크다운을 생성한다. (md_text, review_count) 반환"""
    ms = data["milestone"]
    prs = data["prs"]
    ms_number = ms["number"]

    lines: List[str] = []
    lines.append(f"# [{ms_number:04d}] 코드리뷰 산출물\n")

    lines.append("## 리뷰 개요\n")
    lines.append("| 항목 | 내용 |")
    lines.append("|------|------|")
    lines.append(f"| 마일스톤 | {ms['title']} |")
    lines.append(f"| 대상 PR 수 | {len(prs)}개 |")

    all_reviewers: set = set()
    total_review_comments = 0
    category_counts: Dict[str, int] = {}

    for pr in prs:
        all_reviewers.update(pr["reviewers"])
        for c in pr["review_comments"]:
            cat = c.get("category", "일반리뷰")
            if cat != "질의":
                total_review_comments += 1
            category_counts[cat] = category_counts.get(cat, 0) + 1

    lines.append(
        f"| 리뷰어 | {', '.join(sorted(all_reviewers)) if all_reviewers else '-'} |"
    )
    lines.append(f"| 총 지적 건수 | {total_review_comments}건 |")
    lines.append("")
    lines.append("---\n")

    # PR별 리뷰 상세
    lines.append("## PR별 리뷰 상세\n")

    for pr in prs:
        review_comments = pr["review_comments"]
        issue_comments = pr["issue_comments"]

        lines.append(f"### PR #{pr['number']}: {pr['title']}\n")
        lines.append("| 항목 | 내용 |")
        lines.append("|------|------|")
        lines.append(
            f"| PR | [#{pr['number']}]"
            f"(https://github.com/{owner}/{repo}/pull/{pr['number']}) |"
        )
        lines.append(f"| 작성자 | {pr['author']} |")
        lines.append(
            f"| 리뷰어 | {', '.join(pr['reviewers']) if pr['reviewers'] else '-'} |"
        )
        lines.append(f"| 리뷰 상태 | {pr['final_review_state']} |")
        lines.append(f"| 병합일시 | {_format_date(pr['merged_at'])} |")
        lines.append("")

        non_question = [c for c in review_comments if c.get("category") != "질의"]
        questions = [c for c in review_comments if c.get("category") == "질의"]

        if non_question:
            lines.append(f"**리뷰 지적사항 ({len(non_question)}건):**\n")
            lines.append("| # | 분류 | 파일 | 라인 | 상태 | 리뷰어 | 지적내용 |")
            lines.append("|---|------|------|------|------|--------|----------|")
            for i, c in enumerate(non_question, 1):
                fname = c["path"].split("/")[-1] if c["path"] else "-"
                content = _escape_pipe(c["content"])
                status_icon = {
                    "resolved": "Resolved",
                    "outdated": "Outdated",
                    "active": "Active",
                }.get(c.get("status", "active"), "Active")
                lines.append(
                    f"| {i} | {c['category']} | {fname} | L{c['line']} "
                    f"| {status_icon} | {c['author']} | {content} |"
                )
            lines.append("")

        if questions:
            lines.append(f"**질의응답 ({len(questions)}건):**\n")
            for i, c in enumerate(questions, 1):
                fname = c["path"].split("/")[-1] if c["path"] else "-"
                lines.append(
                    f"- **Q{i}** [{fname}:L{c['line']}] {c['content']} "
                    f"-- _{c['author']}, {_format_date_short(c['created_at'])}_"
                )
            lines.append("")

        if issue_comments:
            lines.append(f"**Conversation 코멘트 ({len(issue_comments)}건):**\n")
            for c in issue_comments:
                author = c.get("user", {}).get("login", "")
                body = c.get("body", "").strip()
                date = _format_date_short(c.get("created_at", ""))
                # 코멘트 헤더 + 구분선
                lines.append(f"#### 💬 {author} _{date}_\n")
                # 본문의 제목 레벨을 +2 시프트 (## → ####, ### → #####)
                # 이렇게 하면 문서 구조와 충돌하지 않으면서 마크다운이 정상 렌더링됨
                for body_line in body.split("\n"):
                    if body_line.startswith("######"):
                        lines.append(body_line)  # 이미 최대 레벨
                    elif body_line.startswith("#####"):
                        lines.append("#" + body_line)
                    elif body_line.startswith("####"):
                        lines.append("##" + body_line)
                    elif body_line.startswith("###"):
                        lines.append("##" + body_line)
                    elif body_line.startswith("##"):
                        lines.append("##" + body_line)
                    elif body_line.startswith("# "):
                        lines.append("###" + body_line)
                    else:
                        lines.append(body_line)
                lines.append("")
            lines.append("")

        if not non_question and not questions and not issue_comments:
            lines.append("_리뷰 코멘트 없음_\n")

        lines.append("---\n")

    # 리뷰 통계
    lines.append("## 리뷰 통계\n")

    if category_counts:
        issue_total = sum(v for k, v in category_counts.items() if k != "질의")

        lines.append("### 분류별 지적 건수\n")
        lines.append("| 분류 | 건수 | 비율 |")
        lines.append("|------|------|------|")
        for cat in [
            "보안", "버그/결함", "로직오류", "성능",
            "코드스타일", "개선제안", "일반리뷰", "기타",
        ]:
            count = category_counts.get(cat, 0)
            if count > 0:
                p = round(count / issue_total * 100) if issue_total > 0 else 0
                lines.append(f"| {cat} | {count} | {p}% |")
        lines.append(f"| **합계** | **{issue_total}** | **100%** |")

        q_count = category_counts.get("질의", 0)
        if q_count > 0:
            lines.append(f"| 질의 (지적 외) | {q_count} | - |")
        lines.append("")

    lines.append("### 종합\n")
    lines.append("| 항목 | 수치 |")
    lines.append("|------|------|")
    lines.append(f"| 대상 PR | {len(prs)}개 |")
    lines.append(f"| 리뷰 참여자 | {len(all_reviewers)}명 |")
    lines.append(f"| 총 지적 건수 | {total_review_comments}건 |")
    avg = round(total_review_comments / len(prs), 1) if prs else 0
    lines.append(f"| PR당 평균 지적 | {avg}건 |")
    lines.append("")

    return "\n".join(lines), total_review_comments


# ──────────────────────────────────────────────
# 노드 핸들러
# ──────────────────────────────────────────────

@NodeHandlerRegistry.register
class DeliverableGeneratorHandler(NodeHandler):
    """기존 단일 산출물 생성기 (하위 호환용)"""

    node_type = "deliverable-generator"
    category = "action"
    display_name = "산출물 생성기"
    description = "GitHub 마일스톤 기반 개발/코드리뷰 산출물 자동 생성"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        # 입력 파라미터 추출
        github_url: str = input_data.get("github_url", "")
        milestone_number_raw = input_data.get("milestone_number")
        github_token: str = input_data.get("github_token", "") or ""

        if not github_url:
            raise ValueError("github_url이 필요합니다.")

        # URL 파싱
        owner, repo, ms_from_url = parse_github_url(github_url)

        # milestone_number 결정
        milestone_number: Optional[int] = None
        if milestone_number_raw:
            try:
                milestone_number = int(milestone_number_raw)
            except (ValueError, TypeError):
                pass
        if not milestone_number:
            milestone_number = ms_from_url
        if not milestone_number:
            raise ValueError(
                "마일스톤 번호를 URL에 포함하거나 milestone_number 필드에 입력하세요."
            )

        logger.info(
            "산출물 생성 시작: %s/%s milestone #%d",
            owner, repo, milestone_number,
        )

        # GitHub API 데이터 수집
        gh = GitHubClient(token=github_token if github_token else None)

        try:
            data = await _collect_data(gh, owner, repo, milestone_number)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"GitHub API 호출 실패: {e.response.status_code} - {e.response.text[:200]}"
            ) from e

        # 마크다운 생성
        dev_md, pr_count, total_additions, total_deletions = _generate_dev_deliverable(
            data, owner, repo
        )
        review_md, review_count = _generate_review_deliverable(data, owner, repo)

        milestone_title = data["milestone"].get("title", "")

        # 결합 문서
        combined = (
            dev_md
            + "\n\n---\n\n"
            + review_md
        )

        logger.info(
            "산출물 생성 완료: PR %d건, +%d -%d, 리뷰 %d건",
            pr_count, total_additions, total_deletions, review_count,
        )

        return {
            "markdown": combined,
            "dev_deliverable": dev_md,
            "review_deliverable": review_md,
            "milestone_title": milestone_title,
            "pr_count": pr_count,
            "total_additions": total_additions,
            "total_deletions": total_deletions,
            "review_count": review_count,
        }


# ──────────────────────────────────────────────
# 파이프라인 분할 핸들러 (Dify-style 3-step)
# ──────────────────────────────────────────────


@NodeHandlerRegistry.register
class MilestoneCollectorHandler(NodeHandler):
    """Step 1: GitHub 마일스톤의 PR, 파일변경, 리뷰 코멘트를 수집"""

    node_type = "milestone-collector"
    category = "action"
    display_name = "마일스톤 수집"
    description = "GitHub 마일스톤의 PR, 파일변경, 리뷰 코멘트를 수집합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        github_url: str = input_data.get("github_url", "")
        milestone_number_raw = input_data.get("milestone_number")
        github_token: str = input_data.get("github_token", "") or ""

        if not github_url:
            raise ValueError("github_url이 필요합니다.")

        owner, repo, ms_from_url = parse_github_url(github_url)

        milestone_number: Optional[int] = None
        if milestone_number_raw:
            try:
                milestone_number = int(milestone_number_raw)
            except (ValueError, TypeError):
                pass
        if not milestone_number:
            milestone_number = ms_from_url
        if not milestone_number:
            raise ValueError(
                "마일스톤 번호를 URL에 포함하거나 milestone_number 필드에 입력하세요."
            )

        logger.info(
            "마일스톤 수집 시작: %s/%s milestone #%d",
            owner, repo, milestone_number,
        )

        gh = GitHubClient(token=github_token if github_token else None)

        try:
            data = await _collect_data(gh, owner, repo, milestone_number)
        except httpx.HTTPStatusError as e:
            raise RuntimeError(
                f"GitHub API 호출 실패: {e.response.status_code} - {e.response.text[:200]}"
            ) from e

        milestone = data["milestone"]
        prs = data["prs"]

        # PR 데이터를 직렬화 가능한 형태로 정리
        serialized_prs = []
        for pr in prs:
            serialized_prs.append({
                "number": pr["number"],
                "title": pr["title"],
                "author": pr["author"],
                "merged_at": pr["merged_at"],
                "additions": pr["additions"],
                "deletions": pr["deletions"],
                "changed_files": pr["changed_files"],
                "head_sha": pr["head_sha"],
                "body_raw": pr["body_raw"],
                "parsed_body": pr["parsed_body"],
                "files": [
                    {
                        "filename": f.get("filename", ""),
                        "additions": f.get("additions", 0),
                        "deletions": f.get("deletions", 0),
                        "status": f.get("status", ""),
                    }
                    for f in pr["files"]
                ],
                "dev_comments": pr["dev_comments"],
                "review_comments": pr["review_comments"],
                "issue_comments": [
                    {
                        "user": {"login": c.get("user", {}).get("login", "")},
                        "body": c.get("body", ""),
                        "created_at": c.get("created_at", ""),
                    }
                    for c in pr["issue_comments"]
                ],
                "reviewers": pr["reviewers"],
                "final_review_state": pr["final_review_state"],
                "labels": pr["labels"],
            })

        logger.info(
            "마일스톤 수집 완료: %s/%s, PR %d건",
            owner, repo, len(serialized_prs),
        )

        return {
            "owner": owner,
            "repo": repo,
            "milestone_title": milestone.get("title", ""),
            "milestone_number": milestone.get("number", milestone_number),
            "pr_count": len(serialized_prs),
            "prs": serialized_prs,
            "milestone": milestone,
        }


@NodeHandlerRegistry.register
class DevDeliverableHandler(NodeHandler):
    """Step 2: 수집된 PR 데이터로 개발산출물 마크다운 문서를 생성"""

    node_type = "dev-deliverable-gen"
    category = "action"
    display_name = "개발산출물 생성"
    description = "수집된 PR 데이터로 개발산출물 마크다운 문서를 생성합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        owner = input_data.get("owner", "")
        repo = input_data.get("repo", "")
        milestone = input_data.get("milestone")
        prs = input_data.get("prs")

        if not milestone or not prs:
            raise ValueError(
                "milestone-collector 노드의 출력 데이터가 필요합니다 "
                "(milestone, prs 필드)"
            )

        data = {"milestone": milestone, "prs": prs}
        dev_md, pr_count, total_additions, total_deletions = _generate_dev_deliverable(
            data, owner, repo
        )

        logger.info(
            "개발산출물 생성 완료: PR %d건, +%d -%d",
            pr_count, total_additions, total_deletions,
        )

        # 이전 데이터를 모두 패스스루하고 새 필드 추가
        result = dict(input_data)
        result.update({
            "dev_deliverable": dev_md,
            "total_additions": total_additions,
            "total_deletions": total_deletions,
            "total_files": sum(len(pr.get("files", [])) for pr in prs),
        })
        return result


@NodeHandlerRegistry.register
class ReviewDeliverableHandler(NodeHandler):
    """Step 3: 수집된 리뷰 코멘트를 분류하고 코드리뷰산출물 마크다운 문서를 생성"""

    node_type = "review-deliverable-gen"
    category = "action"
    display_name = "코드리뷰산출물 생성"
    description = "수집된 리뷰 코멘트를 분류하고 코드리뷰산출물 마크다운 문서를 생성합니다"

    async def execute(
        self,
        node: Any,
        input_data: Dict[str, Any],
        ctx: ExecutionContext,
    ) -> Any:
        owner = input_data.get("owner", "")
        repo = input_data.get("repo", "")
        milestone = input_data.get("milestone")
        prs = input_data.get("prs")
        dev_deliverable = input_data.get("dev_deliverable", "")

        if not milestone or not prs:
            raise ValueError(
                "dev-deliverable-gen 노드의 출력 데이터가 필요합니다 "
                "(milestone, prs 필드)"
            )

        data = {"milestone": milestone, "prs": prs}
        review_md, review_count = _generate_review_deliverable(data, owner, repo)

        # 결합 문서
        combined = dev_deliverable + "\n\n---\n\n" + review_md

        logger.info(
            "코드리뷰산출물 생성 완료: 리뷰 %d건",
            review_count,
        )

        # 이전 데이터를 모두 패스스루하고 새 필드 추가
        result = dict(input_data)
        result.update({
            "review_deliverable": review_md,
            "review_count": review_count,
            "markdown": combined,
        })
        return result
