# btse_sdk/core.py
import time
import hmac
import json
import hashlib
from typing import Any, Dict, Optional

import requests


class BTSEAPIError(Exception):
    """Raised for non-2xx responses from BTSE API."""

    def __init__(self, status_code: int, message: str, payload: Any = None):
        super().__init__(f"BTSE API error {status_code}: {message}")
        self.status_code = status_code
        self.payload = payload


class BTSEClientBase:
    """
    Base client for BTSE HTTP APIs.

    - base_url: e.g. "https://api.btse.com/spot" or "https://api.btse.com/futures"
    - api_prefix: e.g. "/api/v3.3" (spot) or "/api/v2.3" (futures)
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        *,
        base_url: str,
        api_prefix: str,
        timeout: float = 10.0,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.api_prefix = api_prefix.rstrip("/")
        self.timeout = timeout
        self.session = session or requests.Session()

    # ---------- Auth helpers ----------

    def _nonce(self) -> str:
        # “Long format” timestamp (ms) as per docs  [oai_citation:1‡Btsecom](https://btsecom.github.io/docs/spotV3_3/en/)
        return str(int(time.time() * 1000))

    def _sign(self, path: str, body_str: str, nonce: str) -> str:
        """
        HMAC-SHA384(secret, path + nonce + bodyStr) hex digest.

        path: e.g. "/api/v3.3/order"
        body_str: JSON string *exactly* as sent in the HTTP body.
        """
        if not self.api_secret:
            raise ValueError("API secret not set for authenticated request")

        msg = f"{path}{nonce}{body_str}".encode("utf-8")
        secret_bytes = self.api_secret.encode("utf-8")
        return hmac.new(secret_bytes, msg, hashlib.sha384).hexdigest()

    def _auth_headers(
        self,
        path: str,
        body: Optional[Dict[str, Any]],
        query_params: Optional[Dict[str, Any]] = None,
        method: str = "POST"
    ) -> tuple:
        if not self.api_key or not self.api_secret:
            raise ValueError("API key/secret required for authenticated endpoints")

        # Important: serialize JSON the same way for body & signature
        body_str = ""
        headers = {"Content-Type": "application/json"}

        if body is not None:
            # Compact JSON (no spaces) to avoid signature mismatch
            body_str = json.dumps(body, separators=(",", ":"))

        # BTSE signature rules:
        # - GET requests: sign path without query params (params sent in URL)
        # - DELETE requests: sign path WITH query params
        # - POST requests: sign path with body
        sign_path = path
        # if query_params and method == "DELETE":
        #     import urllib.parse
        #     query_string = urllib.parse.urlencode(sorted(query_params.items()))
        #     sign_path = f"{path}"

        nonce = self._nonce()
        sign = self._sign(path=sign_path, body_str=body_str, nonce=nonce)

        headers.update(
            {
                "request-api": self.api_key,
                "request-nonce": nonce,
                "request-sign": sign,
            }
        )

        return headers, body_str

    # ---------- HTTP wrapper ----------

    def _request(
        self,
        method: str,
        endpoint: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        auth: bool = False,
    ) -> Any:
        """
        endpoint: path after api_prefix, e.g. "/price" or "/order"
        """
        path = f"{self.api_prefix}{endpoint}"  # e.g. "/api/v3.3/price"
        url = f"{self.base_url}{path}"

        headers: Dict[str, str] = {}
        json_body = None
        body_bytes = None

        if auth:
            # Include query params in signature for DELETE requests only
            headers, body_str = self._auth_headers(
                path=path,
                body=data,
                query_params=params,
                method=method
            )
            # IMPORTANT: Send the exact body_str that was signed!
            # Don't let requests re-serialize it with different settings
            body_bytes = body_str.encode('utf-8') if body_str else None
        else:
            if data is not None:
                headers["Content-Type"] = "application/json"
                json_body = data

        # Debug: show complete URL with query params
        if params:
            import urllib.parse
            query_string = urllib.parse.urlencode(params)
            # print(f"URL: {url}?{query_string}")
        # else:
        #     print(f"URL: {url}")

        resp = self.session.request(
            method=method.upper(),
            url=url,
            params=params,
            json=json_body,  # Used for non-auth requests
            data=body_bytes,  # Used for auth requests (exact signed bytes)
            headers=headers,
            timeout=self.timeout,
        )

        if not (200 <= resp.status_code < 300):
            # Try to parse JSON error, fallback to text
            try:
                payload = resp.json()
                message = payload.get("message") or payload.get("error") or resp.text
            except Exception:
                payload = resp.text
                message = resp.text
            raise BTSEAPIError(resp.status_code, message, payload)

        # Some endpoints return plain arrays, some objects
        try:
            return resp.json()
        except ValueError:
            return resp.text