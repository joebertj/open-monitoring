# Fix for api.bettergov.ph Being Marked as Down

## Problem
The monitoring system was incorrectly marking `api.bettergov.ph` as DOWN. When checking the root endpoint `/`, the API returns:
- Status code: **404 Not Found**
- Content: `{"error":"Not found","availableEndpoints":["/api/status","/api/weather","/api/forex","/weather","/forex"]}`

This is a valid response from an API that's UP and functioning correctly. The API simply doesn't have a handler for the root path and helpfully lists available endpoints. However, the monitoring system only considered status codes 200-399 as "up", so the 404 was wrongly interpreted as the service being down.

## Solution
Implemented custom check path support so different subdomains can be monitored at specific endpoints:

### Changes Made

1. **Database Migration** (`database/add_check_path.sql`)
   - Added `check_path` column to `monitoring.subdomains` table
   - Set `api.bettergov.ph` to use `/api/status` instead of `/`
   - The `/api/status` endpoint returns 200 OK with service status

2. **Python Uptime Checker** (`backend/uptime_checker.py`)
   - Updated `get_active_subdomains()` to fetch `check_path` from database
   - Modified `check_subdomain()` to accept and use custom `check_path`
   - Updated the check task to pass check_path when checking subdomains

3. **API Endpoint** (`backend/main.py`)
   - Updated `/api/subdomains` endpoint to include `check_path` in response
   - This allows geo-monitor agents to know which path to check

4. **Geo-Monitor Script** (`deploy_geo_monitor.sh`)
   - Updated `check_subdomain()` function to accept `check_path` parameter
   - Modified main loop to parse `check_path` from API response
   - Now checks the correct endpoint for each subdomain

5. **Migration Runner** (`run_migration.sh`)
   - Created helper script to run the database migration
   - Requires `DATABASE_URL` environment variable

## How to Apply the Fix

1. Run the database migration:
   ```bash
   export DATABASE_URL='postgresql://user:pass@host:port/dbname'
   ./run_migration.sh
   ```

2. Restart the monitoring service:
   ```bash
   # Restart the backend service
   cd backend
   # Stop existing service (if running)
   # Start the service
   python3 main.py
   ```

3. Restart geo-monitor agents (if deployed):
   - The agents will automatically pick up the new check_path from the API
   - No code changes needed on agent servers

## Verification

After applying the fix, you can verify it's working:

```bash
# Check that api.bettergov.ph now has check_path set
curl http://your-monitoring-server:8002/api/subdomains | grep -A5 api.bettergov.ph

# Manually test the /api/status endpoint
curl -s https://api.bettergov.ph/api/status
# Should return: {"status":"online",...}

# Check monitoring dashboard to confirm api.bettergov.ph shows as UP
```

## Benefits

- **Flexible Monitoring**: Each subdomain can now have a custom health check endpoint
- **Accurate Status**: APIs that don't respond to root path are now correctly monitored
- **Backward Compatible**: Subdomains without custom check_path default to `/`
- **No Agent Updates**: Geo-monitor agents automatically use the correct path from API

## Future Use Cases

This feature can be used for other services that need custom health check paths:
- `/health` for modern microservices
- `/ping` for simple services
- `/api/v1/status` for versioned APIs
- Any custom endpoint that provides service health information

## Technical Details

### Database Schema
```sql
ALTER TABLE monitoring.subdomains 
ADD COLUMN IF NOT EXISTS check_path TEXT DEFAULT '/';
```

### Example API Response
```json
{
  "subdomains": [
    {
      "subdomain": "api.bettergov.ph",
      "check_path": "/api/status",
      "active": true,
      ...
    }
  ]
}
```

### Geo-Monitor Check
Before: `https://api.bettergov.ph/` → 404 → DOWN  
After: `https://api.bettergov.ph/api/status` → 200 → UP

