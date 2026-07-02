# Real Run Checklist

Use this checklist before the first live LLM or Notion run.

## 1. Environment

- Copy `.env.example` to `.env`.
- Set `LLM_API_KEY`, `LLM_BASE_URL`, and at least `LLM_DEFAULT_MODEL` or `LLM_WRITER_MODEL`.
- Set `NOTION_API_KEY`.
- Set the target parent id, for example `NOTION_DATA_SOURCE_ID_ID`.
- Never commit real secrets.

## 2. Notion Schema

The target data source should include properties used by the mapper:

- `Name`
- `Status`
- `Language`
- `Market`
- `Symbol`
- `Article Type`
- `AI Summary`
- `SEO Title`
- `SEO Description`
- `Source Count`
- `Source URLs`
- `Risk Level`
- `Prompt Version`
- `LLM Model`
- `Content Job Key`
- `Source Bundle Hash`
- `Pipeline Run ID`
- `Generated At`
- optional review fields: `Review Notes`, `Quality Score`, `Factuality Score`, `Language Score`, `SEO Score`, `Compliance Score`

## 3. Preflight

```bash
python -m src.jobs.validate_config
python -m src.jobs.production_check --market usd_idr_id
python -m src.jobs.smoke_test --market usd_idr_id
```

Use stricter checks before live runs:

```bash
python -m src.jobs.production_check --market usd_idr_id --require-real-llm --require-notion
```

## 4. Safe Dry Runs

```bash
python -m src.jobs.run_market --market usd_idr_id --dry-run
python -m src.jobs.run_market --market usd_idr_id --dry-run --include-notion-preview
python -m src.jobs.run_market --market usd_idr_id --use-real-llm --dry-run
```

## 5. Real Notion Upsert

Real Notion writes require explicit confirmation:

```bash
python -m src.jobs.run_market --market usd_idr_id --use-real-llm --upsert-notion --yes
python -m src.jobs.run_batch --enabled-only --use-real-llm --upsert-notion --yes
```

Create-only export is still available, but upsert is preferred to avoid duplicates:

```bash
python -m src.jobs.run_market --market usd_idr_id --export-notion --yes
```

## 6. Batch Dry Run

```bash
python -m src.jobs.run_batch --enabled-only --dry-run
python -m src.jobs.run_batch --enabled-only --dry-run --include-notion-preview
```

## 7. Review Sync And Reports

```bash
python -m src.jobs.sync_notion_reviews --target notion_articles_id --feedback-store-path .runs/review_feedback.jsonl --dry-run
ENABLE_NOTION_FEEDBACK_SYNC=1 python -m src.jobs.sync_notion_reviews --target notion_articles_id --feedback-store-path .runs/review_feedback.jsonl
python -m src.jobs.report_runs --event-store-path .runs/events.jsonl
python -m src.jobs.report_feedback --feedback-store-path .runs/review_feedback.jsonl
```

## 8. Rollback Notes

- This system does not delete Notion pages.
- If a bad page is created, archive or edit it manually in Notion.
- Re-run with `--upsert-notion --yes` after fixing config or prompts.
- Use `.runs/content_jobs.jsonl` and `.runs/events.jsonl` to inspect failed runs.

## 9. Common Failures

- Missing `LLM_API_KEY` or model env.
- Missing `NOTION_API_KEY`.
- Missing Notion data source id env.
- Notion property names do not match mapper output.
- Source bundle has too few usable sources.
- Article validator fails because source grounding or language rules are not satisfied.
