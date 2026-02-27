import { memo } from 'react';
import type { CSSProperties } from 'react';
import { BaseEdge, EdgeLabelRenderer, getBezierPath } from '@xyflow/react';
import type { EdgeProps, Edge } from '@xyflow/react';
import { EDGE_STYLE } from '../../constants/workflow';

interface ConveyorBeltEdgeData extends Record<string, unknown> {
  mappingStatus?: 'complete' | 'partial' | 'none' | 'noSchema';
  mappedCount?: number;
  totalCount?: number;
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
  const [edgePath, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    sourcePosition,
    targetX,
    targetY,
    targetPosition,
  });

  const mergedStyle = {
    ...edgeStyle,
    ...(style || {}),
    ...(selected ? { strokeWidth: 3, filter: 'drop-shadow(0 0 4px #f59e0b)' } : {}),
  };

  const status = data?.mappingStatus;
  const showBadge = status !== undefined;

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
          >
            <div style={getBadgeStyle(status)}>
              {status === 'partial' ? (
                <span style={{ color: 'white', fontSize: 9, fontWeight: 700, lineHeight: 1, whiteSpace: 'nowrap' }}>
                  {data?.mappedCount ?? 0}/{data?.totalCount ?? 0}
                </span>
              ) : (
                <BadgeIcon status={status} />
              )}
            </div>
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}

export const ConveyorBeltEdge = memo(ConveyorBeltEdgeComponent);
