-- Migration script to apply unified subdomains schema to existing database
-- Run this against your existing database to migrate from separate tables to unified table

-- Add discovery_method column if it doesn't exist
ALTER TABLE monitoring.subdomains ADD COLUMN IF NOT EXISTS discovery_method TEXT NOT NULL DEFAULT 'DNS Enumeration';

-- Set all existing subdomains to DNS Enumeration and inactive by default
UPDATE monitoring.subdomains SET discovery_method = 'DNS Enumeration', active = false;

-- Override core projects to Project Discovery and active
UPDATE monitoring.subdomains SET discovery_method = 'Project Discovery', active = true
WHERE subdomain IN ('bettergov.ph', 'visualizations.bettergov.ph', 'budget.bettergov.ph', 'docs.bettergov.ph', 'govchain.bettergov.ph', 'hotlines.bettergov.ph', 'open-congress-api.bettergov.ph', 'saln.bettergov.ph', 'taxdirectory.bettergov.ph', 'api.bettergov.ph');

-- Specifically ensure admin.bettergov.ph is marked as DNS Enumeration
UPDATE monitoring.subdomains SET discovery_method = 'DNS Enumeration', active = false
WHERE subdomain = 'admin.bettergov.ph';

-- Migrate data from other_dns table to subdomains table if it exists
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'monitoring' AND table_name = 'other_dns') THEN
        -- Migrate data
        INSERT INTO monitoring.subdomains (domain, subdomain, discovered_at, last_seen, active, discovery_method, platform, last_platform_check)
        SELECT
            CASE
                WHEN POSITION('.' IN subdomain) > 0 THEN SUBSTRING(subdomain FROM POSITION('.' IN subdomain) + 1)
                ELSE subdomain
            END as domain,
            subdomain,
            discovered_at,
            last_seen,
            false as active,
            'DNS Enumeration' as discovery_method,
            platform,
            last_platform_check
        FROM monitoring.other_dns
        ON CONFLICT (subdomain) DO NOTHING;

        -- Drop the old table
        DROP TABLE monitoring.other_dns;
    END IF;
END $$;

-- Add the new index if it doesn't exist
CREATE INDEX IF NOT EXISTS idx_subdomains_discovery_method ON monitoring.subdomains (discovery_method, active, last_seen DESC);
