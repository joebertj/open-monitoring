from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import asyncpg
import json
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any
import os
import ssl
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from uptime_checker import UptimeChecker

app = FastAPI(title="Open Monitoring API", version="1.0.0")

# Mount static files and templates
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# SSL Configuration for HTTPS
ssl_enabled = os.path.exists("ssl/cert.pem") and os.path.exists("ssl/key.pem")
if ssl_enabled:
    print("🔒 HTTPS enabled with SSL certificates")
else:
    print("⚠️  SSL certificates not found, running HTTP only")

# CORS middleware for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://mon.altgovph.site"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database connection pool
db_pool = None

async def get_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = await asyncpg.create_pool(
            os.getenv("DATABASE_URL", "postgresql://monitor:monitor123@db:5432/monitoring"),
            min_size=5,
            max_size=20
        )
    return db_pool

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

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
    # Auto-start scheduler on application startup
    try:
        print("🔄 Auto-starting monitoring scheduler...")
        await start_scheduler_internal()
    except Exception as e:
        print(f"⚠️  Failed to auto-start scheduler: {e}")

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
    """Get all project subdomains with their latest stats"""
    pool = await get_db_pool()
    rows = await pool.fetch("""
        SELECT
            s.subdomain,
            s.active,
            s.platform,
            s.last_platform_check,
            COALESCE(latest_check.status_code, 0) as status_code,
            COALESCE(latest_check.response_time_ms, 0) as response_time_ms,
            COALESCE(latest_check.up, false) as up,
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
        ORDER BY s.subdomain
    """)

    return [dict(row) for row in rows]

async def get_other_dns():
    """Get other DNS discoveries (non-project subdomains)"""
    pool = await get_db_pool()
    rows = await pool.fetch("""
        SELECT
            subdomain,
            active,
            platform,
            last_platform_check,
            discovered_at,
            last_seen
        FROM monitoring.other_dns
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
@app.get("/")
async def dashboard(request: Request):
    """Serve the main dashboard page"""
    try:
        # Get data
        subdomains_data = await get_subdomains_with_stats()
        other_dns_data = await get_other_dns()
        alerts_data = await get_recent_alerts()

        # Calculate stats
        warning_alerts = [a for a in alerts_data if a.get('severity') == 'warning']
        critical_alerts = [a for a in alerts_data if a.get('severity') == 'critical']
        total_checks = sum(sd.get('check_count', 0) for sd in subdomains_data)

        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "subdomains": subdomains_data,
            "other_dns": other_dns_data,
            "alerts": alerts_data,
            "warning_alerts": warning_alerts,
            "critical_alerts": critical_alerts,
            "total_checks": total_checks
        })
    except Exception as e:
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "subdomains": [],
            "alerts": [],
            "warning_alerts": [],
            "critical_alerts": [],
            "total_checks": 0,
            "error": str(e)
        })

@app.get("/alerts")
async def alerts_page(request: Request):
    """Serve the alerts page"""
    try:
        alerts_data = await get_recent_alerts()
        return templates.TemplateResponse("alerts.html", {
            "request": request,
            "alerts": alerts_data
        })
    except Exception as e:
        return templates.TemplateResponse("alerts.html", {
            "request": request,
            "alerts": [],
            "error": str(e)
        })

@app.get("/api/")
async def root():
    return {"message": "Open Monitoring API", "status": "running"}

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
async def get_subdomains():
    """Get all discovered subdomains with their status"""
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
    SELECT time, status_code, response_time_ms, up, platform, error_message
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
            "error_message": row["error_message"]
        })

    return {"subdomain": subdomain, "checks": checks}

@app.post("/api/geo-report")
async def receive_geo_report(report: dict):
    """Receive monitoring reports from geo-distributed agents"""
    pool = await get_db_pool()
    results = report.get("results", [])
    location = report.get("location", "unknown")

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

                # Insert monitoring results
                for result in results:
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

        return {"status": "success", "received": len(results)}

    except Exception as e:
        print(f"❌ Error saving geo report: {e}")
        return {"status": "error", "message": str(e)}

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
