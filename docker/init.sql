-- Enable TimescaleDB extension
CREATE EXTENSION IF NOT EXISTS timescaledb;

-- Create monitoring schema
CREATE SCHEMA IF NOT EXISTS monitoring;

-- Create hypertable for metrics
CREATE TABLE IF NOT EXISTS monitoring.metrics (
    time TIMESTAMPTZ NOT NULL,
    host TEXT NOT NULL,
    service TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value DOUBLE PRECISION,
    status TEXT,
    metadata JSONB
);

-- Convert to hypertable with 1 day chunks
SELECT create_hypertable('monitoring.metrics', 'time', chunk_time_interval => INTERVAL '1 day');

-- Create indexes for fast queries
CREATE INDEX IF NOT EXISTS idx_metrics_host_time ON monitoring.metrics (host, time DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_service_time ON monitoring.metrics (service, time DESC);
CREATE INDEX IF NOT EXISTS idx_metrics_status ON monitoring.metrics (status);

-- Create alerts table
CREATE TABLE IF NOT EXISTS monitoring.alerts (
    id SERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    host TEXT NOT NULL,
    service TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT,
    acknowledged BOOLEAN DEFAULT FALSE,
    resolved BOOLEAN DEFAULT FALSE
);

-- Create subdomains table
CREATE TABLE IF NOT EXISTS monitoring.subdomains (
    id SERIAL PRIMARY KEY,
    domain TEXT NOT NULL,
    subdomain TEXT NOT NULL UNIQUE,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE,
    platform TEXT,
    last_platform_check TIMESTAMPTZ
);

-- Create uptime checks table
CREATE TABLE IF NOT EXISTS monitoring.uptime_checks (
    time TIMESTAMPTZ NOT NULL,
    subdomain TEXT NOT NULL,
    status_code INTEGER,
    response_time_ms DOUBLE PRECISION,
    up BOOLEAN NOT NULL,
    platform TEXT,
    error_message TEXT,
    headers JSONB
);

-- Convert to hypertable for time series
SELECT create_hypertable('monitoring.uptime_checks', 'time', chunk_time_interval => INTERVAL '1 day');

-- Create other_dns table for non-project subdomains
CREATE TABLE IF NOT EXISTS monitoring.other_dns (
    id SERIAL PRIMARY KEY,
    subdomain TEXT NOT NULL UNIQUE,
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    active BOOLEAN DEFAULT TRUE,
    platform TEXT,
    last_platform_check TIMESTAMPTZ
);

-- Create indexes
CREATE INDEX IF NOT EXISTS idx_uptime_checks_subdomain_time ON monitoring.uptime_checks (subdomain, time DESC);
CREATE INDEX IF NOT EXISTS idx_uptime_checks_status ON monitoring.uptime_checks (up, time DESC);
CREATE INDEX IF NOT EXISTS idx_subdomains_active ON monitoring.subdomains (active, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_other_dns_active ON monitoring.other_dns (active, last_seen DESC);

-- Move DNS-discovered subdomains to other_dns table (keep only legitimate projects in subdomains)
-- Only keep visualizations.bettergov.ph as it's the known project
INSERT INTO monitoring.other_dns (subdomain, discovered_at, last_seen, active, platform, last_platform_check)
SELECT subdomain, discovered_at, last_seen, active, platform, last_platform_check
FROM monitoring.subdomains
WHERE subdomain NOT IN ('visualizations.bettergov.ph', 'bettergov.ph');

-- Remove moved subdomains from main subdomains table
DELETE FROM monitoring.subdomains
WHERE subdomain NOT IN ('visualizations.bettergov.ph', 'bettergov.ph');

-- Insert visualizations.bettergov.ph if it doesn't exist
INSERT INTO monitoring.subdomains (domain, subdomain, discovered_at, active)
VALUES ('bettergov.ph', 'visualizations.bettergov.ph', NOW(), true)
ON CONFLICT (subdomain) DO NOTHING;

-- Create continuous aggregates for hourly stats
CREATE MATERIALIZED VIEW monitoring.hourly_metrics
WITH (timescaledb.continuous) AS
SELECT
    time_bucket('1 hour', time) AS bucket,
    host,
    service,
    metric_name,
    AVG(value) as avg_value,
    MIN(value) as min_value,
    MAX(value) as max_value,
    COUNT(*) as sample_count
FROM monitoring.metrics
GROUP BY bucket, host, service, metric_name
WITH NO DATA;

-- Enable automatic refresh
SELECT add_continuous_aggregate_policy('monitoring.hourly_metrics',
    start_offset => INTERVAL '3 hours',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour');

-- Create retention policy (keep raw data for 30 days)
SELECT add_retention_policy('monitoring.metrics', INTERVAL '30 days');
