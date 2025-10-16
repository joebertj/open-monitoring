#!/usr/bin/env python3
"""
BetterGovPH Monitoring Server Startup Script
Handles both HTTP and HTTPS based on SSL certificate availability
"""

import uvicorn
import os

# Always run on HTTP for development - nginx will handle SSL in production
print('🌐 Starting HTTP server on port 8000')
uvicorn.run('main:app', host='0.0.0.0', port=8000)
