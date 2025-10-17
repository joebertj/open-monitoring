#!/usr/bin/env python3
"""
Deployment Script for BetterGovPH Open Monitoring
Adapted from open-data-visualization deployment_mcp.py

Default configuration:
- SSH Key: ~/.ssh/klti
- Username: joebertj
- Host: 10.27.79.2
- Working Directory: ~/open-monitoring
- Deployment: Docker-based restart
"""

import asyncio
import logging
import paramiko
import os
from typing import Dict, Any
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MonitoringDeploymentServer:
    """Deployment server for Open Monitoring"""

    def __init__(self):
        self.ssh_client = None
        self.connected = False

    async def connect_to_server(
        self,
        host: str = "10.27.79.2",
        username: str = "joebertj",
        key_name: str = "klti",
        port: int = 22,
        working_dir: str = "~/open-monitoring",
    ) -> Dict[str, Any]:
        """Connect to server via SSH"""
        try:
            logger.info(f"🔗 Connecting to {host} as {username}...")

            # Initialize SSH client
            self.ssh_client = paramiko.SSHClient()
            self.ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            # Get key path
            key_path = os.path.expanduser(f"~/.ssh/{key_name}")
            if not os.path.exists(key_path):
                return {
                    "success": False,
                    "error": f"SSH key not found: {key_path}",
                    "key_path": key_path,
                }

            # Connect to server
            self.ssh_client.connect(
                hostname=host,
                username=username,
                port=port,
                key_filename=key_path,
                timeout=30,
            )

            self.connected = True
            self.default_working_dir = working_dir
            logger.info(f"✅ Connected to {host}")

            return {
                "success": True,
                "message": f"Connected to {host} as {username}",
                "host": host,
                "username": username,
                "working_dir": working_dir,
                "key_path": key_path,
            }

        except Exception as e:
            logger.error(f"❌ Failed to connect to {host}: {e}")
            return {"success": False, "error": str(e)}

    async def execute_command(
        self, command: str, working_dir: str = None
    ) -> Dict[str, Any]:
        """Execute a command on the server"""
        if not self.connected or not self.ssh_client:
            return {"success": False, "error": "Not connected to server"}

        try:
            # Use working directory
            working_dir = working_dir or getattr(
                self, "default_working_dir", "~/open-monitoring"
            )

            # Build full command with directory change
            full_command = f"cd {working_dir} && {command}"
            logger.info(f"📁 Working directory: {working_dir}")
            logger.info(f"🔧 Executing: {command}")

            # Execute command
            stdin, stdout, stderr = self.ssh_client.exec_command(full_command)

            # Get output
            output = stdout.read().decode("utf-8").strip()
            error = stderr.read().decode("utf-8").strip()
            exit_code = stdout.channel.recv_exit_status()

            if output:
                logger.info(f"📤 Output: {output[:500]}")
            if error:
                logger.warning(f"⚠️ Stderr: {error[:500]}")

            return {
                "success": exit_code == 0,
                "command": command,
                "output": output,
                "error": error,
                "exit_code": exit_code,
                "working_dir": working_dir,
            }

        except Exception as e:
            logger.error(f"❌ Command execution failed: {e}")
            return {"success": False, "error": str(e), "command": command}

    async def deploy_monitoring(
        self, working_dir: str = "~/open-monitoring"
    ) -> Dict[str, Any]:
        """Deploy Open Monitoring using Docker"""
        try:
            logger.info("🚀 Starting Open Monitoring deployment...")

            # Step 1: Git pull latest changes
            logger.info("📥 Step 1: Pulling latest changes from git...")
            pull_result = await self.execute_command("git pull", working_dir)
            if not pull_result["success"]:
                logger.warning(f"⚠️ Git pull had issues: {pull_result['error']}")

            # Step 2: Rebuild backend Docker image
            logger.info("🔨 Step 2: Rebuilding backend Docker image...")
            build_result = await self.execute_command(
                "/opt/homebrew/bin/docker build -f docker/Dockerfile.backend -t docker-backend .",
                working_dir,
            )

            if not build_result["success"]:
                logger.warning(f"⚠️ Docker build had issues: {build_result['error']}")

            # Step 3: Restart Docker containers
            logger.info("🐳 Step 3: Restarting Docker containers...")
            restart_result = await self.execute_command(
                "/opt/homebrew/bin/docker restart monitoring-backend monitoring-db",
                working_dir,
            )

            if not restart_result["success"]:
                return {
                    "success": False,
                    "error": "Failed to restart Docker containers",
                    "details": restart_result,
                    "step": "docker_restart",
                }

            # Step 3: Wait for services to be ready
            logger.info("⏳ Step 3: Waiting for services to start...")
            await asyncio.sleep(5)

            # Step 4: Health check
            logger.info("🏥 Step 4: Running health check...")
            health_result = await self.execute_command(
                "curl -s http://localhost:8002/api/health | jq -r '.status'",
                working_dir,
            )

            if health_result["success"] and "healthy" in health_result["output"]:
                logger.info("✅ Health check passed!")
            else:
                logger.warning("⚠️ Health check did not return 'healthy'")

            logger.info("✅ Open Monitoring deployment completed successfully!")

            return {
                "success": True,
                "message": "Open Monitoring deployment completed successfully",
                "deployment_time": datetime.now().isoformat(),
                "steps_completed": [
                    "git_pull",
                    "docker_restart",
                    "service_wait",
                    "health_check",
                ],
                "health_status": health_result.get("output", "unknown"),
                "working_dir": working_dir,
                "dashboard_url": "http://10.27.79.2:8002",
            }

        except Exception as e:
            logger.error(f"❌ Deployment failed: {e}")
            return {"success": False, "error": str(e), "step": "deployment_execution"}

    async def check_status(
        self, working_dir: str = "~/open-monitoring"
    ) -> Dict[str, Any]:
        """Check deployment status"""
        try:
            logger.info("📊 Checking Open Monitoring status...")

            # Check Docker containers
            logger.info("🐳 Checking Docker containers...")
            docker_result = await self.execute_command(
                "/opt/homebrew/bin/docker ps --filter name=monitoring", working_dir
            )

            # Check API health
            logger.info("🏥 Checking API health...")
            health_result = await self.execute_command(
                "curl -s http://localhost:8002/api/health", working_dir
            )

            # Check scheduler status
            logger.info("⏰ Checking scheduler status...")
            scheduler_result = await self.execute_command(
                "curl -s http://localhost:8002/api/scheduler/status", working_dir
            )

            return {
                "success": True,
                "check_time": datetime.now().isoformat(),
                "docker_containers": docker_result.get("output", "Unknown"),
                "api_health": health_result.get("output", "Unknown"),
                "scheduler_status": scheduler_result.get("output", "Unknown"),
                "working_dir": working_dir,
            }

        except Exception as e:
            logger.error(f"❌ Status check failed: {e}")
            return {"success": False, "error": str(e), "step": "status_check"}

    async def disconnect(self) -> Dict[str, Any]:
        """Disconnect from server"""
        try:
            if self.ssh_client:
                self.ssh_client.close()
                self.connected = False
                logger.info("🔌 Disconnected from server")

            return {"success": True, "message": "Disconnected from server"}

        except Exception as e:
            logger.error(f"❌ Disconnect failed: {e}")
            return {"success": False, "error": str(e)}


async def deploy_monitoring(
    host: str = "10.27.79.2",
    username: str = "joebertj",
    working_dir: str = "~/open-monitoring",
    check_status: bool = False,
) -> bool:
    """Deploy Open Monitoring"""
    try:
        print(f"🚀 Starting Open Monitoring deployment to {host}...")

        # Create deployment server
        server = MonitoringDeploymentServer()

        # Connect
        connect_result = await server.connect_to_server(
            host=host, username=username, working_dir=working_dir
        )

        if not connect_result["success"]:
            print(f"❌ Connection failed: {connect_result['error']}")
            return False

        print("✅ Connected to server")

        # Check status if requested
        if check_status:
            status_result = await server.check_status(working_dir)
            if status_result["success"]:
                print("📊 Current Status:")
                print(f"  Docker: {status_result['docker_containers'][:100]}...")
                print(f"  API Health: {status_result['api_health'][:100]}...")
                print(f"  Scheduler: {status_result['scheduler_status'][:100]}...")
            return True

        # Deploy
        deploy_result = await server.deploy_monitoring(working_dir)

        if deploy_result["success"]:
            print("✅ Open Monitoring deployment completed successfully!")
            print(f"🌐 Dashboard: {deploy_result.get('dashboard_url', 'N/A')}")
            print(f"🏥 Health: {deploy_result.get('health_status', 'Unknown')}")
            await server.disconnect()
            return True
        else:
            print(f"❌ Deployment failed: {deploy_result['error']}")
            await server.disconnect()
            return False

    except Exception as e:
        print(f"❌ Deployment error: {e}")
        return False


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="BetterGovPH Open Monitoring Deployment Tool"
    )
    parser.add_argument(
        "--host",
        default="10.27.79.2",
        help="Target host (default: 10.27.79.2)",
    )
    parser.add_argument(
        "--user",
        default="joebertj",
        help="SSH username (default: joebertj)",
    )
    parser.add_argument(
        "--dir",
        default="~/open-monitoring",
        help="Working directory on target server (default: ~/open-monitoring)",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Check status only (don't deploy)",
    )
    args = parser.parse_args()

    # Run deployment
    success = asyncio.run(
        deploy_monitoring(
            host=args.host,
            username=args.user,
            working_dir=args.dir,
            check_status=args.status,
        )
    )
    exit(0 if success else 1)

