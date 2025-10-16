#!/usr/bin/env python3
"""
BetterGovPH Monitoring Server Startup Script
Handles both HTTP and HTTPS based on SSL certificate availability
"""

import uvicorn
import os

# Check if SSL certificates exist
ssl_enabled = os.path.exists("ssl/cert.pem") and os.path.exists("ssl/key.pem")

if ssl_enabled:
    print('🔒 Starting HTTPS server on port 8443')
    uvicorn.run(
        'main:app',
        host='0.0.0.0',
        port=8443,
        ssl_keyfile='ssl/key.pem',
        ssl_certfile='ssl/cert.pem'
    )
else:
    print('⚠️  SSL certificates not found, starting HTTP server on port 8000')
    uvicorn.run('main:app', host='0.0.0.0', port=8000)
