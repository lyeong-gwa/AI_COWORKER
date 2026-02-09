import { useEffect } from 'react';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  useEffect(() => {
    document.title = '페이지를 찾을 수 없습니다 | AI 업무도우미';
  }, []);

  return (
    <div className="flex flex-col items-center justify-center h-full text-center p-8">
      <div className="w-24 h-24 rounded-full bg-gray-800 flex items-center justify-center mb-6">
        <span className="text-5xl">🔍</span>
      </div>
      <h1 className="text-4xl font-bold text-white mb-2">404</h1>
      <h2 className="text-xl text-gray-300 mb-4">페이지를 찾을 수 없습니다</h2>
      <p className="text-gray-500 mb-8 max-w-md">
        요청하신 페이지가 존재하지 않거나 이동되었을 수 있습니다.
      </p>
      <Link
        to="/"
        className="px-6 py-3 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
      >
        홈으로 돌아가기
      </Link>
    </div>
  );
}
