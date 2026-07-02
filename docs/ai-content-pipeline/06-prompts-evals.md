# 06 Prompt、结构化输出与评测

## 目标

prompt 不再是单一 writer prompt，而是拆成多个明确任务：

```text
brief prompt
writer prompt
reviewer prompt
rewrite prompt
```

每个任务：

- 有独立目录。
- 有版本号。
- 有输入 schema。
- 有输出 schema。
- prompt 变更可跑 eval。

## 推荐 prompt 目录

```text
src/llm/prompts/editorial_brief/
  spec.yaml
  id.system.md
  user_payload.jinja.md

src/llm/prompts/article_draft/
  spec.yaml
  id.system.md
  user_payload.jinja.md

src/llm/prompts/article_review/
  spec.yaml
  id.system.md
  user_payload.jinja.md

src/llm/prompts/article_rewrite/
  spec.yaml
  id.system.md
  user_payload.jinja.md
```

## Prompt version

示例：

```yaml
name: article_review
version: article_review@2026-07-02
output_schema: ai_review_v1
input_required:
  - article
  - editorial_brief
  - source_bundle
  - source_quality_report
```

版本规则：

- 改 system prompt，升 version。
- 改 user payload，升 version。
- 改 output schema，升 version。
- prompt version 必须写入 Notion 和 event。

## 结构化输出

当前能力：

- OpenAI-compatible chat completions。
- `response_format=json_schema`。
- 本地 JSON schema validation。

目标：

- 所有 LLM 输出都经过 Pydantic validation。
- Writer 输出 `ArticleDraft`。
- Reviewer 输出 `AIReview`。
- Brief generator 输出 `EditorialBrief`。

如果 provider 支持原生 structured output：

- 优先使用。

如果跨 provider 输出不稳定：

- 后续考虑 Instructor。
- 不在 Phase 1-3 强制引入。

## Retry / Repair 策略

默认策略：

1. 首次 LLM 调用。
2. JSON parse 失败：retry 1 次。
3. Pydantic validation 失败：repair prompt 1 次。
4. 仍失败：降级。

降级：

- brief 失败 -> `NEEDS_BRIEF_REWRITE`
- writer 失败 -> `LLM_FAILED`
- reviewer 失败 -> deterministic only + Notion warning
- rewrite 失败 -> 保留原文 + warning

重试必须限制次数，默认：

```text
MAX_LLM_RETRIES=1
```

## Writer prompt 规则

writer 必须：

- 只使用 source bundle 和 editorial brief。
- 不编造价格、日期、机构、URL。
- 不给投资建议。
- 不把相关性写成因果性。
- 解释新闻为什么重要。
- 标明来源和不确定性。
- 输出目标语言。

writer 不应该：

- 判断是否发布。
- 自行修正 source gaps。
- 在来源不足时伪装深度分析。

## Reviewer prompt 规则

reviewer 输入：

- ArticleDraft
- EditorialBrief
- SourceBundle
- SourceQualityReport

reviewer 输出：

- AIReview

reviewer 判断：

- unsupported claims
- overstatements
- missing context
- headline risk
- financial safety
- source usefulness
- depth
- readability

reviewer 不应该：

- 直接改正文。
- 重新写文章。
- 给最终发布许可。

## Rewrite prompt 规则

Phase 1-3 只保留接口，默认关闭。

触发条件：

- `ENABLE_OPTIONAL_REWRITE=1`
- AIReview = `needs_edit`
- blocking validator 没有 financial safety fatal issue

输出仍必须是 `ArticleDraft`。

## Promptfoo Evals

建议目录：

```text
evals/
  promptfoo.yaml
  samples/
    usd_idr/
      sample_001.json
      sample_002.json
  assertions/
```

运行：

```bash
promptfoo eval -c evals/promptfoo.yaml
```

默认不进入普通 pytest。

## Golden sample

建议先准备 20 个样本：

- USDIDR
- 印尼语
- 不同 source quality
- 有完整正文
- 只有短摘要
- 多来源重复
- source gaps 明显
- 容易产生投资建议风险

样本结构：

```json
{
  "id": "usd_idr_001",
  "market_id": "usd_idr_id",
  "source_bundle": {},
  "expected": {
    "must_include_sections": [],
    "forbidden_phrases": [],
    "minimum_source_count": 1
  }
}
```

## Eval 维度

1. 输出完整结构化 JSON。
2. 包含来源支撑。
3. 避免投资建议。
4. 标题不过度夸张。
5. 不是简单复述新闻。
6. 包含宏观/市场背景。
7. 明确 source gaps。
8. 没有编造事实。
9. 适合 Notion 人审。
10. 符合目标语言和风格。

## CI 策略

默认 CI：

```bash
.venv/bin/python -m pytest
```

可选 CI job：

```bash
ENABLE_PROMPTFOO_EVALS=1 promptfoo eval -c evals/promptfoo.yaml
```

eval 不应阻塞日常开发，除非明确开启。

