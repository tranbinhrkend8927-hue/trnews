# 08 执行检查清单

## Phase 0 检查清单

开工前：

- [ ] 运行 `git status --short`。
- [ ] 确认是否保留当前未提交改动。
- [ ] 运行 `.venv/bin/python -m pytest`。
- [ ] 运行 `python -m src.jobs.production_check --market usd_idr_id`。
- [ ] 运行 `python -m src.jobs.smoke_test --market usd_idr_id`。

完成后：

- [ ] 文档已保存。
- [ ] 没有修改运行逻辑。
- [ ] baseline 测试结果记录在最终说明中。

## Phase 1 检查清单

开工前：

- [ ] 确认是否接受新增 `trafilatura` 依赖。
- [ ] 确认默认 `ENABLE_SOURCE_ENRICHMENT=0`。
- [ ] 确认 deep article 最低 usable source 数量。
- [ ] 确认来源不足时的动作：skip / brief_only / topic_candidate。

实现：

- [ ] 新增 `SourceEnrichmentResult`。
- [ ] 新增 `SourceQualityReport`。
- [ ] 新增 `source_enricher.py`。
- [ ] 新增 `source_quality.py`。
- [ ] pipeline 接入 enrichment。
- [ ] pipeline 接入 quality gate。
- [ ] Notion 展示 SourceQualityReport。
- [ ] event 记录 source quality。

测试：

- [ ] 成功抽取正文。
- [ ] 抽取失败。
- [ ] 正文过短。
- [ ] metadata 缺失。
- [ ] 多 source 去重。
- [ ] source quality insufficient 降级。
- [ ] 默认关闭 enrichment 时现有 pipeline 行为不变。
- [ ] 全量 pytest。

完成说明必须包含：

- [ ] 修改文件。
- [ ] 新增文件。
- [ ] 新增模型。
- [ ] 新增配置项。
- [ ] 如何运行。
- [ ] 如何测试。
- [ ] 测试结果。
- [ ] 当前限制。
- [ ] 是否影响现有 pipeline。
- [ ] 下一阶段建议。

## Phase 2 检查清单

开工前：

- [ ] SourceQualityReport 已稳定。
- [ ] 确认 `EditorialBrief` 必填字段。
- [ ] 确认 `content_type` 分支。

实现：

- [ ] 新增 `EditorialBrief`。
- [ ] 新增 `BriefBuilder`。
- [ ] 新增 `BriefValidator`。
- [ ] Writer 接收 structured brief。
- [ ] 保留字符串 formatter fallback。
- [ ] Notion 展示 brief 字段。

测试：

- [ ] brief 完整。
- [ ] brief 缺核心字段。
- [ ] source gaps 存在。
- [ ] confidence low。
- [ ] content_type 不同分支。
- [ ] writer 接收 structured brief。
- [ ] fallback 仍工作。

## Phase 3 检查清单

开工前：

- [ ] writer 输出稳定。
- [ ] structured brief 已稳定。
- [ ] 确认 AI reviewer 默认关闭。

实现：

- [ ] 新增 `AIReview`。
- [ ] 新增 `article_reviewer.py`。
- [ ] 新增 article_review prompt。
- [ ] pipeline 接入 reviewer。
- [ ] Notion 展示 review scores/issues。
- [ ] event 记录 AIReview。

测试：

- [ ] ready。
- [ ] needs_edit。
- [ ] reject。
- [ ] unsupported claims 不能 ready。
- [ ] financial safety issue 不能 ready。
- [ ] reviewer failure 不崩溃。
- [ ] reviewer 不改正文。

## Phase 4 检查清单

开工前：

- [ ] 至少准备 20 个样本来源。
- [ ] 确认 Promptfoo 是否安装。

实现：

- [ ] 新增 `ArticleQualityReport`。
- [ ] 新增 quality report builder。
- [ ] 新增 `evals/promptfoo.yaml`。
- [ ] 新增 samples。
- [ ] 文档说明 eval 运行方式。

测试：

- [ ] quality report score。
- [ ] blocking issue 降分。
- [ ] AIReview reject -> final rejected。
- [ ] Promptfoo config 可解析。
- [ ] eval 默认不影响 pytest。

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
