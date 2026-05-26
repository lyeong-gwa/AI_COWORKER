import type { ComponentType } from 'react';
import type { Node } from '@xyflow/react';

/** 노드 카테고리 */
export type NodeCategory = 'starter' | 'ai' | 'logic' | 'action' | 'output';

/**
 * 팔레트 표시 설정 — 읽기 전용 카탈로그/뷰어에서 썸네일/색상 용도로만 사용.
 *
 * Phase 3c 정리: 드래그앤드롭이 제거되어 `dragType`은 더 이상 의미가 없다.
 * 카탈로그 카드의 색상/아이콘 용도로만 `palette` 필드를 유지한다.
 */
export interface PaletteConfig {
  icon: string;
  label: string;
  description: string;
  bg: string; // tailwind gradient classes
  border: string; // tailwind border class
  textColor?: string;
  descColor?: string;
}

/** 노드 정의 — 레지스트리에 등록되는 단위 */
export interface NodeDefinition {
  /** 노드 정의 타입 (백엔드 NodeDefType과 동일 값) */
  defType: string;
  /** 카테고리 */
  category: NodeCategory;
  /** ReactFlow 노드 타입명 (예: 'formStartNode') */
  reactFlowType: string;
  /** ReactFlow 노드 컴포넌트 */
  component: ComponentType<any>;
  /** 팔레트 설정 (색상/아이콘. 읽기 전용 카탈로그에서만 사용) */
  palette?: PaletteConfig;
  /** MiniMap 색상 */
  minimapColor: string;
  /**
   * 새 노드 데이터를 생성하는 팩토리.
   * Phase 3c 정리: 웹 UI에서는 노드를 생성하지 않으므로 현재 호출부 없음.
   * 레거시 타입 호환을 위해 시그니처만 유지한다.
   */
  createNodeData: (id: string, extra?: any) => Node;
  /** 워크플로우 로드 시 인스턴스 데이터에 추가할 기본 데이터 (config 등) */
  defaultData?: (inst: any) => Record<string, any>;
  /** 고정 출력 필드 (스키마가 없는 시스템 노드용) */
  staticOutputFields?: { name: string; type: string }[];
  /** 기본 소스 핸들 */
  defaultSourceHandle?: string;
}
