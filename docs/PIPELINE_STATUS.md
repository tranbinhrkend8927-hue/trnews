# Pipeline Status

This document records the current checkpoint status through P15. It is a
readiness summary for manual smoke testing, approved-only Notion export, and
future checkpoint commits. It does not enable CMS export, publishing, or
automatic approval.

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
- P14A/P14B: Smoke documentation and checkpoint commit planning.
- P15: Notion export for approved articles only, with `article_exports` history
  records.

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
-> approved-only Notion export
-> article_exports
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
- `export_article_to_notion.py`

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

Confirm live Notion tests are skipped by default:

```bash
.venv/bin/python -m pytest -m live_notion
```

Run live Notion tests manually only when configured:

```bash
RUN_NOTION_LIVE=1 .venv/bin/python -m pytest -m live_notion
```

## Current Automation Boundaries

- No automatic publish.
- No automatic approve.
- Notion export is available only for `generated_articles.status = approved`.
- No CMS export yet.
- No unreviewed article publishing.
- No default real OpenRouter calls.
- No default real network calls in tests.
- No save path should set `status = published`.
- P12 save paths can only create selected drafts as `pending_review`.
- P8 human review is required before an article can become `approved`.
- P15 Notion export does not modify `generated_articles.status` and does not
  mark articles as `published`.
- `pending_review`, `draft`, `rejected`, and `published` articles are not
  exportable in P15.

## Notion Export

Dry-run an approved article export without calling Notion or writing
`article_exports`:

```bash
python export_article_to_notion.py --article-id 1 --dry-run
```

Export an approved article to Notion and write an `article_exports` record:

```bash
python export_article_to_notion.py --article-id 1 --export
```

Required environment for real export:

- `NOTION_API_KEY`
- `NOTION_DATA_SOURCE_ID` or `NOTION_PARENT_PAGE_ID`

The exporter stores sanitized request, response, and error summaries in
`article_exports`. It must not store API keys, Authorization headers, or full
raw Notion responses. Notion is an outbound export target, not the primary
database.

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

- P16: Add idempotency/re-export policy for `article_exports` if repeated
  exports need explicit handling.
- P17: Add CMS export only after approved-only export tracking is stable.
