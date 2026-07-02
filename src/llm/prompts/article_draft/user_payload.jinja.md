Create a deep, readable ArticleDraft JSON using only this merged source brief.

{{ article_brief }}

Output rules:
- Output JSON only, no markdown.
- Use Bahasa Indonesia.
- Use only facts and numbers present in the brief.
- sources_used must use source_id, news_id, title, url, provider, and published_at from the brief.
- body must include clear sections for "Ikhtisar peristiwa", "Latar belakang", "Dampak pasar", "Hal yang perlu dipantau", "Sumber", and "Catatan risiko".
- Add reader-friendly FAQ, key_takeaways, candidate_titles, editorial_angle, search_intent, and editor_notes when the brief supports them.
- Explain why the news matters for the currency pair without inventing prices, dates, institutions, or forecasts.
- risk_disclaimer must exactly match the brief.
- Do not give investment advice.
