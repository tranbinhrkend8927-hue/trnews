# PRD：TradingView 新闻源 → AI 多语言文章草稿 → Notion 人工审核流水线

版本：v0.2
面向对象：项目负责人、后端开发、Codex / AI coding agent
当前主线：先用 `USDIDR + 印尼语` 调试，后续扩展多 symbol、多语言、多 Notion 数据表
核心原则：配置驱动、来源可追踪、LLM 输出只作为草稿、人工审核优先、Codex 可分阶段落地

---

## 0. 本版 PRD 修订说明

上一版 PRD 的方向是正确的，但还不够完整。本版补充以下关键内容：

1. **幂等与重复导出**：避免同一批新闻重复生成多篇 Notion 草稿。
2. **Notion upsert 策略**：明确什么时候创建页面，什么时候更新页面。
3. **批处理失败恢复**：单个 market 失败不能影响其他 market。
4. **配置 schema 与配置校验**：新增市场、语言、模型、Notion 表时必须能自动校验。
5. **source bundle 契约**：明确 LLM 只能使用标准化后的来源包。
6. **LLM 输出契约**：ArticleDraft 需要强类型 schema，而不是普通 dict。
7. **多语言边界**：不同语言的 prompt、风险提示、SEO、Notion 字段规则需要独立配置。
8. **财务合规与人工审核**：LLM 生成结果只能进入 Notion 审核状态，不能直接发布。
9. **日志、成本、限流、重试**：为后续批量化做准备。
10. **Codex 执行顺序**：每个 Phase 明确文件、测试、验收命令、禁止事项。

---

# 1. 背景

## 1.1 当前业务背景

当前项目希望使用 TradingView 作为财经新闻源。系统抓取某个 symbol 的新闻，例如 `USDIDR`，再通过 LLM 生成一篇对应语言的财经文章草稿，最后写入 Notion，由人工审核。

当前只用 `USDIDR + 印尼语` 调试，但后续需要支持：

- USDIDR / 印尼语；
- USDJPY / 日语；
- USDKRW / 韩语；
- EURUSD / 英语；
- 其他 symbol / 其他语言。

每个语言可能有：

- 不同 system prompt；
- 不同风险提示；
- 不同写作语气；
- 不同 SEO 长度限制；
- 不同 LLM model；
- 不同 temperature / max_tokens；
- 不同 Notion database / data source；
- 不同人工审核字段。

## 1.2 当前工程目标

把项目从：

```text
单 symbol + 单语言 + 单 prompt + 手动调试链路
```

升级为：

```text
配置驱动的多语言财经内容生产流水线
```

## 1.3 当前项目已有基础

现有代码已经具备一些可复用能力：

- `tradingview_scraper/`：TradingView 数据抓取；
- `src/llm/`：新 LLM 统一调用层雏形；
- `src/llm/run_task.py`：统一 LLM task 入口雏形；
- `src/llm/prompts/`：prompt 集中管理雏形；
- `src/llm/model_policies.py`：模型参数策略雏形；
- `news_pipeline/source_grounding.py`：source bundle 思路；
- `news_pipeline/safety_validation.py`：金融安全校验；
- `news_pipeline/notion_exporter.py`：Notion 导出。

本 PRD 不要求推倒重写，而是在现有基础上逐步收敛职责。

---

# 2. 产品目标与非目标

## 2.1 产品目标

系统最终应该支持以下流程：

```text
1. 读取配置
2. 根据 market_id 获取 TradingView 新闻
3. 标准化新闻源数据
4. 去重并构建 SourceBundle
5. 调用 LLM 生成 ArticleDraft
6. 做 schema 校验
7. 做 source grounding 校验
8. 做金融安全校验
9. 做语言规则校验
10. 做 Notion 可导出校验
11. 写入对应 Notion 数据表
12. 设置状态为 Needs Review
13. 人工在 Notion 审核
```

## 2.2 成功标准

第一阶段成功标准：

1. `USDIDR + 印尼语` 可以从配置跑通；
2. 不需要在代码里写死 USDIDR / 印尼语 / Notion 表；
3. LLM 生成的文章是强类型 ArticleDraft；
4. 文章通过 validator 后才能写入 Notion；
5. Notion 页面状态默认为 `Needs Review`；
6. 每次生成都有 pipeline run metadata；
7. dry-run 模式可以输出完整结果但不写 Notion；
8. Codex 可以按 Phase 独立开发，每个 Phase 都有测试。

## 2.3 非目标

本阶段不做：

1. 不自动发布到网站；
2. 不绕过人工审核；
3. 不引入复杂 agent 框架；
4. 不强制使用 LangChain；
5. 不强制使用 LiteLLM；
6. 不强制上 Prefect / Airflow；
7. 不做完全自动事实核查；
8. 不做人工审核前端，先用 Notion；
9. 不实现复杂权限系统；
10. 不一次性迁移所有旧模块。

---

# 3. 核心设计原则

## 3.1 配置驱动

新增语言、symbol、Notion 表时，应该优先通过配置完成，而不是修改核心代码。

错误示例：

```python
if language == "id":
    prompt = ID_PROMPT
elif language == "ja":
    prompt = JA_PROMPT
```

正确方向：

```text
config/languages/id.yaml
config/languages/ja.yaml
src/llm/prompts/article_draft/id.system.md
src/llm/prompts/article_draft/ja.system.md
```

## 3.2 LLM 只生成草稿

LLM 输出不能直接发布，只能成为：

```text
ArticleDraft / AI Draft / Needs Review
```

是否发布由人工审核决定。

## 3.3 Prompt 不是安全边界

Prompt 负责引导模型；代码 validator 才是安全边界。

必须用代码检查：

- JSON 结构是否正确；
- 来源是否来自 source_bundle；
- 是否包含投资建议；
- 是否有保证收益；
- 是否有风险提示；
- 是否符合目标语言；
- 是否能导出 Notion。

## 3.4 任务通用，语言参数化

不要为每个语言创建一个完全不同的 task。

推荐抽象：

```text
task = article_draft
language = id / ja / ko / en
market = Indonesia / Japan / Korea / Global
symbol = USDIDR / USDJPY / USDKRW / EURUSD
```

## 3.5 可观测、可重跑、可排查

每次生成必须能回答：

- 哪个 market 跑的？
- 哪个 symbol？
- 哪个语言？
- 用了哪些 source？
- 用了哪个 prompt version？
- 用了哪个 model？
- token usage 多少？
- latency 多少？
- 哪个 validator 失败？
- Notion page id 是什么？
- 是否可以安全重跑？

---

# 4. 总体架构

## 4.1 目标目录结构

```text
config/
  pipeline.yaml
  llm_profiles.yaml
  notion_targets.yaml
  languages/
    id.yaml
    ja.yaml
    ko.yaml
    en.yaml

src/
  config/
    __init__.py
    models.py
    loader.py
    validator.py

  ingest/
    __init__.py
    tradingview.py
    normalize.py
    dedupe.py

  content/
    __init__.py
    article_pipeline.py
    article_schema.py
    source_bundle.py
    result.py
    validators/
      __init__.py
      article_schema.py
      source_grounding.py
      financial_safety.py
      language_rules.py
      notion_exportable.py
      quality.py

  llm/
    client.py
    run_task.py
    result.py
    prompt_renderer.py
    task_spec.py
    registry.py
    prompts/
      article_draft/
        spec.yaml
        id.system.md
        ja.system.md
        ko.system.md
        en.system.md
        user_payload.jinja.md

  notion/
    __init__.py
    client.py
    target_resolver.py
    mapper.py
    exporter.py

  jobs/
    __init__.py
    validate_config.py
    run_market.py
    run_batch.py
    retry_failed.py

news_pipeline/
  legacy compatibility wrappers
```

## 4.2 数据流

```text
ConfigRegistry
    ↓
TradingViewNewsAdapter
    ↓
NormalizedNewsItem[]
    ↓
Dedupe
    ↓
SourceBundleBuilder
    ↓
SourceBundle
    ↓
LLM article_draft task
    ↓
ArticleDraft
    ↓
Validators
    ↓
NotionMapper
    ↓
NotionExporter
    ↓
Needs Review page
```

## 4.3 模块职责

| 模块 | 职责 |
|---|---|
| `src/config` | 加载和校验配置 |
| `src/ingest` | 抓取、标准化、去重新闻源 |
| `src/content` | 构建 source bundle、生成文章、校验文章 |
| `src/llm` | 统一 LLM 调用、prompt 渲染、结果封装 |
| `src/notion` | Notion target 解析、字段映射、导出 |
| `src/jobs` | CLI 任务入口 |
| `news_pipeline` | 旧接口兼容，不再承载新核心逻辑 |

---

# 5. 配置系统

## 5.1 新增配置文件

必须新增：

```text
config/pipeline.yaml
config/llm_profiles.yaml
config/notion_targets.yaml
config/languages/id.yaml
```

后续语言再新增：

```text
config/languages/ja.yaml
config/languages/ko.yaml
config/languages/en.yaml
```

## 5.2 `config/pipeline.yaml`

用途：定义 market / symbol / TradingView / content / LLM / Notion 绑定关系。

示例：

```yaml
version: 1

defaults:
  enabled: true
  schedule: manual
  max_articles_per_run: 3
  min_sources_per_article: 1
  max_sources_per_article: 5
  dry_run: false

markets:
  - id: usd_idr_id
    enabled: true
    symbol: USDIDR
    exchange: FX_IDC
    base_currency: USD
    quote_currency: IDR

    tradingview:
      language: id
      locale: id
      url: "https://id.tradingview.com/symbols/USDIDR/news/"
      sort: latest
      section: all
      provider: null
      area: null
      max_headlines: 10
      max_articles: 3

    content:
      language: id
      market: Indonesia
      task: article_draft
      article_type: fx_news_explainer
      topic_strategy: latest_forex_news
      source_policy:
        min_sources: 1
        max_sources: 5
        require_body: true
        allow_paywalled_summary: true
        max_source_age_hours: 72

    llm:
      draft_profile: article_writer_id
      review_profile: article_reviewer_id
      grounding_profile: grounding_checker_id

    notion:
      target: notion_articles_id
```

## 5.3 `config/llm_profiles.yaml`

用途：统一管理 LLM provider、模型和参数。

示例：

```yaml
providers:
  openrouter:
    base_url_env: LLM_BASE_URL
    api_key_env: LLM_API_KEY

profiles:
  article_writer_id:
    provider: openrouter
    model_env: LLM_WRITER_MODEL
    fallback_model_env: LLM_DEFAULT_MODEL
    temperature: 0.35
    top_p: 1.0
    max_tokens: 2200
    timeout_seconds: 90
    max_retries: 1
    response_format: json_schema
    supports_json_schema: true
    supports_tools: false

  article_reviewer_id:
    provider: openrouter
    model_env: LLM_REVIEW_MODEL
    fallback_model_env: LLM_DEFAULT_MODEL
    temperature: 0.1
    top_p: 1.0
    max_tokens: 1200
    timeout_seconds: 60
    max_retries: 1
    response_format: json_schema
    supports_json_schema: true
    supports_tools: false

  grounding_checker_id:
    provider: openrouter
    model_env: LLM_REVIEW_MODEL
    fallback_model_env: LLM_DEFAULT_MODEL
    temperature: 0.0
    top_p: 1.0
    max_tokens: 1000
    timeout_seconds: 60
    max_retries: 1
    response_format: json_schema
    supports_json_schema: true
    supports_tools: false
```

### LLM 参数规则

- 文章生成：temperature 可以 0.25–0.4；
- 审稿 / grounding：temperature 应接近 0；
- JSON 输出任务优先 `json_schema`；
- 如果 provider 不支持 `json_schema`，必须降级为 `json_object + 本地 Pydantic 校验 + repair`；
- 不允许业务层随意覆盖 `response_format`；
- 普通调用者只允许覆盖 `temperature`、`max_tokens`；
- model override 仅限管理员或测试。

## 5.4 `config/notion_targets.yaml`

用途：将 language/market 路由到 Notion 数据表。

示例：

```yaml
targets:
  notion_articles_id:
    language: id
    market: Indonesia
    parent_type: data_source
    data_source_id_env: NOTION_DATA_SOURCE_ID_ID
    fallback_data_source_id_env: NOTION_DATA_SOURCE_ID
    status_default: AI Draft
    reviewer_status: Needs Review
    duplicate_policy: update_existing
    unique_key_fields:
      - market_id
      - symbol
      - language
      - source_bundle_hash

  notion_articles_ja:
    language: ja
    market: Japan
    parent_type: data_source
    data_source_id_env: NOTION_DATA_SOURCE_ID_JA
    fallback_data_source_id_env: NOTION_DATA_SOURCE_ID
    status_default: AI Draft
    reviewer_status: Needs Review
    duplicate_policy: update_existing
    unique_key_fields:
      - market_id
      - symbol
      - language
      - source_bundle_hash
```

## 5.5 `config/languages/id.yaml`

示例：

```yaml
language: id
locale: id-ID
market: Indonesia
audience: "Indonesian retail readers interested in Rupiah, USD/IDR, Bank Indonesia, Fed, inflation, and macro events."
tone: "clear, careful, explanatory, not sensational"

writing_rules:
  - "Use Bahasa Indonesia."
  - "Avoid sensational claims."
  - "Explain financial terms in simple language."
  - "Do not give buy/sell instructions."
  - "Do not fabricate prices, data, URLs, institutions, or publication dates."

required_sections:
  - "Sumber"
  - "Catatan risiko"

risk_disclaimer: "Artikel ini hanya untuk informasi dan edukasi, bukan rekomendasi investasi atau ajakan membeli/menjual aset keuangan."

forbidden_claims:
  - "profit guarantee"
  - "buy/sell instruction"
  - "take profit"
  - "stop loss"
  - "certain prediction"

seo:
  title_max_length: 70
  description_max_length: 170

slug:
  strategy: ascii_lower_kebab
  allow_unicode: false

notion:
  title_property: Name
  status_property: Status
  language_property: Language
  market_property: Market
  symbol_property: Symbol
```

## 5.6 配置校验规则

`python -m src.jobs.validate_config` 必须检查：

1. `pipeline.yaml` 可解析；
2. 每个 market id 唯一；
3. 每个 enabled market 的 language profile 存在；
4. 每个 enabled market 的 LLM draft profile 存在；
5. 每个 enabled market 的 Notion target 存在；
6. 每个 enabled market 的 prompt 文件存在；
7. `tradingview.language == content.language`；
8. `min_sources <= max_sources`；
9. LLM provider 的 API key env 存在；
10. LLM profile 至少能解析出 model 或 fallback model；
11. Notion target 至少能解析出 data source / database / page id；
12. 不允许 enabled market 引用 disabled 或不存在的配置；
13. 如果配置中包含 `parent_type=data_source`，Notion parent payload 必须使用 `data_source_id`；
14. 如果 prompt 文件缺失，返回 error；
15. 如果某个 env 缺失但有 fallback，返回 warning；
16. 如果某个 env 缺失且无 fallback，返回 error。

返回格式：

```json
{
  "success": true,
  "errors": [],
  "warnings": []
}
```

---

# 6. 数据模型

## 6.1 Config Models

新增：

```text
src/config/models.py
```

核心模型：

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal


class TradingViewSourceConfig(BaseModel):
    language: str
    locale: Optional[str] = None
    url: str
    sort: str = "latest"
    section: str = "all"
    provider: Optional[str] = None
    area: Optional[str] = None
    max_headlines: int = 10
    max_articles: int = 3


class SourcePolicy(BaseModel):
    min_sources: int = 1
    max_sources: int = 5
    require_body: bool = True
    allow_paywalled_summary: bool = True
    max_source_age_hours: Optional[int] = 72


class ContentConfig(BaseModel):
    language: str
    market: str
    task: str = "article_draft"
    article_type: str = "fx_news_explainer"
    topic_strategy: str = "latest_forex_news"
    source_policy: SourcePolicy = Field(default_factory=SourcePolicy)


class LLMBindingConfig(BaseModel):
    draft_profile: str
    review_profile: Optional[str] = None
    grounding_profile: Optional[str] = None


class NotionBindingConfig(BaseModel):
    target: str


class MarketPipelineConfig(BaseModel):
    id: str
    enabled: bool = True
    symbol: str
    exchange: str
    base_currency: str
    quote_currency: str
    tradingview: TradingViewSourceConfig
    content: ContentConfig
    llm: LLMBindingConfig
    notion: NotionBindingConfig
```

## 6.2 NormalizedNewsItem

新增：

```text
src/ingest/normalize.py
```

定义：

```python
from pydantic import BaseModel, Field
from typing import Optional


class NormalizedNewsItem(BaseModel):
    source_id: str
    provider: Optional[str] = None
    symbol: str
    exchange: str
    language: str
    locale: Optional[str] = None
    title: str
    summary: Optional[str] = None
    content: Optional[str] = None
    url: Optional[str] = None
    canonical_url: Optional[str] = None
    published_at: Optional[str] = None
    fetched_at: str
    raw: dict = Field(default_factory=dict)
```

### source_id 生成规则

必须稳定、可复现。推荐：

```text
source_id = sha256(symbol + language + canonical_url_or_url_or_title + published_at).hexdigest()[:16]
```

如果 URL 缺失，则使用 title + published_at。
如果 published_at 缺失，则使用 title + fetched date，但要加 warning。

## 6.3 SourceBundle

新增：

```text
src/content/source_bundle.py
```

定义：

```python
from pydantic import BaseModel, Field


class SourceBundle(BaseModel):
    bundle_id: str
    market_id: str
    symbol: str
    language: str
    sources: list[NormalizedNewsItem]
    source_bundle_hash: str
    missing_source_ids: list[str] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
    errors: list[dict] = Field(default_factory=list)
    source_trace: dict = Field(default_factory=dict)
```

### source_bundle_hash 规则

用于幂等和 Notion 去重。

推荐：

```text
source_bundle_hash = sha256(sorted(source_id list) + market_id + symbol + language).hexdigest()[:16]
```

同一批 source 生成的文章应该具有同一个 hash。

## 6.4 ArticleDraft

新增：

```text
src/content/article_schema.py
```

定义：

```python
from pydantic import BaseModel, Field
from typing import Optional, Literal


class FAQItem(BaseModel):
    question: str
    answer: str


class SourceUsed(BaseModel):
    source_id: str
    news_id: Optional[str | int] = None
    title: str
    url: Optional[str] = None
    provider: Optional[str] = None
    published_at: Optional[str] = None
    used_for: Optional[str] = None


class UncertainClaim(BaseModel):
    claim: str
    reason: str
    severity: Literal["low", "medium", "high"] = "low"


class ArticleDraft(BaseModel):
    title: str
    slug: str
    summary: str
    body: str
    seo_title: str
    seo_description: str
    language: str
    market: str
    symbol: str
    article_type: str
    risk_disclaimer: str
    faq: list[FAQItem] = Field(default_factory=list)
    sources_used: list[SourceUsed] = Field(default_factory=list)
    uncertain_claims: list[UncertainClaim] = Field(default_factory=list)
```

### ArticleDraft 约束

1. `language` 必须等于配置语言；
2. `symbol` 必须等于 market symbol；
3. `risk_disclaimer` 必须包含或等于语言配置中的 disclaimer；
4. `sources_used` 至少 1 条；
5. `sources_used[*].source_id` 必须来自 source_bundle；
6. `body` 必须包含 required sections；
7. `seo_title` 和 `seo_description` 必须符合语言配置长度；
8. `slug` 必须符合语言配置 slug 策略。

---

# 7. LLM 与 Prompt 设计

## 7.1 新任务：article_draft

统一新增任务：

```text
article_draft
```

兼容旧任务：

```text
fx_article_id -> article_draft + language=id
indonesia_fx_content -> article_draft + language=id
japan_fx_content -> article_draft + language=ja
llm_article_draft_candidate -> article_draft
```

## 7.2 Prompt 文件结构

新增：

```text
src/llm/prompts/article_draft/
  spec.yaml
  id.system.md
  ja.system.md
  ko.system.md
  en.system.md
  user_payload.jinja.md
```

## 7.3 `spec.yaml`

```yaml
name: article_draft
version: "article_draft@2026-06-30"
description: "Generate a multilingual FX news explainer article draft from a grounded TradingView source bundle."
output_schema: article_draft_v1
input_required:
  - market
  - language_profile
  - source_bundle
```

## 7.4 `id.system.md`

```md
你是印尼语财经编辑，负责根据 TradingView 新闻源生成 Bahasa Indonesia 的外汇新闻解读文章。

必须遵守：
- 只能使用 source_bundle 中提供的信息。
- 不得编造新闻来源、发布时间、URL、价格、央行表态或经济数据。
- 不得给出买入、卖出、止盈、止损或保证收益表达。
- 不得输出投资建议。
- 必须使用自然、清晰、适合印尼普通读者理解的 Bahasa Indonesia。
- 文章必须包含「Sumber」和「Catatan risiko」段落。
- 输出必须是 JSON，不要输出 Markdown，不要在 JSON 外输出解释。
```

## 7.5 `ja.system.md`

```md
あなたは日本語の金融編集者です。TradingView のニュースソースに基づき、為替ニュースを読者向けにわかりやすく解説してください。

必ず守ること：
- source_bundle に含まれる情報だけを使うこと。
- ニュースソース、公開日時、URL、価格、経済指標、中央銀行発言を捏造しないこと。
- 売買推奨、利益保証、利確、損切り指示を書かないこと。
- 投資助言として読まれる表現を避けること。
- 自然で読みやすい日本語を使うこと。
- 本文には「情報源」と「リスクに関する注記」を含めること。
- 出力は JSON のみ。Markdown や JSON 外の説明は出力しないこと。
```

## 7.6 `user_payload.jinja.md`

```jinja
Create an article draft using the following grounded input.

market:
{{ market | tojson }}

language_profile:
{{ language_profile | tojson }}

source_bundle:
{{ source_bundle | tojson }}

output_rules:
- Output JSON only.
- Use the language from language_profile.language.
- Use only the sources in source_bundle.sources.
- Every item in sources_used must correspond to a source from source_bundle.sources.
- Include all required sections from language_profile.required_sections.
- Include the exact risk disclaimer from language_profile.risk_disclaimer.
- Do not give investment advice.
- Do not fabricate financial numbers, publication dates, URLs, institutions, or source names.
```

## 7.7 PromptRenderer

新增：

```text
src/llm/prompt_renderer.py
```

职责：

1. 根据 task 加载 prompt spec；
2. 根据 language 加载对应 system prompt；
3. 渲染 user payload；
4. 生成 messages；
5. 返回 prompt_version；
6. 如果 prompt 文件缺失，返回明确错误。

接口：

```python
class RenderedPrompt(BaseModel):
    task: str
    language: str
    prompt_version: str
    messages: list[dict]


class PromptRenderer:
    def render(self, task: str, language: str, input_data: dict) -> RenderedPrompt:
        ...
```

---

# 8. LLM 调用结果统一

## 8.1 新增 LLMTaskResult

新增：

```text
src/llm/result.py
```

定义：

```python
from pydantic import BaseModel, Field
from typing import Optional


class LLMTaskError(BaseModel):
    type: str
    message: str
    retryable: bool = False
    raw: dict = Field(default_factory=dict)


class LLMTaskResult(BaseModel):
    success: bool
    task: str
    language: Optional[str] = None
    profile: Optional[str] = None
    model: Optional[str] = None
    prompt_version: Optional[str] = None
    output: Optional[dict] = None
    raw_text: Optional[str] = None
    usage: dict = Field(default_factory=dict)
    latency_ms: Optional[int] = None
    error: Optional[LLMTaskError] = None
    metadata: dict = Field(default_factory=dict)
```

## 8.2 Safe Wrapper

ArticlePipeline 不应该直接处理散乱 exception。

新增：

```python
def run_llm_task_safe(...) -> LLMTaskResult:
    ...
```

要求：

1. JSON parse 失败返回 `success=false`；
2. schema 失败返回 `success=false`；
3. provider timeout 返回 retryable error；
4. provider 429 / 5xx 返回 retryable error；
5. 配置错误返回 non-retryable error；
6. 所有错误都带 task、language、profile。

## 8.3 Retry 规则

第一阶段只做简单 retry：

- provider timeout：可重试；
- 429：可重试；
- 5xx：可重试；
- JSON parse 失败：不自动多次重试，最多进入一次 repair；
- source validation 失败：不重试；
- financial safety 失败：不重试；
- Notion 5xx：可重试；
- Notion schema/property 错误：不可重试。

---

# 9. Validator 设计

新增：

```text
src/content/validators/
  article_schema.py
  source_grounding.py
  financial_safety.py
  language_rules.py
  notion_exportable.py
  quality.py
```

## 9.1 ValidationResult

新增：

```text
src/content/result.py
```

定义：

```python
from pydantic import BaseModel, Field
from typing import Literal, Optional


class ValidationIssue(BaseModel):
    code: str
    message: str
    severity: Literal["info", "warning", "error"]
    field: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class ValidationResult(BaseModel):
    passed: bool
    exportable: bool = True
    issues: list[ValidationIssue] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)
```

规则：

- 有 `severity=error` 时 `passed=false`；
- 如果错误不允许写入 Notion，则 `exportable=false`；
- warning 可以写入 Notion，但必须显示在审核页面；
- 所有 validator 都返回统一格式。

## 9.2 Article Schema Validator

职责：

1. 把原始 dict 转成 ArticleDraft；
2. 检查字段类型；
3. 检查 required fields；
4. 检查 `faq` item；
5. 检查 `sources_used` item；
6. 检查 `uncertain_claims` item。

## 9.3 Source Grounding Validator

职责：

1. `sources_used[*].source_id` 必须来自 source_bundle；
2. `sources_used[*].url` 必须来自 source_bundle；
3. body 中出现的 URL 必须来自 source_bundle；
4. `sources_used` 不能为空；
5. 不允许出现 source_bundle 之外的 provider/source 名称；
6. 如果 source_bundle 为空，禁止调用 LLM。

## 9.4 Financial Safety Validator

可以包装现有 `news_pipeline/safety_validation.py`。

职责：

1. 检查保证收益；
2. 检查买入/卖出建议；
3. 检查止盈/止损；
4. 检查强预测；
5. 检查是否包含风险提示；
6. 检查无来源金融数字。

错误示例：

```text
Beli USD sekarang
Profit pasti
Target harga pasti
Take profit di ...
Stop loss di ...
Harga dijamin naik
```

## 9.5 Language Rules Validator

职责：

1. `article.language` 必须等于 language config；
2. body 必须主要使用目标语言；
3. body 必须包含 required_sections；
4. risk_disclaimer 必须符合语言配置；
5. SEO title / description 长度必须符合配置；
6. slug 必须符合配置；
7. 不允许明显混用错误语言。

## 9.6 Notion Exportable Validator

职责：

1. title 非空；
2. body 非空；
3. Notion properties 可映射；
4. sources 可渲染；
5. validation results 可渲染；
6. body 长度可拆成 blocks；
7. status 字段可设置。

## 9.7 Quality Validator

第一阶段可以轻量实现：

1. title 长度合理；
2. summary 不太短；
3. body 不太短；
4. FAQ 至少 2 条；
5. sources_used 至少 1 条；
6. uncertain_claims 可以为空，但高风险主题建议至少说明不确定性。

Quality warning 不一定阻止写入 Notion，但必须显示给审核者。

---

# 10. ArticlePipeline 主流程

## 10.1 新增文件

```text
src/content/article_pipeline.py
```

## 10.2 类接口

```python
class ArticlePipeline:
    def __init__(
        self,
        config_registry,
        tradingview_adapter,
        source_bundle_builder,
        llm_runner,
        article_validator,
        notion_exporter,
        job_store=None,
    ):
        ...

    def run_market(self, market_id: str, *, dry_run: bool = False, export_notion: bool = False) -> dict:
        ...
```

## 10.3 执行步骤

`run_market()` 必须执行：

1. 创建 `pipeline_run_id`；
2. 加载 market config；
3. 加载 language profile；
4. 加载 LLM profile；
5. 加载 Notion target；
6. 抓取 TradingView headlines；
7. 抓取新闻详情；
8. 标准化为 NormalizedNewsItem；
9. 去重；
10. 构建 SourceBundle；
11. 如果 source_bundle 不合格，停止；
12. 调用 `run_llm_task_safe(article_draft)`；
13. 解析 ArticleDraft；
14. 执行所有 validators；
15. 如果 validation failed 且 `exportable=false`，停止，不写 Notion；
16. 如果 dry_run，返回完整结果，不写 Notion；
17. 如果 export_notion，执行 Notion upsert；
18. 返回完整 PipelineResult。

## 10.4 PipelineResult

```python
class PipelineResult(BaseModel):
    success: bool
    status: str
    pipeline_run_id: str
    market_id: str
    symbol: str
    language: str
    source_bundle_hash: Optional[str] = None
    article: Optional[dict] = None
    source_bundle: Optional[dict] = None
    validation: dict = Field(default_factory=dict)
    llm: dict = Field(default_factory=dict)
    notion: dict = Field(default_factory=dict)
    errors: list[dict] = Field(default_factory=list)
    warnings: list[dict] = Field(default_factory=list)
```

## 10.5 状态列表

内部状态：

```text
CONFIG_LOADED
FETCHING_SOURCES
SOURCES_FETCHED
SOURCE_BUNDLE_READY
LLM_DRAFTING
DRAFT_CREATED
VALIDATING_SCHEMA
VALIDATING_SOURCE_GROUNDING
VALIDATING_SAFETY
VALIDATING_LANGUAGE_RULES
VALIDATING_NOTION_EXPORTABLE
VALIDATION_PASSED
VALIDATION_FAILED
DRY_RUN_SUCCESS
EXPORTING_NOTION
NOTION_EXPORTED
NEEDS_HUMAN_REVIEW
FAILED
```

---

# 11. Notion 导出设计

## 11.1 新增文件

```text
src/notion/target_resolver.py
src/notion/mapper.py
src/notion/exporter.py
```

可以先复用现有 `news_pipeline/notion_exporter.py`，但新流程应该通过 `src/notion/exporter.py` 包一层。

## 11.2 ResolvedNotionTarget

```python
class ResolvedNotionTarget(BaseModel):
    name: str
    language: str
    market: str
    parent_type: str
    parent_id: str
    status_default: str
    reviewer_status: str
    duplicate_policy: str = "update_existing"
    unique_key_fields: list[str] = []
```

## 11.3 Notion parent payload

必须支持：

```python
def build_notion_parent_payload(target: ResolvedNotionTarget) -> dict:
    if target.parent_type == "data_source":
        return {"data_source_id": target.parent_id}
    if target.parent_type == "database":
        return {"database_id": target.parent_id}
    if target.parent_type == "page":
        return {"page_id": target.parent_id}
    raise ValueError(f"Unsupported Notion parent_type: {target.parent_type}")
```

## 11.4 Notion upsert 策略

必须避免重复创建页面。

唯一键推荐：

```text
market_id + symbol + language + source_bundle_hash
```

导出前：

1. 根据 unique key 查询 Notion 是否已有页面；
2. 如果存在且 `duplicate_policy=update_existing`，更新已有页面；
3. 如果存在且 `duplicate_policy=skip_existing`，跳过；
4. 如果不存在，创建页面。

## 11.5 Notion properties

建议统一字段：

```text
Name
Status
Language
Market
Symbol
Article Type
AI Summary
SEO Title
SEO Description
Source Count
Source URLs
Risk Level
Prompt Version
LLM Model
Pipeline Run ID
Source Bundle Hash
Generated At
Review Notes
```

## 11.6 Notion blocks

页面正文结构：

```text
1. 审核说明
2. AI Summary
3. Article Body
4. FAQ
5. Sources
6. Risk Disclaimer
7. Validation Results
8. Generation Metadata
```

## 11.7 默认状态

所有 AI 生成内容写入 Notion 时必须是：

```text
Needs Review
```

不允许直接写入：

```text
Published
```

---

# 12. CLI / Jobs

## 12.1 新增 CLI

```text
src/jobs/validate_config.py
src/jobs/run_market.py
src/jobs/run_batch.py
src/jobs/retry_failed.py
```

## 12.2 命令

配置检查：

```bash
python -m src.jobs.validate_config
```

单 market dry-run：

```bash
python -m src.jobs.run_market --market usd_idr_id --dry-run
```

单 market 写入 Notion：

```bash
python -m src.jobs.run_market --market usd_idr_id --export-notion
```

所有 enabled markets dry-run：

```bash
python -m src.jobs.run_batch --enabled-only --dry-run
```

所有 enabled markets 写入 Notion：

```bash
python -m src.jobs.run_batch --enabled-only --export-notion
```

## 12.3 批处理规则

1. 一个 market 失败不能影响其他 market；
2. 每个 market 结果单独输出；
3. 最终 summary 包含 success_count、failed_count；
4. 失败项包含 market_id、status、error；
5. 批处理默认不重试整个 batch；
6. 单个任务内部根据 retry policy 重试。

---

# 13. 幂等、去重与重跑

## 13.1 为什么需要幂等

批量生成时，如果重复运行命令，不应该无限创建重复 Notion 页面。

## 13.2 幂等键

推荐：

```text
idempotency_key = market_id + symbol + language + source_bundle_hash + task
```

## 13.3 Notion 去重

写入 Notion 前，先查是否存在相同：

```text
Source Bundle Hash
Market
Symbol
Language
```

如果存在：

- `update_existing`：更新页面内容和 metadata；
- `skip_existing`：跳过导出；
- `create_new`：创建新页面，但不推荐默认使用。

## 13.4 重跑规则

允许重跑：

- LLM timeout；
- Notion 5xx；
- 临时抓取失败；
- dry-run 调试。

不建议自动重跑：

- source grounding 失败；
- safety validation 失败；
- Notion schema 错误；
- 配置错误；
- prompt 文件缺失。

---

# 14. 日志、监控与成本

## 14.1 每次运行必须记录

至少 print JSON log，后续可接数据库或 observability 平台。

字段：

```json
{
  "event": "pipeline_run_finished",
  "pipeline_run_id": "...",
  "market_id": "usd_idr_id",
  "symbol": "USDIDR",
  "language": "id",
  "status": "NOTION_EXPORTED",
  "source_bundle_hash": "...",
  "llm_model": "...",
  "prompt_version": "...",
  "input_tokens": 0,
  "output_tokens": 0,
  "latency_ms": 0,
  "notion_page_id": "...",
  "errors": [],
  "warnings": []
}
```

## 14.2 成本控制

配置中未来可增加：

```yaml
budget:
  max_articles_per_run: 3
  max_tokens_per_article: 4000
  max_cost_per_run_usd: 5.0
```

第一阶段可以只记录 usage，不强制计算成本。

## 14.3 限流

第一阶段：串行或低并发。
后续批量：每个 provider/profile 加 semaphore 和 RPM 限制。

---

# 15. 安全、合规与内容边界

## 15.1 金融内容边界

文章必须是信息和教育用途，不能是投资建议。

禁止：

- 买入；
- 卖出；
- 做多；
- 做空；
- 止盈；
- 止损；
- 保证收益；
- 确定性预测；
- 个性化投资建议。

## 15.2 来源边界

LLM 只能使用 source_bundle 里的来源。
不允许编造：

- URL；
- 来源名称；
- 发布时间；
- 价格；
- 经济数据；
- 央行言论；
- 机构观点。

## 15.3 人工审核

所有文章必须进入 Notion 人工审核。
Notion 状态必须是 `Needs Review`。
不允许自动发布。

## 15.4 抓取与版权注意

系统应保留原始来源链接。
文章应该是基于来源的摘要、解释和分析，不应大段复制新闻原文。
如果某来源内容过短、无法读取、疑似付费墙，应降级为 summary-based draft 或进入人工审核。

---

# 16. 测试计划

## 16.1 配置测试

新增：

```text
tests/test_config_registry.py
tests/test_validate_config.py
```

覆盖：

1. 加载 pipeline.yaml；
2. 加载 languages/id.yaml；
3. enabled market 引用的 language 存在；
4. LLM profile 存在；
5. Notion target 存在；
6. prompt 文件存在；
7. 缺失 env var 报错或 warning；
8. language 不一致时报错。

## 16.2 Prompt 测试

新增：

```text
tests/test_prompt_renderer.py
```

覆盖：

1. `article_draft + id` 加载 `id.system.md`；
2. `article_draft + ja` 加载 `ja.system.md`；
3. user payload 正确渲染；
4. prompt_version 正确；
5. 缺 prompt 文件时报错。

## 16.3 Schema 测试

新增：

```text
tests/test_article_schema.py
```

覆盖：

1. 合法 ArticleDraft 通过；
2. 缺 title 失败；
3. sources_used 格式错误失败；
4. faq 格式错误失败；
5. language 不匹配失败。

## 16.4 Source Grounding 测试

新增：

```text
tests/test_source_grounding_validator.py
```

覆盖：

1. source_id 全部来自 source_bundle，通过；
2. 未知 source_id，失败；
3. 未知 URL，失败；
4. body 出现未知 URL，失败；
5. sources_used 为空，失败。

## 16.5 Pipeline 测试

新增：

```text
tests/test_article_pipeline.py
```

使用 fake components：

- FakeTradingViewAdapter；
- FakeLLMRunner；
- FakeNotionExporter。

覆盖：

1. dry-run 不写 Notion；
2. export-notion 调用 exporter；
3. source_bundle 为空不调用 LLM；
4. LLM 失败不导出 Notion；
5. validator 失败不导出 Notion；
6. 成功返回 DRY_RUN_SUCCESS 或 NOTION_EXPORTED。

## 16.6 Notion 测试

新增：

```text
tests/test_notion_mapper.py
tests/test_notion_exporter.py
```

覆盖：

1. ArticleDraft 正确映射 properties；
2. sources 渲染为 blocks；
3. validation results 渲染为 blocks；
4. `parent_type=data_source` 使用 `data_source_id`；
5. `parent_type=database` 使用 `database_id`；
6. duplicate_policy 正确工作。

---

# 17. 分阶段实施计划

## Phase 1：配置系统

目标：先把配置系统建起来，不改 LLM 主链路。

新增文件：

```text
config/pipeline.yaml
config/llm_profiles.yaml
config/notion_targets.yaml
config/languages/id.yaml

src/config/__init__.py
src/config/models.py
src/config/loader.py
src/config/validator.py

src/jobs/__init__.py
src/jobs/validate_config.py

tests/test_config_registry.py
tests/test_validate_config.py
```

验收命令：

```bash
python -m src.jobs.validate_config
pytest tests/test_config_registry.py tests/test_validate_config.py
```

禁止事项：

- 不改 LLM 调用逻辑；
- 不改 Notion 导出逻辑；
- 不删除旧模块。

## Phase 2：Prompt 多语言化

目标：`article_draft` 根据 language 加载不同 system prompt。

新增文件：

```text
src/llm/prompts/article_draft/spec.yaml
src/llm/prompts/article_draft/id.system.md
src/llm/prompts/article_draft/ja.system.md
src/llm/prompts/article_draft/user_payload.jinja.md
src/llm/prompt_renderer.py

tests/test_prompt_renderer.py
```

验收：

```bash
pytest tests/test_prompt_renderer.py
```

## Phase 3：ArticleDraft Schema 与 Validators

目标：LLM 输出强类型化。

新增文件：

```text
src/content/article_schema.py
src/content/result.py
src/content/validators/article_schema.py
src/content/validators/source_grounding.py
src/content/validators/financial_safety.py
src/content/validators/language_rules.py
src/content/validators/notion_exportable.py

tests/test_article_schema.py
tests/test_source_grounding_validator.py
```

验收：

```bash
pytest tests/test_article_schema.py tests/test_source_grounding_validator.py
```

## Phase 4：TradingView Adapter 与 SourceBundle

目标：把 TradingView 输出标准化。

新增文件：

```text
src/ingest/tradingview.py
src/ingest/normalize.py
src/ingest/dedupe.py
src/content/source_bundle.py

tests/test_tradingview_adapter.py
tests/test_source_bundle.py
```

验收：

```bash
pytest tests/test_tradingview_adapter.py tests/test_source_bundle.py
```

## Phase 5：ArticlePipeline dry-run

目标：跑通单个 market dry-run，不写 Notion。

新增文件：

```text
src/content/article_pipeline.py
src/jobs/run_market.py

tests/test_article_pipeline.py
```

验收：

```bash
python -m src.jobs.run_market --market usd_idr_id --dry-run
pytest tests/test_article_pipeline.py
```

## Phase 6：Notion target 路由与导出

目标：根据 market/language 写入对应 Notion target。

新增文件：

```text
src/notion/target_resolver.py
src/notion/mapper.py
src/notion/exporter.py

tests/test_notion_mapper.py
tests/test_notion_exporter.py
```

验收：

```bash
python -m src.jobs.run_market --market usd_idr_id --export-notion
pytest tests/test_notion_mapper.py tests/test_notion_exporter.py
```

## Phase 7：Batch Runner

目标：支持批量跑 enabled markets。

新增文件：

```text
src/jobs/run_batch.py
```

验收：

```bash
python -m src.jobs.run_batch --enabled-only --dry-run
```

---

# 18. Codex 执行规范

## 18.1 总原则

Codex 必须：

1. 按 Phase 实施，不要跨阶段大改；
2. 每个 Phase 必须新增测试；
3. 保持现有测试通过；
4. 新代码优先放在 `src/`；
5. `news_pipeline/` 只做兼容 wrapper；
6. 不写死 API key、Notion ID、模型 ID；
7. 不让 LLM 输出直接进入 published；
8. 不删除旧接口；
9. 不在业务代码散落读取 env；
10. 不把语言逻辑写成大量 if/else。

## 18.2 Codex 第一个任务

请先实现 Phase 1。

任务：

```text
新增配置系统，支持加载 pipeline.yaml、llm_profiles.yaml、notion_targets.yaml、languages/*.yaml，并提供 validate_config CLI。
```

必须创建：

```text
config/pipeline.yaml
config/llm_profiles.yaml
config/notion_targets.yaml
config/languages/id.yaml

src/config/__init__.py
src/config/models.py
src/config/loader.py
src/config/validator.py

src/jobs/__init__.py
src/jobs/validate_config.py

tests/test_config_registry.py
tests/test_validate_config.py
```

不要改：

```text
src/llm/run_task.py
news_pipeline/notion_exporter.py
tradingview_scraper/
```

除非测试 import path 必须微调。

验收：

```bash
python -m src.jobs.validate_config
pytest tests/test_config_registry.py tests/test_validate_config.py
```

---

# 19. 新增语言 / symbol 的未来操作方式

## 19.1 新增语言

例如新增韩语：

1. 新增 `config/languages/ko.yaml`；
2. 新增 `src/llm/prompts/article_draft/ko.system.md`；
3. 在 `config/llm_profiles.yaml` 加 `article_writer_ko`；
4. 在 `config/notion_targets.yaml` 加 `notion_articles_ko`；
5. 在 `config/pipeline.yaml` 加 market；
6. 运行 `python -m src.jobs.validate_config`；
7. 运行 dry-run；
8. 最后 export Notion。

核心 pipeline 不应修改。

## 19.2 新增 symbol

例如新增 USDKRW：

只需要在 `pipeline.yaml` 新增 market：

```yaml
- id: usd_krw_ko
  enabled: true
  symbol: USDKRW
  exchange: FX_IDC
  base_currency: USD
  quote_currency: KRW
  tradingview:
    language: ko
    locale: kr
    url: "https://kr.tradingview.com/symbols/USDKRW/news/"
  content:
    language: ko
    market: Korea
    task: article_draft
  llm:
    draft_profile: article_writer_ko
  notion:
    target: notion_articles_ko
```

## 19.3 新增文章类型

例如新增 `market_alert`：

1. 新增 `src/llm/prompts/market_alert/`；
2. 新增 task spec；
3. 新增 schema；
4. 新增 validator；
5. 在 config 中把 task 改为 `market_alert`。

---

# 20. 风险清单

## 20.1 工程风险

| 风险 | 对策 |
|---|---|
| 配置越来越复杂 | Pydantic schema + validate_config |
| 多语言 prompt 混乱 | prompt 文件按 task/language 分目录 |
| 重复写 Notion | source_bundle_hash + upsert |
| LLM 输出格式不稳定 | json_schema + Pydantic + repair |
| 批处理失败难排查 | pipeline_run_id + structured result |
| 旧代码和新代码冲突 | `news_pipeline` 做兼容 wrapper |

## 20.2 内容风险

| 风险 | 对策 |
|---|---|
| 编造来源 | source grounding validator |
| 投资建议 | financial safety validator |
| 语言错误 | language rules validator |
| 复制原文过多 | prompt 限制 + quality review |
| 旧新闻生成新文章 | source age policy |
| Notion 审核者看不懂来源 | 页面 blocks 显示 sources 和 validation |

## 20.3 成本风险

| 风险 | 对策 |
|---|---|
| 批量生成 token 过高 | max_articles_per_run + max_tokens |
| 重试过多 | max_retries=1 起步 |
| 模型太贵 | profile 可配置 |
| 重复生成 | idempotency key |

---

# 21. 最终总结

本项目的正确方向不是“写一个更长的 prompt”，而是构建一个可扩展、可追踪、可审核的内容生产系统。

最终形态应该是：

```text
新增语言 = 新增 language config + system prompt + LLM profile + Notion target
新增 symbol = 新增 market config
新增文章类型 = 新增 task spec + prompt + schema + validator
```

核心 pipeline 不应该随着语言和市场增加而膨胀。

本 PRD 的第一落地目标是：

```text
先实现配置系统，再实现多语言 prompt，再实现强类型文章 schema，再接入 article pipeline，最后接 Notion upsert 和 batch。
```

最优先执行：

```text
Phase 1：配置系统
```

因为只有配置系统稳定后，后面的多语言、多模型、多 Notion 表才不会变成硬编码泥潭。
