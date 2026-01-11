"""Async HTTP client with retry logic and rate limiting."""

import asyncio
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RetryConfig:
    """Configuration for retry behavior."""
    
    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        exponential_base: float = 2.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base


class AsyncHTTPClient:
    """Async HTTP client with retry, rate limiting, and caching."""
    
    # Rate limit tracking per domain
    _rate_limits: dict[str, dict[str, Any]] = {}
    
    def __init__(
        self,
        timeout: float = 30.0,
        retry_config: RetryConfig | None = None,
    ) -> None:
        """Initialize async client.
        
        Args:
            timeout: Request timeout in seconds
            retry_config: Retry configuration
        """
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()
        self._client: httpx.AsyncClient | None = None
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "upgrade-impact-analyzer/1.0",
                },
            )
        return self._client
    
    async def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make GET request with retry logic.
        
        Args:
            url: URL to request
            headers: Optional headers
            **kwargs: Additional request arguments
            
        Returns:
            Response object
            
        Raises:
            httpx.HTTPError: If all retries fail
        """
        return await self._request_with_retry("GET", url, headers=headers, **kwargs)
    
    async def post(
        self,
        url: str,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make POST request with retry logic."""
        return await self._request_with_retry(
            "POST", url, json=json, headers=headers, **kwargs
        )
    
    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute request with exponential backoff retry."""
        client = await self._get_client()
        last_exception: Exception | None = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # Check rate limit
                await self._wait_for_rate_limit(url)
                
                # Make request
                response = await client.request(method, url, **kwargs)
                
                # Update rate limit from headers
                self._update_rate_limit(url, response)
                
                # Check for rate limit response
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited, waiting {retry_after}s")
                    await asyncio.sleep(retry_after)
                    continue
                
                # Check for server errors (retry-able)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                
                return response
                
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
                last_exception = e
                
                if attempt < self.retry_config.max_retries:
                    delay = min(
                        self.retry_config.base_delay * (
                            self.retry_config.exponential_base ** attempt
                        ),
                        self.retry_config.max_delay,
                    )
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}), retrying in {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(f"Request failed after {attempt + 1} attempts: {e}")
        
        if last_exception:
            raise last_exception
        
        raise httpx.HTTPError("Request failed with no exception")
    
    async def _wait_for_rate_limit(self, url: str) -> None:
        """Wait if necessary to respect rate limits."""
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc
        
        if domain in self._rate_limits:
            limit_info = self._rate_limits[domain]
            remaining = limit_info.get("remaining", 100)
            reset_time = limit_info.get("reset", 0)
            
            if remaining <= 1:
                import time
                wait_time = max(0, reset_time - time.time())
                if wait_time > 0:
                    logger.info(f"Rate limit low for {domain}, waiting {wait_time:.1f}s")
                    await asyncio.sleep(wait_time)
    
    def _update_rate_limit(self, url: str, response: httpx.Response) -> None:
        """Update rate limit tracking from response headers."""
        from urllib.parse import urlparse
        
        domain = urlparse(url).netloc
        
        # GitHub-style headers
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset = response.headers.get("X-RateLimit-Reset")
        
        if remaining is not None:
            self._rate_limits[domain] = {
                "remaining": int(remaining),
                "reset": int(reset) if reset else 0,
            }
    
    async def close(self) -> None:
        """Close the client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    async def __aenter__(self) -> "AsyncHTTPClient":
        """Async context manager entry."""
        return self
    
    async def __aexit__(self, *args: Any) -> None:
        """Async context manager exit."""
        await self.close()


class SyncHTTPClient:
    """Synchronous wrapper for async HTTP client.
    
    Use this for backward compatibility with sync code.
    """
    
    def __init__(
        self,
        timeout: float = 30.0,
        retry_config: RetryConfig | None = None,
    ) -> None:
        self.timeout = timeout
        self.retry_config = retry_config or RetryConfig()
        self._client = httpx.Client(
            timeout=timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "upgrade-impact-analyzer/1.0",
            },
        )
    
    def get(
        self,
        url: str,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make GET request with retry logic."""
        return self._request_with_retry("GET", url, headers=headers, **kwargs)
    
    def post(
        self,
        url: str,
        json: dict | None = None,
        headers: dict[str, str] | None = None,
        **kwargs: Any,
    ) -> httpx.Response:
        """Make POST request with retry logic."""
        return self._request_with_retry(
            "POST", url, json=json, headers=headers, **kwargs
        )
    
    def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        """Execute request with exponential backoff retry."""
        import time
        
        last_exception: Exception | None = None
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                response = self._client.request(method, url, **kwargs)
                
                # Check for rate limit response
                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 60))
                    logger.warning(f"Rate limited, waiting {retry_after}s")
                    time.sleep(retry_after)
                    continue
                
                # Check for server errors (retry-able)
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error: {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                
                return response
                
            except (httpx.TimeoutException, httpx.ConnectError, httpx.HTTPStatusError) as e:
                last_exception = e
                
                if attempt < self.retry_config.max_retries:
                    delay = min(
                        self.retry_config.base_delay * (
                            self.retry_config.exponential_base ** attempt
                        ),
                        self.retry_config.max_delay,
                    )
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}), retrying in {delay:.1f}s: {e}"
                    )
                    time.sleep(delay)
                else:
                    logger.error(f"Request failed after {attempt + 1} attempts: {e}")
        
        if last_exception:
            raise last_exception
        
        raise httpx.HTTPError("Request failed with no exception")
    
    def close(self) -> None:
        """Close the client."""
        self._client.close()
    
    def __enter__(self) -> "SyncHTTPClient":
        """Context manager entry."""
        return self
    
    def __exit__(self, *args: Any) -> None:
        """Context manager exit."""
        self.close()


async def fetch_all(
    urls: list[str],
    headers: dict[str, str] | None = None,
    max_concurrent: int = 10,
) -> list[httpx.Response | Exception]:
    """Fetch multiple URLs concurrently.
    
    Args:
        urls: List of URLs to fetch
        headers: Optional headers for all requests
        max_concurrent: Maximum concurrent requests
        
    Returns:
        List of responses or exceptions
    """
    semaphore = asyncio.Semaphore(max_concurrent)
    
    async def fetch_one(client: AsyncHTTPClient, url: str) -> httpx.Response | Exception:
        async with semaphore:
            try:
                return await client.get(url, headers=headers)
            except Exception as e:
                return e
    
    async with AsyncHTTPClient() as client:
        tasks = [fetch_one(client, url) for url in urls]
        return await asyncio.gather(*tasks)
