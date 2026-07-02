# 07 错误处理、降级策略与金融安全

## 错误处理原则

1. 来源不足时不写假深度文章。
2. LLM 失败不应导致 pipeline 崩溃。
3. Notion 失败不应丢失本地结果。
4. blocking issue 必须阻断发布。
5. warning 可以进入 Notion 人审，但必须清晰展示。
6. 所有失败都要进入 event/job store。

## 失败场景矩阵

| 场景 | 是否重试 | 降级 | 是否进 Notion | 是否阻断发布 | 记录内容 |
|---|---:|---|---|---:|---|
| 新闻源抓取失败 | adapter 内有限重试 | SOURCE_FETCH_FAILED | no | yes | market、symbol、error |
| Trafilatura 抽取失败 | no 或 1 次 | 使用原 summary/content | warning only | no | source_id、url、failure_reason |
| 正文太短 | no | write_brief_only/manual_review | topic candidate | deep article yes | text_length、threshold |
| metadata 缺失 | no | 用原始 metadata | warning only | no | missing fields |
| 多来源重复 | no | dedupe | yes | no | duplicate_count |
| 来源质量不足 | no | skip_or_manual_review | topic candidate | yes | source_quality_report |
| LLM 输出非 JSON | 1 次 | LLM_FAILED | no normal article | yes | raw preview、parse error |
| LLM 输出缺字段 | 1 次 repair | LLM_SCHEMA_FAILED | no normal article | yes | validation errors |
| AI Review 失败 | no | deterministic only | yes with warning | no | reviewer error |
| Validator blocking issue | no | no export 或 needs fix | optional needs fix | yes | validator issues |
| Notion export 失败 | Notion client retry | local result only | no/partial | no publish | API status、retryable |
| Promptfoo eval 失败 | no | eval job fail only | n/a | no runtime effect | eval report |
| 配置缺失 | no | production_check fail | n/a | yes | config error |
| 模型调用超时 | runner retry | LLM_FAILED | no normal article | yes | attempts、timeout |
| 网络异常 | retry transient | failed result | no normal article | depends | retryable flag |

## Pipeline 状态建议

新增或规范状态：

```text
SOURCE_FETCH_FAILED
SOURCE_ENRICHMENT_PARTIAL
SOURCE_QUALITY_INSUFFICIENT
SOURCE_BRIEF_ONLY
BRIEF_VALIDATION_FAILED
NEEDS_BRIEF_REWRITE
LLM_FAILED
LLM_SCHEMA_FAILED
AI_REVIEW_FAILED
AI_REVIEW_REJECTED
VALIDATION_FAILED
NOTION_EXPORT_FAILED
NOTION_EXPORTED
DRY_RUN_SUCCESS
```

## 降级动作

### write_article

条件：

- source quality strong/acceptable。
- brief confidence high/medium。
- validators 无 blocking。

动作：

- 正常 writer。
- AI reviewer。
- Notion Needs Review。

### write_brief_only

条件：

- source quality weak。
- 可解释新闻事件，但不足以深度分析。

动作：

- 不伪装深度文章。
- 生成 market brief 或 topic candidate。
- Notion 状态 `Brief Only` 或 `Needs Source Fix`。

### skip_or_manual_review

条件：

- source quality insufficient。
- source gaps 太严重。
- metadata/正文太薄。

动作：

- 不调用 writer。
- 记录 SourceQualityReport。
- 可导出 topic candidate 给编辑手工判断。

## 金融安全规则

### 必须阻断

1. 明确买入、卖出、做多、做空建议。
2. 承诺收益。
3. 明确价格目标并带确定性。
4. “必涨”“必跌”“guaranteed”。
5. 未标注风险的预测性内容。
6. 无来源支撑的宏观判断。
7. 把市场传闻写成事实。
8. 把相关性写成因果性。
9. 缺少标准免责声明。

### Warning

1. 标题偏强但未构成承诺。
2. “可能导致”但来源不足。
3. 风险提示存在但不完整。
4. 过度简化央行、通胀、利率影响。

## Deterministic rule 检查

应检查：

- buy/sell instruction phrases。
- profit guarantee phrases。
- strong prediction phrases。
- price target with certainty。
- missing risk disclaimer。
- unknown source URL。
- unsupported source_id。
- body URL outside source bundle。
- required sections。
- language mismatch。
- SEO title/description risky phrase。

## AI Reviewer 检查

AI Reviewer 检查 deterministic rules 不擅长的内容：

- 是否只是复述新闻。
- 是否缺少市场背景。
- 是否因果关系过度。
- 是否有标题党风险。
- 是否无来源扩写。
- 是否读者价值不足。
- 是否建议进入人审、返修或拒绝。

## Notion 展示风险

建议展示：

- Risk Level。
- Financial Safety Score。
- Financial Advice Detected。
- Unsupported Claims。
- Overstatements。
- Missing Context。
- Compliance Issues。
- Required Disclaimer。

## 多语言处理

每个 language config 必须包含：

- `risk_disclaimer`
- `forbidden_claims`
- `writing_rules`
- `required_sections`

后续可增加：

```yaml
financial_safety:
  forbidden_phrases:
    - ...
  strong_prediction_phrases:
    - ...
```

## Helpful content / SEO 安全

SEO 必须服务读者，不服务关键词堆砌。

### Blocking

- 标题含收益承诺。
- meta description 含诱导交易。
- 缺来源。
- 缺风险提示。
- 内容无来源支撑。

### Warning

- title 太长或太短。
- description 太长或太短。
- primary keyword 缺失。
- FAQ 为空。
- 正文只是短摘要。
- 缺背景解释。
- 缺读者问题回答。

### Reviewer 软判断

- 是否有额外价值。
- 是否只是复述来源。
- 是否模板化过重。
- 是否信息不足却伪装深度文章。

