import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // 발표 모드 빌드는 별도 폴더에 둔다(같은 폴더에서 일반·발표 빌드를 함께 돌리기 위함)
  distDir: process.env.NEXT_DIST_DIR || ".next",
  reactStrictMode: true,
  poweredByHeader: false,
  images: {
    // 상품 썸네일은 분석 결과 화면에서만 표시한다(README 14.5)
    remotePatterns: [{ protocol: "https", hostname: "**.coupangcdn.com" }],
  },
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
