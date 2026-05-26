/**
 * LinksPanel — Karpathy v2 outgoing links / backlinks 패널
 *
 * 두 섹션을 카드로 표시. 링크 클릭 시 상세 페이지 이동.
 * id 형식: `{category}/{slug}` (예: ito-portal-operations/member-permission)
 */

interface LinksPanelProps {
  links: string[];
  backlinks: string[];
  /** 링크 클릭 시 호출 — id(category/slug) 전달 */
  onNavigate?: (id: string) => void;
}

function LinkItem({
  id,
  onNavigate,
}: {
  id: string;
  onNavigate?: (id: string) => void;
}) {
  const label = id.split('/').pop() ?? id;
  return (
    <li>
      <button
        type="button"
        onClick={() => onNavigate?.(id)}
        className="w-full text-left px-2 py-1 rounded text-xs text-sky-400 hover:text-sky-300 hover:bg-sky-500/10 transition-colors truncate font-mono"
        title={id}
      >
        {label}
        <span className="text-slate-600 ml-1 text-[10px]">{id}</span>
      </button>
    </li>
  );
}

export function LinksPanel({ links, backlinks, onNavigate }: LinksPanelProps) {
  return (
    <div className="space-y-3">
      {/* Outgoing Links */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 overflow-hidden">
        <div className="px-3 py-2 border-b border-slate-800 flex items-center gap-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
            Outgoing Links
          </span>
          <span className="text-[10px] font-mono text-slate-600 ml-auto">
            {links.length}
          </span>
        </div>
        <div className="p-2">
          {links.length === 0 ? (
            <p className="text-[11px] text-slate-600 px-2 py-1">(없음)</p>
          ) : (
            <ul className="space-y-0.5">
              {links.map((id) => (
                <LinkItem key={id} id={id} onNavigate={onNavigate} />
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Backlinks */}
      <div className="rounded-lg border border-slate-800 bg-slate-900/40 overflow-hidden">
        <div className="px-3 py-2 border-b border-slate-800 flex items-center gap-2">
          <span className="text-[10px] font-mono uppercase tracking-wider text-slate-500">
            Backlinks
          </span>
          <span className="text-[10px] font-mono text-slate-600 ml-auto">
            {backlinks.length}
          </span>
        </div>
        <div className="p-2">
          {backlinks.length === 0 ? (
            <p className="text-[11px] text-slate-600 px-2 py-1">(없음)</p>
          ) : (
            <ul className="space-y-0.5">
              {backlinks.map((id) => (
                <LinkItem key={id} id={id} onNavigate={onNavigate} />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
