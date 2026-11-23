"""평가 지표 (순수 파이썬, 외부 의존성 없음).

label: 0 = 사람, 1 = AI / score: P(AI), 클수록 AI에 가까움.
"""
from collections import defaultdict


def auroc(labels, scores):
    """Mann-Whitney U 기반 AUROC (동점은 평균 순위로 처리)."""
    pairs = sorted(zip(scores, labels), key=lambda x: x[0])
    n_pos = sum(1 for _, y in pairs if y == 1)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    rank_sum_pos = 0.0
    i = 0
    while i < len(pairs):
        j = i
        while j + 1 < len(pairs) and pairs[j + 1][0] == pairs[i][0]:
            j += 1
        avg_rank = (i + j) / 2 + 1  # 1-based
        rank_sum_pos += avg_rank * sum(1 for k in range(i, j + 1) if pairs[k][1] == 1)
        i = j + 1
    return (rank_sum_pos - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)


def threshold_at_fpr(human_scores, target_fpr=0.01):
    """사람 글 중 target_fpr 이하만 AI로 오판되도록 하는 임계값.

    판정 규칙: score > threshold 이면 AI.
    """
    if not human_scores:
        raise ValueError("임계값을 정하려면 사람(label=0) 샘플이 필요합니다.")
    s = sorted(human_scores, reverse=True)
    k = int(target_fpr * len(s))
    k = min(k, len(s) - 1)
    return s[k]


def binary_report(labels, scores, threshold):
    tp = fp = tn = fn = 0
    for y, p in zip(labels, scores):
        pred = 1 if p > threshold else 0
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 0:
            tn += 1
        else:
            fn += 1
    tpr = tp / (tp + fn) if tp + fn else None
    fpr = fp / (fp + tn) if fp + tn else None
    precision = tp / (tp + fp) if tp + fp else None
    f1 = (2 * precision * tpr / (precision + tpr)) if precision and tpr else None
    return {
        "n": len(labels), "n_ai": tp + fn, "n_human": fp + tn,
        "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "tpr": tpr, "fpr": fpr, "precision": precision, "f1": f1,
        "auroc": auroc(labels, scores),
    }


def length_bucket(text):
    n = len(text)
    if n < 20:
        return "a) <20자"
    if n < 50:
        return "b) 20-49자"
    if n < 150:
        return "c) 50-149자"
    return "d) 150자+"


def breakdown(records, scores, threshold, key_fn):
    """그룹별 지표. AI 그룹(예: 생성 모델별)은 사람 샘플이 없으므로 TPR 위주로 보면 됩니다."""
    groups = defaultdict(lambda: ([], []))
    for r, s in zip(records, scores):
        g = key_fn(r)
        groups[g][0].append(r["label"])
        groups[g][1].append(s)
    return {g: binary_report(ls, ss, threshold) for g, (ls, ss) in sorted(groups.items())}
