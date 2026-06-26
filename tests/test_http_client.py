from unittest import mock

from tradingview_scraper.symbols.http_client import TradingViewHttpClient


def test_http_client_uses_session_and_default_timeout():
    session = mock.Mock()
    response = mock.Mock()
    session.request.return_value = response

    client = TradingViewHttpClient(
        headers={"User-Agent": "default-agent"},
        timeout=7,
        session=session,
    )

    result = client.get("https://example.com", headers={"X-Test": "1"})

    assert result is response
    session.request.assert_called_once_with(
        "GET",
        "https://example.com",
        headers={"User-Agent": "default-agent", "X-Test": "1"},
        timeout=7,
    )


def test_http_client_request_timeout_override():
    session = mock.Mock()
    client = TradingViewHttpClient(timeout=7, session=session)

    client.post("https://example.com", json={"ok": True}, timeout=2)

    session.request.assert_called_once_with(
        "POST",
        "https://example.com",
        headers={},
        timeout=2,
        json={"ok": True},
    )
