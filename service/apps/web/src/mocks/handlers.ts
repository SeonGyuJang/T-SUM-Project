/** MSW 목업 핸들러 (README 14.8). 응답은 5.7 스키마와 같고 값은 local-backend의 현실적인 예시를 쓴다. */
import { http, HttpResponse, delay } from "msw";
import { apiBaseUrl } from "@/lib/site";
import { ApiError } from "@/lib/api/errors";
import { localCreate, localGet, localResolve } from "@/lib/api/local-backend";

function fail(e: unknown) {
  if (e instanceof ApiError) return HttpResponse.json({ error: { code: e.code, message: e.message } }, { status: e.status || 500 });
  return HttpResponse.json({ error: { code: "error", message: "문제가 생겨 요청을 처리하지 못했어요." } }, { status: 500 });
}

export const handlers = [
  http.post(`${apiBaseUrl}/api/resolve`, async ({ request }) => {
    await delay(500);
    const form = await request.formData();
    const url = form.get("url");
    const query = form.get("query");
    const image = form.get("image");
    try {
      if (typeof url === "string" && url) return HttpResponse.json(localResolve("mock", { url }));
      if (typeof query === "string" && query) return HttpResponse.json(localResolve("mock", { query }));
      if (image) return HttpResponse.json(localResolve("mock", { image: true }));
      throw new ApiError("invalid_input", "링크, 상품명, 이미지 중 하나만 입력해 주세요.", 422);
    } catch (e) {
      return fail(e);
    }
  }),
  http.post(`${apiBaseUrl}/api/analyses`, async ({ request }) => {
    await delay(200);
    const body = (await request.json()) as { product_id?: string };
    try {
      return HttpResponse.json(localCreate("mock", String(body.product_id ?? "")), { status: 202 });
    } catch (e) {
      return fail(e);
    }
  }),
  http.get(`${apiBaseUrl}/api/analyses/:id`, async ({ params }) => {
    await delay(100);
    try {
      return HttpResponse.json(localGet(String(params.id)));
    } catch (e) {
      return fail(e);
    }
  }),
];
