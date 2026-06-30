"""Dry-run comparison helpers for template and LLM article draft candidates."""

import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Tuple

from draft_quality import evaluate_draft_quality
from safety_validation import validate_financial_safety


BLOCKING_SAFETY_TYPES = {"profit_promise", "buy_sell_instruction", "take_profit_stop_loss"}
ALLOWED_RECOMMENDATIONS = {"template", "llm", "neither", "needs_editor_review"}
INDONESIAN_TERMS = ["rupiah", "dolar as", "sumber", "risiko", "artikel"]


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    return str(value)


def _issue(candidate: str, issue_type: str, message: str, *, severity: str = "warning", **extra: Any) -> Dict[str, Any]:
    payload = {"candidate": candidate, "type": issue_type, "severity": severity, "message": message}
    payload.update(extra)
    return json_safe(payload)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _candidate_text(candidate: Dict[str, Any]) -> str:
    return "\n".join(_text(candidate.get(field)) for field in ("title", "summary", "body", "seo_title", "seo_description"))


def _has_section(body: str, name: str) -> bool:
    target = name.lower()
    return any(line.strip().lower().startswith(target) for line in str(body or "").splitlines())


def _sources_json(candidate: Dict[str, Any]) -> Dict[str, Any]:
    value = candidate.get("sources_json")
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except json.JSONDecodeError:
            return {}
    return value if isinstance(value, dict) else {}


def _source_index(source_bundle: Dict[str, Any]) -> Dict[str, set]:
    sources = (source_bundle or {}).get("sources") or []
    ids = set()
    urls = set()
    titles = set()
    for source in sources:
        if source.get("news_id") is not None:
            ids.add(str(source.get("news_id")))
        for key in ("url", "canonical_url", "source_url"):
            if source.get(key):
                urls.add(str(source.get(key)).strip())
        if source.get("title"):
            titles.add(str(source.get("title")).strip().lower())
    return {"ids": ids, "urls": urls, "titles": titles}


def _body_urls(candidate: Dict[str, Any]) -> List[str]:
    text = _candidate_text(candidate)
    return sorted(set(re.findall(r"https?://[^\s)>\]]+", text)))


def validate_candidate_sources(candidate: Dict[str, Any], source_bundle: Dict[str, Any]) -> Dict[str, Any]:
    candidate = candidate or {}
    source_bundle = source_bundle or {}
    blocking_issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    sources = source_bundle.get("sources") or []
    index = _source_index(source_bundle)

    if not sources:
        blocking_issues.append(_issue("candidate", "missing_source_bundle_sources", "source_bundle.sources is empty.", severity="error"))

    sources_json = _sources_json(candidate)
    if not sources_json:
        warnings.append(_issue("candidate", "missing_sources_json", "Candidate does not include sources_json."))
    else:
        expected_ids = [str(item) for item in (source_bundle.get("source_news_ids") or [])]
        candidate_ids = [str(item) for item in (sources_json.get("source_news_ids") or [])]
        if expected_ids and candidate_ids != expected_ids:
            warnings.append(
                _issue(
                    "candidate",
                    "sources_json_source_ids_mismatch",
                    "Candidate sources_json does not preserve source_news_ids exactly.",
                    expected=expected_ids,
                    actual=candidate_ids,
                )
            )
        if sources and not sources_json.get("sources"):
            warnings.append(_issue("candidate", "sources_json_missing_sources", "Candidate sources_json does not preserve source details."))

    sources_used = candidate.get("sources_used", [])
    if not isinstance(sources_used, list):
        blocking_issues.append(_issue("candidate", "sources_used_not_array", "sources_used must be an array.", severity="error"))
        sources_used = []
    if not sources_used and _has_section(candidate.get("body"), "Sumber"):
        warnings.append(_issue("candidate", "sumber_without_sources_used", "Body has Sumber section but sources_used is empty."))

    for used in sources_used:
        if not isinstance(used, dict):
            warnings.append(_issue("candidate", "invalid_sources_used_item", "sources_used item is not an object.", value=used))
            continue
        used_id = used.get("news_id") or used.get("source_news_id") or used.get("id")
        used_url = used.get("url") or used.get("canonical_url") or used.get("source_url")
        used_title = used.get("title") or used.get("source_title") or used.get("cited_claim")
        matched = False
        if used_id is not None and str(used_id) in index["ids"]:
            matched = True
        if used_url:
            if str(used_url).strip() not in index["urls"]:
                blocking_issues.append(
                    _issue(
                        "candidate",
                        "unknown_source_url",
                        "Candidate references a URL that is not in source_bundle.",
                        severity="error",
                        url=used_url,
                    )
                )
            else:
                matched = True
        if used_title and str(used_title).strip().lower() in index["titles"]:
            matched = True
        if used_id is not None and str(used_id) not in index["ids"]:
            blocking_issues.append(
                _issue(
                    "candidate",
                    "unknown_source_news_id",
                    "Candidate references a source news ID that is not in source_bundle.",
                    severity="error",
                    news_id=used_id,
                )
            )
        elif used_title and not matched:
            warnings.append(
                _issue(
                    "candidate",
                    "unknown_source_title",
                    "Candidate references a source title that does not match source_bundle.",
                    title=used_title,
                )
            )

    for url in _body_urls(candidate):
        if url not in index["urls"]:
            blocking_issues.append(
                _issue(
                    "candidate",
                    "unknown_body_url",
                    "Candidate body references a URL that is not in source_bundle.",
                    severity="error",
                    url=url,
                )
            )

    return json_safe(
        {
            "passed": not blocking_issues,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "metadata": {
                "source_count": len(sources),
                "sources_used_count": len(sources_used),
                "body_url_count": len(_body_urls(candidate)),
            },
        }
    )


def _source_text(source_bundle: Dict[str, Any]) -> str:
    return "\n".join(
        " ".join(str(source.get(field) or "") for field in ("title", "summary", "content", "url", "canonical_url", "source_url", "published_at"))
        for source in (source_bundle or {}).get("sources", []) or []
    )


def _financial_number_matches(text: str) -> List[Tuple[str, str, str]]:
    patterns = [
        ("percent", r"\b\d+(?:[.,]\d+)?\s*%"),
        ("usd_idr_level", r"\b(?:USD/IDR|USDIDR)\b.{0,30}\b\d[\d.,]{2,}\b"),
        ("rupiah_level", r"\b(?:Rp|IDR)\s?\d[\d.,]{2,}\b"),
        ("rate_context", r"\b(?:BI rate|suku bunga|Fed rate|CPI|NFP|FOMC)\b.{0,40}\b\d+(?:[.,]\d+)?\b"),
    ]
    matches = []
    for match_type, pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = " ".join(match.group(0).split())
            if re.fullmatch(r"20\d{2}", value):
                continue
            matches.append((match_type, value, match.group(0)))
    return matches


def detect_unsupported_financial_numbers(candidate: Dict[str, Any], source_bundle: Dict[str, Any]) -> Dict[str, Any]:
    candidate = candidate or {}
    source_bundle = source_bundle or {}
    candidate_text = _candidate_text(candidate)
    sources_text = _source_text(source_bundle)
    blocking_issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []

    for match_type, value, raw in _financial_number_matches(candidate_text):
        if value and value in sources_text:
            continue
        if raw and raw in sources_text:
            continue
        blocking_issues.append(
            _issue(
                "candidate",
                "unsupported_financial_number",
                "Candidate contains a financial number that is not present in source_bundle.",
                severity="error",
                match_type=match_type,
                value=value,
            )
        )

    return json_safe(
        {
            "passed": not blocking_issues,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "metadata": {"matches_checked": len(_financial_number_matches(candidate_text))},
        }
    )


def _structure_check(candidate: Dict[str, Any], candidate_name: str) -> Dict[str, Any]:
    blocking_issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    body = _text(candidate.get("body"))
    for field in ("title", "summary", "body"):
        if not _text(candidate.get(field)):
            blocking_issues.append(_issue(candidate_name, f"missing_{field}", f"{field} is required.", severity="error"))
    if not _has_section(body, "Sumber"):
        blocking_issues.append(_issue(candidate_name, "missing_sumber_section", "Body must include a Sumber section.", severity="error"))
    if not _has_section(body, "Catatan risiko") and "risiko" not in body.lower():
        blocking_issues.append(_issue(candidate_name, "missing_risk_section", "Body must include a Catatan risiko section.", severity="error"))
    if "faq" not in body.lower() and not candidate.get("faq"):
        warnings.append(_issue(candidate_name, "missing_faq", "FAQ section is missing."))
    if len(body) < 500:
        warnings.append(_issue(candidate_name, "body_too_short", "Body is short for editor review."))
    return json_safe({"blocking_issues": blocking_issues, "warnings": warnings})


def _seo_check(candidate: Dict[str, Any], candidate_name: str) -> Dict[str, Any]:
    warnings = []
    for field in ("slug", "seo_title", "seo_description"):
        if not _text(candidate.get(field)):
            warnings.append(_issue(candidate_name, f"missing_{field}", f"{field} is missing."))
    title_length = len(_text(candidate.get("title")))
    if title_length and not 20 <= title_length <= 120:
        warnings.append(_issue(candidate_name, "title_length_outside_range", "Title length should be between 20 and 120 characters."))
    return json_safe({"warnings": warnings})


def _readability_check(candidate: Dict[str, Any], candidate_name: str) -> Dict[str, Any]:
    warnings = []
    text = _candidate_text(candidate).lower()
    present_terms = [term for term in INDONESIAN_TERMS if term in text]
    english_terms = re.findall(r"\b(?:the|market|profit|buy|sell|trading|investment|guarantee)\b", text, flags=re.IGNORECASE)
    if len(present_terms) < 3:
        warnings.append(_issue(candidate_name, "weak_indonesian_markers", "Candidate has few Bahasa Indonesia market/readability markers."))
    if len(english_terms) > 8:
        warnings.append(_issue(candidate_name, "too_many_english_terms", "Candidate appears to contain too many English terms."))
    return json_safe({"warnings": warnings, "metadata": {"indonesian_terms_found": present_terms, "english_term_count": len(english_terms)}})


def _risk_check(candidate: Dict[str, Any], candidate_name: str) -> Dict[str, Any]:
    blocking_issues = []
    if not bool(candidate.get("risk_disclaimer_included", False)):
        blocking_issues.append(_issue(candidate_name, "missing_risk_disclaimer_flag", "risk_disclaimer_included must be true.", severity="error"))
    text = _candidate_text(candidate).lower()
    if "risiko" not in text:
        blocking_issues.append(_issue(candidate_name, "missing_risk_disclaimer_text", "Risk disclaimer text is missing.", severity="error"))
    return json_safe({"blocking_issues": blocking_issues, "warnings": []})


def _has_safety_blocker(safety_result: Dict[str, Any]) -> bool:
    if safety_result.get("passed") is False:
        return True
    if safety_result.get("fact_check_status") == "failed":
        return True
    return any(item.get("type") in BLOCKING_SAFETY_TYPES for item in (safety_result.get("violations") or []))


def _candidate_assessment(
    name: str,
    candidate: Dict[str, Any],
    source_bundle: Dict[str, Any],
    safety_result: Optional[Dict[str, Any]],
    quality_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    candidate = candidate or {}
    safety_result = safety_result or validate_financial_safety(candidate)
    quality_result = quality_result or evaluate_draft_quality(candidate, source_bundle=source_bundle, safety_result=safety_result)
    source_result = validate_candidate_sources(candidate, source_bundle)
    number_result = detect_unsupported_financial_numbers(candidate, source_bundle)
    structure_result = _structure_check(candidate, name)
    seo_result = _seo_check(candidate, name)
    readability_result = _readability_check(candidate, name)
    risk_result = _risk_check(candidate, name)

    blocking_issues: List[Dict[str, Any]] = []
    warnings: List[Dict[str, Any]] = []
    if _has_safety_blocker(safety_result):
        blocking_issues.append(_issue(name, "safety_failed", "Safety validation has blocking violations.", severity="error"))
    if quality_result.get("level") == "blocked" or quality_result.get("blocking_issues"):
        blocking_issues.append(_issue(name, "quality_blocked", "Quality gate has blocking issues.", severity="error"))
    for result in (source_result, number_result, structure_result, risk_result):
        blocking_issues.extend([{**issue, "candidate": name} for issue in result.get("blocking_issues", [])])
        warnings.extend([{**warning, "candidate": name} for warning in result.get("warnings", [])])
    for result in (seo_result, readability_result):
        warnings.extend([{**warning, "candidate": name} for warning in result.get("warnings", [])])

    score = int(quality_result.get("score", 0) or 0)
    score -= 20 * len(blocking_issues)
    score -= 3 * len(warnings)
    score = max(0, min(100, score))
    return json_safe(
        {
            "candidate": name,
            "score": score,
            "blocked": bool(blocking_issues),
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "safety_result": safety_result,
            "quality_result": quality_result,
            "source_result": source_result,
            "number_result": number_result,
            "structure_result": structure_result,
            "seo_result": seo_result,
            "readability_result": readability_result,
            "risk_result": risk_result,
        }
    )


def _choose_recommendation(template: Dict[str, Any], llm: Dict[str, Any]) -> Tuple[str, Optional[str], List[Dict[str, Any]]]:
    reasons = []
    if template["blocked"] and llm["blocked"]:
        return "neither", None, [_issue("comparison", "both_blocked", "Both candidates have blocking issues.")]
    if not template["blocked"] and llm["blocked"]:
        return "template", "template", [_issue("comparison", "llm_blocked", "LLM candidate has blocking issues.")]
    if template["blocked"] and not llm["blocked"]:
        return "llm", "llm", [_issue("comparison", "template_blocked", "Template candidate has blocking issues.")]

    diff = int(template["score"]) - int(llm["score"])
    llm_source_problem = any(issue.get("type", "").startswith("unknown_source") for issue in llm.get("blocking_issues", [])) or any(
        warning.get("type", "").startswith("unknown_source") or warning.get("type") == "sources_json_source_ids_mismatch"
        for warning in llm.get("warnings", [])
    )
    if llm_source_problem and llm["score"] > template["score"]:
        return "needs_editor_review", None, [_issue("comparison", "llm_source_grounding_requires_editor", "LLM source grounding issue prevents direct LLM recommendation.")]
    if abs(diff) >= 10:
        if diff > 0:
            return "template", "template", [_issue("comparison", "template_score_advantage", "Template score is at least 10 points higher.")]
        return "llm", "llm", [_issue("comparison", "llm_score_advantage", "LLM score is at least 10 points higher.")]
    return "needs_editor_review", None, [_issue("comparison", "close_scores", "Candidate scores are close; editor review is recommended.")]


def compare_draft_candidates(
    template_draft: Dict[str, Any],
    llm_draft: Dict[str, Any],
    source_bundle: Optional[Dict[str, Any]] = None,
    template_safety_result: Optional[Dict[str, Any]] = None,
    template_quality_result: Optional[Dict[str, Any]] = None,
    llm_safety_result: Optional[Dict[str, Any]] = None,
    llm_quality_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    source_bundle = source_bundle or {}
    template = _candidate_assessment("template", template_draft or {}, source_bundle, template_safety_result, template_quality_result)
    llm = _candidate_assessment("llm", llm_draft or {}, source_bundle, llm_safety_result, llm_quality_result)
    recommendation, winner, reasons = _choose_recommendation(template, llm)
    if recommendation not in ALLOWED_RECOMMENDATIONS:
        recommendation = "needs_editor_review"
        winner = None

    blocking_issues = template["blocking_issues"] + llm["blocking_issues"]
    warnings = template["warnings"] + llm["warnings"]
    comparison = {
        "source_grounding": {"template": template["source_result"], "llm": llm["source_result"]},
        "safety": {"template": template["safety_result"], "llm": llm["safety_result"]},
        "quality": {"template": template["quality_result"], "llm": llm["quality_result"]},
        "structure": {"template": template["structure_result"], "llm": llm["structure_result"]},
        "seo": {"template": template["seo_result"], "llm": llm["seo_result"]},
        "risk_disclaimer": {"template": template["risk_result"], "llm": llm["risk_result"]},
        "indonesian_readability": {"template": template["readability_result"], "llm": llm["readability_result"]},
        "factual_conservativeness": {"template": template["number_result"], "llm": llm["number_result"]},
    }
    return json_safe(
        {
            "success": True,
            "recommendation": recommendation,
            "winner": winner,
            "scores": {"template": template["score"], "llm": llm["score"]},
            "reasons": reasons,
            "blocking_issues": blocking_issues,
            "warnings": warnings,
            "comparison": comparison,
            "metadata": {
                "source_count": len((source_bundle or {}).get("sources") or []),
                "template_status": (template_draft or {}).get("status"),
                "llm_status": (llm_draft or {}).get("status"),
            },
        }
    )
