/**
 * MarkdownView — react-markdown wrapper with Obsidian `[[wikilink]]` rendering.
 *
 * 전략:
 *   1) react-markdown + remark-gfm 로 본문을 HTML 트리로 렌더
 *   2) 모든 text 노드를 가로채 `\[\[([^\]]+)\]\]` 매칭 → WikiLinkChip 으로 치환
 *   3) inline-code/fenced-code 안의 텍스트는 chip 변환 제외 (react-markdown 이 code 컴포넌트로 분기)
 *
 * 다크 테마 친화 색상.
 */
import { useMemo, type ReactNode } from 'react';
import ReactMarkdown, { type Components } from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { WikiLinkChip } from './WikiLinkChip';

const WIKILINK_RE = /\[\[([^\]]+)\]\]/g;

interface MarkdownViewProps {
  content: string;
  /** chip 클릭 시 호출 — id 전달. 없으면 router navigate 사용 */
  onNavigate?: (id: string) => void;
  className?: string;
}

/**
 * 텍스트 문자열에서 `[[...]]` 패턴을 찾아 React 노드 배열로 분리.
 * 매칭 없으면 원본 문자열 그대로 반환.
 */
function splitWikiLinks(
  text: string,
  onNavigate?: (id: string) => void,
  keyPrefix = '',
): ReactNode[] | string {
  if (!text || !text.includes('[[')) return text;
  WIKILINK_RE.lastIndex = 0;
  const parts: ReactNode[] = [];
  let lastIdx = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = WIKILINK_RE.exec(text)) !== null) {
    if (m.index > lastIdx) {
      parts.push(text.slice(lastIdx, m.index));
    }
    parts.push(
      <WikiLinkChip
        key={`${keyPrefix}wl-${i}-${m.index}`}
        target={m[1]}
        onNavigate={onNavigate}
      />,
    );
    lastIdx = m.index + m[0].length;
    i += 1;
  }
  if (lastIdx === 0) return text;
  if (lastIdx < text.length) parts.push(text.slice(lastIdx));
  return parts;
}

/**
 * 자식 노드들을 재귀적으로 순회하며, 문자열 children 에서 `[[...]]` 변환.
 * React 요소(이미 변환된 노드, code, link 등)는 그대로 둠.
 */
function transformChildren(
  children: ReactNode,
  onNavigate: ((id: string) => void) | undefined,
  keyPrefix: string,
): ReactNode {
  if (children == null || typeof children === 'boolean') return children;
  if (typeof children === 'string') {
    const r = splitWikiLinks(children, onNavigate, keyPrefix);
    return r;
  }
  if (typeof children === 'number') return children;
  if (Array.isArray(children)) {
    return children.map((c, idx) => {
      if (typeof c === 'string') {
        const r = splitWikiLinks(c, onNavigate, `${keyPrefix}${idx}-`);
        if (typeof r === 'string') return r;
        // 배열 반환의 경우 fragment로 감싸 key 보전
        return <span key={`${keyPrefix}frag-${idx}`}>{r}</span>;
      }
      return c;
    });
  }
  return children;
}

export function MarkdownView({ content, onNavigate, className = '' }: MarkdownViewProps) {
  const components = useMemo<Components>(() => {
    return {
      // 헤딩 — 옵시디언 톤
      h1: ({ children }) => (
        <h1 className="text-2xl font-semibold text-slate-50 mt-2 mb-4 pb-2 border-b border-slate-800 leading-tight">
          {transformChildren(children, onNavigate, 'h1-')}
        </h1>
      ),
      h2: ({ children }) => (
        <h2 className="text-xl font-semibold text-slate-100 mt-7 mb-3 leading-snug">
          {transformChildren(children, onNavigate, 'h2-')}
        </h2>
      ),
      h3: ({ children }) => (
        <h3 className="text-base font-semibold text-slate-100 mt-5 mb-2">
          {transformChildren(children, onNavigate, 'h3-')}
        </h3>
      ),
      h4: ({ children }) => (
        <h4 className="text-sm font-semibold text-slate-200 mt-4 mb-1.5 uppercase tracking-wide">
          {transformChildren(children, onNavigate, 'h4-')}
        </h4>
      ),
      h5: ({ children }) => (
        <h5 className="text-sm font-semibold text-slate-300 mt-3 mb-1">
          {transformChildren(children, onNavigate, 'h5-')}
        </h5>
      ),
      h6: ({ children }) => (
        <h6 className="text-xs font-semibold text-slate-400 mt-3 mb-1 uppercase tracking-wider">
          {transformChildren(children, onNavigate, 'h6-')}
        </h6>
      ),

      // 단락 / 인라인
      p: ({ children }) => (
        <p className="text-[14px] text-slate-200 leading-[1.75] my-3">
          {transformChildren(children, onNavigate, 'p-')}
        </p>
      ),
      strong: ({ children }) => (
        <strong className="font-semibold text-slate-50">
          {transformChildren(children, onNavigate, 's-')}
        </strong>
      ),
      em: ({ children }) => (
        <em className="italic text-slate-100">
          {transformChildren(children, onNavigate, 'em-')}
        </em>
      ),
      del: ({ children }) => (
        <del className="line-through text-slate-500">
          {transformChildren(children, onNavigate, 'del-')}
        </del>
      ),

      // 링크 (일반 외부)
      a: ({ children, href }) => (
        <a
          href={href}
          target={href?.startsWith('http') ? '_blank' : undefined}
          rel={href?.startsWith('http') ? 'noopener noreferrer' : undefined}
          className="text-sky-400 hover:text-sky-300 underline decoration-sky-700/50 underline-offset-2 hover:decoration-sky-400"
        >
          {transformChildren(children, onNavigate, 'a-')}
        </a>
      ),

      // 리스트
      ul: ({ children }) => (
        <ul className="list-disc pl-6 my-3 space-y-1 marker:text-slate-600 text-[14px] text-slate-200 leading-[1.7]">
          {children}
        </ul>
      ),
      ol: ({ children }) => (
        <ol className="list-decimal pl-6 my-3 space-y-1 marker:text-slate-500 text-[14px] text-slate-200 leading-[1.7]">
          {children}
        </ol>
      ),
      li: ({ children }) => (
        <li className="pl-1">{transformChildren(children, onNavigate, 'li-')}</li>
      ),

      // 인용
      blockquote: ({ children }) => (
        <blockquote className="border-l-4 border-cyan-600/50 bg-cyan-500/5 pl-4 pr-3 py-2 my-4 text-slate-300 italic rounded-r">
          {transformChildren(children, onNavigate, 'bq-')}
        </blockquote>
      ),

      // 코드 (inline vs block)
      code: ({ className: cls, children, ...rest }) => {
        const isInline = !(cls && cls.startsWith('language-'));
        if (isInline) {
          return (
            <code className="px-1.5 py-0.5 mx-0.5 rounded bg-slate-800/80 border border-slate-700/60 text-[12.5px] text-amber-200 font-mono">
              {children}
            </code>
          );
        }
        return (
          <code className={`${cls ?? ''} text-[12.5px]`} {...rest}>
            {children}
          </code>
        );
      },
      pre: ({ children }) => (
        <pre className="my-4 p-4 rounded-lg bg-slate-950/80 border border-slate-800 overflow-x-auto text-[12.5px] text-slate-200 font-mono leading-relaxed">
          {children}
        </pre>
      ),

      // 표 (GFM)
      table: ({ children }) => (
        <div className="my-4 overflow-x-auto rounded-lg border border-slate-800">
          <table className="w-full text-[13px] text-slate-200 border-collapse">{children}</table>
        </div>
      ),
      thead: ({ children }) => (
        <thead className="bg-slate-900/80 text-slate-100">{children}</thead>
      ),
      tbody: ({ children }) => <tbody className="divide-y divide-slate-800">{children}</tbody>,
      tr: ({ children }) => <tr className="hover:bg-slate-900/40">{children}</tr>,
      th: ({ children, style }) => (
        <th
          style={style}
          className="px-3 py-2 text-left font-semibold border-b border-slate-700 whitespace-nowrap"
        >
          {transformChildren(children, onNavigate, 'th-')}
        </th>
      ),
      td: ({ children, style }) => (
        <td style={style} className="px-3 py-2 border-b border-slate-900 align-top">
          {transformChildren(children, onNavigate, 'td-')}
        </td>
      ),

      // 구분선
      hr: () => <hr className="my-6 border-slate-800" />,

      // 이미지
      img: ({ src, alt }) => (
        <img
          src={src as string | undefined}
          alt={alt as string | undefined}
          className="my-3 max-w-full rounded-lg border border-slate-800"
        />
      ),
    };
  }, [onNavigate]);

  return (
    <div className={`markdown-body ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    </div>
  );
}
