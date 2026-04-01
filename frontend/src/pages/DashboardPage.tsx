import { useState, useEffect, useCallback } from 'react';
import { useToast } from '../components/common/Toast';
import { exportImportApi, type ImportResult } from '../services/api';

// ─── Helpers ─────────────────────────────────────────────────────────────────

function downloadJson(data: unknown, filename: string) {
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function todayStr() {
  return new Date().toISOString().slice(0, 10).replace(/-/g, '');
}

function resultSummary(r: ImportResult) {
  const parts: string[] = [];
  if (r.created) parts.push(`${r.created}개 생성`);
  if (r.updated) parts.push(`${r.updated}개 업데이트`);
  if (r.skipped) parts.push(`${r.skipped}개 건너뜀`);
  return parts.length ? parts.join(', ') : '변경 없음';
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

const TYPE_LABELS: Record<string, string> = {
  workflows: '워크플로우',
  nodes: 'AI 노드',
  'api-definitions': 'API 정의',
  knowledge: '지식 베이스',
};

// ─── Card ─────────────────────────────────────────────────────────────────────

interface CardProps {
  icon: string;
  title: string;
  subtitle?: string;
  onExport: () => Promise<void>;
  onImport: () => void;
}

function DataCard({ icon, title, subtitle, onExport, onImport }: CardProps) {
  const [exporting, setExporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      await onExport();
    } finally {
      setExporting(false);
    }
  }

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-xl p-6 flex flex-col gap-4">
      <div className="flex items-start gap-3">
        <span className="text-3xl leading-none">{icon}</span>
        <div>
          <h2 className="text-lg font-semibold text-white">{title}</h2>
          {subtitle && (
            <p className="text-xs text-gray-400 mt-0.5">{subtitle}</p>
          )}
        </div>
      </div>

      <div className="flex gap-3 mt-auto">
        <button
          onClick={handleExport}
          disabled={exporting}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg
                     bg-blue-600 hover:bg-blue-500 disabled:bg-blue-800 disabled:opacity-60
                     text-white text-sm font-medium transition-colors"
        >
          {exporting ? (
            <>
              <span className="inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              내보내는 중...
            </>
          ) : (
            <>
              <span>↓</span>
              내보내기
            </>
          )}
        </button>

        <button
          onClick={onImport}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg
                     bg-emerald-600 hover:bg-emerald-500
                     text-white text-sm font-medium transition-colors"
        >
          <span>↑</span>
          가져오기
        </button>
      </div>
    </div>
  );
}

// ─── Local File Picker Modal ─────────────────────────────────────────────────

interface LocalFile {
  name: string;
  size: number;
  modifiedAt: number;
}

function LocalFilePickerModal({
  onClose,
  onImported,
  filterKeyword,
}: {
  onClose: () => void;
  onImported: (type: string, result: ImportResult) => void;
  filterKeyword?: string;
}) {
  const [files, setFiles] = useState<LocalFile[]>([]);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState<string | null>(null);
  const { toast } = useToast();

  const fetchFiles = useCallback(async () => {
    setLoading(true);
    try {
      let all = await exportImportApi.listLocalFiles();
      if (filterKeyword) {
        all = all.filter((f) => f.name.toLowerCase().includes(filterKeyword.toLowerCase()));
      }
      setFiles(all);
    } catch {
      toast.error('파일 목록을 불러올 수 없습니다');
    } finally {
      setLoading(false);
    }
  }, [filterKeyword, toast]);

  useEffect(() => {
    fetchFiles();
  }, [fetchFiles]);

  async function handleImport(filename: string) {
    setImporting(filename);
    try {
      const result = await exportImportApi.importLocalFile(filename);
      const typeLabel = TYPE_LABELS[result.type] || result.type;
      toast.success(`${typeLabel} 가져오기 완료 — ${resultSummary(result)}`);
      onImported(result.type, result);
      onClose();
    } catch (e: unknown) {
      toast.error(`가져오기 실패: ${e instanceof Error ? e.message : String(e)}`);
    } finally {
      setImporting(null);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50" onClick={onClose}>
      <div
        className="bg-gray-800 border border-gray-700 rounded-xl w-full max-w-lg max-h-[70vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="px-5 py-4 border-b border-gray-700 flex items-center justify-between">
          <div>
            <h3 className="text-white font-semibold">서버 파일에서 가져오기</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              backend/data/download/ 에 JSON 파일을 배치하세요
            </p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-white text-xl px-1">
            ✕
          </button>
        </div>

        {/* File list */}
        <div className="flex-1 overflow-auto p-4 space-y-2">
          {loading ? (
            <div className="flex items-center justify-center py-10">
              <div className="w-6 h-6 border-2 border-blue-500/30 border-t-blue-500 rounded-full animate-spin" />
            </div>
          ) : files.length === 0 ? (
            <div className="text-center py-10">
              <div className="text-3xl mb-2">📂</div>
              <p className="text-gray-500 text-sm">JSON 파일이 없습니다</p>
              <p className="text-gray-600 text-xs mt-1">
                backend/data/download/ 폴더에 JSON 파일을 넣어주세요
              </p>
            </div>
          ) : (
            files.map((f) => (
              <div
                key={f.name}
                className="bg-gray-900 rounded-lg border border-gray-700 px-4 py-3 flex items-center justify-between hover:border-gray-600 transition-colors"
              >
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-lg">📄</span>
                  <div className="min-w-0">
                    <div className="text-sm text-gray-200 font-mono truncate">{f.name}</div>
                    <div className="text-[10px] text-gray-500">
                      {formatBytes(f.size)} · {new Date(f.modifiedAt * 1000).toLocaleString('ko-KR')}
                    </div>
                  </div>
                </div>
                <button
                  onClick={() => handleImport(f.name)}
                  disabled={importing !== null}
                  className="flex-shrink-0 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500
                             disabled:bg-emerald-800 disabled:opacity-60
                             text-white text-xs font-medium transition-colors"
                >
                  {importing === f.name ? (
                    <span className="inline-block w-3 h-3 border-2 border-white border-t-transparent rounded-full animate-spin" />
                  ) : (
                    '가져오기'
                  )}
                </button>
              </div>
            ))
          )}
        </div>

        {/* Footer */}
        <div className="px-5 py-3 border-t border-gray-700 flex justify-between items-center">
          <button
            onClick={fetchFiles}
            className="text-xs text-gray-400 hover:text-gray-200 transition-colors"
          >
            🔄 새로고침
          </button>
          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-gray-700 hover:bg-gray-600 text-gray-300 text-sm transition-colors"
          >
            닫기
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { toast } = useToast();
  const [importModal, setImportModal] = useState<{ filter?: string } | null>(null);

  // Export handlers
  async function exportKnowledge() {
    try {
      const data = await exportImportApi.exportKnowledge();
      downloadJson(data, `knowledge_${todayStr()}.json`);
      toast.success(`지식 베이스 ${data.length}개 내보내기 완료`);
    } catch (e: unknown) {
      toast.error(`내보내기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function exportNodes() {
    try {
      const data = await exportImportApi.exportNodes();
      downloadJson(data, `nodes_${todayStr()}.json`);
      toast.success(`AI 노드 ${data.length}개 내보내기 완료`);
    } catch (e: unknown) {
      toast.error(`내보내기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function exportApiDefs() {
    try {
      const data = await exportImportApi.exportApiDefinitions();
      downloadJson(data, `api_definitions_${todayStr()}.json`);
      toast.success(`API 정의 ${data.length}개 내보내기 완료`);
    } catch (e: unknown) {
      toast.error(`내보내기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function exportWorkflows() {
    try {
      const data = await exportImportApi.exportAllWorkflows();
      downloadJson(data, `workflows_${todayStr()}.json`);
      toast.success(`워크플로우 ${data.length}개 내보내기 완료`);
    } catch (e: unknown) {
      toast.error(`내보내기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  return (
    <div className="h-full overflow-auto bg-gray-900 p-6">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-white">데이터 관리</h1>
        <p className="text-gray-400 mt-1 text-sm">
          각 데이터 유형을 JSON 파일로 내보내거나 가져올 수 있습니다.
        </p>
        <p className="text-gray-500 mt-0.5 text-xs">
          가져오기: backend/data/download/ 폴더에 JSON 파일을 배치한 후 가져오기 버튼을 누르세요.
        </p>
      </div>

      {/* 2×2 Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 max-w-3xl">
        <DataCard
          icon="📚"
          title="지식 베이스"
          subtitle="RAG에 사용되는 문서 및 텍스트 데이터"
          onExport={exportKnowledge}
          onImport={() => setImportModal({ filter: 'knowledge' })}
        />
        <DataCard
          icon="🤖"
          title="AI 노드"
          subtitle="시스템 프롬프트 및 노드 설정 데이터"
          onExport={exportNodes}
          onImport={() => setImportModal({ filter: 'node' })}
        />
        <DataCard
          icon="🌐"
          title="API 정의"
          subtitle="외부 API 연결 스펙 및 파라미터 정의"
          onExport={exportApiDefs}
          onImport={() => setImportModal({ filter: 'api' })}
        />
        <DataCard
          icon="⚙️"
          title="워크플로우"
          subtitle="의존성(노드 / API / 지식) 포함 전체 내보내기"
          onExport={exportWorkflows}
          onImport={() => setImportModal({ filter: 'workflow' })}
        />
      </div>

      {/* 전체 파일 가져오기 버튼 */}
      <div className="mt-6 max-w-3xl">
        <button
          onClick={() => setImportModal({})}
          className="w-full py-3 border border-dashed border-gray-600 text-gray-400 text-sm rounded-xl
                     hover:bg-gray-800 hover:border-gray-500 hover:text-gray-300 transition-colors"
        >
          📂 전체 파일 목록에서 가져오기
        </button>
      </div>

      {/* Import Modal */}
      {importModal && (
        <LocalFilePickerModal
          filterKeyword={importModal.filter}
          onClose={() => setImportModal(null)}
          onImported={() => {}}
        />
      )}
    </div>
  );
}
