Create a deep, readable ArticleDraft JSON using only this merged source brief.

{{ article_brief }}

Output rules:
- Output JSON only, no markdown.
- Use Bahasa Indonesia.
- Output fields must strictly match the configured JSON Schema. Do not add extra fields.
- Use only facts and numbers present in the brief.
- sources_used must use source_id, news_id, title, url, provider, and published_at from the brief.
- body must include these exact section headings on their own lines: "Ikhtisar peristiwa", "Latar belakang", "Dampak pasar", "Hal yang perlu dipantau", "FAQ", "Sumber", and "Catatan risiko".
- Include title, slug, summary, body, seo_title, seo_description, faq, sources_used, risk_disclaimer, uncertain_claims, language, market, symbol, article_type, region, search_intent, primary_keyword, secondary_keywords, candidate_titles, editorial_angle, key_takeaways, evergreen_context, and editor_notes.
- Explain why the news matters for the currency pair without inventing prices, dates, institutions, or forecasts.
- risk_disclaimer must exactly match the brief.
- Do not give investment advice.
