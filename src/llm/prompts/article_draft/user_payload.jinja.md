Create a short ArticleDraft JSON using only this merged source brief.

{{ article_brief }}

Output rules:
- Output JSON only, no markdown.
- Use Bahasa Indonesia.
- Use only facts and numbers present in the brief.
- sources_used must use source_id, news_id, title, url, provider, and published_at from the brief.
- body must include sections "Sumber" and "Catatan risiko".
- risk_disclaimer must exactly match the brief.
- Do not give investment advice.
