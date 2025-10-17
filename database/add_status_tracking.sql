-- Add status tracking fields to subdomains table for 3-strike rule
-- This enables tracking consecutive status changes and detecting flapping

-- Add columns for status tracking
ALTER TABLE monitoring.subdomains 
ADD COLUMN IF NOT EXISTS current_status TEXT DEFAULT 'UNKNOWN',
ADD COLUMN IF NOT EXISTS consecutive_up_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS consecutive_down_count INTEGER DEFAULT 0,
ADD COLUMN IF NOT EXISTS last_status_change TIMESTAMPTZ,
ADD COLUMN IF NOT EXISTS is_flapping BOOLEAN DEFAULT FALSE;

-- Add index for status queries
CREATE INDEX IF NOT EXISTS idx_subdomains_status ON monitoring.subdomains (current_status, active);
CREATE INDEX IF NOT EXISTS idx_subdomains_flapping ON monitoring.subdomains (is_flapping, active);

-- Add comments
COMMENT ON COLUMN monitoring.subdomains.current_status IS 'Current stable status: UP, DOWN, UNKNOWN, or FLAPPING';
COMMENT ON COLUMN monitoring.subdomains.consecutive_up_count IS 'Count of consecutive UP checks';
COMMENT ON COLUMN monitoring.subdomains.consecutive_down_count IS 'Count of consecutive DOWN checks';
COMMENT ON COLUMN monitoring.subdomains.last_status_change IS 'Timestamp of last status change';
COMMENT ON COLUMN monitoring.subdomains.is_flapping IS 'TRUE if status is inconsistent (flapping)';

