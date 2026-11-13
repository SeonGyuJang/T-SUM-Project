import type { Metadata } from "next";
import { PipelineDiagram } from "@/components/features/pipeline-diagram";
import { ButtonLink } from "@/components/ui/button";
import { site } from "@/lib/site";

export const metadata: Metadata = {
  title: "작동 원리",
  description: "리뷰 수집, AI 작성 판별, 사람 리뷰 기준 별점 재계산이 어떻게 이루어지는지 설명해요.",
};

const SIGNALS = [
  { t: "문장 패턴 분류기", d: "한국어 리뷰를 많이 읽은 언어 모델이 사람 리뷰와 AI 리뷰의 차이를 직접 배워요." },
  { t: "언어 모델의 반응", d: "다른 언어 모델이 이 글을 얼마나 ‘예상 가능하게’ 느끼는지 살펴봐요. AI 글은 지나치게 매끄러운 경향이 있어요." },
  { t: "한국어 글쓰기 습관", d: "띄어쓰기, ㅋㅋ·ㅠㅠ 같은 표현, 문장 길이의 들쭉날쭉함처럼 사람 글에 자주 보이는 특징을 봐요." },
  { t: "종합 판단", d: "여러 신호를 합쳐 AI가 썼을 확률을 계산하고, 확신이 낮으면 ‘판단 보류’로 둬요." },
];

export default function HowItWorksPage() {
  const m = site.modelMetrics;
  return (
    <article className="container-page section">
      <div className="mx-auto max-w-prose">
        <h1 className="text-h1">작동 원리</h1>
        <p className="mt-4 text-muted">
          {site.name}은 쿠팡 상품의 공개 리뷰를 모아 AI가 썼을 가능성을 추정하고, 사람이 쓴 리뷰만으로 별점을 다시 계산해요.
        </p>
      </div>

      <div className="mx-auto mt-12 max-w-4xl">
        <PipelineDiagram />
      </div>

      <div className="prose-ko mx-auto mt-4 max-w-prose">
        <h2>1. 리뷰 모으기</h2>
        <p>
          상품 페이지에서 전체 리뷰 수와 별점별 개수를 확인한 뒤, 별점마다 최신순으로 최대 100개를 모아요.
          사람이 브라우저로 보는 속도에 맞춰 천천히 모으고, 쿠팡이 접근을 막으면 바로 멈춰요. 작성자 닉네임은 저장하지 않아요.
        </p>

        <h2>2. AI 작성 판별</h2>
        <p>서로 다른 원리의 신호 네 가지를 함께 써요. 한 가지 신호만 쓰면 놓치는 경우를 서로 보완해요.</p>
        <ul>
          {SIGNALS.map((s) => (
            <li key={s.t}><strong className="text-text">{s.t}</strong> — {s.d}</li>
          ))}
        </ul>
        <p>판정은 세 가지예요. <strong className="text-human">사람 리뷰</strong>, <strong className="text-ai">AI 작성 추정</strong>, 그리고 확신이 낮거나 너무 짧은 <strong className="text-text">판단 보류</strong>예요.</p>

        <h2>3. 사람 리뷰 기준 별점 계산</h2>
        <p>
          별점마다 똑같이 100개씩 모으기 때문에 표본의 평균을 그대로 쓰면 안 돼요(그러면 평균이 항상 3점 근처가 돼요).
          대신 별점마다 사람 비율을 구하고, 그 별점의 실제 리뷰 수에 곱해 사람 리뷰 수를 추정한 뒤 평균을 다시 내요.
        </p>
        <details className="rounded-lg border border-border bg-subtle p-4">
          <summary className="cursor-pointer font-semibold text-text">수식으로 보기</summary>
          <div className="mt-3 space-y-2 font-mono text-caption text-text">
            <p>N_s = s점 리뷰 전체 개수, h_s·a_s = 표본의 사람·AI 추정 수</p>
            <p>r_s = h_s / (h_s + a_s)  (판단 보류 제외)</p>
            <p>전체 평균 = Σ s·N_s / Σ N_s</p>
            <p>사람 리뷰 기준 평균 = Σ s·N_s·r_s / Σ N_s·r_s</p>
            <p>추정 AI 비중 = 1 − Σ N_s·r_s / Σ N_s</p>
            <p>95% 신뢰구간 = 별점별 표본 복원추출 부트스트랩 1,000회</p>
          </div>
        </details>

        <h2>판별 모델 성능</h2>
        {m ? (
          <p>
            평가 기준일 {m.evaluatedAt} · 표본 {m.samples.toLocaleString("ko-KR")}개 · 사람 리뷰 오판율 1%에서 AI 리뷰 탐지율 {(m.tprAt1Fpr * 100).toFixed(1)}%
            {m.note ? ` · ${m.note}` : ""}
          </p>
        ) : (
          <p>판별 모델의 평가 결과는 평가가 끝나는 대로 이곳에 공개해요. 지표는 사람 리뷰를 AI로 잘못 판정하는 비율을 1%로 묶었을 때의 탐지율로 보고해요.</p>
        )}

        <h2>한계</h2>
        <ul>
          <li>AI 작성 여부는 확률적 추정이라 틀릴 수 있어요. 특정 작성자를 비난하는 근거로 쓰면 안 돼요.</li>
          <li>짧은 리뷰는 판별이 어려워 ‘판단 보류’로 분류돼요.</li>
          <li>사람이 쓴 체험단·대가성 리뷰는 걸러지지 않아요.</li>
          <li>새로운 AI 모델이 나오면 성능이 떨어질 수 있어 주기적으로 다시 학습해요.</li>
          <li>쿠팡 화면 구조가 바뀌면 일시적으로 분석이 안 될 수 있어요.</li>
        </ul>
      </div>
      <div className="mx-auto mt-12 max-w-prose">
        <ButtonLink href="/analyze" size="lg">상품 분석하기</ButtonLink>
      </div>
    </article>
  );
}
