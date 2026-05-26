"""
wipe.py — AI 업무도우미 DB 초기화 스크립트

사용법:
  # Dry-run (실제 삭제 없이 확인만):
  python scripts/wipe.py

  # 실제 삭제:
  python scripts/wipe.py --confirm

  # 지식 파일(knowledge/*.md)은 보존하고 DB/벡터만 삭제:
  python scripts/wipe.py --confirm --keep-templates

Phase 1c에서 작성. 미래의 재초기화를 위한 도구.
"""

import argparse
import shutil
import sys
from pathlib import Path

# 이 스크립트는 backend/ 디렉토리 기준으로 실행
BACKEND_DIR = Path(__file__).parent.parent
DATA_DIR = BACKEND_DIR / "data"
DB_FILE = DATA_DIR / "app.db"
CHROMA_DIR = DATA_DIR / "chroma"
KNOWLEDGE_DIR = BACKEND_DIR / "knowledge"
INSTANCE_DB_DIR = DATA_DIR / "instance_dbs"


def collect_targets(keep_templates: bool) -> list[tuple[str, Path]]:
    """초기화 대상 수집.

    Note
    ----
    - SQLite DB 파일은 통째로 unlink. 다음 서버 기동 시 ``Base.metadata.create_all``
      이 모든 테이블을 재생성한다. 구 ``instance_dbs`` / ``instance_db_records``
      테이블은 ``database.init_db()`` 의 마이그레이션이 DROP 처리하므로 별도 작업 없음.
    - 인스턴스DB 폴더(``backend/data/instance_dbs/``) 도 함께 통째로 삭제하여 잔재 0.
    """
    targets = []
    if DB_FILE.exists():
        targets.append(("SQLite DB", DB_FILE))
    if CHROMA_DIR.exists():
        targets.append(("ChromaDB 벡터 저장소", CHROMA_DIR))
    if INSTANCE_DB_DIR.exists():
        targets.append(("인스턴스DB 폴더", INSTANCE_DB_DIR))
    if not keep_templates and KNOWLEDGE_DIR.exists():
        md_files = list(KNOWLEDGE_DIR.glob("*.md"))
        for f in md_files:
            targets.append(("지식 파일", f))
    return targets


def main():
    parser = argparse.ArgumentParser(description="AI 업무도우미 DB/벡터 초기화 도구")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="실제 삭제 수행. 없으면 dry-run.",
    )
    parser.add_argument(
        "--keep-templates",
        action="store_true",
        help="knowledge/*.md 파일을 보존하고 DB/벡터만 삭제.",
    )
    args = parser.parse_args()

    targets = collect_targets(args.keep_templates)

    if not targets:
        print("[wipe.py] 삭제할 항목이 없습니다. 이미 깨끗한 상태입니다.")
        sys.exit(0)

    print("[wipe.py] 삭제 예정 항목:")
    for label, path in targets:
        print(f"  - [{label}] {path}")

    if not args.confirm:
        print("\n[dry-run] 실제 삭제를 위해 --confirm 플래그를 추가하세요.")
        print("예: python scripts/wipe.py --confirm")
        sys.exit(0)

    print("\n[wipe.py] 삭제 시작...")
    for label, path in targets:
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
            print(f"  삭제됨: {path}")
        except Exception as e:
            print(f"  오류: {path} — {e}", file=sys.stderr)

    print("\n[wipe.py] 완료. 백엔드 재기동 시 빈 DB/벡터 저장소로 재생성됩니다.")


if __name__ == "__main__":
    main()
