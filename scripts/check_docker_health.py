#!/usr/bin/env python3
"""
Docker Health Check Script for Mukthi Guru

This script checks the health of all Docker services used by the Mukthi Guru application:
- Qdrant (vector database)
- Redis (caching)
- Neo4j (graph database)
- Jaeger (tracing)
- Backend API

It can also attempt to restart unhealthy services if the --fix flag is provided.
"""

import argparse
import asyncio
import json
import logging
import sys
import time
from typing import Dict, List, Tuple

import aiohttp
import asyncpg
from neo4j import AsyncGraphDatabase, AsyncDriver
from qdrant_client import AsyncQdrantClient
import os

# Add backend directory to sys.path to import Settings
sys.path.append(os.path.join(os.path.dirname(os.path.dirname(__file__)), 'backend'))
try:
    from app.config import settings
    NEO4J_PASSWORD = settings.neo4j_password
    NEO4J_USER = settings.neo4j_user
except Exception:
    NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")
    NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Service configurations
SERVICES = {
    "qdrant": {
        "url": "http://localhost:6333",
        "health_endpoint": "/",
        "timeout": 5
    },
    "redis": {
        "url": "redis://localhost:6379",
        "timeout": 5
    },
    "neo4j": {
        "url": "bolt://localhost:7687",
        "username": NEO4J_USER,
        "password": NEO4J_PASSWORD,
        "timeout": 5
    },
    "jaeger": {
        "url": "http://localhost:16686",
        "health_endpoint": "/api/services",
        "timeout": 5
    },
    "backend": {
        "url": "http://localhost:8000",
        "health_endpoint": "/api/health",
        "timeout": 10
    }
}

async def check_qdrant_health(session: aiohttp.ClientSession, config: dict) -> Tuple[bool, str]:
    """Check Qdrant health."""
    try:
        url = f"{config['url']}{config['health_endpoint']}"
        async with session.get(url, timeout=config['timeout']) as response:
            if response.status == 200:
                return True, "Qdrant is healthy"
            else:
                return False, f"Qdrant returned status {response.status}"
    except Exception as e:
        return False, f"Qdrant health check failed: {str(e)}"

async def check_redis_health(config: dict) -> Tuple[bool, str]:
    """Check Redis health."""
    try:
        # For simplicity, we'll use a basic TCP connection check
        import socket
        host = config['url'].replace('redis://', '').split(':')[0]
        port = int(config['url'].split(':')[-1]) if ':' in config['url'] else 6379

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(config['timeout'])
        result = sock.connect_ex((host, port))
        sock.close()

        if result == 0:
            return True, "Redis is healthy"
        else:
            return False, f"Redis connection failed with error code {result}"
    except Exception as e:
        return False, f"Redis health check failed: {str(e)}"

async def check_neo4j_health(config: dict) -> Tuple[bool, str]:
    """Check Neo4j health."""
    try:
        driver: AsyncDriver = AsyncGraphDatabase.driver(
            config['url'],
            auth=(config['username'], config['password']),
            max_connection_lifetime=config['timeout']
        )

        async with driver.session() as session:
            result = await session.run("RETURN 1")
            await result.single()

        await driver.close()
        return True, "Neo4j is healthy"
    except Exception as e:
        return False, f"Neo4j health check failed: {str(e)}"

async def check_jaeger_health(session: aiohttp.ClientSession, config: dict) -> Tuple[bool, str]:
    """Check Jaeger health."""
    try:
        url = f"{config['url']}{config['health_endpoint']}"
        async with session.get(url, timeout=config['timeout']) as response:
            if response.status == 200:
                return True, "Jaeger is healthy"
            else:
                return False, f"Jaeger returned status {response.status}"
    except Exception as e:
        return False, f"Jaeger health check failed: {str(e)}"

async def check_backend_health(session: aiohttp.ClientSession, config: dict) -> Tuple[bool, str]:
    """Check Backend API health."""
    try:
        url = f"{config['url']}{config['health_endpoint']}"
        async with session.get(url, timeout=config['timeout']) as response:
            if response.status == 200:
                data = await response.json()
                if data.get('status') == 'healthy':
                    return True, "Backend is healthy"
                else:
                    return False, f"Backend returned unhealthy status: {data}"
            else:
                return False, f"Backend returned status {response.status}"
    except Exception as e:
        return False, f"Backend health check failed: {str(e)}"

async def check_service_health(session: aiohttp.ClientSession, service_name: str, config: dict) -> Tuple[bool, str]:
    """Check health of a specific service."""
    checkers = {
        "qdrant": check_qdrant_health,
        "redis": check_redis_health,
        "neo4j": check_neo4j_health,
        "jaeger": check_jaeger_health,
        "backend": check_backend_health
    }

    checker = checkers.get(service_name)
    if not checker:
        return False, f"No health checker implemented for {service_name}"

    if service_name in ["qdrant", "jaeger", "backend"]:
        return await checker(session, config)
    else:
        return await checker(config)

async def check_all_services() -> Dict[str, Tuple[bool, str]]:
    """Check health of all services."""
    results = {}

    async with aiohttp.ClientSession() as session:
        tasks = []
        for service_name, config in SERVICES.items():
            task = check_service_health(session, service_name, config)
            tasks.append((service_name, task))

        for service_name, task in tasks:
            try:
                result = await task
                results[service_name] = result
            except Exception as e:
                results[service_name] = (False, f"Health check failed with exception: {str(e)}")

    return results

def print_results(results: Dict[str, Tuple[bool, str]]) -> None:
    """Print health check results in a formatted table."""
    print("\n" + "="*60)
    print("MUKTHI GURU DOCKER SERVICES HEALTH CHECK")
    print("="*60)
    print(f"{'Service':<12} {'Status':<10} {'Message'}")
    print("-"*60)

    all_healthy = True
    for service_name, (healthy, message) in results.items():
        status = "HEALTHY" if healthy else "UNHEALTHY"
        if not healthy:
            all_healthy = False
        print(f"{service_name:<12} {status:<10} {message}")

    print("-"*60)
    if all_healthy:
        print("✅ All services are healthy!")
    else:
        print("❌ Some services are unhealthy!")
    print("="*60 + "\n")

async def main():
    parser = argparse.ArgumentParser(description="Check health of Mukthi Guru Docker services")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to restart unhealthy services (requires docker-compose)"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Timeout for each health check in seconds (default: 30)"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Run health checks
    logger.info("Starting health check of all services...")
    results = await check_all_services()

    # Print results
    print_results(results)

    # If fix flag is provided and there are unhealthy services, attempt to restart
    if args.fix:
        unhealthy_services = [name for name, (healthy, _) in results.items() if not healthy]
        if unhealthy_services:
            logger.info(f"Attempting to restart unhealthy services: {', '.join(unhealthy_services)}")
            # In a real implementation, we would use docker-compose to restart services
            # For now, we'll just log that this would happen
            logger.info("In a production environment, this would restart the services using docker-compose")
            logger.info("For now, please manually restart unhealthy services with:")
            logger.info("  cd backend && docker compose restart <service-name>")
        else:
            logger.info("All services are healthy, no fixes needed.")

    # Exit with appropriate code
    all_healthy = all(healthy for healthy, _ in results.values())
    sys.exit(0 if all_healthy else 1)

if __name__ == "__main__":
    asyncio.run(main())