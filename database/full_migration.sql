-- Full Migration Script for Open Monitoring
-- Combines all migrations and ensures database is in correct state
-- Safe to run multiple times (uses IF NOT EXISTS and ADD COLUMN IF NOT EXISTS)

-- Step 1: Add all required columns to subdomains table
ALTER TABLE monitoring.subdomains ADD COLUMN IF NOT EXISTS discovery_method TEXT NOT NULL DEFAULT 'DNS Enumeration';
ALTER TABLE monitoring.subdomains ADD COLUMN IF NOT EXISTS current_status TEXT DEFAULT 'UNKNOWN';
ALTER TABLE monitoring.subdomains ADD COLUMN IF NOT EXISTS consecutive_up_count INTEGER DEFAULT 0;
ALTER TABLE monitoring.subdomains ADD COLUMN IF NOT EXISTS consecutive_down_count INTEGER DEFAULT 0;
ALTER TABLE monitoring.subdomains ADD COLUMN IF NOT EXISTS last_status_change TIMESTAMPTZ;
ALTER TABLE monitoring.subdomains ADD COLUMN IF NOT EXISTS is_flapping BOOLEAN DEFAULT FALSE;
ALTER TABLE monitoring.subdomains ADD COLUMN IF NOT EXISTS check_path TEXT DEFAULT '/';

-- Step 2: Create all indexes
CREATE INDEX IF NOT EXISTS idx_subdomains_discovery_method ON monitoring.subdomains (discovery_method, active, last_seen DESC);
CREATE INDEX IF NOT EXISTS idx_subdomains_status ON monitoring.subdomains (current_status, active);
CREATE INDEX IF NOT EXISTS idx_subdomains_flapping ON monitoring.subdomains (is_flapping, active);
CREATE INDEX IF NOT EXISTS idx_subdomains_check_path ON monitoring.subdomains (subdomain, check_path);

-- Step 3: Ensure core project subdomains are marked correctly
-- Set all to DNS Enumeration first
UPDATE monitoring.subdomains SET discovery_method = 'DNS Enumeration', active = false;

-- Mark core 10 projects as active with Project Discovery
UPDATE monitoring.subdomains 
SET discovery_method = 'Project Discovery', active = true
WHERE subdomain IN (
    'bettergov.ph',
    'visualizations.bettergov.ph',
    'budget.bettergov.ph',
    'docs.bettergov.ph',
    'govchain.bettergov.ph',
    'hotlines.bettergov.ph',
    'open-congress-api.bettergov.ph',
    'saln.bettergov.ph',
    'taxdirectory.bettergov.ph',
    'api.bettergov.ph'
);

-- Step 4: Set custom check paths
UPDATE monitoring.subdomains 
SET check_path = '/api/status'
WHERE subdomain = 'api.bettergov.ph';

-- Step 5: Create agent_heartbeats table if it doesn't exist
CREATE TABLE IF NOT EXISTS monitoring.agent_heartbeats (
    location TEXT PRIMARY KEY,
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status TEXT DEFAULT 'active',
    agent_token TEXT,
    expected_token TEXT,
    token_generated_at TIMESTAMPTZ,
    out_of_sync BOOLEAN DEFAULT FALSE
);

-- Add token columns if table already exists
ALTER TABLE monitoring.agent_heartbeats ADD COLUMN IF NOT EXISTS agent_token TEXT;
ALTER TABLE monitoring.agent_heartbeats ADD COLUMN IF NOT EXISTS expected_token TEXT;
ALTER TABLE monitoring.agent_heartbeats ADD COLUMN IF NOT EXISTS token_generated_at TIMESTAMPTZ;
ALTER TABLE monitoring.agent_heartbeats ADD COLUMN IF NOT EXISTS out_of_sync BOOLEAN DEFAULT FALSE;

-- Remove old serial columns if they exist
ALTER TABLE monitoring.agent_heartbeats DROP COLUMN IF EXISTS agent_serial;
ALTER TABLE monitoring.agent_heartbeats DROP COLUMN IF EXISTS expected_serial;

-- Add comments
COMMENT ON COLUMN monitoring.agent_heartbeats.agent_token IS 'SHA-256 token from agent (secret code for authentication)';
COMMENT ON COLUMN monitoring.agent_heartbeats.expected_token IS 'Expected token (generated on scheduler restart using salt + datetime)';
COMMENT ON COLUMN monitoring.agent_heartbeats.token_generated_at IS 'Timestamp when token was generated';
COMMENT ON COLUMN monitoring.agent_heartbeats.out_of_sync IS 'TRUE if agent token does not match expected token';

-- Step 6: Insert known agents if they don't exist
INSERT INTO monitoring.agent_heartbeats (location, last_seen, status)
VALUES 
    ('EU', NOW(), 'active'),
    ('PH', NOW(), 'active'),
    ('SG', NOW(), 'active')
ON CONFLICT (location) DO NOTHING;

-- Step 7: Verify data integrity
-- Ensure only 10 core projects are active
DO $$
DECLARE
    active_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO active_count FROM monitoring.subdomains WHERE active = true;
    IF active_count != 10 THEN
        RAISE NOTICE 'WARNING: Found % active subdomains, expected 10', active_count;
    ELSE
        RAISE NOTICE 'SUCCESS: Exactly 10 active subdomains configured';
    END IF;
END $$;

-- Final verification
SELECT 
    'Active Subdomains' as metric,
    COUNT(*) as value
FROM monitoring.subdomains 
WHERE active = true
UNION ALL
SELECT 
    'Inactive Subdomains' as metric,
    COUNT(*) as value
FROM monitoring.subdomains 
WHERE active = false
UNION ALL
SELECT 
    'Project Discovery' as metric,
    COUNT(*) as value
FROM monitoring.subdomains 
WHERE discovery_method = 'Project Discovery'
UNION ALL
SELECT 
    'DNS Enumeration' as metric,
    COUNT(*) as value
FROM monitoring.subdomains 
WHERE discovery_method = 'DNS Enumeration';

