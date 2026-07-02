from src.content.validators.depth_quality import validate_depth_quality
from tests.test_article_schema import valid_article


def test_depth_quality_passes_with_rich_article_metadata():
    result = validate_depth_quality(
        valid_article(
            body=(
                "Ikhtisar peristiwa\nPasar mencermati berita terbaru USD/IDR dan dampaknya bagi pembaca.\n\n"
                "Latar belakang\nUSD/IDR dipengaruhi kebijakan moneter, inflasi, arus modal, dan sentimen risiko global.\n\n"
                "Dampak pasar\nBerita membantu pembaca memahami konteks, tetapi tidak cukup untuk menyimpulkan arah harga.\n\n"
                "Hal yang perlu dipantau\nPembaca perlu mencermati data ekonomi berikutnya.\n\n"
                "Sumber\nhttps://example.com/a\n\n"
                "Catatan risiko\nArtikel ini hanya untuk informasi dan edukasi."
            )
        ),
        {"quality": {"min_body_length": 180, "min_faq_count": 1, "min_key_takeaways": 1}},
        {"source_trace": {"source_count": 1}},
    )

    assert result.passed is True
    assert result.metadata["body_length"] >= 180


def test_depth_quality_warns_for_thin_article_without_blocking_export():
    article = valid_article(body="Sumber\nhttps://example.com/a\n\nCatatan risiko\nArtikel ini hanya untuk informasi dan edukasi.")
    article["faq"] = []
    article["key_takeaways"] = []
    article["search_intent"] = ""

    result = validate_depth_quality(article, {"quality": {"min_body_length": 180}})

    assert result.passed is True
    assert result.exportable is True
    assert {issue.code for issue in result.issues} >= {"body_too_short_for_depth", "faq_too_sparse", "missing_key_takeaways", "missing_search_intent"}
