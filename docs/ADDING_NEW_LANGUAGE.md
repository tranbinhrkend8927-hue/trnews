# Adding A New Language

1. Create `config/languages/<lang>.yaml`.
2. Add writing rules, required sections, disclaimer, SEO settings, quality thresholds, and Notion field overrides if needed.
3. Create `src/llm/prompts/article_draft/<lang>.system.md`.
4. Confirm `src/llm/prompts/article_draft/spec.yaml` still applies.
5. Add or reuse an LLM profile in `config/llm_profiles.yaml`.
6. Add or reuse a Notion target in `config/notion_targets.yaml`.
7. Bind the language, LLM profile, and Notion target from `config/pipeline.yaml`.
8. Run:

```bash
python -m src.jobs.production_check --market <market_id>
python -m src.jobs.smoke_test --market <market_id>
python -m src.jobs.run_market --market <market_id> --dry-run
python -m src.jobs.run_market --market <market_id> --dry-run --include-notion-preview
```

9. Add focused tests for language rules if the language has custom constraints.
