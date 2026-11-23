"""생성 프롬프트 (MODEL_DEV.md 4.5.2).

사람 리뷰 하나를 '기준 리뷰(anchor)'로 주고, 같은 상품을 산 다른 구매자로서 새 리뷰를 쓰게 한다.
→ AI 리뷰의 상품·주제 분포가 사람 리뷰와 같아져서, 모델이 '주제' 차이로 구분하는 지름길을 막는다.
변화 요소(페르소나·말투·분량·휴머나이즈·참고 리뷰 수·모드)는 매 샘플 무작위로 뽑는다.
Claude 최신 모델은 temperature를 받지 않으므로(400) 다양성은 프롬프트 변화로 만든다.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

PROMPT_VERSION = "gen-v1"

PERSONAS = [
    "20대 대학생", "20대 사회초년생", "30대 직장인", "30대 육아 중인 부모", "40대 주부", "40대 회사원",
    "50대 자영업자", "50대 주부", "60대 은퇴자", "자취하는 1인 가구", "꼼꼼하게 비교해 보고 사는 소비자", "물건을 자주 사는 단골 구매자",
]
TONES = [
    "담백하고 짧게", "수다스럽게", "불만이 있으면 솔직하게", "꼼꼼하게 장단점을 따져서", "무심하게 핵심만", "친근한 말투로",
]
HUMANIZE = {
    "none": "",
    "natural": "실제 구매자가 쓴 것처럼 자연스럽게 써.",
    "casual": "실제 구매자처럼 편하게 써. 맞춤법·띄어쓰기를 가끔 틀려도 되고, ㅋㅋ, ㅠㅠ, ^^ 같은 표현을 써도 돼.",
}
HUMANIZE_WEIGHTS = {"none": 0.5, "natural": 0.25, "casual": 0.25}

SYSTEM = ("너는 온라인 쇼핑몰에서 실제로 상품을 구매한 소비자다. 요청한 리뷰 본문만 출력한다. "
          "인사말, 설명, 따옴표, 제목 표시, 마크다운은 쓰지 않는다.")


@dataclass
class GenSpec:
    mode: str                       # write: 같은 상품의 새 리뷰 / polish: 기준 리뷰를 다듬기(MODEL_DEV.md A3)
    star: int
    target_chars: int
    persona: str
    tone: str
    humanize: str
    anchor_id: str
    anchor_text: str
    anchor_group: str = ""          # 기준 리뷰의 분할 그룹 → 생성 샘플도 같은 그룹·분할에 둔다
    ref_ids: list[str] = field(default_factory=list)
    ref_texts: list[str] = field(default_factory=list)


def build_prompt(spec: GenSpec) -> str:
    if spec.mode == "polish":
        return (
            f"다음은 별점 {spec.star}점짜리 상품 리뷰야.\n\n{spec.anchor_text}\n\n"
            f"이 리뷰를 더 자연스럽고 읽기 좋게 다듬어서 다시 써 줘. 내용과 별점의 느낌은 유지하고, 분량은 약 {spec.target_chars}자로 맞춰. "
            f"{HUMANIZE[spec.humanize]}".strip()
        )
    lines = [
        "다음은 어떤 상품을 산 구매자가 남긴 리뷰야. 이 리뷰로 어떤 상품인지만 파악해.",
        f"\n[기준 리뷰]\n{spec.anchor_text}\n",
    ]
    if spec.ref_texts:
        lines.append("[다른 상품에 남겨진 리뷰들 — 실제 구매자들의 말투만 참고하고 내용·표현은 베끼지 마]")
        lines += [f"- {t}" for t in spec.ref_texts]
        lines.append("")
    lines += [
        f"너는 같은 상품을 산 다른 구매자({spec.persona})야. 이 상품에 별점 {spec.star}점을 주는 새 리뷰를 써.",
        f"말투: {spec.tone}. 분량: 약 {spec.target_chars}자.",
        "기준 리뷰의 문장이나 표현을 그대로 가져오지 마.",
    ]
    if HUMANIZE[spec.humanize]:
        lines.append(HUMANIZE[spec.humanize])
    return "\n".join(lines)


def pick(rng: random.Random, weights: dict[str, float]) -> str:
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]
