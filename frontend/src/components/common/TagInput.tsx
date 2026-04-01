import { useState, useRef, useEffect, useCallback } from 'react';

// ─────────────────────────────────────────────────────────────────────────────
// TagInput - 자동완성 지원 태그 입력 컴포넌트
// value/onChange는 쉼표 구분 문자열 형식으로 기존 코드와 호환
// ─────────────────────────────────────────────────────────────────────────────

interface TagInputProps {
  value: string;
  onChange: (value: string) => void;
  availableTags: string[];
  placeholder?: string;
  className?: string;
}

export function TagInput({
  value,
  onChange,
  availableTags,
  placeholder = '태그 입력...',
  className = '',
}: TagInputProps) {
  // 쉼표 구분 문자열 → 태그 배열
  const currentTags = value
    ? value
        .split(',')
        .map((t) => t.trim())
        .filter(Boolean)
    : [];

  const [inputValue, setInputValue] = useState('');
  const [showDropdown, setShowDropdown] = useState(false);
  const [highlightedIndex, setHighlightedIndex] = useState(-1);
  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  // 입력 중인 텍스트로 필터링된 자동완성 후보
  const suggestions = inputValue.trim()
    ? availableTags.filter(
        (tag) =>
          tag.toLowerCase().includes(inputValue.toLowerCase()) &&
          !currentTags.includes(tag)
      )
    : availableTags.filter((tag) => !currentTags.includes(tag));

  // 태그 추가
  const addTag = useCallback(
    (tag: string) => {
      const trimmed = tag.trim();
      if (!trimmed || currentTags.includes(trimmed)) return;
      const newTags = [...currentTags, trimmed];
      onChange(newTags.join(', '));
      setInputValue('');
      setShowDropdown(false);
      setHighlightedIndex(-1);
    },
    [currentTags, onChange]
  );

  // 태그 제거
  const removeTag = useCallback(
    (tagToRemove: string) => {
      const newTags = currentTags.filter((t) => t !== tagToRemove);
      onChange(newTags.join(', '));
    },
    [currentTags, onChange]
  );

  // 외부 클릭 시 드롭다운 닫기
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
        setHighlightedIndex(-1);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' || e.key === ',') {
      e.preventDefault();
      if (highlightedIndex >= 0 && highlightedIndex < suggestions.length) {
        addTag(suggestions[highlightedIndex]);
      } else if (inputValue.trim()) {
        addTag(inputValue);
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightedIndex((prev) =>
        prev < suggestions.length - 1 ? prev + 1 : prev
      );
      return;
    }

    if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightedIndex((prev) => (prev > 0 ? prev - 1 : -1));
      return;
    }

    if (e.key === 'Escape') {
      setShowDropdown(false);
      setHighlightedIndex(-1);
      return;
    }

    if (e.key === 'Backspace' && inputValue === '' && currentTags.length > 0) {
      removeTag(currentTags[currentTags.length - 1]);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setInputValue(e.target.value);
    setShowDropdown(true);
    setHighlightedIndex(-1);
  };

  const handleInputFocus = () => {
    setShowDropdown(true);
  };

  // 매칭 텍스트 하이라이트
  const highlightMatch = (tag: string, query: string) => {
    if (!query.trim()) return <span>{tag}</span>;
    const idx = tag.toLowerCase().indexOf(query.toLowerCase());
    if (idx === -1) return <span>{tag}</span>;
    return (
      <span>
        {tag.slice(0, idx)}
        <span className="text-blue-300 font-semibold">{tag.slice(idx, idx + query.length)}</span>
        {tag.slice(idx + query.length)}
      </span>
    );
  };

  const showList = showDropdown && suggestions.length > 0;

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      {/* 외곽 컨테이너: 기존 input과 동일한 스타일 */}
      <div
        className="flex flex-wrap gap-1.5 items-center w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 cursor-text focus-within:ring-1 focus-within:ring-blue-500 min-h-[42px]"
        onClick={() => inputRef.current?.focus()}
      >
        {/* 현재 태그 칩 */}
        {currentTags.map((tag) => (
          <span
            key={tag}
            className="flex items-center gap-1 bg-blue-600/30 text-blue-300 border border-blue-600/50 rounded px-2 py-0.5 text-xs"
          >
            {tag}
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                removeTag(tag);
              }}
              className="text-blue-400 hover:text-white leading-none ml-0.5"
              aria-label={`${tag} 태그 제거`}
            >
              &times;
            </button>
          </span>
        ))}

        {/* 입력 필드 */}
        <input
          ref={inputRef}
          type="text"
          value={inputValue}
          onChange={handleInputChange}
          onKeyDown={handleKeyDown}
          onFocus={handleInputFocus}
          placeholder={currentTags.length === 0 ? placeholder : ''}
          className="flex-1 min-w-[80px] bg-transparent text-gray-200 placeholder-gray-500 focus:outline-none text-sm"
        />
      </div>

      {/* 자동완성 드롭다운 */}
      {showList && (
        <ul className="absolute z-50 left-0 right-0 top-full mt-1 bg-gray-800 border border-gray-600 rounded-lg shadow-lg max-h-48 overflow-y-auto">
          {suggestions.slice(0, 12).map((tag, idx) => (
            <li
              key={tag}
              onMouseDown={(e) => {
                // mousedown 이후 blur가 먼저 발생하므로 preventDefault로 막기
                e.preventDefault();
                addTag(tag);
              }}
              onMouseEnter={() => setHighlightedIndex(idx)}
              className={`px-3 py-2 cursor-pointer text-sm transition-colors ${
                idx === highlightedIndex
                  ? 'bg-gray-700 text-white'
                  : 'text-gray-300 hover:bg-gray-700 hover:text-white'
              }`}
            >
              {highlightMatch(tag, inputValue)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
