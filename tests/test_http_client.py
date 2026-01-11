"""Comprehensive tests for HTTP client with retry and rate limiting."""

import pytest
from unittest.mock import MagicMock, patch
import httpx

from upgrade_analyzer.http_client import (
    AsyncHTTPClient,
    SyncHTTPClient,
    RetryConfig,
)


class TestRetryConfig:
    """Test retry configuration."""
    
    def test_default_config(self):
        """Test default retry settings."""
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 2.0
    
    def test_custom_config(self):
        """Test custom retry settings."""
        config = RetryConfig(
            max_retries=5,
            base_delay=0.5,
            max_delay=30.0,
            exponential_base=3.0,
        )
        assert config.max_retries == 5
        assert config.base_delay == 0.5


class TestSyncHTTPClient:
    """Test synchronous HTTP client."""
    
    def test_client_initialization(self):
        """Test client initializes correctly."""
        client = SyncHTTPClient(timeout=15.0)
        assert client.timeout == 15.0
        assert client.retry_config.max_retries == 3
        client.close()
    
    def test_custom_retry_config(self):
        """Test client with custom retry config."""
        config = RetryConfig(max_retries=5)
        client = SyncHTTPClient(retry_config=config)
        assert client.retry_config.max_retries == 5
        client.close()
    
    def test_context_manager(self):
        """Test client as context manager."""
        with SyncHTTPClient() as client:
            assert client._client is not None
        # Client is closed after context
    
    @patch.object(httpx.Client, 'request')
    def test_successful_request(self, mock_request):
        """Test successful GET request."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_request.return_value = mock_response
        
        with SyncHTTPClient() as client:
            response = client.get("https://example.com")
            assert response.status_code == 200
    
    @patch.object(httpx.Client, 'request')
    def test_retry_on_server_error(self, mock_request):
        """Test retry on 500 error."""
        # First call fails with 500, second succeeds
        error_response = MagicMock()
        error_response.status_code = 500
        error_response.request = MagicMock()
        
        success_response = MagicMock()
        success_response.status_code = 200
        
        mock_request.side_effect = [
            httpx.HTTPStatusError("500", request=MagicMock(), response=error_response),
            success_response,
        ]
        
        config = RetryConfig(base_delay=0.01)  # Fast retry for tests
        with SyncHTTPClient(retry_config=config) as client:
            response = client.get("https://example.com")
            assert response.status_code == 200
            assert mock_request.call_count == 2
    
    @patch.object(httpx.Client, 'request')
    def test_rate_limit_handling(self, mock_request):
        """Test 429 rate limit response handling."""
        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {"Retry-After": "1"}
        
        success_response = MagicMock()
        success_response.status_code = 200
        
        mock_request.side_effect = [rate_limit_response, success_response]
        
        config = RetryConfig(base_delay=0.01)
        with SyncHTTPClient(retry_config=config) as client:
            with patch('time.sleep'):  # Skip actual sleep
                response = client.get("https://example.com")
                assert response.status_code == 200


class TestAsyncHTTPClient:
    """Test async HTTP client."""
    
    @pytest.mark.asyncio
    async def test_async_client_initialization(self):
        """Test async client initializes correctly."""
        client = AsyncHTTPClient(timeout=15.0)
        assert client.timeout == 15.0
        await client.close()
    
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        """Test async client as context manager."""
        async with AsyncHTTPClient() as client:
            assert client is not None
