# 09 Notion Review Schema

This file is the operational schema note for Phase 5. It separates fields written by the AI pipeline from fields edited by humans.

## AI-Written Properties

The exporter may create or update these properties:

- `Name`
- `Status`
- `Language`
- `Market`
- `Symbol`
- `Article Type`
- `AI Summary`
- `SEO Title`
- `SEO Description`
- `Search Intent`
- `Primary Keyword`
- `Candidate Titles`
- `Source Count`
- `Source URLs`
- `Usable Source Count`
- `Source Quality`
- `Brief Content Type`
- `Brief Confidence`
- `AI Review Readiness`
- `AI Grounding Score`
- `AI Depth Score`
- `AI Financial Safety Score`
- `Editor Ready Score`
- `Final Recommended Status`
- `Risk Level`
- `Prompt Version`
- `LLM Model`
- `Content Job Key`
- `Source Bundle Hash`
- `Pipeline Run ID`
- `Generated At`

Detailed source quality, brief, AI review, validators, and quality report data should stay in page blocks.

## Human-Edited Properties

Editors may fill these fields manually in Notion. The AI exporter should not write blank values into these fields during upsert.

- `Status`
- `Editor Score`
- `Rejection Reason`
- `Edited Headline`
- `Edited Summary`
- `Editor Notes`
- `Final Publish Decision`
- `Reviewed At`

Recommended property types:

| Property | Type |
|---|---|
| `Editor Score` | number, 1-5 |
| `Rejection Reason` | rich_text |
| `Edited Headline` | rich_text |
| `Edited Summary` | rich_text |
| `Editor Notes` | rich_text |
| `Final Publish Decision` | select: `publish`, `do_not_publish`, `revise` |
| `Reviewed At` | date |

## Status Mapping

Feedback sync maps these Notion statuses:

| Notion Status | Feedback Status |
|---|---|
| `Approved` | `approved` |
| `Published` | `published` |
| `Rejected` | `rejected` |
| `Needs Edit` | `needs_edit` |
| `Needs Rewrite` | `needs_rewrite` |
| `Needs Source Fix` | `needs_source_fix` |
| `Needs Compliance Fix` | `needs_compliance_fix` |
| `Needs Language Fix` | `needs_language_fix` |
| `Ignored` | `ignored` |

These statuses are intentionally ignored by feedback sync:

- `AI Draft`
- `Needs Review`
- `In Review`

## Sync Command

Feedback sync remains opt-in:

```bash
ENABLE_NOTION_FEEDBACK_SYNC=1 .venv/bin/python -m src.jobs.sync_notion_reviews --target notion_articles_id --dry-run
```

`--dry-run` is allowed without the env flag because it does not write to the feedback store.
For real writes, keep `ENABLE_NOTION_FEEDBACK_SYNC=1` in the command or pass `--force` for a one-off operator run:

```bash
ENABLE_NOTION_FEEDBACK_SYNC=1 .venv/bin/python -m src.jobs.sync_notion_reviews --target notion_articles_id
```

Remove `--dry-run` only after checking the parsed feedback payload.

## Feedback Report Data Quality

`report_feedback` includes a `summary.data_quality` section. It is used to keep human-review data clean before the records become prompt evaluation or model comparison samples.

Current warnings:

- `missing_stable_identifier`: neither `Content Job Key` nor Notion page id is available.
- `rejected_without_reason`: rejected page has no rejection reason or editor notes.
- `positive_status_with_negative_publish_decision`: approved/published status conflicts with `do_not_publish`.
- `negative_status_with_publish_decision`: rejected/needs-fix status conflicts with `publish`.
- `positive_status_with_low_editor_score`: approved/published item has editor score 1-2.
- `negative_status_with_high_editor_score`: rejected/needs-fix item has editor score 4-5.
- `source_metadata_warning`: Notion sync stored parse warnings in feedback metadata.
