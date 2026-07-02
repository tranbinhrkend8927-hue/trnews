# 05 Notion 审核工作台与反馈回流

## 目标

Notion 不只是文章存放处，而是编辑审核工作台和反馈入口。

页面应该让编辑快速判断：

1. 这篇文章在写什么。
2. 来源够不够。
3. AI 按什么角度写。
4. AI reviewer 发现了什么问题。
5. deterministic validators 有没有 blocking issue。
6. 是否适合发布、返修或拒绝。

## 当前 Notion 能力

当前 `src/notion/mapper.py` 已支持：

- Name
- Status
- Language
- Market
- Symbol
- Article Type
- AI Summary
- SEO Title
- SEO Description
- Search Intent
- Primary Keyword
- Candidate Titles
- Source Count
- Source URLs
- Risk Level
- Prompt Version
- LLM Model
- Content Job Key
- Source Bundle Hash
- Pipeline Run ID
- Generated At

Blocks 已展示：

- Review Note
- AI Summary
- Editorial Brief
- Article Body
- FAQ
- Sources
- Risk Disclaimer
- Editor Notes
- Validation Results
- Generation Metadata

## 目标 Notion 页面结构

### Article Draft

展示：

- title
- summary
- body
- FAQ
- meta title
- meta description

建议 property：

| 字段 | 类型 | required |
|---|---|---:|
| Name | title | yes |
| AI Summary | rich_text | yes |
| Article Type | select | yes |
| Language | select | yes |
| Market | select | yes |
| Symbol | rich_text 或 select | yes |
| SEO Title | rich_text | no |
| SEO Description | rich_text | no |

### Source Quality

展示：

- source_count
- usable_source_count
- source_quality
- extraction_quality
- source_gaps
- source URLs

建议 property：

| 字段 | 类型 | required |
|---|---|---:|
| Source Count | number | yes |
| Usable Source Count | number | no |
| Source Quality | select | no |
| Extraction Success Rate | number | no |
| Source Gaps | rich_text | no |
| Source URLs | rich_text | no |

详细 JSON 放 block，不建议为每个 source 都建 property。

### Editorial Brief

展示：

- event_summary
- why_it_matters
- primary_angle
- market_context
- reader_questions
- must_cover
- avoid_claims
- recommended_structure

建议 property：

| 字段 | 类型 | required |
|---|---|---:|
| Primary Angle | rich_text | no |
| Why It Matters | rich_text | no |
| Search Intent | rich_text | no |
| Target Reader | rich_text | no |
| Content Type | select | no |
| Brief Confidence | select | no |

其余详细内容放 block。

### AI Review

展示：

- publish_readiness
- grounding_score
- depth_score
- readability_score
- headline_quality_score
- financial_safety_score
- issues
- unsupported_claims
- overstatements
- missing_context
- recommended_editor_action

建议 property：

| 字段 | 类型 | required |
|---|---|---:|
| Publish Readiness | select | no |
| Grounding Score | number | no |
| Depth Score | number | no |
| Readability Score | number | no |
| Headline Quality Score | number | no |
| Financial Safety Score | number | no |
| Recommended Editor Action | rich_text | no |

AI review issue 列表放 block。

### Deterministic Quality Report

展示：

- validation passed / failed
- blocking issues
- warnings
- financial_advice_detected
- headline_risk_level
- grounded_claim_ratio
- editor_ready_score

建议 property：

| 字段 | 类型 | required |
|---|---|---:|
| Editor Ready Score | number | no |
| Headline Risk Level | select | no |
| Financial Advice Detected | checkbox | no |
| Validation Passed | checkbox | no |

详细 validator 输出放 block。

### Human Review Feedback

编辑填写：

| 字段 | 类型 | required | 用途 |
|---|---|---:|---|
| Status | status | yes | Needs Review / Approved / Needs Edit / Rejected |
| Editor Score | number | no | 1-5 |
| Rejection Reason | rich_text | no | 拒绝原因 |
| Edited Headline | rich_text | no | 编辑后的标题 |
| Edited Summary | rich_text | no | 编辑后的摘要 |
| Editor Notes | rich_text | no | 人工审核备注 |
| Final Publish Decision | select | no | publish / do_not_publish / revise |
| Reviewed At | date | no | 审核时间 |

## Status 建议

最小 status 集：

- `AI Draft`
- `Needs Review`
- `Needs Edit`
- `Needs Rewrite`
- `Needs Source Fix`
- `Needs Compliance Fix`
- `Approved`
- `Rejected`
- `Published`
- `Ignored`

当前 config 中应继续禁止默认 `Published`。

## 如何避免字段过多

原则：

1. 常用筛选字段做 property。
2. 长文本和详细 JSON 放 block。
3. issue 列表放 block，不拆成多个 property。
4. 每个评分可以做 number property。
5. Notion property 主要服务列表筛选，不服务完整审稿阅读。

推荐 blocks：

```text
Source Quality Report
Editorial Brief
AI Review
Deterministic Validation
Generation Metadata
Raw JSON
```

## Feedback Sync

当前已有：

- `src/review/notion_sync.py`
- `src/review/feedback.py`
- `src/review/feedback_store.py`
- `src/jobs/sync_notion_reviews.py`

Phase 5 需要扩展：

- 映射 `Needs Edit`。
- 映射 `Needs Rewrite`。
- 映射 `Editor Score`。
- 映射 `Rejection Reason`。
- 映射 `Edited Headline`。
- 映射 `Edited Summary`。
- 映射 `Final Publish Decision`。
- 映射 `Reviewed At`。

## Notion Schema 验收标准

1. 创建页面时 required property 都存在。
2. Upsert 不破坏已有页面。
3. AI review 和 quality report 能在页面中看到。
4. 人工修改 Status 后，sync job 能生成 feedback record。
5. 没有 Notion API key 时 live test 默认 skip。

## 回滚策略

- 保留旧 `NotionPropertyMapper` 字段。
- 新字段缺失时只 warning。
- 详细信息优先放 block，减少 schema 强依赖。
- `ENABLE_NOTION_FEEDBACK_SYNC=0` 可关闭回流。

