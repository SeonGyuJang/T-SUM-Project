export class ApiError extends Error {
  constructor(
    public code: string,
    message: string,
    public status = 0,
  ) {
    super(message);
  }
}

export const NETWORK_ERROR_MESSAGE = "서버에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.";
export const DEMO_ONLY_MESSAGE = "발표 모드에서는 예시 상품만 분석할 수 있어요.";
