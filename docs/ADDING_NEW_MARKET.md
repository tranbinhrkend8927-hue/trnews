# Adding A New Market

Example: adding `USDJPY`.

1. Add a market entry to `config/pipeline.yaml`.
2. Set a stable `id`, for example `usd_jpy_ja`.
3. Set `symbol`, `exchange`, `base_currency`, and `quote_currency`.
4. Configure `tradingview.url`, `language`, `locale`, and source limits.
5. Confirm `content.language` has a matching file in `config/languages/`.
6. Confirm `llm.draft_profile` exists in `config/llm_profiles.yaml`.
7. Confirm `notion.target` exists in `config/notion_targets.yaml`.
8. Run:

```bash
python -m src.jobs.production_check --market usd_jpy_ja
python -m src.jobs.smoke_test --market usd_jpy_ja
python -m src.jobs.run_market --market usd_jpy_ja --dry-run
python -m src.jobs.run_market --market usd_jpy_ja --dry-run --include-notion-preview
```

9. For a real run, use upsert:

```bash
python -m src.jobs.run_market --market usd_jpy_ja --use-real-llm --upsert-notion --yes
```

10. Inspect `.runs/content_jobs.jsonl`, `.runs/events.jsonl`, and Notion.
