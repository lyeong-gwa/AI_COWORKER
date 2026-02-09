import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

const markdownComponents: Components = {
  table: ({ children, ...props }) => (
    <div className="overflow-x-auto my-3">
      <table className="w-full border-collapse text-sm" {...props}>
        {children}
      </table>
    </div>
  ),
  thead: ({ children, ...props }) => (
    <thead className="bg-gray-700/80" {...props}>{children}</thead>
  ),
  th: ({ children, ...props }) => (
    <th className="text-left px-3 py-2 text-gray-200 font-semibold border-b border-gray-600 text-xs uppercase tracking-wider" {...props}>
      {children}
    </th>
  ),
  tr: ({ children, ...props }) => (
    <tr className="border-b border-gray-700/50 hover:bg-gray-700/30 transition-colors" {...props}>
      {children}
    </tr>
  ),
  td: ({ children, ...props }) => (
    <td className="px-3 py-2 text-gray-300" {...props}>
      {children}
    </td>
  ),
  blockquote: ({ children, ...props }) => (
    <blockquote className="border-l-4 border-blue-500/70 bg-gray-800/50 rounded-r-lg pl-4 pr-3 py-2 my-3 text-gray-300 italic" {...props}>
      {children}
    </blockquote>
  ),
  hr: (props) => (
    <hr className="my-4 border-0 h-px bg-gradient-to-r from-blue-500/50 via-gray-600 to-transparent" {...props} />
  ),
  code: ({ children, className, ...props }) => {
    const isBlock = className?.includes('language-');
    if (isBlock) {
      return (
        <code className={`${className} text-sm`} {...props}>
          {children}
        </code>
      );
    }
    return (
      <code className="bg-gray-700 text-blue-300 px-1.5 py-0.5 rounded text-xs font-mono" {...props}>
        {children}
      </code>
    );
  },
  pre: ({ children, ...props }) => (
    <pre className="bg-gray-900 border border-gray-700 rounded-lg overflow-x-auto p-4 my-3 text-sm" {...props}>
      {children}
    </pre>
  ),
  a: ({ children, href, ...props }) => (
    <a href={href} className="text-blue-400 hover:text-blue-300 underline underline-offset-2" target="_blank" rel="noopener noreferrer" {...props}>
      {children}
    </a>
  ),
  ul: ({ children, ...props }) => (
    <ul className="list-disc pl-5 my-2 space-y-1 marker:text-blue-400" {...props}>
      {children}
    </ul>
  ),
  ol: ({ children, ...props }) => (
    <ol className="list-decimal pl-5 my-2 space-y-1 marker:text-blue-400" {...props}>
      {children}
    </ol>
  ),
  li: ({ children, ...props }) => (
    <li className="text-gray-300 leading-relaxed" {...props}>
      {children}
    </li>
  ),
  h1: ({ children, ...props }) => (
    <h1 className="text-lg font-bold text-gray-100 mt-4 mb-2 pb-1 border-b border-gray-600" {...props}>
      {children}
    </h1>
  ),
  h2: ({ children, ...props }) => (
    <h2 className="text-base font-bold text-gray-100 mt-3 mb-2 pb-1 border-b border-gray-700" {...props}>
      {children}
    </h2>
  ),
  h3: ({ children, ...props }) => (
    <h3 className="text-sm font-bold text-gray-200 mt-3 mb-1" {...props}>
      {children}
    </h3>
  ),
  p: ({ children, ...props }) => (
    <p className="my-2 leading-relaxed" {...props}>
      {children}
    </p>
  ),
  strong: ({ children, ...props }) => (
    <strong className="text-gray-100 font-semibold" {...props}>
      {children}
    </strong>
  ),
  em: ({ children, ...props }) => (
    <em className="text-gray-300 italic" {...props}>
      {children}
    </em>
  ),
  del: ({ children, ...props }) => (
    <del className="text-gray-500 line-through" {...props}>
      {children}
    </del>
  ),
};

const variantClasses: Record<string, string> = {
  chat: 'text-sm leading-relaxed max-w-none text-gray-200',
  'chat-user': 'text-sm leading-relaxed max-w-none text-white',
  comment: 'text-sm leading-relaxed max-w-none text-gray-300',
  activity: 'text-xs leading-relaxed max-w-none text-gray-400',
};

interface StyledMarkdownProps {
  children: string;
  variant?: 'chat' | 'chat-user' | 'comment' | 'activity';
  className?: string;
}

export function StyledMarkdown({ children, variant = 'chat', className = '' }: StyledMarkdownProps) {
  return (
    <div className={`${variantClasses[variant] || variantClasses.chat} ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
        {children}
      </ReactMarkdown>
    </div>
  );
}
