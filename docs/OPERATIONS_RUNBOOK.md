# Operations Runbook

Common commands for local operation.

For the full first-run validation sequence, use [Validation Flow](VALIDATION_FLOW.md).

```bash
python -m src.jobs.validate_config
python -m src.jobs.production_check --market usd_idr_id
python -m src.jobs.smoke_test --market usd_idr_id
python -m src.jobs.run_market --market usd_idr_id --dry-run
python -m src.jobs.run_market --market usd_idr_id --use-real-llm --dry-run
python -m src.jobs.run_market --market usd_idr_id --use-real-llm --upsert-notion --yes
python -m src.jobs.run_batch --enabled-only --dry-run
python -m src.jobs.run_batch --enabled-only --use-real-llm --upsert-notion --yes
python -m src.jobs.retry_failed --job-store-path .runs/content_jobs.jsonl
python -m src.jobs.report_runs --event-store-path .runs/events.jsonl
python -m src.jobs.sync_notion_reviews --target notion_articles_id --feedback-store-path .runs/review_feedback.jsonl
python -m src.jobs.report_feedback --feedback-store-path .runs/review_feedback.jsonl
```

## Guardrails

- Default commands do not call a real LLM.
- Default commands do not write Notion.
- `--export-notion` and `--upsert-notion` require `--yes`.
- Prefer `--upsert-notion --yes` over `--export-notion --yes` for repeated runs.

## Local Files

- Job records: `.runs/content_jobs.jsonl`
- Observation events: `.runs/events.jsonl`
- Review feedback: `.runs/review_feedback.jsonl`
