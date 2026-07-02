# AI Content Pipeline 改造规划索引

本目录用于拆分保存外汇/财经 AI 内容生产系统的工程规划。拆分原因是避免单个超长文档在后续交给 LLM 或工程执行时造成上下文混淆。

当前目标不是一次性大重构，而是把现有流程：

```text
新闻源 -> prompt -> AI 生成文章 -> validators -> Notion
```

逐步升级为：

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

## 文档列表

1. [当前架构梳理](01-current-architecture.md)
   - 当前目录结构、主入口、source fetch、LLM writer、validators、Notion、config、测试覆盖和现有数据流。

2. [目标架构与模块边界](02-target-architecture.md)
   - 目标 pipeline、模块化单体设计、各模块职责、不该做的事、失败降级方式。

3. [核心数据模型设计](03-data-models.md)
   - SourceItem、SourceEnrichmentResult、SourceQualityReport、EditorialBrief、ArticleDraft、AIReview、ArticleQualityReport、EditorFeedback。

4. [分阶段落地路线图](04-phased-roadmap.md)
   - Phase 0 到 Phase 6，每个阶段的目标、文件改动、配置、测试、验收、风险和回滚。

5. [Notion 审核工作台与反馈回流](05-notion-feedback.md)
   - Notion schema、页面展示、字段类型、feedback sync、如何避免字段过多。

6. [Prompt、结构化输出与评测](06-prompts-evals.md)
   - prompt 管理、structured output、retry/repair、Promptfoo 黄金样本和回归评测。

7. [错误处理、降级策略与金融安全](07-error-handling-safety.md)
   - 失败场景、是否重试、是否进 Notion、是否阻断发布、financial safety 和 helpful content 规则。

8. [执行检查清单](08-execution-checklists.md)
   - 每个 phase 开工前、完成后、测试和验收清单。

9. [Notion Review Schema](09-notion-review-schema.md)
   - Phase 5 的 Notion 人审字段、状态映射、feedback sync 命令和数据质量 warning。

10. [Implementation Status](10-implementation-status.md)
    - Phase 1-5 当前实现状态、默认开关、验证基线、运行命令和已知限制。

## 当前工程状态备注

当前工作区已经实现 Phase 1-5 的主体能力，包括：

- Source enrichment 和 SourceQualityReport。
- Structured EditorialBrief。
- Deterministic/optional LLM AI reviewer。
- ArticleQualityReport。
- Promptfoo eval skeleton。
- Notion 审核工作台和 feedback sync。

当前验证基线记录在 [Implementation Status](10-implementation-status.md)。这些改动仍未提交，提交前应再次运行全量验证。

## 推荐执行顺序

```text
Phase 0: 架构梳理与最小改造点确认
Phase 1: Source Enrichment + Source Quality Gate
Phase 2: Structured EditorialBrief
Phase 3: AI Reviewer
Phase 4: ArticleQualityReport + Promptfoo Evals
Phase 5: Notion Feedback Loop
Phase 6: Langfuse / 数据集 / 大框架等后续增强
```

## 最小可行版本

最小可行版本建议只做：

1. Trafilatura 来源增强。
2. SourceQualityReport。
3. Source Quality Gate。
4. Structured EditorialBrief。
5. Notion 展示 source quality 和 brief。

先不要做 LangGraph、Haystack、LlamaIndex、Ragas、DeepEval、Argilla、Label Studio。
