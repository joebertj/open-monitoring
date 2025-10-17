-- Add check_path column to subdomains table
-- This allows specifying a custom endpoint to check for each subdomain
-- For example, api.bettergov.ph should check /api/status instead of /

ALTER TABLE monitoring.subdomains 
ADD COLUMN IF NOT EXISTS check_path TEXT DEFAULT '/';

-- Set custom check path for api.bettergov.ph
UPDATE monitoring.subdomains 
SET check_path = '/api/status'
WHERE subdomain = 'api.bettergov.ph';

-- Create index for check_path lookups
CREATE INDEX IF NOT EXISTS idx_subdomains_check_path ON monitoring.subdomains (subdomain, check_path);

