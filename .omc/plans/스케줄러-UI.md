# 워크플로 스케줄러 UI

작성일: 2026-05-27

## 목표

각 워크플로마다 **웹 UI 에서 스케줄러 ON/OFF + 주기 설정** 가능하게.
CLI 없이 운영자가 직접 관리.

## 확정 결정

| # | 결정 |
|---|---|
| D1 | 워크플로 메타에 `schedule_config` JSON 필드 추가 (모델 변경) |
| D2 | scheduler 가 그 필드 기반으로 cron job 등록 (기존 schedule-trigger 노드 메커니즘과 병행 가능) |
| D3 | UI preset 주기: **5분 / 10분 / 30분 / 1시간 / 6시간 / 매일 자정 / 매주 월요일 09:00** + custom cron 입력 |
| D4 | timezone: **Asia/Seoul 고정** (한국 운영 기준) |
| D5 | 즉시 실행 버튼 같이 제공 (`POST /ops/scheduler/trigger/{wf_id}` 활용) |
| D6 | 기존 워크플로의 default = `{enabled: false, cronExpr: "0 * * * *"}` (매시 정각, 비활성) |

## Phase A — Backend

### A-1. 모델 변경 (`models/workflow.py`)
```python
class Workflow(Base):
    ...existing...
    schedule_config: Mapped[Dict[str, Any]] = mapped_column(
        JSON, 
        default=lambda: {"enabled": False, "cronExpr": "0 * * * *", "timezone": "Asia/Seoul"}
    )
```
- 마이그레이션: 기존 워크플로 모두 default 부여

### A-2. 스케줄러 갱신 (`core/scheduler.py`)
- `reload_jobs()` 가 두 종류 스캔:
  - 기존: status=ACTIVE + 첫 노드 = schedule-trigger
  - 신규: status=ACTIVE + `schedule_config.enabled = true`
- 둘 다 cron job 등록
- 동일 워크플로 중복 등록 방지 (job_id = `wf:{workflow_id}`)

### A-3. 신규 엔드포인트
- `PATCH /api/v1/workflows/{id}/schedule` body `{enabled, cronExpr, timezone?}` → schedule_config 갱신 + `reload_jobs()` 자동 호출
- `GET /api/v1/workflows/{id}/schedule/next-run` → 다음 실행 예정 시각 1건 (APScheduler 의 next_run_time)

### A-4. 응답 확장
- `GET /workflows/{id}` 및 목록 응답에 `scheduleConfig` 포함

### A-5. 테스트
- `test_workflow_schedule.py`:
  - schedule_config default 검증
  - PATCH 후 reload_jobs 자동 호출 확인
  - cron 표현식 유효성 (잘못된 표현식 → 422)
  - 토글 OFF 시 job 제거

기존 282 회귀 0.

## Phase B — Frontend

### B-1. 신규 컴포넌트 `WorkflowScheduleCard.tsx`
- 워크플로 상세 페이지 (또는 카드) 에 노출
- 내용:
  - **토글 스위치** (ON/OFF)
  - **주기 드롭다운** (preset 7종 + "커스텀 cron" 옵션)
  - cron 표현식 입력 (커스텀 선택 시)
  - "다음 실행 시간" 표시 (`/schedule/next-run` 호출)
  - **즉시 실행** 버튼 (`ops/scheduler/trigger/{wf_id}`)
  - 저장 버튼 → PATCH

### B-2. preset 매핑
```
5분마다     →  */5 * * * *
10분마다    →  */10 * * * *
30분마다    →  */30 * * * *
1시간마다   →  0 * * * *
6시간마다   →  0 */6 * * *
매일 자정   →  0 0 * * *
매주 월요일 09:00 → 0 9 * * 1
커스텀      →  사용자 입력
```

### B-3. `WorkflowListPage.tsx`
- 각 카드에 "스케줄: ON / OFF (주기)" 배지 노출
- 스케줄 ON 인 워크플로는 cyan 배지로 강조

### B-4. `services/api.ts`
- `getWorkflowScheduleNextRun(wfId)`
- `updateWorkflowSchedule(wfId, body)`
- `triggerWorkflowNow(wfId)` (기존 ops/trigger 활용)

## Phase C — 검증

- pytest 회귀 0
- npm build 0
- Playwright: 워크플로 상세 진입 → 스케줄 카드 → 토글 ON + 10분 선택 + 저장 → 다음 실행 시간 노출
- ops/scheduler/jobs 응답에 wf:wf-xxx 등록 확인

## 운영 제약

- `workflow_engine.py` 수정 금지
- 8002 재기동 시 `--reload` 금지
- 라이브 워크플로 3건 데이터 보존
- ChromaDB·archive 미수정

## Out of Scope

- 스케줄러 실행 이력 별도 UI (기존 instance 목록으로 충분)
- 워크플로 간 trigger 의존 (예: A 끝나면 B)
- 스케줄 실패 시 재시도 정책 (APScheduler default 동작 활용)
