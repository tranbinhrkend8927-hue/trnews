"""Rule-based financial safety validation for article draft shells."""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional


PROFIT_PROMISE_PHRASES = [
    "pasti untung",
    "dijamin profit",
    "keuntungan pasti",
    "guaranteed profit",
]
BUY_SELL_PHRASES = [
    "beli sekarang",
    "jual sekarang",
    "buy now",
    "sell now",
]
TAKE_PROFIT_STOP_LOSS_PHRASES = [
    "take profit",
    "stop loss",
    "TP di",
    "SL di",
]
KEY_FINANCIAL_TERMS = [
    "CPI",
    "NFP",
    "FOMC",
    "BI rate",
    "suku bunga BI",
    "USD/IDR",
    "USDIDR",
    "rupiah",
    "inflasi",
    "dolar AS",
    "Bank Indonesia",
    "The Fed",
]


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return str(value)


def article_text(article: Dict[str, Any]) -> str:
    return "\n".join(
        str(article.get(field) or "")
        for field in ("title", "summary", "body", "seo_title", "seo_description")
    )


def contains_blocked_phrase(text: str, phrases: Iterable[str]) -> List[str]:
    normalized = str(text or "").lower()
    matches = []
    for phrase in phrases:
        if phrase.lower() in normalized:
            matches.append(phrase)
    return matches


def has_key_financial_terms(text: str) -> bool:
    return bool(contains_blocked_phrase(text, KEY_FINANCIAL_TERMS))


def _json_has_content(value: Any) -> bool:
    if value in (None, "", [], {}):
        return False
    if isinstance(value, str):
        try:
            loaded = json.loads(value)
        except json.JSONDecodeError:
            return bool(value.strip())
        return _json_has_content(loaded)
    if isinstance(value, dict):
        if value.get("news_id"):
            return True
        source_news_ids = value.get("source_news_ids")
        if source_news_ids:
            return True
        for key in ("source_url", "url", "canonical_url"):
            if value.get(key):
                return True
        for key in ("source_urls", "urls", "canonical_urls"):
            urls = value.get(key)
            if isinstance(urls, (list, tuple)) and any(urls):
                return True
        source_trace = value.get("source_trace")
        if isinstance(source_trace, dict) and _json_has_content(source_trace):
            return True
        return any(
            _json_has_content(item)
            for item in value.values()
            if isinstance(item, (dict, list, tuple))
        )
    if isinstance(value, (list, tuple)):
        return any(_json_has_content(item) for item in value)
    return True


def has_sources(article: Dict[str, Any], article_sources: Optional[Iterable[Dict[str, Any]]] = None) -> bool:
    if article_sources and any(source for source in article_sources):
        return True
    return _json_has_content(article.get("sources_json"))


def _violation(violation_type: str, matches: Optional[List[str]] = None) -> Dict[str, Any]:
    payload = {"type": violation_type}
    if matches:
        payload["matches"] = matches
    return payload


def validate_financial_safety(
    article: Dict[str, Any],
    article_sources: Optional[Iterable[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    text = article_text(article)
    violations = []

    profit_matches = contains_blocked_phrase(text, PROFIT_PROMISE_PHRASES)
    if profit_matches:
        violations.append(_violation("profit_promise", profit_matches))

    buy_sell_matches = contains_blocked_phrase(text, BUY_SELL_PHRASES)
    if buy_sell_matches:
        violations.append(_violation("buy_sell_instruction", buy_sell_matches))

    tp_sl_matches = contains_blocked_phrase(text, TAKE_PROFIT_STOP_LOSS_PHRASES)
    if tp_sl_matches:
        violations.append(_violation("take_profit_stop_loss", tp_sl_matches))

    has_financial_terms = has_key_financial_terms(text)
    has_article_sources = has_sources(article, article_sources)
    if has_financial_terms and not has_article_sources:
        violations.append(_violation("missing_sources_for_financial_terms", contains_blocked_phrase(text, KEY_FINANCIAL_TERMS)))

    if not bool(article.get("risk_disclaimer_included", False)):
        violations.append(_violation("missing_risk_disclaimer"))

    fact_check_status = article.get("fact_check_status") or "pending"
    blocking_types = {"profit_promise", "buy_sell_instruction", "take_profit_stop_loss"}
    if any(item["type"] in blocking_types for item in violations):
        fact_check_status = "failed"
    elif any(item["type"] == "missing_sources_for_financial_terms" for item in violations):
        fact_check_status = "needs_sources"

    return json_safe(
        {
            "passed": not violations,
            "violations": violations,
            "fact_check_status": fact_check_status,
            "risk_disclaimer_required": not bool(article.get("risk_disclaimer_included", False)),
        }
    )


def apply_fact_check_status(article: Dict[str, Any], validation_result: Dict[str, Any]) -> Dict[str, Any]:
    updated = dict(article or {})
    updated["fact_check_status"] = validation_result.get("fact_check_status") or updated.get("fact_check_status") or "pending"
    if updated.get("status") == "published":
        updated["status"] = "pending_review"
    return json_safe(updated)
