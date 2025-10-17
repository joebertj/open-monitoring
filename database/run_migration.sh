#!/bin/bash
# Run the check_path migration
# This script assumes DATABASE_URL is set in the environment

if [ -z "$DATABASE_URL" ]; then
    echo "❌ ERROR: DATABASE_URL environment variable is not set"
    echo "Please set it like: export DATABASE_URL='postgresql://user:pass@host:port/dbname'"
    exit 1
fi

echo "🔧 Running check_path migration..."

# Extract database connection details from DATABASE_URL
# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
psql "$DATABASE_URL" -f "$SCRIPT_DIR/add_check_path.sql"

if [ $? -eq 0 ]; then
    echo "✅ Migration completed successfully!"
    echo "✅ api.bettergov.ph will now be checked at /api/status"
else
    echo "❌ Migration failed"
    exit 1
fi

