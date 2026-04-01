import type { NodeTypes } from '@xyflow/react';
import type { NodeDefinition, NodeCategory } from './types';

class NodeRegistryClass {
  private definitions = new Map<string, NodeDefinition>();
  private reactFlowTypeMap = new Map<string, NodeDefinition>(); // reactFlowType -> def

  register(def: NodeDefinition): void {
    this.definitions.set(def.defType, def);
    this.reactFlowTypeMap.set(def.reactFlowType, def);
  }

  get(defType: string): NodeDefinition | undefined {
    return this.definitions.get(defType);
  }

  getByReactFlowType(rfType: string): NodeDefinition | undefined {
    return this.reactFlowTypeMap.get(rfType);
  }

  getByCategory(category: NodeCategory): NodeDefinition[] {
    return [...this.definitions.values()].filter(d => d.category === category);
  }

  /** 팔레트에 표시할 노드 정의 (palette가 있는 것만) */
  getPaletteNodes(category?: NodeCategory): NodeDefinition[] {
    return [...this.definitions.values()].filter(d => {
      if (!d.palette) return false;
      if (category && d.category !== category) return false;
      return true;
    });
  }

  /** ReactFlow nodeTypes 객체 자동 생성 */
  getNodeTypes(): NodeTypes {
    const types: NodeTypes = {};
    for (const def of this.definitions.values()) {
      types[def.reactFlowType] = def.component;
    }
    return types;
  }

  /** defType -> reactFlowType 매핑 */
  getReactFlowType(defType: string): string {
    const def = this.definitions.get(defType);
    return def?.reactFlowType || 'factoryNode';  // fallback
  }

  /** MiniMap 색상 조회 */
  getMinimapColor(reactFlowType: string): string {
    const def = this.reactFlowTypeMap.get(reactFlowType);
    return def?.minimapColor || '#475569';
  }

  /** 고정 출력 필드 조회 */
  getStaticOutputFields(defType: string): { name: string; type: string }[] | undefined {
    return this.definitions.get(defType)?.staticOutputFields;
  }

  /** 기본 소스 핸들 */
  getDefaultSourceHandle(defType: string): string {
    const def = this.definitions.get(defType);
    return def?.defaultSourceHandle || 'output';
  }

  all(): NodeDefinition[] {
    return [...this.definitions.values()];
  }
}

export const nodeRegistry = new NodeRegistryClass();
