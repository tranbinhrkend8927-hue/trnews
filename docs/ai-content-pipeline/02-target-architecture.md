# 02 目标架构与模块边界

## 目标系统定位

目标不是“AI 一键写文章工具”，而是：

```text
外汇新闻深度文章生产流水线
```

它必须知道：

1. 什么时候可以写。
2. 什么时候不该写。
3. 应该从什么角度写。
4. 文章来源是否足够。
5. 是否有读者价值。
6. 是否需要人工编辑介入。
7. 哪些 prompt、模型、来源组合表现更好。

## 核心设计原则

1. AI 不直接决定事实，来源决定事实。
2. Writer 负责表达，Reviewer 负责挑错。
3. Deterministic validators 负责硬规则，AI Reviewer 负责软质量判断。
4. Notion 不只是文章存放处，也应该是编辑审核工作台和反馈入口。
5. 核心数据结构化，不靠字符串拼接。
6. 所有 LLM 输出可验证、可重试、可降级。
7. 模块可测试、可替换、可关闭。
8. 采用分阶段、小步可运行，不一次性大重构。
9. 优先模块化单体，不先做微服务。
10. 当前不引入 LangGraph、Haystack、LlamaIndex、Ragas、DeepEval、Argilla、Label Studio。

## 目标 pipeline

```text
fetch_sources
-> enrich_sources
-> deduplicate_sources
-> build_source_bundle
-> source_quality_gate
-> topic_angle_planning
-> generate_editorial_brief
-> validate_editorial_brief
-> write_article
-> ai_review
-> deterministic_validate
-> optional_rewrite_if_enabled
-> generate_quality_report
-> export_to_notion
-> collect_editor_feedback
-> eval_and_prompt_iteration
```

## 推荐模块化单体结构

近期新增：

```text
src/models/
  source.py
  brief.py
  review.py
  quality.py
  feedback.py
  pipeline.py

src/planning/
  __init__.py
  topic_planner.py
  brief_builder.py
  brief_validator.py

src/writing/
  __init__.py
  article_writer.py
  rewrite_engine.py

src/evals/
  __init__.py
  promptfoo_runner.py
```

继续保留：

```text
src/ingest/
src/content/
src/llm/
src/notion/
src/review/
src/observability/
src/jobs/
src/config/
```

暂不建议迁移：

- 不把 `src/content/article_pipeline.py` 一次性拆空。
- 不把所有 model 一次性搬到 `src/models/`。
- 不把 `src/notion/` 改名为 `src/export/`。
- 不大动 `news_pipeline/`。

## ingest 模块

职责：

- 获取新闻源。
- URL 正文抽取。
- metadata 抽取。
- 去重。
- 来源质量判断。
- 生成 SourceBundle 和 SourceQualityReport。

不应该做：

- 不写文章。
- 不判断标题。
- 不生成 Notion 页面。
- 不做 AI 审稿。

输入：

```text
MarketPipelineConfig
SourceFetchResult
```

输出：

```text
SourceBundle
SourceQualityReport
```

失败降级：

- fetch fail -> `SOURCE_FETCH_FAILED`
- enrichment fail -> 原 source + warning
- source weak -> `write_brief_only`
- source insufficient -> `skip_or_manual_review`

## planning 模块

职责：

- 判断选题是否值得写。
- 提炼事件。
- 判断为什么重要。
- 识别读者问题。
- 生成写作角度。
- 识别信息缺口。
- 生成结构化 EditorialBrief。

不应该做：

- 不直接写正文。
- 不替代 Reviewer。
- 不直接决定发布。

输入：

```text
SourceBundle
SourceQualityReport
Market config
Language config
```

输出：

```text
EditorialBrief
BriefValidationResult
```

失败降级：

- brief 缺核心字段 -> `NEEDS_BRIEF_REWRITE`
- confidence low -> `NEEDS_MANUAL_REVIEW`
- source gaps 严重 -> `WRITE_BRIEF_ONLY`

## writing 模块

职责：

- 根据 SourceBundle 和 EditorialBrief 生成 ArticleDraft。
- 生成标题、摘要、正文、FAQ、SEO 字段。
- 提供 rewrite interface。

不应该做：

- 不自己编造事实。
- 不自己判断是否可发布。
- 不绕过 Reviewer 和 validators。
- 不把无来源信息写成确定事实。

输入：

```text
EditorialBrief
SourceBundle
LanguageConfig
```

输出：

```text
ArticleDraft
LLMTaskResult
```

失败降级：

- invalid JSON -> retry once
- schema invalid -> repair prompt once
- still failed -> `LLM_FAILED`

## review 模块

职责：

- AI Reviewer 审稿。
- 判断 grounding、depth、readability、headline quality、financial safety。
- 输出结构化 AIReview。
- 生成 ArticleQualityReport。

不应该做：

- Reviewer 不直接改正文。
- Reviewer 不负责最终发布。
- Reviewer 不替代 deterministic validators。

输入：

```text
ArticleDraft
EditorialBrief
SourceBundle
SourceQualityReport
ValidationResult
```

输出：

```text
AIReview
ArticleQualityReport
```

失败降级：

- AI review 失败 -> deterministic only + Notion warning
- financial risk -> `Needs Compliance Fix` 或 `Rejected`

## validators 模块

职责：

- 硬规则检查。
- 投资建议检查。
- 夸张标题检查。
- 来源引用检查。
- 正文长度。
- FAQ。
- forbidden phrases。
- 免责声明。
- 格式。

不应该做：

- 不做主观审稿。
- 不判断文章“有没有深度”。
- 不替代 AI Reviewer。

## export 模块

职责：

- 把结构化数据映射到 Notion。
- 创建或更新 Notion 页面。
- 展示文章、brief、source quality、AI review、quality report、human feedback 字段。

不应该做：

- 不生成文章。
- 不调用 LLM。
- 不做内容判断。

## feedback 模块

职责：

- 从 Notion 读取人工审核结果。
- 结构化存储 editor feedback。
- 为 prompt eval、标题策略、reviewer rubric 提供数据。

初期继续使用：

```text
src/review/notion_sync.py
src/review/feedback_store.py
.runs/review_feedback.jsonl
```

## evals 模块

职责：

- 用 Promptfoo 管理黄金样本。
- 对 prompt/model 改动做 regression tests。
- 测试结构化输出、来源支撑、金融安全、标题质量、深度、非复述能力。

## 不建议当前做

1. 不建议马上引入 LangGraph。
2. 不建议马上引入 Haystack/LlamaIndex。
3. 不建议马上引入 Argilla/Label Studio。
4. 不建议一口气重构全部目录。
5. 不建议让 AI Reviewer 自动改正文。
6. 不建议来源不足时强行生成深度文章。

