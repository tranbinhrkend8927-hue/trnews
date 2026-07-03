# 01 当前架构梳理

## 当前项目结构

当前项目有两条历史线：

```text
src/
  config/              新配置系统
  ingest/              新采集适配层
  content/             新文章流水线、ArticleDraft、SourceBundle、validators
  llm/                 新统一 LLM runner、prompt renderer、model policy
  notion/              新 Notion target resolver、mapper、exporter、client
  jobs/                新 CLI
  observability/       JSONL event、quality summary、metrics
  review/              Notion review feedback sync、本地 review feedback store

news_pipeline/
  legacy pipeline      旧版数据库文章生成、review、quality、Notion export、Postgres schema

config/
  pipeline.yaml
  llm_profiles.yaml
  notion_targets.yaml
  languages/id.yaml
```

后续改造应以 `src/` 为主线，`news_pipeline/` 只作为 legacy reference 和少量可复用逻辑来源。

## 当前主入口

主要入口：

- `src/jobs/run_market.py`
- `src/jobs/run_batch.py`
- `src/jobs/smoke_test.py`
- `src/jobs/production_check.py`
- `src/jobs/sync_notion_reviews.py`

核心构建函数：

```python
src.jobs.run_market.build_pipeline()
```

它根据参数选择：

- `PostgresNewsAdapter`
- `RefreshingPostgresNewsAdapter`
- `TradingViewNewsAdapter`
- `LLMTaskRunner`
- `NotionDryRunExporter`
- `NotionRealExporter`
- `NotionUpsertExporter`

## 当前 source fetch

主要文件：

- `src/ingest/tradingview.py`
- `src/ingest/postgres_news.py`
- `src/ingest/normalize.py`
- `src/ingest/dedupe.py`

当前 live TradingView 流程：

```text
TradingViewNewsAdapter.fetch()
-> _fetch_raw_items()
-> normalize_tradingview_item()
-> dedupe_news_items()
-> SourceFetchResult
```

当前 DB source 流程：

```text
PostgresNewsAdapter.fetch()
-> SELECT forex_news
-> _row_to_news_item()
-> SourceFetchResult
```

当前 refresh DB 流程：

```text
RefreshingPostgresNewsAdapter.fetch()
-> legacy news_pipeline.fetch_forex_news_json
-> save_result_to_postgres()
-> PostgresNewsAdapter.fetch()
```

## 当前 TradingView 新闻源处理逻辑

`NormalizedNewsItem` 字段：

```python
source_id
provider
symbol
exchange
language
locale
title
summary
content
url
canonical_url
published_at
fetched_at
raw
```

当前不足：

- 没有独立 URL 正文抽取。
- 没有 `SourceEnrichmentResult`。
- 没有 `SourceQualityReport`。
- 无法区分“能写深度文章”和“只能写短 brief”。
- 来源太短时，后续 writer 仍可能被调用。

## 当前 SourceBundle

文件：

```text
src/content/source_bundle.py
```

当前职责：

- 接收 `SourceFetchResult`。
- 根据 source policy 截断 max sources。
- 检查 fetch 是否成功。
- 检查 min sources。
- 检查是否有 content 或 summary。
- 生成 `bundle_id` 和 `source_trace`。

当前 `SourceBundle` 仍较薄：

```python
bundle_id
market_id
symbol
language
sources
source_bundle_hash
missing_source_ids
warnings
errors
source_trace
```

缺少：

- enriched sources
- deduped source ids
- source quality report
- recommended action
- detected theme
- source gaps

## 当前 article_brief

位置：

```text
src/content/article_pipeline.py
```

函数：

```python
build_article_brief_for_llm()
```

当前状态：

- 已从短摘要升级为更深的字符串 brief。
- 包含 task、language、region、market、symbol、search intent、editorial brief 文本、required sections、merged sources。
- 仍然是字符串拼接，不是强类型对象。

关键问题：

- 系统不能验证 brief 是否完整。
- 系统不能判断 confidence。
- 系统不能基于 brief 字段做 Notion 展示和 eval。
- Writer prompt 仍消费 `article_brief` 字符串。

## 当前 writer prompt

路径：

```text
src/llm/prompts/article_draft/
  spec.yaml
  id.system.md
  ja.system.md
  user_payload.jinja.md
```

当前 prompt 只定义 writer，没有：

- brief prompt
- reviewer prompt
- rewrite prompt

`spec.yaml` 当前只要求：

```yaml
input_required:
  - article_brief
```

## 当前 LLM 调用

调用链：

```text
ArticlePipeline._run_llm_or_fake_article()
-> LLMTaskRunner.run()
-> run_llm_task()
-> build_messages()
-> get_model_policy()
-> OpenAICompatibleClient.create_response()
-> parse_llm_json()
-> validate_json_schema()
```

主要文件：

- `src/llm/task_runner.py`
- `src/llm/run_task.py`
- `src/llm/build_messages.py`
- `src/llm/model_policies.py`
- `src/llm/client.py`
- `news_pipeline/llm_schemas.py`

当前能力：

- OpenAI Responses API。
- `text.format=json_schema`。
- 本地 JSON schema 校验。
- 超时和重试。
- LLM profile 参数已开始传入 runner overrides。

当前不足：

- task/policy 逻辑仍偏旧。
- JSON schema 还放在 legacy `news_pipeline/llm_schemas.py`。
- 没有 `EditorialBrief`、`AIReview`、`ArticleQualityReport` schema。
- 没有 repair retry prompt。

## 当前 validators

路径：

```text
src/content/validators/
```

当前 validator：

- `article_schema.py`
- `source_grounding.py`
- `language_rules.py`
- `depth_quality.py`
- `financial_safety.py`
- `notion_exportable.py`

当前边界：

- deterministic validators 已经能挡住格式、来源、安全、语言、Notion exportability。
- `depth_quality` 当前是 warning，不阻断导出。

缺口：

- 没有 SourceQualityGate。
- 没有 BriefValidator。
- 没有 AIReview。
- 没有综合 ArticleQualityReport。
- SEO/helpful content 还不系统。

## 当前 Notion export

路径：

```text
src/notion/
  target_resolver.py
  mapper.py
  exporter.py
  client.py
```

当前能力：

- dry-run payload。
- real create。
- upsert by Content Job Key。
- status 默认 `Needs Review`。
- blocks 展示 summary、body、FAQ、sources、risk disclaimer、validation、generation metadata。

当前缺口：

- SourceQualityReport 尚未展示。
- Structured EditorialBrief 尚未展示。
- AIReview scores 尚未展示。
- ArticleQualityReport 尚未展示。
- HumanFeedback 字段不完整。

## 当前 config / env

配置文件：

```text
config/pipeline.yaml
config/llm_profiles.yaml
config/notion_targets.yaml
config/languages/id.yaml
```

代码：

```text
src/config/loader.py
src/config/models.py
src/config/validator.py
```

当前配置能力：

- market/symbol/tradingview/source policy
- LLM provider/profile/model env
- Notion target
- language writing rules/SEO/slug/quality
- Notion field override

缺少 feature flags：

- source enrichment
- source quality gate
- structured brief
- AI reviewer
- optional rewrite
- quality report
- promptfoo eval
- Langfuse tracing

## 当前 Pydantic models

主要已有：

- `SourceFetchResult`
- `NormalizedNewsItem`
- `SourceBundle`
- `FAQItem`
- `SourceUsed`
- `UncertainClaim`
- `EditorialSuggestion`
- `ArticleDraft`
- `ValidationIssue`
- `ValidationResult`
- `LLMTaskError`
- `LLMTaskResult`
- `ResolvedNotionTarget`
- `NotionExportPayload`
- `NotionExportResult`
- `ObservationEvent`
- `ReviewFeedback`

缺少：

- `SourceItem`
- `SourceEnrichmentResult`
- `SourceQualityReport`
- `EditorialBrief`
- `AIReview`
- `ArticleQualityReport`
- `EditorFeedback`
- `PipelineContext`

## 当前测试覆盖

测试覆盖较好，包括：

- article pipeline
- schema
- source bundle
- source grounding
- financial safety
- language rules
- Notion mapper/exporter/client/upsert
- config registry
- production_check/smoke/run_market/run_batch
- observability
- review feedback sync
- legacy `news_pipeline`

Phase 0 historical baseline：

```text
800 passed, 29 skipped
```

Current implementation verification is tracked in [Implementation Status](10-implementation-status.md).

## 当前完整数据流

```text
CLI run_market
-> load_config_registry
-> choose source adapter
-> ArticlePipeline.run_market
-> adapter.fetch(market)
-> SourceBundleBuilder.build()
-> compute source_bundle_hash / content_job_key / pipeline_run_id
-> if source_bundle.errors: SOURCE_BUNDLE_FAILED
-> build_article_brief_for_llm()  # string
-> LLMTaskRunner.run() or _fake_article()
-> normalize article output
-> validators
-> if validation failed: VALIDATION_FAILED
-> dry-run Notion preview or real Notion export/upsert
-> optional job_store/event_store
```

## 当前最小侵入式改造点

1. 在 `adapter.fetch()` 后、`SourceBundleBuilder.build()` 前插入 source enrichment。
2. 扩展 `SourceBundle`，不替换它。
3. 新增 `EditorialBrief`，但先保留字符串 formatter 兼容 writer prompt。
4. 新增 `AIReview`，默认关闭。
5. Notion 先在 blocks 展示详细报告，property 只放核心字段。
