PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_versions (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO schema_versions (version) VALUES (1);

CREATE TABLE IF NOT EXISTS securities (
    symbol TEXT PRIMARY KEY,
    provider_symbol TEXT NOT NULL UNIQUE,
    company_name TEXT NOT NULL,
    exchange TEXT NOT NULL DEFAULT 'SGX',
    currency TEXT NOT NULL DEFAULT 'SGD',
    sector TEXT,
    instrument_type TEXT NOT NULL DEFAULT 'equity',
    board_lot INTEGER,
    is_active INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1)),
    metadata_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS screening_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of_date TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('running', 'completed', 'failed')),
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TEXT,
    parameters_json TEXT NOT NULL,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS screening_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL REFERENCES screening_runs(id),
    symbol TEXT NOT NULL REFERENCES securities(symbol),
    eligible INTEGER NOT NULL CHECK (eligible IN (0, 1)),
    rank INTEGER,
    score REAL,
    signals_json TEXT NOT NULL,
    rejection_reasons_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE (run_id, symbol)
);

CREATE TABLE IF NOT EXISTS research_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT REFERENCES securities(symbol),
    source_url TEXT NOT NULL,
    source_name TEXT NOT NULL,
    published_at TEXT,
    retrieved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    content_hash TEXT NOT NULL,
    document_type TEXT NOT NULL DEFAULT 'news'
        CHECK (document_type IN ('news', 'announcement', 'filing', 'issuer_ir', 'other')),
    title TEXT NOT NULL,
    content_text TEXT NOT NULL,
    UNIQUE (source_url, content_hash)
);

CREATE TABLE IF NOT EXISTS trade_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    screening_result_id INTEGER NOT NULL REFERENCES screening_results(id),
    proposal_date TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('long', 'avoid', 'exit_existing')),
    conviction TEXT NOT NULL CHECK (conviction IN ('low', 'medium', 'high')),
    thesis TEXT NOT NULL,
    invalidation TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'approved_manual', 'rejected', 'expired')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    symbol TEXT NOT NULL REFERENCES securities(symbol),
    trade_date TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity REAL NOT NULL CHECK (quantity > 0),
    price REAL NOT NULL CHECK (price > 0),
    fees REAL NOT NULL DEFAULT 0 CHECK (fees >= 0),
    currency TEXT NOT NULL DEFAULT 'SGD',
    source TEXT NOT NULL DEFAULT 'manual',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS cash_ledger_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_id TEXT UNIQUE,
    event_date TEXT NOT NULL,
    entry_type TEXT NOT NULL
        CHECK (entry_type IN ('deposit', 'withdrawal', 'dividend', 'interest', 'fee', 'tax', 'other')),
    amount REAL NOT NULL CHECK (amount != 0),
    currency TEXT NOT NULL DEFAULT 'SGD',
    symbol TEXT REFERENCES securities(symbol),
    source TEXT NOT NULL DEFAULT 'manual',
    notes TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    as_of_at TEXT NOT NULL,
    cash_balance REAL NOT NULL,
    total_market_value REAL NOT NULL,
    total_cost_basis REAL NOT NULL,
    realized_pnl REAL NOT NULL DEFAULT 0,
    unrealized_pnl REAL NOT NULL DEFAULT 0,
    currency TEXT NOT NULL DEFAULT 'SGD',
    source TEXT NOT NULL DEFAULT 'manual',
    UNIQUE (as_of_at, source)
);

CREATE TABLE IF NOT EXISTS portfolio_positions (
    snapshot_id INTEGER NOT NULL REFERENCES portfolio_snapshots(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL REFERENCES securities(symbol),
    quantity REAL NOT NULL CHECK (quantity >= 0),
    average_cost REAL NOT NULL CHECK (average_cost >= 0),
    cost_basis REAL NOT NULL CHECK (cost_basis >= 0),
    market_price REAL CHECK (market_price >= 0),
    market_value REAL CHECK (market_value >= 0),
    unrealized_pnl REAL,
    PRIMARY KEY (snapshot_id, symbol)
);

CREATE TABLE IF NOT EXISTS trade_tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id INTEGER REFERENCES trade_proposals(id),
    symbol TEXT NOT NULL REFERENCES securities(symbol),
    side TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity REAL NOT NULL CHECK (quantity > 0),
    limit_price REAL CHECK (limit_price > 0),
    estimated_fees REAL NOT NULL DEFAULT 0 CHECK (estimated_fees >= 0),
    currency TEXT NOT NULL DEFAULT 'SGD',
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN (
            'proposed', 'approved_manual', 'rejected', 'executed_manual', 'cancelled', 'expired'
        )),
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT,
    executed_at TEXT,
    external_reference TEXT,
    execution_manifest_json TEXT,
    CHECK (status != 'executed_manual' OR execution_manifest_json IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id TEXT,
    actor TEXT NOT NULL DEFAULT 'system',
    payload_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_screening_runs_date ON screening_runs(as_of_date);
CREATE INDEX IF NOT EXISTS idx_screening_results_run ON screening_results(run_id);
CREATE INDEX IF NOT EXISTS idx_research_symbol_published
    ON research_documents(symbol, published_at);
CREATE INDEX IF NOT EXISTS idx_proposals_date_status
    ON trade_proposals(proposal_date, status);
CREATE INDEX IF NOT EXISTS idx_transactions_symbol_date
    ON portfolio_transactions(symbol, trade_date);
CREATE INDEX IF NOT EXISTS idx_cash_ledger_date
    ON cash_ledger_entries(event_date);
CREATE INDEX IF NOT EXISTS idx_positions_symbol
    ON portfolio_positions(symbol);
CREATE INDEX IF NOT EXISTS idx_trade_tickets_status
    ON trade_tickets(status, generated_at);
