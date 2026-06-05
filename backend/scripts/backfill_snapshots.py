"""backfill_snapshots.py — 레거시 워크플로우 재료 스냅샷 백필 스크립트.

목적
----
Self-contained workflow blueprint (Phase 1-3) 이전에 생성된 워크플로우는
노드 config 에 ``apiSpecSnapshot`` / ``apiSpecSnapshots`` / ``aiNodeSnapshot`` /
``instanceDbMeta`` 같은 동결(freeze) 스냅샷이 없다. 이 스크립트는 모든 워크플로우를
순회하며 **현재 라이브 재료** 기준으로 누락된 스냅샷을 채워 넣는다.

핵심 성질
---------
- **멱등(idempotent)**: ``embed_snapshots_into_nodes`` 의 freeze-once 보장 덕분에
  여러 번 실행해도 이미 동결된 스냅샷은 보존되고, 새로 채워질 노드만 갱신된다.
- **재료 누락 관용**: 참조 재료가 라이브에 없으면 해당 노드는 건너뛰고(warn) 진행한다.
- **부분 갱신만 persist**: config 가 실제로 바뀐 노드만 DB 에 기록한다.
- **generationTraceIds 등 다른 필드는 절대 건드리지 않는다** (노드 config 만 갱신).

사용법
------
  # Dry-run (실제 저장 없이 변경 예정만 출력):
  python scripts/backfill_snapshots.py --dry-run

  # 실제 백필 수행:
  python scripts/backfill_snapshots.py
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서도 한국어/em-dash 출력이 깨지지 않도록 UTF-8 강제.
try:
    sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
except Exception:
    pass

# 이 스크립트는 backend/ 디렉토리 기준으로 실행되므로 sys.path 에 backend/ 추가.
BACKEND_DIR = Path(__file__).parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# FastAPI 앱을 먼저 임포트하여 모듈 의존 순서를 안정화한다.
# (blueprint_snapshot → api.routes.export_import → app.api.__init__ → blueprint
#  순환 부분초기화를 피하기 위함. tests/conftest.py 와 동일 취지.)
from app.main import app as _app  # noqa: E402,F401

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import selectinload  # noqa: E402
from sqlalchemy.orm.attributes import flag_modified  # noqa: E402

from app.core.database import async_session_maker, init_db  # noqa: E402
from app.models.workflow import Workflow  # noqa: E402
from app.services.blueprint_snapshot import embed_snapshots_into_nodes  # noqa: E402


# ── 스냅샷 대상 def 타입 (재료 누락 경고 판단용) ─────────────────────────────
_SNAPSHOTTABLE = {
    "api-call",
    "api-start",
    "ai-api-router",
    "ai-custom",
    "instance-db-insert",
    "instance-db-lookup",
}

_SNAPSHOT_KEYS = (
    "apiSpecSnapshot",
    "apiSpecSnapshots",
    "aiNodeSnapshot",
    "instanceDbMeta",
)


def _has_snapshot(config: dict) -> bool:
    return any(k in (config or {}) for k in _SNAPSHOT_KEYS)


async def backfill(dry_run: bool) -> dict:
    """모든 워크플로우를 순회하며 누락 스냅샷을 백필한다.

    Returns
    -------
    집계 dict: ``{workflows, nodes_snapshotted, nodes_missing_material, persisted}``
    """
    totals = {
        "workflows": 0,
        "nodes_snapshotted": 0,
        "nodes_missing_material": 0,
        "persisted": 0,
    }

    async with async_session_maker() as db:
        result = await db.execute(
            select(Workflow).options(selectinload(Workflow.nodes))
        )
        workflows = list(result.scalars().all())

        if not workflows:
            print("[backfill] 워크플로우가 없습니다. 백필할 대상이 없습니다.")
            return totals

        for wf in workflows:
            totals["workflows"] += 1
            nodes = list(wf.nodes)

            # 변경 감지를 위해 각 노드 config 의 사전 상태를 deep-copy 로 보존.
            before = {n.id: copy.deepcopy(n.config or {}) for n in nodes}

            # 라이브 재료 기준으로 freeze-once 임베딩 (멱등).
            await embed_snapshots_into_nodes(db, nodes)

            wf_snapshotted = 0
            wf_missing = 0

            for n in nodes:
                after_cfg = n.config or {}
                changed = after_cfg != before.get(n.id, {})

                if changed:
                    wf_snapshotted += 1
                    totals["nodes_snapshotted"] += 1
                    # JSON 컬럼 in-place 변경 추적 보장
                    flag_modified(n, "config")
                else:
                    # 스냅샷 대상인데 여전히 스냅샷이 없다면 = 라이브 재료 누락.
                    if (
                        n.definition_type in _SNAPSHOTTABLE
                        and not _has_snapshot(after_cfg)
                    ):
                        wf_missing += 1
                        totals["nodes_missing_material"] += 1
                        print(
                            f"  [warn] wf={wf.id} node={n.node_id}"
                            f"({n.definition_type}) — 라이브 재료 없음, 스냅샷 건너뜀"
                        )

            if wf_snapshotted or wf_missing:
                print(
                    f"[backfill] wf={wf.id} '{wf.name}' — "
                    f"스냅샷 {wf_snapshotted}개"
                    + (f", 누락 {wf_missing}개" if wf_missing else "")
                )

            if wf_snapshotted:
                totals["persisted"] += wf_snapshotted

        if dry_run:
            print("\n[dry-run] 실제 저장하지 않았습니다. 위 변경을 적용하려면 --dry-run 없이 실행하세요.")
            # rollback 으로 메모리 변경 폐기 (보수적)
            await db.rollback()
        else:
            await db.commit()
            print(f"\n[backfill] 완료. 갱신된 노드 {totals['persisted']}개 저장됨.")

    return totals


async def _amain(dry_run: bool) -> None:
    # 테이블/마이그레이션 보장 (서버 미기동 상태에서도 동작)
    await init_db()
    totals = await backfill(dry_run)
    print(
        "[backfill] 요약: "
        f"워크플로우 {totals['workflows']}개, "
        f"스냅샷 노드 {totals['nodes_snapshotted']}개, "
        f"재료누락 노드 {totals['nodes_missing_material']}개"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="레거시 워크플로우에 재료 스냅샷을 백필한다 (freeze-once, 멱등)."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="실제 저장 없이 변경 예정만 출력.",
    )
    args = parser.parse_args()
    asyncio.run(_amain(args.dry_run))


if __name__ == "__main__":
    main()
