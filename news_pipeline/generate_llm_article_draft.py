"""Generate an LLM article draft candidate in dry-run mode only."""

import argparse
import json
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

from .article_drafts import fetch_topic_for_draft
from .fetch_forex_news_json import get_postgres_dsn
from .llm_article_drafts import generate_llm_article_draft_candidate, json_safe
from .source_grounding import build_source_bundle, fetch_source_news_for_topic


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a dry-run LLM article draft candidate.")
    parser.add_argument("--topic-id", type=int, required=True, help="content_topics.id to use as draft input.")
    parser.add_argument("--language", default="id", help="Language profile. First version supports only id.")
    parser.add_argument("--template", help="Optional template hint for the prompt.")
    parser.add_argument("--provider", choices=["mock", "openrouter"], default="mock", help="LLM provider. Default is mock.")
    parser.add_argument("--dry-run", action="store_true", help="Required. P10 never writes generated articles.")
    return parser


def _error(error_type: str, message: str, *, retryable: bool = False) -> Dict[str, Any]:
    return {"type": error_type, "message": message, "retryable": bool(retryable)}


def _result(
    *,
    topic_id: int,
    language: str = "id",
    provider: str = "mock",
    source_bundle: Optional[Dict[str, Any]] = None,
    llm_result: Optional[Dict[str, Any]] = None,
    draft_candidate: Optional[Dict[str, Any]] = None,
    safety_result: Optional[Dict[str, Any]] = None,
    quality_result: Optional[Dict[str, Any]] = None,
    errors: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    errors = errors or []
    return json_safe(
        {
            "success": not errors,
            "topic_id": topic_id,
            "language": language,
            "provider": provider,
            "dry_run": True,
            "source_bundle": source_bundle or {},
            "llm_result": llm_result or {},
            "draft_candidate": draft_candidate or {},
            "safety_result": safety_result or {},
            "quality_result": quality_result or {},
            "summary": {
                "would_write_db": False,
                "would_publish": False,
            },
            "errors": errors,
        }
    )


def _source_line(source: Dict[str, Any]) -> str:
    if not source:
        return "Source news tersimpan"
    news_id = source.get("news_id")
    title = source.get("title") or "Source news tersimpan"
    url = source.get("url") or source.get("canonical_url") or source.get("source_url")
    parts = []
    if news_id:
        parts.append(f"Source news ID {news_id}: {title}")
    else:
        parts.append(str(title))
    if url:
        parts.append(f"URL: {url}")
    return "\n".join(parts)


def build_mock_article_output(source_bundle: Dict[str, Any]) -> Dict[str, Any]:
    first_source = (source_bundle.get("sources") or [{}])[0]
    source_line = _source_line(first_source)
    body = "\n\n".join(
        [
            "Pembuka singkat\nUSD/IDR dan Rupiah menjadi perhatian pembaca Indonesia berdasarkan sumber berita yang tersimpan.",
            "Apa yang terjadi?\nSumber terkait menyoroti konteks Rupiah, Dolar AS, Bank Indonesia, dan The Fed tanpa menyimpulkan arah pasar secara pasti.",
            "Mengapa ini penting untuk Rupiah?\nKonteks ini membantu pembaca memahami mengapa sentimen global dan kebijakan bank sentral dapat menjadi perhatian dalam pembahasan Rupiah.",
            "Faktor yang perlu dipantau\nPembaca dapat mencermati komunikasi Bank Indonesia, sentimen terhadap Dolar AS, dan agenda makro yang disebut dalam sumber resmi.",
            "Apa dampaknya bagi pembaca Indonesia?\nArtikel ini memberi konteks umum agar pembaca dapat memahami berita USD/IDR secara hati-hati dan tidak menganggap pergerakan pasar sebagai sesuatu yang pasti.",
            "FAQ\nQ: Apakah ini rekomendasi transaksi?\nA: Tidak, ini informasi umum dan edukatif.\nQ: Apakah artikel ini memprediksi arah Rupiah?\nA: Tidak, artikel ini hanya merangkum konteks dari sumber yang tersedia.",
            f"Sumber\n{source_line}",
            "Catatan risiko\nArtikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
        ]
    )
    return {
        "title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau Pembaca Indonesia",
        "slug": "usd-idr-rupiah-faktor-yang-perlu-dipantau",
        "summary": "Ringkasan edukatif tentang USD/IDR, Rupiah, Dolar AS, dan faktor makro berdasarkan sumber berita yang tersimpan.",
        "body": body,
        "seo_title": "USD/IDR dan Rupiah: Faktor yang Perlu Dipantau",
        "seo_description": "Konteks USD/IDR dan Rupiah untuk pembaca Indonesia berdasarkan sumber berita yang tersimpan.",
        "faq": [
            {"question": "Apakah ini rekomendasi transaksi?", "answer": "Tidak, ini informasi umum dan edukatif."},
            {"question": "Apakah artikel ini memprediksi arah Rupiah?", "answer": "Tidak, artikel ini hanya merangkum konteks."},
        ],
        "sources_used": [{"news_id": first_source.get("news_id"), "title": first_source.get("title")}],
        "risk_disclaimer": "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
        "uncertain_claims": [],
        "language": "id",
    }


def build_gateway(provider_name: str, source_bundle: Dict[str, Any]):
    if provider_name == "openrouter":
        return None
    mock_output = build_mock_article_output(source_bundle)

    def mock_runner(task_name: str, input_data: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "success": True,
            "provider": "mock",
            "model": "mock-model",
            "task_name": task_name,
            "prompt_version": "mock@2026-06-30",
            "output": mock_output,
            "raw_response": {"mock": True},
            "usage": {},
            "latency_ms": 0,
            "error": None,
        }

    return mock_runner


def main(argv: Optional[List[str]] = None) -> int:
    load_dotenv()
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    if not args.dry_run:
        result = _result(
            topic_id=args.topic_id,
            language=args.language,
            provider=args.provider,
            errors=[_error("dry_run_required", "P10 only supports --dry-run and never writes to the database.", retryable=False)],
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1

    try:
        dsn = get_postgres_dsn()
        topic = fetch_topic_for_draft(dsn, args.topic_id)
        if not topic:
            result = _result(
                topic_id=args.topic_id,
                language=args.language,
                provider=args.provider,
                errors=[_error("topic_not_found", f"Topic not found: {args.topic_id}", retryable=False)],
            )
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 1

        source_news_result = fetch_source_news_for_topic(dsn, topic)
        source_bundle = build_source_bundle(topic, source_news_result)
        gateway = build_gateway(args.provider, source_bundle)
        result = generate_llm_article_draft_candidate(
            topic,
            source_bundle,
            gateway,
            language=args.language,
            template_hint=args.template,
            provider_label=args.provider,
        )
    except Exception as exc:
        result = _result(
            topic_id=args.topic_id,
            language=args.language,
            provider=args.provider,
            errors=[_error("llm_article_draft_cli_error", str(exc), retryable=False)],
        )

    print(json.dumps(json_safe(result), ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
