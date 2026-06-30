# Pipeline Status

This document records the current checkpoint status after P13. It is a readiness
summary for manual smoke testing and future checkpoint commits. It does not
enable Notion export, CMS export, publishing, or automatic approval.

## Stage Overview

- P0/P1: News fetching, JSON summaries, Postgres schema initialization, database
  insert, and deduplication.
- P1.5: Test baseline governance and default test stability.
- P2: `content_topics` generation from stored forex news.
- P3: `generated_articles` draft shell structure.
- P4: Rule-based `safety_validation`.
- P5: Rule-template Indonesian article drafts.
- P6: Source grounding and source enrichment through `source_bundle` and
  `article_sources`.
- P7: Draft quality gate.
- P8: Human review workflow, review reports, and review records.
- P9: Provider-agnostic LLM Gateway with OpenRouter and mock providers.
- P10: LLM article draft candidate dry-run.
- P11: Template vs LLM candidate comparison dry-run.
- P12: Explicit editor-selected candidate save as `pending_review`.
- P13: End-to-end smoke runner for topic, selected save, review report, and
  review decision dry-run.

## Main Pipeline

```text
forex_news
-> content_topics
-> source_bundle
-> template / LLM candidate
-> comparison
-> explicit editor selection
-> generated_articles pending_review
-> article_sources
-> review report
-> human review approved/rejected/needs_changes
```

## Current CLI Entry Points

- `fetch_forex_news_json.py`
- `generate_content_topics.py`
- `generate_article_drafts.py`
- `generate_llm_article_draft.py`
- `compare_article_drafts.py`
- `save_selected_article_draft.py`
- `review_article.py`
- `smoke_article_pipeline.py`

## Current Test Commands

Run the default suite:

```bash
.venv/bin/python -m pytest
```

Confirm live LLM tests are skipped by default:

```bash
.venv/bin/python -m pytest -m live_llm
```

Run live LLM tests manually:

```bash
RUN_LLM_LIVE=1 .venv/bin/python -m pytest -m live_llm
```

## Current Automation Boundaries

- No automatic publish.
- No automatic approve.
- No Notion export yet.
- No CMS export yet.
- No unreviewed article publishing.
- No default real OpenRouter calls.
- No default real network calls in tests.
- No save path should set `status = published`.
- P12 save paths can only create selected drafts as `pending_review`.
- P8 human review is required before an article can become `approved`.

## Checkpoint Commit Grouping Suggestion

Do not run these commands automatically. This is only a suggested grouping for a
future checkpoint plan.

- Commit 1: fetch/db/topic foundation.
- Commit 2: draft/safety/source grounding/quality.
- Commit 3: review workflow.
- Commit 4: LLM gateway and dry-run candidate.
- Commit 5: comparison and selected save.
- Commit 6: smoke runner and docs.

## Next Step Suggestions

- P14B: Create an explicit checkpoint commit plan and review the dirty worktree
  before staging.
- P15: Add Notion export for approved articles only.
- P16: Add `article_exports` table or exporter tracking so outbound exports are
  auditable and idempotent.
