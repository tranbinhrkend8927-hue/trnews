# Validation Flow

This is the recommended end-to-end validation path from a fresh local checkout to the first real Notion upsert.

Use `.venv/bin/python` unless your shell has already activated the project virtualenv.

## 1. Prepare Environment

Copy the template and fill only the values needed for the stage you are testing:

```bash
cp .env.example .env
```

Minimum values for real LLM:

```bash
LLM_API_KEY=
LLM_BASE_URL=https://openrouter.ai/api/v1
LLM_DEFAULT_MODEL=
LLM_WRITER_MODEL=
LLM_REVIEW_MODEL=
LLM_WRITER_MODEL_JA=
```

Minimum values for real Notion:

```bash
NOTION_API_KEY=
NOTION_DATA_SOURCE_ID_ID=
```

Runtime stores:

```bash
CONTENT_JOB_STORE_PATH=.runs/content_jobs.jsonl
OBSERVABILITY_EVENT_STORE_PATH=.runs/events.jsonl
REVIEW_FEEDBACK_STORE_PATH=.runs/review_feedback.jsonl
```

Do not commit real secrets.

## 2. Prepare Notion Data Source

Before any real Notion write, confirm the target data source has these properties:

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

Optional review sync properties:

- `Review Notes`
- `Quality Score`
- `Factuality Score`
- `Language Score`
- `SEO Score`
- `Compliance Score`

## 3. Local Safe Checks

These commands do not call a real LLM and do not write Notion.

```bash
.venv/bin/python -m src.jobs.validate_config
.venv/bin/python -m src.jobs.production_check --market usd_idr_id
.venv/bin/python -m src.jobs.smoke_test --market usd_idr_id
```

Expected results:

- `validate_config` returns `success: true`.
- `production_check` returns `PRODUCTION_CHECK_PASSED`.
- `smoke_test` returns `SMOKE_TEST_PASSED`.

Fallback warnings for missing local LLM or Notion env are acceptable before a real run.

## 4. Safe Single-Market Dry Runs

Fake article dry-run:

```bash
.venv/bin/python -m src.jobs.run_market \
  --market usd_idr_id \
  --dry-run
```

Notion preview dry-run:

```bash
.venv/bin/python -m src.jobs.run_market \
  --market usd_idr_id \
  --dry-run \
  --include-notion-preview
```

Dry-run with local job and event records:

```bash
.venv/bin/python -m src.jobs.run_market \
  --market usd_idr_id \
  --dry-run \
  --include-notion-preview \
  --job-store-path .runs/content_jobs.jsonl \
  --event-store-path .runs/events.jsonl
```

Expected result: `DRY_RUN_SUCCESS`. If preview is enabled, output includes `notion_preview`.

## 5. Real LLM Dry Run

After setting LLM env:

```bash
.venv/bin/python -m src.jobs.production_check \
  --market usd_idr_id \
  --require-real-llm
```

Then run:

```bash
.venv/bin/python -m src.jobs.run_market \
  --market usd_idr_id \
  --use-real-llm \
  --dry-run \
  --include-notion-preview \
  --job-store-path .runs/content_jobs.jsonl \
  --event-store-path .runs/events.jsonl
```

Expected result: validators pass and no Notion write occurs.

## 6. Final Preflight Before Notion Write

After setting Notion env:

```bash
.venv/bin/python -m src.jobs.production_check \
  --market usd_idr_id \
  --require-real-llm \
  --require-notion
```

Do not continue to a real write until this passes.

## 7. First Real Notion Upsert

Real Notion writes require explicit `--yes`. Prefer upsert to prevent duplicates.

```bash
.venv/bin/python -m src.jobs.run_market \
  --market usd_idr_id \
  --use-real-llm \
  --upsert-notion \
  --yes \
  --job-store-path .runs/content_jobs.jsonl \
  --event-store-path .runs/events.jsonl
```

Expected result:

- Status is `NOTION_EXPORTED`.
- `notion.metadata.action` is `created` or `updated`.
- Notion page contains `Content Job Key`, `Source Bundle Hash`, and `Pipeline Run ID`.

Guardrail check:

```bash
.venv/bin/python -m src.jobs.run_market \
  --market usd_idr_id \
  --upsert-notion
```

Expected result: `CONFIRMATION_REQUIRED`, with no Notion write.

## 8. Batch Validation

Batch dry-run:

```bash
.venv/bin/python -m src.jobs.run_batch \
  --enabled-only \
  --dry-run \
  --job-store-path .runs/content_jobs.jsonl \
  --event-store-path .runs/events.jsonl
```

Batch preview:

```bash
.venv/bin/python -m src.jobs.run_batch \
  --enabled-only \
  --dry-run \
  --include-notion-preview \
  --job-store-path .runs/content_jobs.jsonl \
  --event-store-path .runs/events.jsonl
```

Batch real LLM + Notion upsert:

```bash
.venv/bin/python -m src.jobs.run_batch \
  --enabled-only \
  --use-real-llm \
  --upsert-notion \
  --yes \
  --job-store-path .runs/content_jobs.jsonl \
  --event-store-path .runs/events.jsonl
```

## 9. Reports And Review Feedback

Run metrics report:

```bash
.venv/bin/python -m src.jobs.report_runs \
  --event-store-path .runs/events.jsonl
```

Retry failed jobs in safe dry-run mode:

```bash
.venv/bin/python -m src.jobs.retry_failed \
  --job-store-path .runs/content_jobs.jsonl \
  --dry-run
```

Sync Notion review feedback read-only:

```bash
.venv/bin/python -m src.jobs.sync_notion_reviews \
  --target notion_articles_id \
  --feedback-store-path .runs/review_feedback.jsonl \
  --dry-run
```

Write Notion review feedback after checking the dry-run payload:

```bash
ENABLE_NOTION_FEEDBACK_SYNC=1 .venv/bin/python -m src.jobs.sync_notion_reviews \
  --target notion_articles_id \
  --feedback-store-path .runs/review_feedback.jsonl
```

Report review feedback:

```bash
.venv/bin/python -m src.jobs.report_feedback \
  --feedback-store-path .runs/review_feedback.jsonl
```

## 10. Acceptance Criteria

- `validate_config` returns `success: true`.
- `production_check --require-real-llm --require-notion` passes before real write.
- `smoke_test` passes.
- Fake dry-run and real LLM dry-run pass.
- Notion preview has properties and blocks.
- First `--upsert-notion --yes` succeeds.
- `.runs/content_jobs.jsonl` contains a job record.
- `.runs/events.jsonl` contains a pipeline event.
- Notion page contains `Content Job Key`, `Source Bundle Hash`, and `Pipeline Run ID`.
- `sync_notion_reviews` can import reviewed pages into `.runs/review_feedback.jsonl`.

## 11. Safety Rules

- Defaults do not call a real LLM.
- Defaults do not write Notion.
- `--export-notion` and `--upsert-notion` require `--yes`.
- Prefer `--upsert-notion --yes` for repeated real runs.
- The system does not delete Notion pages.
