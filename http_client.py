"""
Persistent HTTP client with connection pooling.

This module provides a singleton HTTP client that maintains persistent connections
across requests, significantly reducing connection overhead for repeated domain access.

Key optimizations:
1. Connection pooling - Reuses TCP connections (limit=100 total, 10 per host)
2. DNS caching - 5-minute TTL reduces DNS lookup overhead
3. Keep-alive - Maintains connections for 30 seconds
4. Session lifecycle - Single session for the entire bot lifecycle

Usage:
    from http_client import get_http_client, close_http_client

    # In async context:
    client = await get_http_client()
    async with client.session.get(url) as response:
        ...

    # On shutdown:
    await close_http_client()
"""

import asyncio
import aiohttp
from typing import Optional, Dict, Any
from logger import setup_logger
from config import Config

logger = setup_logger()


class PersistentHTTPClient:
    """
    Singleton HTTP client with connection pooling and lifecycle management.

    This class manages a single aiohttp.ClientSession that persists across
    multiple requests, enabling connection reuse and reducing latency.

    Features:
    - Connection pooling with configurable limits
    - DNS caching to reduce lookup overhead
    - Automatic timeout handling
    - Graceful shutdown with connection draining
    """

    _instance: Optional['PersistentHTTPClient'] = None
    _lock: asyncio.Lock = None

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._connector: Optional[aiohttp.TCPConnector] = None
        self._initialized: bool = False

    @classmethod
    async def get_instance(cls) -> 'PersistentHTTPClient':
        """
        Get or create the singleton instance.

        Thread-safe via asyncio lock.
        """
        if cls._lock is None:
            cls._lock = asyncio.Lock()

        async with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
                await cls._instance._initialize()
            elif not cls._instance._initialized:
                await cls._instance._initialize()
            return cls._instance

    async def _initialize(self) -> None:
        """
        Initialize the HTTP client with optimized connection pooling.

        Connector settings:
        - limit=100: Maximum 100 simultaneous connections total
        - limit_per_host=10: Maximum 10 connections per domain
        - ttl_dns_cache=300: Cache DNS lookups for 5 minutes
        - keepalive_timeout=30: Keep connections alive for 30 seconds
        - enable_cleanup_closed=True: Clean up closed connections
        """
        if self._initialized and self._session and not self._session.closed:
            return

        # Create optimized connector with connection pooling
        self._connector = aiohttp.TCPConnector(
            limit=100,                    # Total connections across all hosts
            limit_per_host=10,            # Connections per host
            ttl_dns_cache=300,            # DNS cache TTL (5 minutes)
            keepalive_timeout=30,         # Keep connections alive (seconds)
            enable_cleanup_closed=True,   # Clean up closed connections
            force_close=False,            # Allow connection reuse
        )

        # Default timeout configuration
        timeout = aiohttp.ClientTimeout(
            total=Config.REQUEST_TIMEOUT,
            connect=5,  # Connection timeout
            sock_read=Config.REQUEST_TIMEOUT  # Read timeout
        )

        # Create session with connector
        self._session = aiohttp.ClientSession(
            connector=self._connector,
            timeout=timeout,
            # Trust environment for proxy settings
            trust_env=True,
        )

        self._initialized = True
        logger.info("Persistent HTTP client initialized with connection pooling "
                   f"(limit=100, per_host=10, dns_cache=300s)")

    @property
    def session(self) -> aiohttp.ClientSession:
        """Get the underlying aiohttp session."""
        if not self._initialized or self._session is None or self._session.closed:
            raise RuntimeError("HTTP client not initialized. Call get_instance() first.")
        return self._session

    async def close(self) -> None:
        """
        Gracefully close the HTTP client and drain connections.

        Call this on application shutdown to ensure clean termination.
        """
        if self._session and not self._session.closed:
            await self._session.close()
            # Wait briefly for connections to close gracefully
            await asyncio.sleep(0.25)
            logger.info("Persistent HTTP client closed")

        self._initialized = False
        self._session = None
        self._connector = None

    def get_stats(self) -> Dict[str, Any]:
        """
        Get connection pool statistics for monitoring.

        Returns:
            Dictionary with current connection counts and limits
        """
        if not self._connector:
            return {"status": "not_initialized"}

        return {
            "status": "active",
            "limit": self._connector.limit,
            "limit_per_host": self._connector.limit_per_host,
            # Note: Detailed stats would require tracking, aiohttp doesn't expose them directly
        }


# Module-level convenience functions

async def get_http_client() -> PersistentHTTPClient:
    """
    Get the singleton HTTP client instance.

    This is the primary entry point for accessing the persistent HTTP client.
    The client is automatically initialized on first access.

    Returns:
        PersistentHTTPClient instance with active session

    Example:
        client = await get_http_client()
        async with client.session.get('https://example.com') as resp:
            text = await resp.text()
    """
    return await PersistentHTTPClient.get_instance()


async def get_http_session() -> aiohttp.ClientSession:
    """
    Get the underlying aiohttp session directly.

    Convenience function for when you only need the session object.

    Returns:
        aiohttp.ClientSession with connection pooling
    """
    client = await get_http_client()
    return client.session


async def close_http_client() -> None:
    """
    Close the HTTP client and release all connections.

    Call this during application shutdown to ensure clean termination.
    This drains all pending connections gracefully.
    """
    if PersistentHTTPClient._instance:
        await PersistentHTTPClient._instance.close()
        PersistentHTTPClient._instance = None
        logger.info("HTTP client shutdown complete")
