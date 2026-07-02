# 04 分阶段落地路线图

## Phase 0：架构梳理与最小改造点确认

### 目标

- 固化当前 pipeline 事实。
- 保护当前可运行状态。
- 决定是否保留并提交当前未提交改动。
- 为 Phase 1 建立 baseline。

### 修改文件

只建议新增或更新文档：

```text
docs/ai-content-pipeline/*
```

### 新增文件

无代码文件。

### 新增配置

无。

### 主要逻辑

- 确认 `src/` 为新主线。
- 确认 `news_pipeline/` 为 legacy reference。
- 确认 Phase 1 插入点：`adapter.fetch()` 后、`SourceBundleBuilder.build()` 前。
- 确认 Notion 仍是唯一人审入口。

### 测试方案

```bash
git status --short
.venv/bin/python -m pytest
python -m src.jobs.production_check --market usd_idr_id
python -m src.jobs.smoke_test --market usd_idr_id
```

### 验收标准

- 当前工作区状态明确。
- 全量测试通过。
- roadmap 文档落地。
- 未修改运行逻辑。

### 风险

- 当前已有未提交代码改动，可能与后续 Phase 混在一起。

### 回滚方案

- Phase 0 只涉及文档，可直接 revert 文档。

### 复杂度

低。

---

## Phase 1：Source Enrichment + Source Quality Gate

### 目标

解决 TradingView/DB 新闻正文太短、AI 写空话的问题。

### 修改文件

```text
requirements.txt
src/content/source_bundle.py
src/content/article_pipeline.py
src/jobs/run_market.py
src/jobs/run_batch.py
src/config/models.py
src/config/validator.py
src/notion/mapper.py
src/observability/events.py
src/observability/quality.py
config/pipeline.yaml
.env.example
```

### 新增文件

```text
src/models/source.py
src/ingest/source_enricher.py
src/ingest/source_quality.py

tests/test_source_enricher.py
tests/test_source_quality.py
tests/test_article_pipeline_source_quality.py
```

### 新增依赖

```text
trafilatura
```

### 新增配置

```text
ENABLE_SOURCE_ENRICHMENT=0
SOURCE_ENRICHMENT_TIMEOUT_SECONDS=8
MIN_ENRICHED_TEXT_LENGTH=600
MIN_USABLE_SOURCE_COUNT=2
ENABLE_SOURCE_QUALITY_GATE=0
```

可选 YAML 配置：

```yaml
content:
  source_quality:
    min_usable_sources: 2
    min_text_length: 600
    allow_brief_only: true
```

### 数据模型

- `SourceEnrichmentResult`
- `SourceQualityReport`

### 主要逻辑

```text
adapter.fetch()
-> maybe enrich_sources(fetch_result.items)
-> dedupe enriched sources
-> build_source_quality_report()
-> SourceBundleBuilder.build(..., enrichment, quality)
-> source_quality_gate()
```

### 降级策略

- URL 为空：跳过 enrichment，记录 warning。
- Trafilatura timeout：`extraction_quality=failed`。
- metadata 缺失：保留原 source metadata。
- 正文过短：`extraction_quality=poor`。
- 多 source 重复：记录 `duplicate_count`。
- quality insufficient：不调用 writer，返回 `SOURCE_QUALITY_INSUFFICIENT` 或生成 topic candidate。

### 测试方案

Unit tests：

- 成功抽取正文。
- 抽取失败。
- 正文过短。
- metadata 缺失。
- URL 为空。
- 多 source 去重。
- source quality insufficient 降级。

Integration tests：

- fetch -> enrich -> quality gate。
- insufficient 不调用 LLM。
- Notion preview 包含 SourceQualityReport。

### 验收标准

1. 现有新闻获取流程不被破坏。
2. 抓取失败时 pipeline 不崩溃。
3. 来源质量不足时不会生成假深度文章。
4. Notion 中能看到 SourceQualityReport。
5. 默认关闭 enrichment 时，现有 pipeline 行为不变。
6. 全量 pytest 通过。

### 风险

- Trafilatura 对部分站点抽取失败。
- 新闻站点可能反爬。
- 增加运行耗时。

### 回滚方案

```text
ENABLE_SOURCE_ENRICHMENT=0
ENABLE_SOURCE_QUALITY_GATE=0
```

### 复杂度

中。

---

## Phase 2：Structured EditorialBrief

### 目标

把当前字符串 `article_brief` 改为强类型对象，让系统可以稳定检查 brief 是否完整。

### 修改文件

```text
src/content/article_pipeline.py
src/llm/prompts/article_draft/spec.yaml
src/llm/prompts/article_draft/user_payload.jinja.md
src/llm/prompt_renderer.py
src/notion/mapper.py
src/observability/events.py
```

### 新增文件

```text
src/models/brief.py
src/planning/__init__.py
src/planning/topic_planner.py
src/planning/brief_builder.py
src/planning/brief_validator.py

tests/test_editorial_brief.py
tests/test_brief_builder.py
tests/test_brief_validator.py
```

### 新增配置

```text
ENABLE_STRUCTURED_BRIEF=0
DEFAULT_CONTENT_TYPE=deep_article
```

### 数据模型

- `EditorialBrief`
- `BriefValidationResult`

### 主要逻辑

```text
SourceBundle + SourceQualityReport
-> TopicPlanner
-> BriefBuilder
-> BriefValidator
-> Writer
```

### Writer 输入

从：

```python
{"article_brief": "string"}
```

改为：

```python
{
  "editorial_brief": editorial_brief,
  "source_bundle": compact_source_bundle,
  "source_quality_report": source_quality_report,
  "language_profile": language_profile,
}
```

保留临时 formatter：

```python
format_editorial_brief_for_prompt(brief)
```

### 降级策略

- brief 缺核心字段 -> `NEEDS_BRIEF_REWRITE`
- confidence low -> `NEEDS_MANUAL_REVIEW`
- source gaps 严重 -> `WRITE_BRIEF_ONLY`

### 测试方案

- brief 完整。
- brief 缺 event_summary。
- brief 缺 why_it_matters。
- source gaps 存在。
- confidence low。
- content_type 分支。
- writer 接收 structured brief。

### 验收标准

1. `article_brief` 不再只是字符串。
2. Writer 使用结构化 brief。
3. 缺核心字段必须失败或返修。
4. Notion 中能看到 AI 按什么角度写作。
5. 默认关闭时旧 pipeline 不破坏。

### 风险

- prompt 输入结构变化影响 LLM 输出。
- 旧测试依赖 `article_brief` 字符串。

### 回滚方案

```text
ENABLE_STRUCTURED_BRIEF=0
```

### 复杂度

中。

---

## Phase 3：AI Reviewer

### 目标

新增真正的 AI Reviewer，负责审稿、评分和指出问题，不负责写作。

### 修改文件

```text
src/content/article_pipeline.py
src/llm/build_messages.py
src/llm/model_policies.py
src/notion/mapper.py
src/observability/events.py
config/llm_profiles.yaml
```

### 新增文件

```text
src/models/review.py
src/review/article_reviewer.py
src/llm/prompts/article_review/spec.yaml
src/llm/prompts/article_review/id.system.md
src/llm/prompts/article_review/user_payload.jinja.md

tests/test_ai_reviewer.py
tests/test_article_pipeline_ai_review.py
```

### 新增配置

```text
ENABLE_AI_REVIEWER=0
AI_REVIEW_MIN_READY_SCORE=75
AI_REVIEW_REJECT_ON_FINANCIAL_SAFETY=1
```

### 数据模型

- `AIReview`
- `AIReviewScores`
- `AIReviewIssue`

### 主要逻辑

```text
ArticleDraft + EditorialBrief + SourceBundle + SourceQualityReport
-> AIReviewer
-> AIReview
-> determine review status
```

### Reviewer 必须判断

- 是否有无来源支撑的 claim。
- 是否只是复述新闻。
- 是否缺少市场背景。
- 标题是否夸张。
- 是否存在金融安全风险。
- 是否包含投资建议。
- 是否过度推断。
- 是否适合进入 Notion 人审。

### 状态映射

```text
ready      -> Needs Review
needs_edit -> Needs Edit
reject     -> Needs Rewrite 或 Rejected
```

### 测试方案

- ready case。
- needs_edit case。
- reject case。
- unsupported claims -> not ready。
- financial safety issue -> reject/needs_edit。
- reviewer LLM failed -> deterministic only + warning。
- Reviewer 不改正文。

### 验收标准

1. Reviewer 输出结构化 AIReview。
2. Reviewer 不直接改正文。
3. unsupported claims 存在时不能 ready。
4. financial safety issue 存在时必须 reject 或 needs_edit。
5. Notion 中展示 review scores 和主要问题。
6. 默认关闭时现有 pipeline 不变。

### 风险

- AI reviewer 误判。
- 增加 LLM 成本和耗时。
- 不同模型打分不稳定。

### 回滚方案

```text
ENABLE_AI_REVIEWER=0
```

### 复杂度

中高。

---

## Phase 4：ArticleQualityReport + Promptfoo Evals

### 目标

建立可回归的质量评估体系，避免 prompt 改动只能靠人工感觉判断。

### 修改文件

```text
src/content/article_pipeline.py
src/notion/mapper.py
src/observability/events.py
docs/OPERATIONS_RUNBOOK.md
```

### 新增文件

```text
src/models/quality.py
src/review/quality_report.py
src/evals/promptfoo_runner.py

evals/promptfoo.yaml
evals/samples/usd_idr/*.json

tests/test_article_quality_report.py
tests/test_promptfoo_config.py
```

### 新增配置

```text
ENABLE_QUALITY_REPORT=0
ENABLE_PROMPTFOO_EVALS=0
```

### 数据模型

- `ArticleQualityReport`

### Promptfoo 测试维度

1. 是否输出完整结构化 JSON。
2. 是否包含来源支撑。
3. 是否避免投资建议。
4. 标题是否不过度夸张。
5. 是否只是复述新闻。
6. 是否包含宏观/市场背景。
7. 是否明确 source gaps。
8. 是否没有编造事实。
9. 是否适合 Notion 人审。
10. 是否符合目标语言和风格。

### 验收标准

1. 可以本地运行 eval。
2. 至少有 20 个固定测试样本。
3. prompt 改动后可以比较新旧输出。
4. 有明确 pass/fail 或 score。
5. CI 中可以选择性运行 eval。
6. eval 默认不阻塞日常开发。

### 风险

- 准备黄金样本耗时。
- eval 需要 LLM 成本。
- 自动评估不等于真实编辑判断。

### 回滚方案

```text
ENABLE_PROMPTFOO_EVALS=0
```

### 复杂度

中。

---

## Phase 5：Notion 人审与反馈回流

### 目标

让 Notion 从文章存放处升级为编辑审核工作台。

### 修改文件

```text
src/notion/mapper.py
src/review/feedback.py
src/review/notion_sync.py
src/jobs/sync_notion_reviews.py
src/jobs/report_feedback.py
config/notion_targets.yaml
docs/VALIDATION_FLOW.md
docs/OPERATIONS_RUNBOOK.md
```

### 新增配置

```text
ENABLE_NOTION_FEEDBACK_SYNC=0
```

### 主要逻辑

- Notion 页面展示 Article Draft。
- 展示 Source Quality。
- 展示 Editorial Brief。
- 展示 AI Review。
- 展示 ArticleQualityReport。
- 提供 Human Review Feedback 字段。
- sync job 把 Notion feedback 写回本地 JSONL。

### 验收标准

1. Notion 可作为审核工作台。
2. 编辑能看到为什么写、来源够不够、AI 怎么评。
3. feedback sync 能结构化保存审核结果。
4. 现有 upsert 不破坏。

### 当前实现状态

已完成：

- Notion properties 展示 source quality、structured brief、AI review、quality report 摘要。
- Notion blocks 展示 article draft、EditorialBrief、SourceQualityReport、AIReview、ArticleQualityReport、validators。
- feedback sync 支持 `Editor Score`、`Rejection Reason`、`Edited Headline`、`Edited Summary`、`Editor Notes`、`Final Publish Decision`、`Reviewed At`。
- feedback sync 默认关闭；`--dry-run` 可直接运行，真实写入需要 `ENABLE_NOTION_FEEDBACK_SYNC=1` 或 `--force`。
- feedback report 输出 `summary.data_quality`，用于发现人审数据缺字段或状态冲突。

验收命令：

```bash
.venv/bin/python -m pytest tests/test_notion_mapper.py tests/test_notion_exporter_dry_run.py tests/test_notion_exporter.py tests/test_sync_notion_reviews_cli.py tests/test_review_notion_sync.py tests/test_review_metrics.py tests/test_report_feedback_cli.py tests/test_review_feedback.py
.venv/bin/python -m pytest
.venv/bin/python -m src.jobs.production_check --market usd_idr_id
.venv/bin/python -m src.jobs.smoke_test --market usd_idr_id
```

### 风险

- Notion schema 手工配置易错。
- 字段过多影响编辑体验。

### 回滚方案

- 保留旧 mapper。
- feedback sync 可关闭。
- 详细信息只放 blocks，不依赖 properties。

### 复杂度

中。

---

## Phase 6：后续增强

### Langfuse

用途：

- LLM tracing。
- prompt version。
- model version。
- token / latency / cost。
- review score 回流。
- human feedback score。
- prompt / model 对比。

时机：

- pipeline 稳定后再接入。

### Ragas / DeepEval

用途：

- 50-100 篇人工审核样本后，用于自动评分校准。

时机：

- 暂不引入。

### Argilla / Label Studio

用途：

- 审核量变大后形成训练/评测数据集。

时机：

- 当前 Notion 足够做人审入口。

### LangGraph

用途：

- 多 agent。
- 可中断流程。
- human-in-the-loop。
- 失败恢复。
- 状态持久化。

时机：

- 当前线性 pipeline 不需要。

### Haystack / LlamaIndex

用途：

- 宏观知识库。
- 历史文章检索。
- 央行事件库。
- 自动内链。
- RAG。

时机：

- 等需要知识库和历史语境时再考虑。
