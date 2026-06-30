"""调试演示脚本：逐个验证各 Scraper 模块的实际效果。

运行方式（任选其一）：
    .venv/bin/python -m news_pipeline.debug_demo          # 直接用已建好的 venv
    uv run --python .venv/bin/python -m news_pipeline.debug_demo
"""

import json
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def show(title, data, limit=2):
    """精简打印结果：条数 + 前几条样例。"""
    print(f"\n{'=' * 60}\n[{title}]\n{'=' * 60}")
    if isinstance(data, dict):
        print(json.dumps(data, ensure_ascii=False, indent=2)[:800])
    elif isinstance(data, list):
        print(f"共 {len(data)} 条")
        for item in data[:limit]:
            print(json.dumps(item, ensure_ascii=False, indent=2)[:600])
            print("-" * 40)
    else:
        print(data)


def demo_indicators():
    """技术指标（无需 cookie，最稳定）。"""
    from tradingview_scraper.symbols.technicals import Indicators
    scraper = Indicators()
    result = scraper.scrape(
        exchange="BINANCE",
        symbol="BTCUSDT",
        timeframe="1d",
        indicators=["RSI", "Stoch.K"],
    )
    show("Indicators 技术指标", result)


def demo_news():
    """新闻头条（无需 cookie）。"""
    from tradingview_scraper.symbols.news import NewsScraper
    scraper = NewsScraper()
    result = scraper.scrape_headlines(symbol="BTCUSD", exchange="BINANCE")
    show("News 新闻头条", result)


def demo_ideas():
    """交易想法（可能触发 captcha，需要时才配 TRADINGVIEW_COOKIE）。"""
    from tradingview_scraper.symbols.ideas import Ideas
    scraper = Ideas()
    result = scraper.scrape(symbol="BTCUSD", startPage=1, endPage=1, sort="popular")
    show("Ideas 交易想法", result)


if __name__ == "__main__":
    demos = [
        ("indicators", demo_indicators),
        ("news", demo_news),
        ("ideas", demo_ideas),
    ]
    for name, fn in demos:
        try:
            fn()
        except Exception as e:  # noqa: BLE001  调试脚本，捕获所有异常逐个演示
            print(f"\n[{name}] 运行失败: {type(e).__name__}: {e}")
