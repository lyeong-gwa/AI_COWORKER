/**
 * ServiceBadge — 서비스별 색상 배지
 *
 * 색상 매핑:
 *   codeeyes → cyan (시안)
 *   unknown  → slate (회색)
 *   그 외     → serviceId 해시 기반 5색 중 택1
 *
 * compact=true 일 때 dot + id 약어만 표시 (사이드바 그룹 헤더용)
 */

interface ServiceBadgeProps {
  serviceId: string;
  serviceTitle?: string;
  compact?: boolean;
  className?: string;
}

// 사전 정의 색상 (id → tailwind 클래스 세트)
const PREDEFINED: Record<string, { bg: string; text: string; border: string; dot: string }> = {
  codeeyes: {
    bg: 'bg-cyan-500/15',
    text: 'text-cyan-300',
    border: 'border-cyan-500/30',
    dot: '#06b6d4',
  },
  unknown: {
    bg: 'bg-slate-500/15',
    text: 'text-slate-400',
    border: 'border-slate-500/30',
    dot: '#64748b',
  },
};

// 해시 기반 5색 팔레트 (predefined 에 없는 서비스용)
const HASH_PALETTE: Array<{ bg: string; text: string; border: string; dot: string }> = [
  { bg: 'bg-violet-500/15', text: 'text-violet-300', border: 'border-violet-500/30', dot: '#8b5cf6' },
  { bg: 'bg-amber-500/15',  text: 'text-amber-300',  border: 'border-amber-500/30',  dot: '#f59e0b' },
  { bg: 'bg-emerald-500/15',text: 'text-emerald-300',border: 'border-emerald-500/30',dot: '#10b981' },
  { bg: 'bg-rose-500/15',   text: 'text-rose-300',   border: 'border-rose-500/30',   dot: '#f43f5e' },
  { bg: 'bg-orange-500/15', text: 'text-orange-300', border: 'border-orange-500/30', dot: '#f97316' },
];

function hashServiceId(id: string): number {
  let h = 0;
  for (let i = 0; i < id.length; i++) {
    h = (h * 31 + id.charCodeAt(i)) >>> 0;
  }
  return h;
}

export function getServiceColor(serviceId: string): { bg: string; text: string; border: string; dot: string } {
  if (PREDEFINED[serviceId]) return PREDEFINED[serviceId];
  return HASH_PALETTE[hashServiceId(serviceId) % HASH_PALETTE.length];
}

export function ServiceBadge({ serviceId, serviceTitle, compact = false, className = '' }: ServiceBadgeProps) {
  const cfg = getServiceColor(serviceId);
  const label = serviceTitle ?? serviceId;

  if (compact) {
    return (
      <span
        className={`inline-flex items-center gap-1 ${className}`}
        title={label}
      >
        <span
          className="w-2 h-2 rounded-full flex-shrink-0"
          style={{ backgroundColor: cfg.dot }}
        />
        <span className={`text-[10px] font-mono ${cfg.text} truncate`}>
          {serviceId}
        </span>
      </span>
    );
  }

  return (
    <span
      className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium border ${cfg.bg} ${cfg.text} ${cfg.border} ${className}`}
    >
      <span
        className="w-1.5 h-1.5 rounded-full flex-shrink-0"
        style={{ backgroundColor: cfg.dot }}
      />
      {label}
    </span>
  );
}
