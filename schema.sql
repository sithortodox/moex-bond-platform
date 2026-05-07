CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS bonds (
    id                  SERIAL PRIMARY KEY,
    isin0               VARCHAR(20),
    rating              VARCHAR(50),
    industry            VARCHAR(200),
    yield_cb            NUMERIC,
    yield_dohod         NUMERIC,
    yield_avg           NUMERIC,
    yield_deviation     NUMERIC,
    yield_category      VARCHAR(50),
    liquidity_cb        NUMERIC,
    liquidity_dohod     VARCHAR(50),
    liquidity_avg       NUMERIC,
    liquidity_category  VARCHAR(50),
    isin                VARCHAR(20) UNIQUE,
    name                VARCHAR(500),
    issuer              VARCHAR(500),
    primary_borrower    VARCHAR(500),
    borrower_country    VARCHAR(100),
    nominal_currency    VARCHAR(10),
    issue_volume_bln    NUMERIC,
    nearest_date_str    VARCHAR(50),
    years_to_date       NUMERIC,
    duration            NUMERIC,
    event_at_date       VARCHAR(100),
    ytm                 NUMERIC,
    yield_no_reinvest   NUMERIC,
    reinvest_profit_pct NUMERIC,
    simple_yield        NUMERIC,
    current_yield       NUMERIC,
    credit_quality_rank VARCHAR(50),
    credit_quality_num  NUMERIC,
    issuer_quality      NUMERIC,
    inside_q            NUMERIC,
    outside_q           NUMERIC,
    netdebt_equity_rank NUMERIC,
    liquidity_ratio     NUMERIC,
    median_daily_turnover NUMERIC,
    complexity          NUMERIC,
    size_rank           NUMERIC,
    issue_date          VARCHAR(50),
    maturity_date       VARCHAR(50),
    yield_calc_date     VARCHAR(50),
    current_nominal     NUMERIC,
    min_lot             NUMERIC,
    price_pct           NUMERIC,
    nkd                 NUMERIC,
    coupon_size         NUMERIC,
    current_coupon_pct  NUMERIC,
    coupon_freq         NUMERIC,
    coupon_type         VARCHAR(100),
    is_subordinated     VARCHAR(10),
    has_guarantee       VARCHAR(10),
    issuer_type         VARCHAR(100),
    base_index_frn      VARCHAR(200),
    frn_premium_discount NUMERIC,
    board_group         INTEGER,
    board_id            VARCHAR(20),
    secid               VARCHAR(20),
    moex_yield          NUMERIC,
    moex_duration       NUMERIC,
    moex_price          NUMERIC,
    moex_nkd            NUMERIC,
    moex_volume_15d     NUMERIC,
    trade_mode          VARCHAR(100),
    offer_call_date     VARCHAR(50),
    offer_put_date      VARCHAR(50),
    g_spread            NUMERIC,
    amortization        VARCHAR(10),
    is_qualified        VARCHAR(10),
    payments_known      VARCHAR(10),
    updated_at          TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bonds_isin ON bonds(isin);
CREATE INDEX IF NOT EXISTS idx_bonds_name_trgm ON bonds USING gin (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_bonds_issuer_trgm ON bonds USING gin (issuer gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_bonds_ytm ON bonds(ytm);
CREATE INDEX IF NOT EXISTS idx_bonds_rating ON bonds(rating);
CREATE INDEX IF NOT EXISTS idx_bonds_duration ON bonds(duration);
CREATE INDEX IF NOT EXISTS idx_bonds_price ON bonds(price_pct);
CREATE INDEX IF NOT EXISTS idx_bonds_issuer_type ON bonds(issuer_type);
CREATE INDEX IF NOT EXISTS idx_bonds_updated_at ON bonds(updated_at);

CREATE TABLE IF NOT EXISTS collection_log (
    id         SERIAL PRIMARY KEY,
    started_at TIMESTAMP DEFAULT NOW(),
    finished_at TIMESTAMP,
    status     VARCHAR(20),
    bonds_found INTEGER,
    bonds_updated INTEGER,
    bonds_inserted INTEGER,
    errors     INTEGER DEFAULT 0,
    log_text   TEXT
);
