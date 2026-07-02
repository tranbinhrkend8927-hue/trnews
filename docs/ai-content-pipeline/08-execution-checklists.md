# 08 执行检查清单

## Phase 0 检查清单

开工前：

- [x] 运行 `git status --short`。
- [x] 确认是否保留当前未提交改动。
- [x] 运行 `.venv/bin/python -m pytest`。
- [x] 运行 `python -m src.jobs.production_check --market usd_idr_id`。
- [x] 运行 `python -m src.jobs.smoke_test --market usd_idr_id`。

完成后：

- [x] 文档已保存。
- [x] 没有修改运行逻辑。
- [x] baseline 测试结果记录在最终说明中。

## Phase 1 检查清单

开工前：

- [x] 确认是否接受新增 `trafilatura` 依赖。
- [x] 确认默认 `ENABLE_SOURCE_ENRICHMENT=0`。
- [x] 确认 deep article 最低 usable source 数量。
- [x] 确认来源不足时的动作：skip / brief_only / topic_candidate。

实现：

- [x] 新增 `SourceEnrichmentResult`。
- [x] 新增 `SourceQualityReport`。
- [x] 新增 `source_enricher.py`。
- [x] 新增 `source_quality.py`。
- [x] pipeline 接入 enrichment。
- [x] pipeline 接入 quality gate。
- [x] Notion 展示 SourceQualityReport。
- [x] event 记录 source quality。

测试：

- [x] 成功抽取正文。
- [x] 抽取失败。
- [x] 正文过短。
- [x] metadata 缺失。
- [x] 多 source 去重。
- [x] source quality insufficient 降级。
- [x] 默认关闭 enrichment 时现有 pipeline 行为不变。
- [x] 全量 pytest。

完成说明必须包含：

- [x] 修改文件。
- [x] 新增文件。
- [x] 新增模型。
- [x] 新增配置项。
- [x] 如何运行。
- [x] 如何测试。
- [x] 测试结果。
- [x] 当前限制。
- [x] 是否影响现有 pipeline。
- [x] 下一阶段建议。

## Phase 2 检查清单

开工前：

- [x] SourceQualityReport 已稳定。
- [x] 确认 `EditorialBrief` 必填字段。
- [x] 确认 `content_type` 分支。

实现：

- [x] 新增 `EditorialBrief`。
- [x] 新增 `BriefBuilder`。
- [x] 新增 `BriefValidator`。
- [x] Writer 接收 structured brief。
- [x] 保留字符串 formatter fallback。
- [x] Notion 展示 brief 字段。

测试：

- [x] brief 完整。
- [x] brief 缺核心字段。
- [x] source gaps 存在。
- [x] confidence low。
- [x] content_type 不同分支。
- [x] writer 接收 structured brief。
- [x] fallback 仍工作。

## Phase 3 检查清单

开工前：

- [x] writer 输出稳定。
- [x] structured brief 已稳定。
- [x] 确认 AI reviewer 默认关闭。

实现：

- [x] 新增 `AIReview`。
- [x] 新增 `article_reviewer.py`。
- [x] 新增 article_review prompt。
- [x] pipeline 接入 reviewer。
- [x] Notion 展示 review scores/issues。
- [x] event 记录 AIReview。

测试：

- [x] ready。
- [x] needs_edit。
- [x] reject。
- [x] unsupported claims 不能 ready。
- [x] financial safety issue 不能 ready。
- [x] reviewer failure 不崩溃。
- [x] reviewer 不改正文。

## Phase 4 检查清单

开工前：

- [ ] 至少准备 20 个样本来源。
- [x] 确认 Promptfoo 是否安装。

实现：

- [x] 新增 `ArticleQualityReport`。
- [x] 新增 quality report builder。
- [x] 新增 `evals/promptfoo.yaml`。
- [x] 新增 samples。
- [x] 文档说明 eval 运行方式。

测试：

- [x] quality report score。
- [x] blocking issue 降分。
- [x] AIReview reject -> final rejected。
- [x] Promptfoo config 可解析。
- [x] eval 默认不影响 pytest。

未完成：

- [ ] 将 `evals/samples/` 扩展到 20-50 个历史外汇新闻黄金样本。
- [ ] 决定 Promptfoo rubric judge provider/model。
- [ ] 选择是否在 CI 中按环境变量运行 eval。

## Phase 5 检查清单

开工前：

- [ ] 确认 Notion data source 可新增字段。
- [ ] 确认 status 枚举。
- [ ] 确认哪些字段做 property，哪些放 block。

实现：

- [x] Notion property 增加 source quality。
- [x] Notion property 增加 AI review。
- [x] Notion blocks 展示 brief/source/review/quality report。
- [x] feedback sync 支持新增字段。
- [x] feedback report 支持新字段。
- [x] feedback report 输出 data quality warnings。

测试：

- [x] dry-run payload 包含新字段。
- [x] upsert 不破坏旧页面。
- [x] review sync 可读取 status 和 scores。
- [x] missing optional property 不失败。
- [x] feedback sync 默认关闭，dry-run 可运行。

## Phase 6 检查清单

仅在 Phase 1-5 稳定后考虑：

- [ ] Langfuse tracing。
- [ ] Ragas/DeepEval 评分校准。
- [ ] Argilla/Label Studio 数据集。
- [ ] LangGraph 多 agent 编排。
- [ ] Haystack/LlamaIndex 知识库和 RAG。

## Optional Rewrite Interface 检查清单

实现：

- [x] 新增 `RewritePlan`。
- [x] 新增 plan-only rewrite engine。
- [x] 新增 `ENABLE_OPTIONAL_REWRITE=0`。
- [x] pipeline 可选接入 rewrite plan。
- [x] Notion blocks 展示 rewrite plan。
- [x] 当前阶段不自动改写正文。

测试：

- [x] 默认关闭时 pipeline 不输出 rewrite_plan。
- [x] 开启后生成 rewrite_plan。
- [x] rewrite_plan 不修改 article body。
- [x] rejected / validator failed draft 进入 blocked plan。

## 每次提交前通用检查

```bash
git status --short
.venv/bin/python -m pytest
git diff --check
python -m src.jobs.production_check --market usd_idr_id
```

如果修改 Notion：

```bash
python -m src.jobs.run_market --market usd_idr_id --dry-run --include-notion-preview
```

如果修改 prompt：

```bash
.venv/bin/python -m pytest tests/test_prompt_renderer.py tests/test_unified_llm_task.py
```

如果修改 source：

```bash
.venv/bin/python -m pytest tests/test_ingest_normalize.py tests/test_tradingview_adapter.py tests/test_source_bundle.py
```

如果修改 feedback：

```bash
.venv/bin/python -m pytest tests/test_review_feedback.py tests/test_review_notion_sync.py tests/test_sync_notion_reviews_cli.py
```
