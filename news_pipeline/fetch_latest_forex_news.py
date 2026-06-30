"""获取最新外汇新闻并抓取第一条完整内容的演示脚本。

用法：
    .venv/bin/python -m news_pipeline.fetch_latest_forex_news
"""

from tradingview_scraper.symbols.news import NewsScraper
from datetime import datetime, timezone
from dotenv import load_dotenv

load_dotenv()


def fetch_latest_forex_news_content(symbol='USDIDR', exchange='FX_IDC'):
    """
    获取指定外汇货币对的最新新闻，并返回第一条的完整内容。

    Args:
        symbol: 货币对符号（如 'USDIDR', 'EURUSD', 'USDJPY'）
        exchange: 交易所（外汇通常是 'FX_IDC'）

    Returns:
        dict: 包含 headlines (新闻列表) 和 first_article (第一条完整内容)
    """
    scraper = NewsScraper()

    # 步骤 1：获取最新新闻列表（按时间排序）
    print(f"正在获取 {exchange}:{symbol} 的最新新闻...")
    headlines = scraper.scrape_headlines(
        symbol=symbol,
        exchange=exchange,
        sort='latest'  # 按最新时间排序
    )

    if not headlines:
        print("未找到任何新闻")
        return {'headlines': [], 'first_article': None}

    print(f"✓ 获取到 {len(headlines)} 条新闻头条")

    # 步骤 2：抓取第一条新闻的完整内容
    first_headline = headlines[0]
    story_path = first_headline['storyPath']

    print(f"\n正在抓取最新一条新闻的完整内容...")
    print(f"标题: {first_headline['title']}")
    print(f"来源: {first_headline['source']}")
    print(f"链接: https://www.tradingview.com{story_path}")

    article = scraper.scrape_news_content(story_path)

    print(f"\n✓ 完整内容抓取成功")
    print(f"正文段落数: {len(article['body'])}")

    return {
        'headlines': headlines,
        'first_article': article
    }


def display_article(article):
    """格式化显示文章内容"""
    print("\n" + "=" * 70)
    print("文章完整内容")
    print("=" * 70)
    print(f"标题: {article['title']}")
    print(f"发布时间: {article['published_datetime']}")

    if article['related_symbols']:
        symbols = ', '.join(s['symbol'] for s in article['related_symbols'])
        print(f"相关品种: {symbols}")

    print("\n正文:")
    print("-" * 70)
    for item in article['body']:
        if item['type'] == 'text':
            print(item['content'])
            print()  # 段落间空行
        elif item['type'] == 'image':
            print(f"[图片: {item.get('alt', '无描述')}]")
            print(f"图片地址: {item['src']}")
            print()

    if article['tags']:
        print("-" * 70)
        print(f"标签: {', '.join(article['tags'])}")


def main():
    """主函数：演示完整流程"""
    # 可以改成任何外汇货币对，如 'EURUSD', 'USDJPY', 'GBPUSD' 等
    result = fetch_latest_forex_news_content(
        symbol='USDIDR',
        exchange='FX_IDC'
    )

    if result['first_article']:
        display_article(result['first_article'])

        # 可选：显示其他头条的标题和链接
        print("\n" + "=" * 70)
        print("其他最新头条（前 5 条）")
        print("=" * 70)
        for i, headline in enumerate(result['headlines'][1:6], 2):
            ts = datetime.fromtimestamp(
                headline['published'],
                tz=timezone.utc
            ).strftime('%Y-%m-%d %H:%M UTC')
            print(f"{i}. [{ts}] {headline['title']}")
            print(f"   来源: {headline['source']}")
            print(f"   链接: https://www.tradingview.com{headline['storyPath']}")
            print()


if __name__ == "__main__":
    main()
