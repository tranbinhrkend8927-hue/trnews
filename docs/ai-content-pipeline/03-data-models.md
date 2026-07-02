# 03 核心数据模型设计

本文件描述目标架构需要的 Pydantic models。执行时应渐进式新增，避免一次性替换当前 `NormalizedNewsItem`、`SourceBundle`、`ArticleDraft`。

## SourceItem

建议文件：

```text
src/models/source.py
```

用途：作为标准化新闻源对象，兼容当前 `NormalizedNewsItem`。

```python
class SourceItem(BaseModel):
    id: str
    url: str | None = None
    canonical_url: str | None = None
    original_title: str
    original_summary: str | None = None
    provider: str | None = None
    published_at: str | None = None
    fetched_at: str
    language: str
    symbols: list[str] = []
    raw_payload: dict = {}
```

迁移建议：

- Phase 1 不替换 `NormalizedNewsItem`。
- 先提供转换函数：`source_item_from_normalized_news_item()`。

## SourceEnrichmentResult

用途：保存 Trafilatura 或其他正文抽取结果。

```python
class SourceEnrichmentResult(BaseModel):
    source_id: str
    original_url: str | None = None
    extracted_title: str | None = None
    extracted_text: str | None = None
    author: str | None = None
    published_at: str | None = None
    site_name: str | None = None
    language: str | None = None
    text_length: int = 0
    extraction_quality: Literal["good", "partial", "poor", "failed"]
    failure_reason: str | None = None
    usable_for_deep_article: bool = False
    metadata_confidence: Literal["high", "medium", "low"] = "low"
    extraction_method: str = "trafilatura"
```

质量判断建议：

- `good`: text_length >= `MIN_ENRICHED_TEXT_LENGTH`
- `partial`: 有正文但偏短
- `poor`: 只有摘要或极短正文
- `failed`: 抽取失败或无 URL

## SourceQualityReport

用途：决定能不能写深度文章。

```python
class SourceQualityReport(BaseModel):
    source_count: int
    usable_source_count: int
    average_text_length: float
    has_primary_source: bool = False
    has_recent_sources: bool = False
    duplicate_count: int = 0
    extraction_success_rate: float
    overall_source_quality: Literal["strong", "acceptable", "weak", "insufficient"]
    recommended_action: Literal["write_article", "write_brief_only", "skip_or_manual_review"]
    reasons: list[str] = []
    source_gaps: list[str] = []
```

推荐 action：

- `write_article`: 来源足够写深度文章。
- `write_brief_only`: 只能写短 brief 或市场观察。
- `skip_or_manual_review`: 不应调用 writer。

## SourceBundle

当前已有：

```text
src/content/source_bundle.py
```

建议渐进扩展：

```python
class SourceBundle(BaseModel):
    bundle_id: str
    market_id: str
    symbol: str
    language: str
    sources: list[NormalizedNewsItem]
    enriched_sources: list[SourceEnrichmentResult] = []
    deduped_source_ids: list[str] = []
    source_quality_report: SourceQualityReport | None = None
    detected_theme: str | None = None
    time_window: dict = {}
    source_gaps: list[str] = []
    recommended_action: str = "write_article"
    warnings: list[dict] = []
    errors: list[dict] = []
```

兼容要求：

- 保留 `sources`。
- 保留 `source_trace`。
- 保留 `source_bundle_hash` 规则。
- 旧 tests 不应失效。

## EditorialBrief

建议文件：

```text
src/models/brief.py
```

```python
class EditorialBrief(BaseModel):
    event_summary: str
    why_it_matters: str
    market_context: str
    primary_angle: str
    reader_questions: list[str]
    must_cover: list[str]
    avoid_claims: list[str]
    source_gaps: list[str] = []
    recommended_structure: list[str]
    target_reader: str
    content_type: Literal["deep_article", "market_brief", "explainer", "news_update"]
    confidence_level: Literal["high", "medium", "low"]
    editorial_notes: list[str] = []
```

生成策略：

1. 先 deterministic 生成基础 brief。
2. 后续可选 AI 补充。
3. brief validation 失败不进入 writer。

## ArticleDraft

当前已有：

```text
src/content/article_schema.py
```

当前字段已包括：

- title
- slug
- summary
- body
- seo_title
- seo_description
- language
- market
- symbol
- article_type
- risk_disclaimer
- region
- search_intent
- primary_keyword
- secondary_keywords
- candidate_titles
- editorial_angle
- key_takeaways
- evergreen_context
- editor_notes
- faq
- sources_used
- uncertain_claims

后续建议增加：

```python
class ArticleSection(BaseModel):
    heading: str
    body: str
    source_ids: list[str] = []

class ArticleDraft(BaseModel):
    sections: list[ArticleSection] = []
    meta_title: str | None = None
    meta_description: str | None = None
    disclaimers: list[str] = []
    target_reader: str = ""
    created_at: str | None = None
    prompt_version: str | None = None
    model_name: str | None = None
```

兼容要求：

- 不要立刻删除 `seo_title` / `seo_description`。
- `meta_title` / `meta_description` 可作为 alias 后续引入。

## AIReview

建议文件：

```text
src/models/review.py
```

```python
class AIReviewIssue(BaseModel):
    issue_type: str
    severity: Literal["low", "medium", "high"]
    location: str | None = None
    description: str
    suggested_fix: str | None = None

class AIReviewScores(BaseModel):
    grounding: int
    depth: int
    readability: int
    headline_quality: int
    financial_safety: int
    source_usefulness: int

class AIReview(BaseModel):
    publish_readiness: Literal["ready", "needs_edit", "reject"]
    scores: AIReviewScores
    issues: list[AIReviewIssue] = []
    unsupported_claims: list[str] = []
    overstatements: list[str] = []
    missing_context: list[str] = []
    rewrite_suggestions: list[str] = []
    recommended_editor_action: str
```

边界：

- Reviewer 不直接改正文。
- Reviewer 输出结构化建议和分数。
- 最终状态由 pipeline 结合 validators 决定。

## ValidationResult

当前已有：

```text
src/content/validators/result.py
```

建议兼容式增强：

```python
class ValidationResult(BaseModel):
    passed: bool
    exportable: bool = True
    issues: list[ValidationIssue] = []
    metadata: dict = {}

    blocking_issues: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    checks: dict = {}
    financial_advice_detected: bool = False
    headline_risk_level: Literal["low", "medium", "high"] = "low"
    source_attribution_passed: bool = True
    format_passed: bool = True
```

执行建议：

- Phase 1-3 不强制改当前 `ValidationResult`。
- Phase 4 做 `ArticleQualityReport` 时再统一聚合。

## ArticleQualityReport

建议文件：

```text
src/models/quality.py
```

```python
class ArticleQualityReport(BaseModel):
    source_count: int
    usable_source_count: int
    body_length: int
    faq_count: int
    has_market_context: bool
    has_risk_disclaimer: bool
    has_source_attribution: bool
    grounded_claim_ratio: float | None = None
    headline_risk_level: Literal["low", "medium", "high"]
    financial_advice_detected: bool
    editor_ready_score: int
    blocking_issues: list[str] = []
    warnings: list[str] = []
    final_recommended_status: Literal["needs_review", "needs_edit", "needs_rewrite", "rejected"]
```

输入来源：

- SourceQualityReport
- EditorialBrief
- ArticleDraft
- AIReview
- deterministic validators

## EditorFeedback

当前已有 `ReviewFeedback`。后续可新增 alias 或新版：

```python
class EditorFeedback(BaseModel):
    notion_page_id: str
    editor_status: Literal["approved", "needs_edit", "rejected"]
    editor_score: int | None = None
    rejection_reason: str | None = None
    edited_headline: str | None = None
    edited_summary: str | None = None
    editor_notes: str | None = None
    final_publish_decision: str | None = None
    reviewed_at: str | None = None
```

迁移建议：

- Phase 5 不必替换现有 `ReviewFeedback`。
- 可在 `notion_sync.py` 中扩展字段映射。

