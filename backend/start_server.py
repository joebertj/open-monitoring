#!/usr/bin/env python3
"""
BetterGovPH Monitoring Server Startup Script
Handles both HTTP and HTTPS based on SSL certificate availability
"""

import uvicorn
import os

# Always run on HTTP for development - nginx will handle SSL in production
print('🌐 Starting HTTP server on port 8000')

# Run Flask app with Gunicorn
from main import app

if __name__ == "__main__":
    from gunicorn.app.wsgiapp import WSGIApplication
    WSGIApplication("%(prog)s [OPTIONS] [APP_MODULE]").run()
