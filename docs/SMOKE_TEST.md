# Smoke Test Guide

This document describes the current manual smoke flow for the forex news article
pipeline. It includes the approved-only Notion export check added in P15. It
does not add CMS export, publishing, or automatic approval.

## Prerequisites

- `.env` exists for local configuration.
- `POSTGRES_DSN` points to the target Postgres database.
- `forex_news` contains stored source news rows.
- `content_topics` contains at least one generated topic.
- OpenRouter is optional and is not used by default.
- Notion export is optional and is not used by the smoke runner.
- For real Notion export, `NOTION_API_KEY` plus `NOTION_DATA_SOURCE_ID` or
  `NOTION_PARENT_PAGE_ID` must be configured.

Default LLM provider behavior:

- The default provider is `mock`.
- OpenRouter is used only when `--provider openrouter` is passed explicitly.
- `live_llm` tests are skipped by default.

## Recommended Manual Flow

```text
fetch news
-> save DB
-> generate topic
-> generate selected draft dry-run
-> save selected draft as pending_review
-> review report
-> review decision dry-run
-> manual review save-db via review_article.py
-> optional approved-only Notion export
```

## Example Commands

Fetch news and save it to the database:

```bash
python fetch_forex_news_json.py --symbol USDIDR --save-db
```

Generate content topics:

```bash
python generate_content_topics.py --symbol USDIDR --save-db
```

Run the selected candidate smoke flow without writing to the database:

```bash
python smoke_article_pipeline.py --topic-id 1 --candidate template --dry-run
```

Save the explicitly selected template draft. This writes to `generated_articles`
and `article_sources`, and the saved article status must be `pending_review`.

```bash
python smoke_article_pipeline.py --topic-id 1 --candidate template --save-selected-draft
```

Build a review report without writing to the database:

```bash
python smoke_article_pipeline.py --article-id 1 --review-report
```

Validate a review decision in dry-run mode. This does not insert
`article_reviews` and does not update `generated_articles.status`.

```bash
python smoke_article_pipeline.py --article-id 1 --review-decision approved --reviewer editor --notes "Smoke test review" --dry-run
```

If the dry-run review is valid and a human editor wants to make the decision
real, use the P8 review CLI explicitly:

```bash
python review_article.py --article-id 1 --decision approved --reviewer editor --notes "Reviewed sources" --save-db
```

Dry-run an approved-only Notion export. This does not call Notion and does not
write `article_exports`:

```bash
python export_article_to_notion.py --article-id 1 --dry-run
```

Export an already approved article to Notion and record the export history:

```bash
python export_article_to_notion.py --article-id 1 --export
```

## LLM Dry-Run Examples

Mock provider, no real LLM call:

```bash
python smoke_article_pipeline.py --topic-id 1 --candidate llm --provider mock --dry-run
```

OpenRouter provider, explicit opt-in:

```bash
python smoke_article_pipeline.py --topic-id 1 --candidate llm --provider openrouter --dry-run
```

OpenRouter requires environment configuration such as `OPENROUTER_API_KEY` and
`OPENROUTER_DEFAULT_MODEL`. Do not place API keys in code, tests, logs, or
fixtures.

## Write Boundaries

- `--dry-run` does not write selected drafts.
- `--save-selected-draft` writes `generated_articles` and `article_sources`.
- `--save-selected-draft` never writes `article_reviews`.
- Review decision smoke is dry-run only.
- Real review writes are handled by `review_article.py --save-db`.
- Notion export is handled only by `export_article_to_notion.py`.
- `export_article_to_notion.py --export` writes `article_exports` only.
- Notion export never updates `generated_articles.status`.
- There is no current publish command.
- There is no current CMS export.

## Safety Boundaries

- A saved selected draft must have `status = pending_review`.
- `approved` can only be produced by the P8 human review workflow.
- Only `status = approved` articles can be exported to Notion.
- `pending_review`, `draft`, `rejected`, and `published` articles cannot be
  exported by P15.
- There is no automatic path to `published`.
- `needs_sources`, safety failed, or quality blocked content cannot be saved or
  approved.
- Notion export does not publish and does not change article status.
- Notion is an export target only, not the source of truth.
- Notion API keys must stay in environment variables and must not be written to
  code, logs, database JSON, or CLI output.
- LLM output must pass through safety validation, draft quality checks, and
  comparison or selected-candidate validation.
- LLM source references do not replace the real `source_bundle`.
- `article_sources` must be built from stored source rows, not from invented LLM
  metadata.

## Test Commands

Default test suite:

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
