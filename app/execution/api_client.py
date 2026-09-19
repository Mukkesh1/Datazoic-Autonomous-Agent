import httpx
import structlog
import base64
from typing import Dict, Any, Optional
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from app.core.config import Config

logger = structlog.get_logger()

class APIClient:
    """
    A resilient HTTP client for executing external tool calls.
    Includes exponential backoff and structured logging for auditability.
    """
    def __init__(self):
        self.client = httpx.AsyncClient(timeout=10.0)
        self._paypal_token = None

    async def _get_paypal_token(self) -> str:
        """Fetches and caches a PayPal OAuth Bearer token using Client Credentials."""
        if self._paypal_token:
            return self._paypal_token # Simple cache
            
        if not Config.PAYPAL_CLIENT_ID or not Config.PAYPAL_SECRET:
            raise Exception("Missing PAYPAL_CLIENT_ID or PAYPAL_SECRET in configuration.")
            
        auth_str = f"{Config.PAYPAL_CLIENT_ID}:{Config.PAYPAL_SECRET}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        
        logger.info("fetching_paypal_oauth_token")
        resp = await self.client.post(
            f"{Config.PAYPAL_BASE_URL}/v1/oauth2/token",
            headers={"Authorization": f"Basic {b64_auth}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials"}
        )
        
        if not resp.is_success:
            logger.error("paypal_auth_failed", status=resp.status_code, response=resp.text)
            resp.raise_for_status()
            
        self._paypal_token = resp.json()["access_token"]
        return self._paypal_token

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=2, max=10),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
        reraise=True
    )
    async def execute_call(
        self, 
        url: str, 
        method: str, 
        auth_type: str = "none",
        query_params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Executes the API request securely.
        """
        logger.info("api_request_started", url=url, method=method, auth=auth_type)
        
        headers = {"Content-Type": "application/json"}
        
        try:
            # 1. Handle Authentication
            if auth_type == "paypal_oauth":
                token = await self._get_paypal_token()
                headers["Authorization"] = f"Bearer {token}"
            elif auth_type == "bearer":
                # Fallback generic bearer if stored in env
                pass 
                
            # 2. Build Request
            kwargs = {"headers": headers}
            if query_params:
                kwargs["params"] = query_params
            if json_body:
                kwargs["json"] = json_body
                
            response = await self.client.request(method=method, url=url, **kwargs)
            response.raise_for_status()
            
            logger.info("api_request_success", url=url, status=response.status_code)
            
            try:
                return response.json()
            except ValueError:
                return {"response_text": response.text}
                
        except httpx.HTTPStatusError as e:
            logger.error("api_request_failed", url=url, status=e.response.status_code, error=str(e))
            return {
                "error": f"API Error: {e.response.status_code}", 
                "details": e.response.text
            }
