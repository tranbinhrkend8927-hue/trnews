# Configuration Guide

Configuration lives under `config/`.

## `pipeline.yaml`

Defines markets, symbols, TradingView source settings, language, content task, LLM profiles, and Notion target bindings.

Important fields:

- `id`: stable market id used by CLI commands.
- `symbol`: article symbol, for example `USDIDR`.
- `tradingview.url`: source URL for readiness checks and documentation.
- `content.language`: language profile key.
- `content.source_policy`: minimum and maximum source requirements.
- `llm.draft_profile`: profile from `llm_profiles.yaml`.
- `notion.target`: target from `notion_targets.yaml`.

## `llm_profiles.yaml`

Defines providers and model profiles.

- Provider env fields should point to API key and base URL env vars.
- Profile env fields should point to model env vars such as `LLM_WRITER_MODEL`.
- Fallback values are for local validation only; production should use explicit env.

## `notion_targets.yaml`

Defines Notion parent targets.

- Prefer `parent_type: data_source`.
- Use env vars such as `NOTION_DATA_SOURCE_ID_ID`.
- Do not hard-code real Notion ids in config.

## `languages/*.yaml`

Defines language-specific writing rules, required sections, disclaimer text, SEO settings, slug rules, and optional Notion property names.

## Environment Variables

See `.env.example`.

Required for live LLM:

- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_DEFAULT_MODEL` or `LLM_WRITER_MODEL`

Required for live Notion:

- `NOTION_API_KEY`
- target-specific parent id, for example `NOTION_DATA_SOURCE_ID_ID`

## Add A Notion Target

1. Add a target under `config/notion_targets.yaml`.
2. Use a new env var for the data source id.
3. Add that env var to `.env.example`.
4. Run `python -m src.jobs.production_check --market <market> --require-notion`.

## Add An LLM Profile

1. Add provider settings if needed.
2. Add a profile under `profiles`.
3. Bind the profile in `pipeline.yaml`.
4. Run `python -m src.jobs.production_check --market <market> --require-real-llm`.
