# Open Monitoring Dashboard

A dynamic AI-powered monitoring dashboard for bettergov.ph, inspired by Nagios and MRTG. Built with server-side rendering, FastAPI, and TimescaleDB for high-performance time series monitoring.

## 🎯 **Current Status (October 2025)**

- ✅ **Core Architecture**: FastAPI backend + TimescaleDB + geo-distributed agents
- ✅ **D3.js Charts**: Professional time series visualization with proper filtering
- ✅ **Server-side Rendering**: Fast, reliable HTML generation
- ✅ **Geo-monitoring**: Agents in EU, SG, PH locations
- ✅ **AJAX Auto-refresh**: Preserves UI state, updates data without page reloads
- ✅ **UTC+8 Timezone**: Consistent time display across all agents
- 🚧 **Time Series Filtering**: D3.js implementation with proper data filtering
- 🚧 **EU Agent**: Monitoring agent deployment and data collection

## 🤖 Why Build Our Own?

While powerful monitoring tools like Nagios, Zabbix, and Prometheus exist, we chose to build our own AI-native monitoring system for several reasons:

### 🎯 **AI-First Design**
- **Custom AI Integration**: Built from the ground up for AI-powered insights, anomaly detection, and predictive monitoring
- **Application-Specific**: Tailored for government transparency platforms with domain-specific metrics
- **Future-Ready**: Extensible architecture for advanced AI features like automated incident response and root cause analysis

### ⚡ **Performance & Simplicity**
- **Server-Side Rendering**: Eliminates client-side JavaScript overhead for instant page loads
- **Minimal Dependencies**: No complex JavaScript frameworks or heavy monitoring agents
- **Container Optimized**: Designed for cloud-native deployment with minimal resource usage
- **BusyBox Compatible**: Agents run on the most minimal Linux systems

### 🌐 **Geo-Distributed Architecture**
- **Global Coverage**: Built-in support for distributed monitoring agents across multiple geographic regions
- **Network Awareness**: Understands latency and connectivity patterns across different locations
- **Federated Design**: Decentralized agents report to central API without complex orchestration

### 🔧 **Developer Experience**
- **Simple Deployment**: Single-command deployment with Docker and automated scripts
- **Easy Customization**: Python-based backend makes it easy to add new monitoring checks and AI features
- **Transparent Architecture**: No vendor lock-in or proprietary monitoring protocols

**The future of monitoring is AI-specific, not generic.** This system provides the foundation for intelligent, automated monitoring that learns from your infrastructure and proactively identifies issues before they impact users.

## 🚀 Features

- **Real-time Monitoring**: Integrated scheduler with live data updates
- **Server-side Rendering**: Fast, reliable HTML generation with Jinja2
- **Geo-distributed Monitoring**: Agents in EU, SG, PH locations for global coverage
- **D3.js Charts**: Professional time series visualization with proper filtering
- **FastAPI Backend**: High-performance async API with Python
- **TimescaleDB**: Optimized time series database for monitoring data
- **Container Ready**: Docker and docker-compose setup
- **Clean UI**: Tailwind CSS with minimal JavaScript and D3.js charts
- **Nagios-inspired**: Status overviews, alerts, and service monitoring
- **BusyBox Compatible**: Agents run on minimal Linux systems
- **AJAX Auto-refresh**: Preserves UI state, updates data without page reloads

## 🛠 Tech Stack

- **Frontend**: Server-side rendered HTML + Tailwind CSS + D3.js charts
- **Backend**: FastAPI (Python) + Jinja2 templates + APScheduler
- **Database**: TimescaleDB (PostgreSQL extension for time series)
- **Geo-Agents**: Bash scripts compatible with BusyBox (minimal Linux)
- **Deployment**: Docker + Docker Compose + automated deployment scripts
- **Charts**: D3.js v7 for professional, responsive visualizations

## 📦 Quick Start

### Prerequisites

- Docker and Docker Compose
- Python 3.11+ (for development)

### 1. Clone and Setup

```bash
git clone <repository-url>
cd open-monitoring
```

### 2. Start with Docker (Recommended)

```bash
# Start all services
docker-compose -f docker/docker-compose.yml up -d

# View logs
docker-compose -f docker/docker-compose.yml logs -f

# Stop services
docker-compose -f docker/docker-compose.yml down
```

The dashboard will be available at:
- **Dashboard**: http://localhost:8002
- **API**: http://localhost:8002/api/
- **Database**: localhost:5433

**Note**: All ports have been selected to avoid conflicts with TP-Link Omada systems (which use ports 8043, 29810-29814, 27010-27017). The dashboard uses server-side rendering for optimal performance and reliability.

## 🛡️ Reliability & Production Deployment

### Current Setup (Container-based)
- **Auto-restart**: Containers restart automatically with `restart: unless-stopped`
- **Health checks**: Database health monitoring with 30-second intervals
- **Scheduler integration**: Scheduler starts automatically with FastAPI application
- **Error recovery**: Database connection retry logic (3 attempts)

### Production Deployment Options

#### Option 1: Container Orchestration (Recommended)
```bash
# Using Docker Compose (current setup)
docker-compose up -d

# Or Kubernetes
kubectl apply -f kubernetes/
```

#### Option 2: Systemd Service (High Reliability)
```bash
# Deploy as systemd service
./deploy-scheduler.sh

# Monitor with journald
sudo journalctl -u monitoring-scheduler -f

# Health checks
curl http://localhost:8002/api/health
```

#### Option 3: Process Manager (Supervisor)
```ini
[program:monitoring-scheduler]
command=/path/to/venv/bin/python backend/scheduler_service.py --continuous
autostart=true
autorestart=true
redirect_stderr=true
stdout_logfile=/var/log/monitoring-scheduler.log
```

### Reliability Features

- ✅ **Automatic restarts** on container/process failure
- ✅ **Database connection retry** with exponential backoff
- ✅ **Job misfire handling** (grace time for missed executions)
- ✅ **Health monitoring** via `/api/health` endpoint
- ✅ **Graceful shutdown** on application termination
- ✅ **Resource limits** (memory/CPU quotas)
- ✅ **Comprehensive logging** with timestamps

### Crash Recovery

**Container Level:**
```yaml
restart: unless-stopped
healthcheck:
  test: ["CMD-SHELL", "pg_isready -U monitor"]
  interval: 30s
  timeout: 10s
  retries: 3
```

**Application Level:**
- Scheduler auto-starts on FastAPI startup
- Database connection pools with retry logic
- Job execution with error handling and retries

### Monitoring & Alerting

- **Health endpoint**: `GET /api/health` - comprehensive system status
- **Scheduler status**: `GET /api/scheduler/status` - job execution details
- **Manual controls**: `POST /api/scheduler/start|stop` - runtime management

**Example Health Response:**
```json
{
  "status": "healthy",
  "timestamp": "2025-10-16T13:20:36.123Z",
  "services": {
    "database": "connected",
    "scheduler": {
      "running": true,
      "jobs_count": 2,
      "jobs": [...]
    },
    "monitoring": {
      "active_subdomains": 11
    }
  }
}
```

### 3. Development Setup

#### Backend Setup
```bash
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

## 🗄 Database Schema

### Metrics Table
```sql
CREATE TABLE monitoring.metrics (
    time TIMESTAMPTZ NOT NULL,
    host TEXT NOT NULL,
    service TEXT NOT NULL,
    metric_name TEXT NOT NULL,
    value DOUBLE PRECISION,
    status TEXT,
    metadata JSONB
);
```

### Alerts Table
```sql
CREATE TABLE monitoring.alerts (
    id SERIAL PRIMARY KEY,
    time TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    host TEXT NOT NULL,
    service TEXT NOT NULL,
    severity TEXT NOT NULL,
    message TEXT,
    acknowledged BOOLEAN DEFAULT FALSE,
    resolved BOOLEAN DEFAULT FALSE
);
```

## 📡 API Endpoints

### GET `/api/health`
Health check endpoint.

### GET `/api/metrics`
Retrieve metrics data.
- Query params: `host`, `service`, `metric_name`, `hours`

### POST `/api/metrics`
Insert new metric data.

### GET `/api/alerts`
Retrieve alerts.
- Query params: `resolved`, `limit`

### WebSocket `/ws`
Real-time updates endpoint.

## 🔧 Configuration

### Environment Variables

Copy the example environment file and configure your database connection:

```bash
cp backend/.env.example backend/.env
```

Then edit `backend/.env` with your actual database credentials:

```env
DATABASE_URL=postgresql://username:password@host:port/database
```

### CORS Configuration

Update allowed origins in `backend/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://mon.altgovph.site"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 📊 Adding Metrics

### Via API
```bash
curl -X POST http://localhost:8000/api/metrics \
  -H "Content-Type: application/json" \
  -d '{
    "host": "web-server-01",
    "service": "nginx",
    "metric_name": "cpu_usage",
    "value": 45.2,
    "status": "ok",
    "metadata": {"cores": 4}
  }'
```

### Python Client
```python
import requests

metric = {
    "host": "web-server-01",
    "service": "nginx",
    "metric_name": "cpu_usage",
    "value": 45.2,
    "status": "ok"
}

response = requests.post("http://localhost:8000/api/metrics", json=metric)
```

## 🎨 Customization

### Adding New Charts

1. Create a new D3.js chart function in `templates/dashboard.html`
2. Add the chart to the modal or dashboard template
3. Update the backend API if new data is needed

### Custom Metrics

1. Define new metric types in your monitoring agents
2. Update the database schema if needed
3. Add chart visualizations for new metrics

## 🔮 Future AI Features

- Anomaly detection with scikit-learn
- Predictive alerting with TensorFlow
- Natural language queries
- Automated threshold adjustments
- Root cause analysis

## 📝 Recent Updates (October 2025)

### ✅ **Completed**
- **D3.js Implementation**: Replaced custom SVG charts with professional D3.js visualizations
- **AJAX Auto-refresh**: Fixed page reload issues by implementing AJAX data updates
- **UTC+8 Timezone**: Consistent time display across all geo-agents
- **Server-side Rendering**: Pure server-side HTML generation without client frameworks

### 🚧 **In Progress**
- **EU Agent Deployment**: Monitoring agent setup and data collection
- **Time Series Filtering**: D3.js chart filtering by time range (24h/1h/5m)
- **Performance Optimization**: Chart rendering and data processing improvements

### 🔧 **Technical Improvements**
- Switched from custom SVG to D3.js v7 for charts
- Removed Vue.js frontend dependency
- AJAX data updates preserve UI state
- Consistent UTC+8 timezone display
- Improved error handling and debugging

## 🚀 Deployment

### Automated Deployment (Server)

For server deployments, use the automated deployment script:

```bash
# Run deployment script (pulls code + restarts containers)
./deploy.sh
```

This script will:
1. Pull the latest code from git
2. Restart all containers to apply changes
3. Display deployment status

### Manual Deployment

```bash
# Pull latest code
git pull

# Restart containers to apply changes
cd docker
docker-compose restart

# Or rebuild if dependencies changed
docker-compose up -d --build
```

### Production Build

```bash
# Build and deploy with Docker
docker-compose -f docker/docker-compose.yml up -d --build
```

### Nginx Configuration

```nginx
server {
    listen 80;
    server_name mon.altgovph.site;

    location / {
        proxy_pass http://localhost:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🙏 Acknowledgments

- Inspired by Nagios and MRTG
- Built for bettergov.ph monitoring needs
- Thanks to the open source community