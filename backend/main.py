from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
import asyncpg
import json
import asyncio
from datetime import datetime, timedelta
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from typing import Dict, Any
import os
import logging

from uptime_checker import UptimeChecker

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="BetterGovPH Open Monitoring API")

# SSL Configuration for HTTPS
ssl_enabled = os.path.exists("ssl/cert.pem") and os.path.exists("ssl/key.pem")
if ssl_enabled:
    print("🔒 HTTPS enabled with SSL certificates")
else:
    print("⚠️  SSL certificates not found, running HTTP only")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Database connection pool
db_pool = None

async def get_db_pool():
    global db_pool
    if db_pool is None:
        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            raise ValueError("DATABASE_URL environment variable must be set")
        db_pool = await asyncpg.create_pool(
            database_url,
            min_size=5,
            max_size=20
        )
    return db_pool

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except:
                self.disconnect(connection)

manager = ConnectionManager()

# Global scheduler instance
scheduler = AsyncIOScheduler()
uptime_checker = UptimeChecker()

@app.on_event("startup")
async def startup_event():
    await get_db_pool()
    # Auto-start scheduler on application startup - DISABLED for debugging
    # try:
    #     print("🔄 Auto-starting monitoring scheduler...")
    #     await start_scheduler_internal()
    # except Exception as e:
    #     print(f"⚠️  Failed to auto-start scheduler: {e}")
    print("🔄 Scheduler disabled for debugging")

@app.on_event("shutdown")
async def shutdown_event():
    # Gracefully shutdown scheduler on application shutdown
    try:
        if scheduler.running:
            scheduler.shutdown()
            print("🔄 Scheduler shutdown gracefully")
    except Exception as e:
        print(f"⚠️  Error during scheduler shutdown: {e}")

    # Close database pool
    global db_pool
    if db_pool:
        await db_pool.close()

# Helper functions for dashboard data
async def get_subdomains_with_stats():
    """Get active project subdomains with their latest stats"""
    pool = await get_db_pool()
    rows = await pool.fetch("""
        SELECT
            s.subdomain,
            s.active,
            s.platform,
            s.last_platform_check,
            COALESCE(s.current_status, 'UNKNOWN') as status,
            s.is_flapping,
            s.consecutive_up_count,
            s.consecutive_down_count,
            s.last_status_change,
            COALESCE(latest_check.status_code, 0) as status_code,
            COALESCE(latest_check.response_time_ms, 0) as response_time_ms,
            latest_check.up as up,
            COALESCE(latest_check.time, s.last_seen) as last_check,
            COALESCE(stats.uptime_percentage, 0) as uptime_percentage,
            COALESCE(stats.check_count, 0) as check_count
        FROM monitoring.subdomains s
        LEFT JOIN LATERAL (
            SELECT *
            FROM monitoring.uptime_checks uc
            WHERE uc.subdomain = s.subdomain
            ORDER BY uc.time DESC
            LIMIT 1
        ) latest_check ON true
        LEFT JOIN LATERAL (
            SELECT
                COUNT(*) as check_count,
                (COUNT(*) FILTER (WHERE up = true))::float / NULLIF(COUNT(*), 0) * 100 as uptime_percentage
            FROM monitoring.uptime_checks uc
            WHERE uc.subdomain = s.subdomain
            AND uc.time >= NOW() - INTERVAL '24 hours'
        ) stats ON true
        WHERE s.active = true
        ORDER BY s.subdomain
    """)

    return [dict(row) for row in rows]

async def get_inactive_subdomains():
    """Get inactive/down subdomains from the unified monitoring table"""
    pool = await get_db_pool()
    rows = await pool.fetch("""
        SELECT
            s.subdomain,
            s.active,
            s.platform,
            s.last_platform_check,
            s.discovered_at,
            s.last_seen,
            s.discovery_method,
            COALESCE(latest_check.up, false) as is_up
        FROM monitoring.subdomains s
        LEFT JOIN LATERAL (
            SELECT up
            FROM monitoring.uptime_checks uc
            WHERE uc.subdomain = s.subdomain
            ORDER BY uc.time DESC
            LIMIT 1
        ) latest_check ON true
        WHERE COALESCE(latest_check.up, false) = false
        ORDER BY s.last_seen DESC
    """)

    return [dict(row) for row in rows]

async def get_other_dns():
    """Get other DNS discoveries from the unified subdomains table"""
    pool = await get_db_pool()
    rows = await pool.fetch("""
        SELECT
            subdomain,
            active,
            platform,
            last_platform_check,
            discovered_at,
            last_seen,
            discovery_method
        FROM monitoring.subdomains
        WHERE discovery_method = 'DNS Enumeration'
        ORDER BY last_seen DESC
        LIMIT 20
    """)

    return [dict(row) for row in rows]

async def get_recent_alerts(limit: int = 50):
    """Get recent alerts"""
    # For now, return empty list as we don't have an alerts table yet
    # This can be expanded when we implement alerting
    return []

# Dashboard routes
@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    """Serve the main dashboard page"""
    try:
        # Get data
        subdomains_data = await get_subdomains_with_stats()
        inactive_subdomains = await get_inactive_subdomains()
        other_dns_data = await get_other_dns()
        alerts_data = await get_recent_alerts()

        # Combine inactive subdomains and other DNS for discoveries count
        dns_discoveries_count = len(inactive_subdomains) + len(other_dns_data)

        # Calculate stats
        warning_alerts = [a for a in alerts_data if a.get('severity') == 'warning']
        critical_alerts = [a for a in alerts_data if a.get('severity') == 'critical']

        # Add UTC+8 time to subdomains for consistent display
        for subdomain in subdomains_data:
            if subdomain.get('last_check'):
                subdomain['last_check_utc8'] = subdomain['last_check'] + timedelta(hours=8)

        # Get agent status for known locations (EU, PH, SG)
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Get agent heartbeats for known locations
            agent_rows = await conn.fetch("""
                SELECT
                    location,
                    last_seen,
                    status,
                    EXTRACT(EPOCH FROM (NOW() - last_seen)) / 60 as minutes_since_last_seen
                FROM monitoring.agent_heartbeats
                WHERE location IN ('EU', 'PH', 'SG')
                ORDER BY last_seen DESC
            """)

            # Calculate agent stats
            agents = []
            up_agents = 0
            down_agents = 0

            for row in agent_rows:
                is_online = row["minutes_since_last_seen"] < 10  # Consider online if seen within 10 minutes
                status = "online" if is_online else "offline"

                if is_online:
                    up_agents += 1
                else:
                    down_agents += 1

                agents.append({
                    "location": row["location"],
                    "last_seen": row["last_seen"].isoformat(),
                    "status": status,
                    "minutes_since_last_seen": round(row["minutes_since_last_seen"], 1)
                })

            total_agents = len(agents)  # Total known agents

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "subdomains": subdomains_data,
            "inactive_subdomains": inactive_subdomains,
            "other_dns": other_dns_data,
            "dns_discoveries_count": dns_discoveries_count,
            "alerts": alerts_data,
            "warning_alerts": warning_alerts,
            "critical_alerts": critical_alerts,
            "total_agents": total_agents,
            "up_agents": up_agents,
            "down_agents": down_agents,
            "agents": agents
        })
    except Exception as e:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "subdomains": [],
            "inactive_subdomains": [],
            "other_dns": [],
            "dns_discoveries_count": 0,
            "alerts": [],
            "warning_alerts": [],
            "critical_alerts": [],
            "total_agents": 3,  # Default to 3 known agents
            "up_agents": 0,
            "down_agents": 0,
            "agents": [],
            "error": str(e)
        })

@app.get("/alerts", response_class=HTMLResponse)
async def alerts_page(request: Request):
    """Serve the alerts page - shows all non-UP subdomains"""
    try:
        # Get all subdomains
        all_subdomains = await get_subdomains_with_stats()
        
        # Filter for non-UP subdomains (DOWN, FLAPPING, UNKNOWN)
        alert_subdomains = [s for s in all_subdomains if s['status'] != 'UP']
        
        return templates.TemplateResponse("alerts.html", {
            "request": request,
            "subdomains": alert_subdomains,
            "total_alerts": len(alert_subdomains),
            "down_count": len([s for s in alert_subdomains if s['status'] == 'DOWN']),
            "flapping_count": len([s for s in alert_subdomains if s['status'] == 'FLAPPING']),
            "unknown_count": len([s for s in alert_subdomains if s['status'] == 'UNKNOWN'])
        })
    except Exception as e:
        return templates.TemplateResponse("alerts.html", {
            "request": request,
            "subdomains": [],
            "total_alerts": 0,
            "down_count": 0,
            "flapping_count": 0,
            "unknown_count": 0,
            "error": str(e)
        })

@app.get("/test-api")
def root():
    print("API root endpoint called")
    return {"message": "Open Monitoring API", "status": "running"}

@app.get("/simple-test")
def test_simple():
    print("Simple test endpoint called")
    return {"test": "simple", "status": "ok"}

@app.get("/api/health")
async def health_check():
    """Comprehensive health check including scheduler status"""
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "services": {}
    }

    # Check database
    try:
        pool = await get_db_pool()
        await pool.fetchval("SELECT 1")
        health_status["services"]["database"] = "connected"
    except Exception as e:
        health_status["services"]["database"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # Check scheduler
    try:
        jobs = []
        if scheduler.running:
            for job in scheduler.get_jobs():
                next_run = job.next_run_time.isoformat() if job.next_run_time else None
                jobs.append({
                    "id": job.id,
                    "name": job.name,
                    "next_run_time": next_run,
                    "trigger": str(job.trigger)
                })

        health_status["services"]["scheduler"] = {
            "running": scheduler.running,
            "jobs_count": len(jobs),
            "jobs": jobs
        }
    except Exception as e:
        health_status["services"]["scheduler"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    # Check subdomain count
    try:
        pool = await get_db_pool()
        subdomain_count = await pool.fetchval("SELECT COUNT(*) FROM monitoring.subdomains WHERE active = true")
        health_status["services"]["monitoring"] = {
            "active_subdomains": subdomain_count or 0
        }
    except Exception as e:
        health_status["services"]["monitoring"] = f"error: {str(e)}"
        health_status["status"] = "degraded"

    return health_status

@app.get("/api/metrics")
async def get_metrics(
    host: str = None,
    service: str = None,
    metric_name: str = None,
    hours: int = 24
):
    """Get metrics data for the specified time range"""
    pool = await get_db_pool()

    # Build query
    conditions = ["time > $1"]
    params = [datetime.utcnow() - timedelta(hours=hours)]
    param_count = 1

    if host:
        param_count += 1
        conditions.append(f"host = ${param_count}")
        params.append(host)

    if service:
        param_count += 1
        conditions.append(f"service = ${param_count}")
        params.append(service)

    if metric_name:
        param_count += 1
        conditions.append(f"metric_name = ${param_count}")
        params.append(metric_name)

    where_clause = " AND ".join(conditions)

    query = f"""
    SELECT time, host, service, metric_name, value, status, metadata
    FROM monitoring.metrics
    WHERE {where_clause}
    ORDER BY time DESC
    LIMIT 10000
    """

    rows = await pool.fetch(query, *params)

    # Convert to dict format
    metrics = []
    for row in rows:
        metrics.append({
            "time": row["time"].isoformat(),
            "host": row["host"],
            "service": row["service"],
            "metric_name": row["metric_name"],
            "value": float(row["value"]) if row["value"] else None,
            "status": row["status"],
            "metadata": row["metadata"]
        })

    return {"metrics": metrics}

@app.get("/api/alerts")
async def get_alerts(resolved: bool = False, limit: int = 100):
    """Get active alerts"""
    pool = await get_db_pool()

    query = """
    SELECT id, time, host, service, severity, message, acknowledged, resolved
    FROM monitoring.alerts
    WHERE resolved = $1
    ORDER BY time DESC
    LIMIT $2
    """

    rows = await pool.fetch(query, resolved, limit)

    alerts = []
    for row in rows:
        alerts.append({
            "id": row["id"],
            "time": row["time"].isoformat(),
            "host": row["host"],
            "service": row["service"],
            "severity": row["severity"],
            "message": row["message"],
            "acknowledged": row["acknowledged"],
            "resolved": row["resolved"]
        })

    return {"alerts": alerts}

@app.post("/api/metrics")
async def insert_metric(metric: Dict[str, Any]):
    """Insert a new metric"""
    pool = await get_db_pool()

    query = """
    INSERT INTO monitoring.metrics (time, host, service, metric_name, value, status, metadata)
    VALUES ($1, $2, $3, $4, $5, $6, $7)
    """

    await pool.execute(
        query,
        datetime.fromisoformat(metric["time"]) if "time" in metric else datetime.utcnow(),
        metric["host"],
        metric["service"],
        metric["metric_name"],
        metric["value"],
        metric.get("status"),
        json.dumps(metric.get("metadata", {}))
    )

    # Broadcast update to WebSocket clients
    await manager.broadcast(json.dumps({
        "type": "metric_update",
        "data": metric
    }))

    return {"status": "inserted"}

async def start_scheduler_internal(interval_minutes: int = 1):
    """Internal function to start the scheduler (used by auto-start)"""
    if scheduler.running:
        return

    # Clear any existing jobs
    scheduler.remove_all_jobs()

    # Add uptime check job
    scheduler.add_job(
        uptime_checker.run_checks,
        trigger=IntervalTrigger(minutes=interval_minutes),
        id='uptime_check',
        name='Uptime Check',
        max_instances=1,
        replace_existing=True,
        misfire_grace_time=30  # Allow 30 seconds grace time for missed jobs
    )

    # Add subdomain discovery job (run every 6 hours)
    scheduler.add_job(
        uptime_checker.run_discovery,
        trigger=IntervalTrigger(hours=6),
        id='subdomain_discovery',
        name='Subdomain Discovery',
        max_instances=1,
        replace_existing=True,
        misfire_grace_time=300  # 5 minutes grace time
    )

    scheduler.start()
    print(f"✅ Scheduler started with {interval_minutes}-minute intervals")

# Monitoring Control Endpoints
@app.get("/api/scheduler/status")
async def get_scheduler_status():
    """Get the current status of the monitoring scheduler"""
    try:
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run_time": job.next_run_time.isoformat() if job.next_run_time else None,
                "trigger": str(job.trigger)
            })

        return {
            "running": scheduler.running,
            "jobs": jobs
        }
    except Exception as e:
        return {"error": str(e), "running": False, "jobs": []}

@app.post("/api/scheduler/start")
async def start_scheduler(interval_minutes: int = 1):
    """Start the monitoring scheduler"""
    try:
        if scheduler.running:
            return {"message": "Scheduler is already running"}

        # Clear any existing jobs
        scheduler.remove_all_jobs()

        # Add uptime check job
        scheduler.add_job(
            uptime_checker.run_checks,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id='uptime_check',
            name='Uptime Check',
            max_instances=1,
            replace_existing=True
        )

        # Add subdomain discovery job (run every 6 hours)
        scheduler.add_job(
            uptime_checker.run_discovery,
            trigger=IntervalTrigger(hours=6),
            id='subdomain_discovery',
            name='Subdomain Discovery',
            max_instances=1,
            replace_existing=True
        )

        scheduler.start()
        return {"message": f"Scheduler started with {interval_minutes}-minute intervals"}

    except Exception as e:
        return {"error": str(e)}

@app.post("/api/scheduler/stop")
async def stop_scheduler():
    """Stop the monitoring scheduler"""
    try:
        if scheduler.running:
            scheduler.shutdown()
            return {"message": "Scheduler stopped"}
        else:
            return {"message": "Scheduler was not running"}
    except Exception as e:
        return {"error": str(e)}

@app.post("/api/checks/run")
async def run_manual_checks():
    """Manually trigger all monitoring checks"""
    try:
        # Run subdomain discovery
        await uptime_checker.run_discovery()

        # Run uptime checks
        await uptime_checker.run_checks()

        return {"message": "Manual checks completed"}
    except Exception as e:
        return {"error": str(e)}

@app.get("/api/subdomains")
async def get_subdomains(request: Request):
    """Get all discovered subdomains with their status"""
    print(f"Subdomains endpoint called from {request.client.host}")
    pool = await get_db_pool()
    rows = await pool.fetch("""
        SELECT
            s.id, s.domain, s.subdomain, s.discovered_at,
            s.last_seen, s.active, s.platform, s.last_platform_check,
            COUNT(uc.subdomain) as check_count,
            AVG(CASE WHEN uc.up THEN 1 ELSE 0 END) * 100 as uptime_percentage,
            MAX(uc.time) as last_check
        FROM monitoring.subdomains s
        LEFT JOIN monitoring.uptime_checks uc ON s.subdomain = uc.subdomain
            AND uc.time > NOW() - INTERVAL '24 hours'
        GROUP BY s.id, s.domain, s.subdomain, s.discovered_at, s.last_seen, s.active, s.platform, s.last_platform_check
        ORDER BY s.active DESC, s.last_seen DESC
    """)

    subdomains = []
    for row in rows:
        subdomains.append({
            "id": row["id"],
            "domain": row["domain"],
            "subdomain": row["subdomain"],
            "discovered_at": row["discovered_at"].isoformat(),
            "last_seen": row["last_seen"].isoformat() if row["last_seen"] else None,
            "active": row["active"],
            "platform": row["platform"],
            "last_platform_check": row["last_platform_check"].isoformat() if row["last_platform_check"] else None,
            "check_count": row["check_count"] or 0,
            "uptime_percentage": round(float(row["uptime_percentage"] or 0), 2),
            "last_check": row["last_check"].isoformat() if row["last_check"] else None
        })

    return {"subdomains": subdomains}

@app.get("/api/subdomains/{subdomain}/checks")
async def get_subdomain_checks(subdomain: str, hours: int = 24):
    """Get uptime check history for a specific subdomain"""
    pool = await get_db_pool()

    query = """
    SELECT time, status_code, response_time_ms, up, platform, error_message, location
    FROM monitoring.uptime_checks
    WHERE subdomain = $1 AND time > $2
    ORDER BY time DESC
    """

    rows = await pool.fetch(query, subdomain, datetime.utcnow() - timedelta(hours=hours))

    checks = []
    for row in rows:
        checks.append({
            "time": row["time"].isoformat(),
            "status_code": row["status_code"],
            "response_time_ms": float(row["response_time_ms"]) if row["response_time_ms"] else None,
            "up": row["up"],
            "platform": row["platform"],
            "error_message": row["error_message"],
            "location": row["location"] or "EU"
        })

    return {"subdomain": subdomain, "checks": checks}

async def update_subdomain_status_with_3strike(conn, subdomain: str, is_up: bool):
    """
    Update subdomain status using 3-strike rule
    - Requires 3 consecutive same checks to change status
    - Detects FLAPPING if status keeps changing
    """
    # Get current subdomain state
    row = await conn.fetchrow("""
        SELECT current_status, consecutive_up_count, consecutive_down_count, is_flapping
        FROM monitoring.subdomains
        WHERE subdomain = $1
    """, subdomain)
    
    if not row:
        # Subdomain doesn't exist in subdomains table, skip
        return
    
    current_status = row['current_status'] or 'UNKNOWN'
    consecutive_up = row['consecutive_up_count'] or 0
    consecutive_down = row['consecutive_down_count'] or 0
    is_flapping = row['is_flapping'] or False
    
    # Get last 5 checks to detect flapping
    recent_checks = await conn.fetch("""
        SELECT up FROM monitoring.uptime_checks
        WHERE subdomain = $1
        ORDER BY time DESC
        LIMIT 5
    """, subdomain)
    
    # Detect flapping: if we have 5+ checks and they alternate
    if len(recent_checks) >= 5:
        ups = sum(1 for c in recent_checks if c['up'])
        # If roughly 40-60% up, it's flapping
        if 2 <= ups <= 3:
            is_flapping = True
        else:
            is_flapping = False
    
    # Update consecutive counters
    if is_up:
        consecutive_up += 1
        consecutive_down = 0
    else:
        consecutive_down += 1
        consecutive_up = 0
    
    # Determine new status (3-strike rule)
    new_status = current_status
    status_changed = False
    
    if is_flapping:
        new_status = 'FLAPPING'
        status_changed = (current_status != 'FLAPPING')
    elif consecutive_up >= 3:
        new_status = 'UP'
        status_changed = (current_status != 'UP')
    elif consecutive_down >= 3:
        new_status = 'DOWN'
        status_changed = (current_status != 'DOWN')
    
    # Update subdomain status
    await conn.execute("""
        UPDATE monitoring.subdomains
        SET current_status = $1,
            consecutive_up_count = $2,
            consecutive_down_count = $3,
            is_flapping = $4,
            last_status_change = CASE WHEN $5 THEN NOW() ELSE last_status_change END
        WHERE subdomain = $6
    """, new_status, consecutive_up, consecutive_down, is_flapping, status_changed, subdomain)
    
    if status_changed:
        logger.info(f"📊 Status changed for {subdomain}: {current_status} → {new_status}")

@app.post("/api/geo-report")
async def receive_geo_report(report: dict):
    """Receive monitoring reports from geo-distributed agents"""
    pool = await get_db_pool()
    results = report.get("results", [])
    location = report.get("location", "UNKNOWN").upper()

    # Only accept reports from known agents (EU, PH, SG)
    if location not in ['EU', 'PH', 'SG']:
        print(f"🚫 Rejected {len(results)} geo-reports from unauthorized location: {location}")
        return {"status": "rejected", "message": f"Unauthorized location: {location}"}

    print(f"📥 Received {len(results)} geo-reports from {location}")

    try:
        async with pool.acquire() as conn:
            async with conn.transaction():
                # Update agent heartbeat
                await conn.execute("""
                    INSERT INTO monitoring.agent_heartbeats (location, last_seen, status)
                    VALUES ($1, NOW(), 'active')
                    ON CONFLICT (location) DO UPDATE SET
                        last_seen = NOW(),
                        status = 'active'
                """, location)

                # Insert monitoring results and update status
                for result in results:
                    # Insert uptime check
                    await conn.execute("""
                        INSERT INTO monitoring.uptime_checks
                        (time, subdomain, status_code, response_time_ms, up, platform, error_message, location)
                        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    """,
                    datetime.fromisoformat(result["timestamp"].replace('Z', '+00:00')),
                    result["subdomain"],
                    result["status_code"],
                    result["response_time_ms"],
                    result["up"],
                    None,  # platform detection not implemented for geo agents yet
                    result.get("error"),
                    location
                    )
                    
                    # Update subdomain status with 3-strike rule
                    await update_subdomain_status_with_3strike(conn, result["subdomain"], result["up"])

        return {"status": "success", "received": len(results)}

    except Exception as e:
        print(f"❌ Error saving geo report: {e}")
        return {"status": "error", "message": str(e)}

@app.get("/api/dns-discoveries")
async def get_dns_discoveries():
    """Get all DNS discoveries (inactive subdomains and other DNS)"""
    try:
        inactive_subdomains = await get_inactive_subdomains()
        other_dns = await get_other_dns()

        # Combine both lists
        discoveries = inactive_subdomains + other_dns

        return {"discoveries": discoveries, "count": len(discoveries)}
    except Exception as e:
        logger.error(f"DNS discoveries error: {e}")
        return {"discoveries": [], "error": str(e)}

@app.get("/api/agent-status")
async def get_agent_status():
    """Get status of all geo-monitoring agents"""
    pool = await get_db_pool()
    rows = await pool.fetch("""
        SELECT
            location,
            last_seen,
            status,
            EXTRACT(EPOCH FROM (NOW() - last_seen)) / 60 as minutes_since_last_seen
        FROM monitoring.agent_heartbeats
        ORDER BY last_seen DESC
    """)

    agents = []
    for row in rows:
        status = "online" if row["minutes_since_last_seen"] < 10 else "offline"
        agents.append({
            "location": row["location"],
            "last_seen": row["last_seen"].isoformat(),
            "status": status,
            "minutes_since_last_seen": round(row["minutes_since_last_seen"], 1)
        })

    return {"agents": agents}

@app.post("/api/restart-agent/{location}")
async def restart_agent(location: str):
    """Endpoint to trigger agent restart (for future use)"""
    # This would be used by a management interface to restart agents
    return {"status": "not_implemented", "location": location, "message": "Agent restart not yet implemented"}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates"""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo back for now - can be extended for client commands
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
