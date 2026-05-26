import { createContext } from 'react';

/**
 * InstanceExecutionContext
 *
 * 인스턴스 상세 페이지에서 ReactFlow 하위 노드들(예: WarehouseNode)에게
 * 현재 실행 ID를 전달하는 컨텍스트. 컨텍스트가 없으면(편집 화면 등) null을 반환한다.
 */
export interface InstanceExecutionContextValue {
  executionId: string;
}

export const InstanceExecutionContext =
  createContext<InstanceExecutionContextValue | null>(null);
