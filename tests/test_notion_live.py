import pytest

from notion_config import load_notion_config
from notion_exporter import export_article_to_notion


@pytest.mark.live_notion
def test_live_notion_configuration_and_dry_run_payload(monkeypatch):
    config = load_notion_config(require_api_key=True)
    if not config.get("success"):
        pytest.skip("NOTION_API_KEY and a Notion parent/data source id are required for live Notion checks")

    article = {
        "id": 1,
        "topic_id": 1,
        "symbol": "USDIDR",
        "language": "id",
        "title": "USD/IDR Smoke Test Approved Article",
        "summary": "Ringkasan smoke test untuk konfigurasi Notion.",
        "body": "\n\n".join(
            [
                "Pembuka singkat\nUSD/IDR menjadi perhatian pembaca Indonesia.",
                "Apa yang terjadi?\nSumber tersimpan digunakan untuk validasi dry-run Notion.",
                "FAQ\nQ: Apakah ini rekomendasi transaksi?\nA: Tidak.",
                "Sumber\nSource news ID 1: Smoke source\nURL: https://example.com/source",
                "Catatan risiko\nArtikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan.",
            ]
        ),
        "seo_title": "USD/IDR Smoke Test",
        "seo_description": "Dry-run Notion smoke test.",
        "status": "approved",
        "fact_check_status": "passed",
        "risk_disclaimer_included": True,
        "sources_json": {
            "sources": [
                {
                    "title": "Smoke source",
                    "url": "https://example.com/source",
                    "source": "Example",
                }
            ]
        },
        "published_at": None,
    }
    sources = [
        {
            "article_id": 1,
            "source_type": "forex_news",
            "source_name": "Example",
            "source_url": "https://example.com/source",
            "cited_claim": "Smoke source",
        }
    ]

    result = export_article_to_notion(article, sources, notion_client=None, dry_run=True)

    assert result["dry_run"] is True
    assert result["summary"]["would_publish"] is False
