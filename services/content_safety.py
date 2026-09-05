"""Hard content boundaries shared by title, planning, and script workers."""

from __future__ import annotations

import json
import re
from typing import Any


# Finance categories have been retired.  These terms are intentionally checked
# before any model call, not merely reported by a downstream QA gate.
FORBIDDEN_FINANCE_TERMS = (
    "국민연금", "퇴직연금", "연금수령", "연금계산", "노후자금",
    "금융", "재테크", "주식", "채권", "펀드", "etf", "코스피", "나스닥",
    "비트코인", "가상화폐", "암호화폐", "투자", "금리", "환율",
    "대출", "부동산투자", "은행예금", "통장", "가계부", "자동이체",
    "pension", "retirement fund", "financial", "finance", "investment", "stock",
    "government bond", "corporate bond", "bond market", "fund", "bitcoin", "cryptocurrency", "interest rate", "exchange rate",
    "loan", "bankbook", "年金", "老後資金", "金融", "投資", "株式", "債券",
    "ビットコイン", "仮想通貨", "金利", "為替", "ローン",
)

AMBIGUOUS_FINANCE_TERMS = {
    "매수": ("주식", "채권", "코인", "증권", "거래", "주문", "가격", "수익", "손실", "보유", "매도"),
    "매도": ("주식", "채권", "코인", "증권", "거래", "주문", "가격", "수익", "손실", "보유", "매수"),
}


def _as_text(value: Any) -> str:
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return str(value or "")


def finance_content_matches(*values: Any) -> list[str]:
    """Return unique forbidden finance terms found in arbitrary job content."""
    text = _as_text(values).casefold()
    compact = re.sub(r"[\s\W_]+", "", text)
    matches = []
    for term in FORBIDDEN_FINANCE_TERMS:
        normalized = term.casefold()
        # Latin abbreviations/words must remain whole words.  Compact matching
        # made harmless prompt prose such as "gentle tilt from" look like
        # "ETF" after spaces were removed.
        if re.fullmatch(r"[a-z ]+", normalized):
            found = bool(re.search(rf"(?<![a-z]){re.escape(normalized)}(?![a-z])", text))
        else:
            found = normalized in text or re.sub(r"[\s\W_]+", "", normalized) in compact
        if found:
            matches.append(term)
    for term, context_terms in AMBIGUOUS_FINANCE_TERMS.items():
        for occurrence in re.finditer(term, text):
            window = text[max(0, occurrence.start() - 80):occurrence.end() + 80]
            if any(context in window for context in context_terms):
                matches.append(term)
                break
    return matches


def reject_finance_content(context: str, *values: Any) -> None:
    matches = finance_content_matches(*values)
    if matches:
        raise ValueError(
            f"finance/pension content is prohibited before generation in {context}: "
            + ", ".join(matches[:8])
        )
