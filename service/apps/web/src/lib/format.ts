/** 숫자 표기 규칙 (README 14.6): 별점 소수 둘째 자리, 비율 소수 첫째 자리, 개수 천 단위 쉼표. */
const MINUS = "−";

export function fmtStar(v: number | null | undefined): string {
  return v == null ? "–" : v.toFixed(2);
}

export function fmtDiff(v: number | null | undefined): string {
  if (v == null) return "–";
  const r = Math.round(v * 100) / 100;
  if (r === 0) return "0.00";
  return (r > 0 ? "+" : MINUS) + Math.abs(r).toFixed(2);
}

export function fmtPct(v: number | null | undefined, digits = 1): string {
  return v == null ? "–" : `${(v * 100).toFixed(digits)}%`;
}

export function fmtCount(v: number | null | undefined): string {
  return v == null ? "–" : v.toLocaleString("ko-KR");
}

export function fmtPrice(v: number | null | undefined): string {
  return v == null ? "" : `${v.toLocaleString("ko-KR")}원`;
}

const KST = "Asia/Seoul";

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "–";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return new Intl.DateTimeFormat("ko-KR", {
    timeZone: KST,
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(d);
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "–";
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (m) return `${m[1]}.${m[2]}.${m[3]}`;
  return iso;
}

export function fmtDuration(sec: number | null | undefined): string {
  if (sec == null || sec <= 0) return "곧";
  if (sec < 60) return "1분 이내";
  const m = Math.round(sec / 60);
  return `약 ${m}분`;
}

/** 차이의 방향에 따라 문장을 만든다(README 14.4-2). */
export function diffSentence(diff: number | null | undefined): string {
  if (diff == null) return "사람 리뷰 기준 별점을 계산하지 못했어요.";
  const r = Math.round(diff * 100) / 100;
  if (r === 0) return "AI 추정 리뷰를 제외해도 별점이 거의 같아요.";
  return `AI 추정 리뷰를 제외하면 별점이 ${Math.abs(r).toFixed(2)}점 ${r < 0 ? "낮아져요" : "높아져요"}.`;
}
