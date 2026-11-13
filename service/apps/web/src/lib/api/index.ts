import { isDemoMode } from "@/lib/site";
import { httpApi } from "./http-client";
import { localApiFor } from "./local-backend";
import type { RealstarApi } from "./types";

/**
 * - 발표 모드: 브라우저 안 로컬 구현(네트워크 없음)
 * - 그 외: HTTP 클라이언트. 목업 모드에서는 MSW가 같은 요청을 가로챈다.
 */
export const api: RealstarApi = isDemoMode ? localApiFor("demo") : httpApi;
export * from "./schema";
export { ApiError } from "./errors";
