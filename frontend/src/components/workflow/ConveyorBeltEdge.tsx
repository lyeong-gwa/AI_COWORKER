import { memo, useState } from 'react';
import type { CSSProperties } from 'react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@xyflow/react';
import type { EdgeProps, Edge } from '@xyflow/react';
import { EDGE_STYLE } from '../../constants/workflow';

interface ConveyorBeltEdgeData extends Record<string, unknown> {
  mappingStatus?: 'complete' | 'partial' | 'none' | 'noSchema';
  mappedCount?: number;
  totalCount?: number;
  executionStatus?: 'idle' | 'running' | 'completed' | 'failed';
  sourceOutput?: unknown;
}

const edgeStyle = EDGE_STYLE;

function BadgeIcon({ status }: { status: ConveyorBeltEdgeData['mappingStatus'] }) {
  if (status === 'complete') {
    return (
      <svg width="12" height="12" viewBox="0 0 12 12" fill="none">
        <path d="M2 6l3 3 5-5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  if (status === 'none') {
    return (
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
        <path d="M2 2l6 6M8 2l-6 6" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    );
  }
  if (status === 'noSchema') {
    return <span style={{ color: 'white', fontSize: 11, fontWeight: 700, lineHeight: 1 }}>—</span>;
  }
  return null;
}

function getBadgeStyle(status: ConveyorBeltEdgeData['mappingStatus']): CSSProperties {
  const base: CSSProperties = {
    width: 22,
    height: 22,
    borderRadius: '50%',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    cursor: 'pointer',
    boxShadow: '0 1px 4px rgba(0,0,0,0.5)',
    border: '1.5px solid rgba(255,255,255,0.15)',
    userSelect: 'none',
  };

  switch (status) {
    case 'complete':
      return { ...base, backgroundColor: '#059669' };
    case 'partial':
      return { ...base, backgroundColor: '#d97706', width: 'auto', minWidth: 22, borderRadius: 11, padding: '0 5px' };
    case 'none':
      return { ...base, backgroundColor: '#dc2626' };
    case 'noSchema':
    default:
      return { ...base, backgroundColor: '#4b5563' };
  }
}

/** 실행 상태별 엣지 스타일 오버라이드 */
function getExecutionEdgeStyle(execStatus: ConveyorBeltEdgeData['executionStatus']): CSSProperties {
  switch (execStatus) {
    case 'running':
      return {
        stroke: '#3b82f6',
        strokeWidth: 3,
        filter: 'drop-shadow(0 0 6px rgba(59,130,246,0.6))',
        animation: 'conveyor-flow 0.6s linear infinite',
      };
    case 'completed':
      return {
        stroke: '#22c55e',
        strokeWidth: 3,
        filter: 'drop-shadow(0 0 4px rgba(34,197,94,0.4))',
      };
    case 'failed':
      return {
        stroke: '#6b7280',
        strokeWidth: 2,
        opacity: 0.5,
        strokeDasharray: '4 4',
      };
    default:
      return {};
  }
}

/** 값을 간결하게 표시 */
function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'null';
  if (typeof value === 'string') {
    return value.length > 30 ? `"${value.slice(0, 27)}..."` : `"${value}"`;
  }
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  if (Array.isArray(value)) return `Array(${value.length})`;
  if (typeof value === 'object') {
    const keys = Object.keys(value);
    return `{${keys.length} fields}`;
  }
  return String(value);
}

/** 데이터 미리보기 툴팁 */
function DataPreviewTooltip({ data }: { data: unknown }) {
  if (!data || typeof data !== 'object') return null;
  const entries = Object.entries(data as Record<string, unknown>).slice(0, 6);
  if (entries.length === 0) return null;

  return (
    <div
      style={{
        background: '#1e293b',
        border: '1px solid #334155',
        borderRadius: 8,
        padding: '6px 10px',
        minWidth: 160,
        maxWidth: 260,
        boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
      }}
    >
      <div style={{ fontSize: 9, color: '#94a3b8', marginBottom: 4, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
        데이터 미리보기
      </div>
      {entries.map(([key, val]) => (
        <div key={key} style={{ display: 'flex', gap: 6, fontSize: 10, lineHeight: '16px' }}>
          <span style={{ color: '#60a5fa', fontWeight: 500, flexShrink: 0 }}>{key}:</span>
          <span style={{ color: '#cbd5e1', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {formatValue(val)}
          </span>
        </div>
      ))}
      {Object.keys(data as object).length > 6 && (
        <div style={{ fontSize: 9, color: '#64748b', marginTop: 2 }}>
          +{Object.keys(data as object).length - 6}개 더...
        </div>
      )}
    </div>
  );
}

function ConveyorBeltEdgeComponent({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  selected,
  style,
  markerEnd,
}: EdgeProps<Edge<ConveyorBeltEdgeData>>) {
  const [showTooltip, setShowTooltip] = useState(false);

  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const execStatus = data?.executionStatus;
  const execStyle = getExecutionEdgeStyle(execStatus);

  const mergedStyle: CSSProperties = {
    ...edgeStyle,
    ...(style || {}),
    ...execStyle,
    ...(selected ? { strokeWidth: 3, filter: 'drop-shadow(0 0 4px #f59e0b)' } : {}),
  };

  const mappingStatus = data?.mappingStatus;
  const showBadge = mappingStatus !== undefined;
  const hasOutputData = execStatus === 'completed' && data?.sourceOutput != null;

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={mergedStyle} markerEnd={markerEnd} />
      {showBadge && (
        <EdgeLabelRenderer>
          <div
            style={{
              position: 'absolute',
              transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
              pointerEvents: 'all',
            }}
            className="nodrag nopan"
            onMouseEnter={() => hasOutputData && setShowTooltip(true)}
            onMouseLeave={() => setShowTooltip(false)}
          >
            {/* 매핑 상태 배지 */}
            <div style={{ position: 'relative' }}>
              <div style={getBadgeStyle(mappingStatus)}>
                {mappingStatus === 'partial' ? (
                  <span style={{ color: 'white', fontSize: 9, fontWeight: 700, lineHeight: 1, whiteSpace: 'nowrap' }}>
                    {data?.mappedCount ?? 0}/{data?.totalCount ?? 0}
                  </span>
                ) : (
                  <BadgeIcon status={mappingStatus} />
                )}
              </div>

              {/* 실행 데이터 인디케이터 */}
              {hasOutputData && (
                <div
                  style={{
                    position: 'absolute',
                    top: -4,
                    right: -4,
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    backgroundColor: '#22c55e',
                    border: '1.5px solid #111827',
                  }}
                />
              )}

              {/* Running 상태 링 */}
              {execStatus === 'running' && (
                <div
                  style={{
                    position: 'absolute',
                    inset: -3,
                    borderRadius: '50%',
                    border: '2px solid rgba(59,130,246,0.5)',
                    animation: 'ping 1s cubic-bezier(0,0,0.2,1) infinite',
                  }}
                />
              )}
            </div>

            {/* 데이터 미리보기 툴팁 */}
            {showTooltip && hasOutputData && (
              <div style={{ position: 'absolute', top: 28, left: '50%', transform: 'translateX(-50%)', zIndex: 50 }}>
                <DataPreviewTooltip data={data.sourceOutput} />
              </div>
            )}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const ConveyorBeltEdge = memo(ConveyorBeltEdgeComponent);
