import { useRef, useState } from 'react';
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

function readJsonFile(file: File): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      try {
        resolve(JSON.parse(reader.result as string));
      } catch {
        reject(new Error('잘못된 JSON 파일입니다'));
      }
    };
    reader.onerror = () => reject(reader.error);
    reader.readAsText(file);
  });
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

// ─── Card ─────────────────────────────────────────────────────────────────────

interface CardProps {
  icon: string;
  title: string;
  subtitle?: string;
  onExport: () => Promise<void>;
  onImport: (file: File) => Promise<void>;
}

function DataCard({ icon, title, subtitle, onExport, onImport }: CardProps) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [exporting, setExporting] = useState(false);
  const [importing, setImporting] = useState(false);

  async function handleExport() {
    setExporting(true);
    try {
      await onExport();
    } finally {
      setExporting(false);
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    // Reset so same file can be re-selected
    e.target.value = '';
    setImporting(true);
    try {
      await onImport(file);
    } finally {
      setImporting(false);
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
          onClick={() => fileRef.current?.click()}
          disabled={importing}
          className="flex-1 flex items-center justify-center gap-2 px-4 py-2 rounded-lg
                     bg-emerald-600 hover:bg-emerald-500 disabled:bg-emerald-800 disabled:opacity-60
                     text-white text-sm font-medium transition-colors"
        >
          {importing ? (
            <>
              <span className="inline-block w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
              가져오는 중...
            </>
          ) : (
            <>
              <span>↑</span>
              가져오기
            </>
          )}
        </button>

        <input
          ref={fileRef}
          type="file"
          accept=".json"
          className="hidden"
          onChange={handleFileChange}
        />
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function DashboardPage() {
  const { toast } = useToast();

  // Knowledge
  async function exportKnowledge() {
    try {
      const data = await exportImportApi.exportKnowledge();
      downloadJson(data, `knowledge_${todayStr()}.json`);
      toast.success(`지식 베이스 ${data.length}개 내보내기 완료`);
    } catch (e: unknown) {
      toast.error(`내보내기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function importKnowledge(file: File) {
    try {
      const raw = await readJsonFile(file);
      const result = await exportImportApi.importKnowledge(raw as any[]);
      toast.success(`지식 베이스 가져오기 완료 — ${resultSummary(result)}`);
    } catch (e: unknown) {
      toast.error(`가져오기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // Nodes
  async function exportNodes() {
    try {
      const data = await exportImportApi.exportNodes();
      downloadJson(data, `nodes_${todayStr()}.json`);
      toast.success(`AI 노드 ${data.length}개 내보내기 완료`);
    } catch (e: unknown) {
      toast.error(`내보내기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function importNodes(file: File) {
    try {
      const raw = await readJsonFile(file);
      const result = await exportImportApi.importNodes(raw as any[]);
      toast.success(`AI 노드 가져오기 완료 — ${resultSummary(result)}`);
    } catch (e: unknown) {
      toast.error(`가져오기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // API Definitions
  async function exportApiDefs() {
    try {
      const data = await exportImportApi.exportApiDefinitions();
      downloadJson(data, `api_definitions_${todayStr()}.json`);
      toast.success(`API 정의 ${data.length}개 내보내기 완료`);
    } catch (e: unknown) {
      toast.error(`내보내기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function importApiDefs(file: File) {
    try {
      const raw = await readJsonFile(file);
      const result = await exportImportApi.importApiDefinitions(raw as any[]);
      toast.success(`API 정의 가져오기 완료 — ${resultSummary(result)}`);
    } catch (e: unknown) {
      toast.error(`가져오기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  // Workflows
  async function exportWorkflows() {
    try {
      const data = await exportImportApi.exportAllWorkflows();
      downloadJson(data, `workflows_${todayStr()}.json`);
      toast.success(`워크플로우 ${data.length}개 내보내기 완료`);
    } catch (e: unknown) {
      toast.error(`내보내기 실패: ${e instanceof Error ? e.message : String(e)}`);
    }
  }

  async function importWorkflows(file: File) {
    try {
      const raw = await readJsonFile(file);
      const result = await exportImportApi.importWorkflows(raw as any[]);
      toast.success(`워크플로우 가져오기 완료 — ${resultSummary(result)}`);
    } catch (e: unknown) {
      toast.error(`가져오기 실패: ${e instanceof Error ? e.message : String(e)}`);
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
      </div>

      {/* 2×2 Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5 max-w-3xl">
        <DataCard
          icon="📚"
          title="지식 베이스"
          subtitle="RAG에 사용되는 문서 및 텍스트 데이터"
          onExport={exportKnowledge}
          onImport={importKnowledge}
        />
        <DataCard
          icon="🤖"
          title="AI 노드"
          subtitle="시스템 프롬프트 및 노드 설정 데이터"
          onExport={exportNodes}
          onImport={importNodes}
        />
        <DataCard
          icon="🌐"
          title="API 정의"
          subtitle="외부 API 연결 스펙 및 파라미터 정의"
          onExport={exportApiDefs}
          onImport={importApiDefs}
        />
        <DataCard
          icon="⚙️"
          title="워크플로우"
          subtitle="의존성(노드 / API / 지식) 포함 전체 내보내기"
          onExport={exportWorkflows}
          onImport={importWorkflows}
        />
      </div>
    </div>
  );
}
