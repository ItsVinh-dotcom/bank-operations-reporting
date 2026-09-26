-- Schemas (layers) of the DLB data warehouse
--   ctl  : batch control & file logs
--   stg  : raw landing of core-banking extracts (all TEXT, truncated every batch)
--   dwh  : conformed dimensions (SCD2) and facts
--   mart : reporting tables consumed by Power BI / Excel
--   dq   : data-quality rules and results
CREATE SCHEMA IF NOT EXISTS ctl;
CREATE SCHEMA IF NOT EXISTS stg;
CREATE SCHEMA IF NOT EXISTS dwh;
CREATE SCHEMA IF NOT EXISTS mart;
CREATE SCHEMA IF NOT EXISTS dq;

CREATE TABLE IF NOT EXISTS ctl.batch (
    batch_id        serial PRIMARY KEY,
    business_date   date        NOT NULL,
    batch_type      text        NOT NULL CHECK (batch_type IN ('HISTORY', 'EOD')),
    folder          text        NOT NULL,
    status          text        NOT NULL DEFAULT 'RUNNING',   -- RUNNING / SUCCESS / FAILED
    started_at      timestamptz NOT NULL DEFAULT now(),
    finished_at     timestamptz,
    message         text,
    UNIQUE (business_date, batch_type)
);

CREATE TABLE IF NOT EXISTS ctl.file_log (
    batch_id        int  NOT NULL REFERENCES ctl.batch(batch_id),
    entity          text NOT NULL,
    file_name       text NOT NULL,
    revision        int  NOT NULL DEFAULT 0,
    trailer_count   int,
    loaded_count    int,
    status          text NOT NULL,             -- LOADED / REJECTED
    message         text,
    logged_at       timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (batch_id, entity, revision)
);

CREATE TABLE IF NOT EXISTS ctl.step_log (
    batch_id    int  NOT NULL,
    step        text NOT NULL,
    rows_affected bigint,
    started_at  timestamptz NOT NULL,
    finished_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
