# 10 Implementation Status

This document records the current implementation baseline after Phase 1-5. It is intentionally separate from the roadmap so future planning does not overwrite the verified state.

## Current Phase Status

| Phase | Status | Default Runtime Impact |
|---|---|---|
| Phase 1 Source Enrichment + Source Quality Gate | implemented | off by default |
| Phase 2 Structured EditorialBrief | implemented | off by default |
| Phase 3 AI Reviewer | implemented | off by default |
| Phase 4 ArticleQualityReport + Promptfoo skeleton | implemented | off by default |
| Phase 5 Notion Feedback Loop | implemented | feedback sync off by default |
| Phase 6 Langfuse / datasets / heavy frameworks | not started | no impact |

## Feature Flags

All new pipeline-changing features are opt-in:

```bash
ENABLE_SOURCE_ENRICHMENT=0
ENABLE_SOURCE_QUALITY_GATE=0
ENABLE_STRUCTURED_BRIEF=0
ENABLE_AI_REVIEWER=0
ENABLE_LLM_AI_REVIEWER=0
ENABLE_QUALITY_REPORT=0
ENABLE_PROMPTFOO_EVALS=0
ENABLE_NOTION_FEEDBACK_SYNC=0
```

Safe dry-run commands can run with default flags. Real Notion writes still require explicit export/upsert flags, and feedback sync writes require `ENABLE_NOTION_FEEDBACK_SYNC=1` or `--force`.

## Implemented Modules

### Ingest

- `src/ingest/source_enricher.py`
- `src/ingest/source_quality.py`

Capabilities:

- URL extraction through Trafilatura.
- Safe extraction failure handling.
- `SourceEnrichmentResult`.
- `SourceQualityReport`.
- Source quality recommended actions: `write_article`, `write_brief_only`, `skip_or_manual_review`.

### Planning

- `src/models/brief.py`
- `src/planning/brief_builder.py`
- `src/planning/brief_validator.py`

Capabilities:

- Deterministic structured `EditorialBrief`.
- Brief validation.
- Pipeline fallback when structured brief is disabled.

### Review

- `src/models/review.py`
- `src/review/article_reviewer.py`
- `src/llm/prompts/article_review/`

Capabilities:

- Deterministic reviewer.
- Optional LLM reviewer path through `review_profile`.
- Pydantic-validated `AIReview`.
- Deterministic fallback when LLM reviewer fails.

### Quality

- `src/models/quality.py`
- `src/review/quality_report.py`
- `evals/promptfoo.yaml`
- `evals/samples/`

Capabilities:

- Deterministic `ArticleQualityReport`.
- Promptfoo config skeleton and static sample validation.
- Evals do not run during normal pytest unless explicitly invoked.

### Notion Feedback

- `src/review/feedback.py`
- `src/review/notion_sync.py`
- `src/review/metrics.py`
- `src/jobs/sync_notion_reviews.py`
- `src/jobs/report_feedback.py`

Capabilities:

- Human review status sync from Notion.
- Editor fields: score, rejection reason, edited headline, edited summary, notes, final publish decision, reviewed at.
- Feedback JSONL store.
- Feedback summary and data-quality warnings.
- Sync write guard through `ENABLE_NOTION_FEEDBACK_SYNC`.

## Verification Baseline

Latest local verification:

```text
git diff --check: passed
pytest: 914 passed, 29 skipped
production_check --market usd_idr_id: PRODUCTION_CHECK_PASSED
smoke_test --market usd_idr_id: SMOKE_TEST_PASSED
```

Useful commands:

```bash
.venv/bin/python -m pytest
.venv/bin/python -m src.jobs.production_check --market usd_idr_id
.venv/bin/python -m src.jobs.smoke_test --market usd_idr_id
git diff --check
```

Phase 5 focused verification:

```bash
.venv/bin/python -m pytest tests/test_notion_mapper.py tests/test_notion_exporter_dry_run.py tests/test_notion_exporter.py tests/test_sync_notion_reviews_cli.py tests/test_review_notion_sync.py tests/test_review_metrics.py tests/test_report_feedback_cli.py tests/test_review_feedback.py
```

## Operational Commands

Preview Notion review feedback without writing:

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

Generate a feedback report:

```bash
.venv/bin/python -m src.jobs.report_feedback \
  --feedback-store-path .runs/review_feedback.jsonl
```

Run Promptfoo manually:

```bash
ENABLE_PROMPTFOO_EVALS=1 promptfoo eval -c evals/promptfoo.yaml
```

## Known Limits

- Promptfoo currently has only a small skeleton sample set, not the final 20-50 golden samples.
- LLM reviewer is wired but disabled by default and should be enabled only after checking `review_profile` configuration.
- Source enrichment depends on external site availability and can fail because of timeout, extraction quality, paywalls, or anti-bot behavior.
- The system is still a modular monolith. Langfuse, LangGraph, LlamaIndex, Haystack, Ragas, DeepEval, Argilla, and Label Studio are intentionally not part of the current runtime path.

## Recommended Next Step

Before Phase 6, prepare a clean commit boundary:

1. Review the large unstaged diff.
2. Decide whether to commit Phase 1-5 together or split by phase.
3. Run the verification baseline again immediately before commit.
4. Tag the commit message with the migration scope, for example `feat: add ai content quality pipeline phases 1-5`.
