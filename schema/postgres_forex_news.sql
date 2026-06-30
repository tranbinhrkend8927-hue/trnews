CREATE TABLE IF NOT EXISTS forex_symbols (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL UNIQUE,
    base_currency TEXT,
    quote_currency TEXT,
    locale TEXT,
    tradingview_news_url TEXT,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS forex_news (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    base_currency TEXT,
    quote_currency TEXT,
    locale TEXT,
    title TEXT,
    summary TEXT,
    content TEXT,
    url TEXT,
    canonical_url TEXT,
    source TEXT,
    source_url TEXT,
    published_at TIMESTAMPTZ,
    fetched_at TIMESTAMPTZ,
    content_hash TEXT NOT NULL,
    raw_json JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS forex_news_symbol_canonical_url_uidx
ON forex_news(symbol, canonical_url)
WHERE canonical_url IS NOT NULL AND canonical_url <> '';

CREATE UNIQUE INDEX IF NOT EXISTS forex_news_symbol_url_uidx
ON forex_news(symbol, url)
WHERE url IS NOT NULL AND url <> '';

CREATE UNIQUE INDEX IF NOT EXISTS forex_news_symbol_content_hash_uidx
ON forex_news(symbol, content_hash);

CREATE TABLE IF NOT EXISTS content_topics (
    id BIGSERIAL PRIMARY KEY,
    symbol TEXT NOT NULL,
    topic_type TEXT NOT NULL,
    title TEXT NOT NULL,
    score NUMERIC(6,2) NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'candidate',
    reason_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_news_ids BIGINT[] NOT NULL DEFAULT '{}',
    topic_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT content_topics_topic_type_check CHECK (
        topic_type IN (
            'daily_usdidr_update',
            'rupiah_explainer',
            'macro_event_watch',
            'bank_indonesia_watch'
        )
    ),
    CONSTRAINT content_topics_status_check CHECK (
        status IN ('candidate', 'approved', 'rejected', 'generated')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS content_topics_symbol_topic_hash_uidx
ON content_topics(symbol, topic_hash);

CREATE INDEX IF NOT EXISTS content_topics_symbol_status_score_idx
ON content_topics(symbol, status, score DESC);

CREATE TABLE IF NOT EXISTS generated_articles (
    id BIGSERIAL PRIMARY KEY,
    topic_id BIGINT NOT NULL,
    symbol TEXT NOT NULL,
    language TEXT NOT NULL DEFAULT 'id',
    title TEXT NOT NULL,
    slug TEXT,
    summary TEXT,
    body TEXT,
    seo_title TEXT,
    seo_description TEXT,
    status TEXT NOT NULL DEFAULT 'draft',
    fact_check_status TEXT NOT NULL DEFAULT 'pending',
    risk_disclaimer_included BOOLEAN NOT NULL DEFAULT FALSE,
    sources_json JSONB NOT NULL DEFAULT '[]'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at TIMESTAMPTZ,
    CONSTRAINT generated_articles_topic_id_fkey
        FOREIGN KEY (topic_id) REFERENCES content_topics(id) ON DELETE RESTRICT,
    CONSTRAINT generated_articles_status_check CHECK (
        status IN ('draft', 'pending_review', 'approved', 'rejected', 'published')
    ),
    CONSTRAINT generated_articles_fact_check_status_check CHECK (
        fact_check_status IN ('pending', 'passed', 'failed', 'needs_sources')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS generated_articles_topic_id_uidx
ON generated_articles(topic_id);

CREATE INDEX IF NOT EXISTS generated_articles_topic_id_idx
ON generated_articles(topic_id);

CREATE INDEX IF NOT EXISTS generated_articles_symbol_status_idx
ON generated_articles(symbol, status);

CREATE INDEX IF NOT EXISTS generated_articles_fact_check_status_idx
ON generated_articles(fact_check_status);

CREATE TABLE IF NOT EXISTS article_sources (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT NOT NULL,
    source_type TEXT,
    source_name TEXT,
    source_url TEXT,
    cited_claim TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT article_sources_article_id_fkey
        FOREIGN KEY (article_id) REFERENCES generated_articles(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS article_sources_article_id_idx
ON article_sources(article_id);

CREATE TABLE IF NOT EXISTS article_reviews (
    id BIGSERIAL PRIMARY KEY,
    article_id BIGINT NOT NULL REFERENCES generated_articles(id) ON DELETE CASCADE,
    decision TEXT NOT NULL,
    reviewer TEXT,
    reviewer_notes TEXT,
    previous_status TEXT,
    new_status TEXT,
    safety_result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    quality_result_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    review_report_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT article_reviews_decision_check
        CHECK (decision IN ('approved', 'rejected', 'needs_changes'))
);

CREATE INDEX IF NOT EXISTS idx_article_reviews_article_id
ON article_reviews(article_id);

CREATE INDEX IF NOT EXISTS idx_article_reviews_decision
ON article_reviews(decision);

CREATE INDEX IF NOT EXISTS idx_article_reviews_created_at
ON article_reviews(created_at);
