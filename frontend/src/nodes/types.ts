import type { ComponentType } from 'react';
import type { Node } from '@xyflow/react';

/** 노드 카테고리 */
export type NodeCategory = 'starter' | 'ai' | 'logic' | 'action' | 'output';

/** 팔레트 표시 설정 */
export interface PaletteConfig {
  icon: string;
  label: string;
  description: string;
  bg: string;          // tailwind gradient classes
  border: string;      // tailwind border class
  textColor?: string;
  descColor?: string;
  /** 팔레트에서 드래그 시 사용되는 DataTransfer 타입. 없으면 팔레트에 미표시 */
  dragType?: string;
}

/** 모든 ConfigPanel이 받는 공통 props */
export interface ConfigPanelProps {
  nodeId: string;
  nodeName: string;
  config: Record<string, any>;
  inputMapping: Record<string, string>;
  upstreamFields?: { name: string; type: string }[];
  onUpdateName: (name: string) => void;
  onUpdateConfig: (config: Record<string, any>) => void;
  onDelete: () => void;
  onClose: () => void;
  // 실행 관련 (starter 전용)
  onExecute?: (inputData?: Record<string, unknown>) => void;
  executing?: boolean;
  // 분류기 전용
  handleTargets?: Record<string, string>;
  rules?: any[];
  onUpdateRules?: (rules: any[]) => void;
}

/** 패널 동작 정의 */
export interface PanelBehavior {
  /** 노드 클릭 시 동작 */
  onClick?: 'config' | 'detail' | 'queue' | 'warehouse' | 'none';
  /** 노드 더블클릭 시 동작 */
  onDoubleClick?: 'detail' | 'result-modal' | 'markdown-modal' | 'none';
}

/** 노드 정의 -- 레지스트리에 등록되는 단위 */
export interface NodeDefinition {
  /** 노드 정의 타입 (백엔드 NodeDefType과 동일 값) */
  defType: string;
  /** 카테고리 */
  category: NodeCategory;
  /** ReactFlow 노드 타입명 (예: 'formStartNode') */
  reactFlowType: string;
  /** ReactFlow 노드 컴포넌트 */
  component: ComponentType<any>;
  /** 팔레트 설정 (없으면 팔레트에 미표시 -- AI 노드 등) */
  palette?: PaletteConfig;
  /** MiniMap 색상 */
  minimapColor: string;
  /** 드롭 시 새 노드 데이터를 생성하는 팩토리 */
  createNodeData: (id: string, position: { x: number; y: number }, extra?: any) => Node;
  /** 워크플로우 로드 시 인스턴스 데이터에 추가할 기본 데이터 (config 등) */
  defaultData?: (inst: any) => Record<string, any>;
  /** 고정 출력 필드 (스키마가 없는 시스템 노드용) */
  staticOutputFields?: { name: string; type: string }[];
  /** 기본 소스 핸들 */
  defaultSourceHandle?: string;
  /** 노드 클릭/더블클릭 시 우측 패널 동작 정의 */
  panelBehavior?: PanelBehavior;
  /** 설정 패널 컴포넌트 (panelBehavior.onClick === 'config'일 때 사용) */
  configPanel?: ComponentType<any>;
}
