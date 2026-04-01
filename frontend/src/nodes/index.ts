export { nodeRegistry } from './registry';
export type { NodeDefinition, NodeCategory, PaletteConfig } from './types';

// 등록 사이드이펙트 -- import 하면 자동 등록
import './registrations';
