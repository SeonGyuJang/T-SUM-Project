"use client";

import "./globals.css";

export default function GlobalError({ reset }: { error: Error; reset: () => void }) {
  return (
    <html lang="ko">
      <body>
        <main className="container-page section text-center">
          <h1 className="text-h1">잠시 문제가 생겼어요</h1>
          <p className="mt-3 text-muted">페이지를 다시 불러와 주세요.</p>
          <button type="button" onClick={reset} className="mt-8 rounded bg-primary px-5 py-3 font-semibold text-primary-fg">다시 시도</button>
        </main>
      </body>
    </html>
  );
}
