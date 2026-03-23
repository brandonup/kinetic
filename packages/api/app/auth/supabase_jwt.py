"""
Supabase JWT verification utilities.

Ported from FounderPanel. Supports:
  - HS256 verification via SUPABASE_JWT_SECRET (preferred)
  - RS256/ES256 verification via JWKS endpoint (fallback)
"""

import json
import logging
from typing import Any, Dict, Optional, cast

import jwt

from app.core.config import settings
from app.core.errors import AuthenticationError

logger = logging.getLogger(__name__)


class SupabaseJWTVerifier:
    """Verifies Supabase JWTs and extracts user information."""

    def __init__(self) -> None:
        self.jwt_secret = settings.SUPABASE_JWT_SECRET

        self.jwks_data: Optional[Dict[str, Any]] = None
        self.jwks_client = None

        base_url = settings.SUPABASE_URL.rstrip("/")
        self.jwks_url = f"{base_url}/auth/v1/.well-known/jwks.json"
        logger.info(f"JWKS URL set to: {self.jwks_url}")

        if not self.jwt_secret:
            logger.info("JWT secret missing; will rely on JWKS fallback")
            self._ensure_jwks(eager=True)
        else:
            logger.info("Using JWT secret for token verification")

    def _ensure_jwks(self, jwks_url: str = "", eager: bool = False) -> None:
        """Ensure JWKS data is loaded. Eager on init when no jwt_secret; lazy otherwise."""
        url = jwks_url or self.jwks_url

        if self.jwks_data and url == self.jwks_url:
            return

        headers: Dict[str, str] = {}
        if settings.SUPABASE_ANON_KEY:
            headers["apikey"] = settings.SUPABASE_ANON_KEY
            headers["Authorization"] = f"Bearer {settings.SUPABASE_ANON_KEY}"

        try:
            import httpx

            logger.info(f"Fetching JWKS from {url}")
            response = httpx.get(url, headers=headers, timeout=5.0)
            if response.status_code != 200:
                logger.warning(
                    f"JWKS endpoint returned {response.status_code}. Retrying without auth..."
                )
                response = httpx.get(url, timeout=5.0)

            if response.status_code == 200:
                self.jwks_data = response.json()
                self.jwks_client = None
                self.jwks_url = url
                logger.info(
                    f"Fetched JWKS with {len((self.jwks_data or {}).get('keys', []))} keys"
                )
            else:
                raise Exception(
                    f"JWKS endpoint not accessible: {response.status_code}. "
                    "Set SUPABASE_JWT_SECRET for direct verification."
                )
        except Exception as e:
            logger.error(f"Failed to fetch JWKS: {e}")
            if eager:
                logger.error(
                    "Add SUPABASE_JWT_SECRET to your .env file. "
                    "Find it in Supabase Dashboard > Project Settings > API > JWT Secret"
                )
            raise

    def verify_token(self, token: str) -> Dict[str, Any]:
        """
        Verify a Supabase JWT and return the decoded payload.

        Args:
            token: The JWT token to verify.

        Returns:
            Decoded JWT payload.

        Raises:
            AuthenticationError: If token is invalid or expired.
        """
        try:
            header = jwt.get_unverified_header(token)
            token_alg = header.get("alg")
            unverified_payload = jwt.decode(token, options={"verify_signature": False})

            if self.jwt_secret and token_alg == "HS256":
                payload = jwt.decode(
                    token,
                    self.jwt_secret,
                    algorithms=["HS256"],
                    audience="authenticated",
                    options={"verify_aud": True},
                )
            else:
                # JWKS fallback — also handles ES256
                iss = unverified_payload.get("iss")
                if iss:
                    derived_jwks = iss.rstrip("/") + "/.well-known/jwks.json"
                    if derived_jwks != self.jwks_url:
                        try:
                            self._ensure_jwks(jwks_url=derived_jwks)
                        except Exception:
                            pass

                if not self.jwks_data:
                    self._ensure_jwks()

                kid = header.get("kid")
                jwks = self.jwks_data if isinstance(self.jwks_data, dict) else {}
                keys = jwks.get("keys", [])
                matching_key = next(
                    (k for k in keys if isinstance(k, dict) and k.get("kid") == kid), None
                )

                if not matching_key:
                    raise AuthenticationError(f"No matching key found for kid: {kid}")

                from jwt.algorithms import ECAlgorithm, RSAAlgorithm

                alg = header.get("alg", "RS256")
                if alg.startswith("ES"):
                    public_key: Any = ECAlgorithm.from_jwk(json.dumps(matching_key))
                else:
                    public_key = RSAAlgorithm.from_jwk(json.dumps(matching_key))

                payload = jwt.decode(
                    token,
                    public_key,
                    algorithms=[alg, "RS256", "ES256"],
                    audience="authenticated",
                    options={"verify_aud": True},
                )

            return cast(Dict[str, Any], payload)

        except jwt.ExpiredSignatureError as e:
            logger.warning("Token has expired")
            raise AuthenticationError("Token has expired") from e
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {str(e)}")
            raise AuthenticationError("Invalid authentication token") from e
        except AuthenticationError:
            raise
        except Exception as e:
            error_msg = str(e)
            logger.error(f"Token verification failed: {error_msg}")
            if "401" in error_msg or "Unauthorized" in error_msg:
                raise AuthenticationError(
                    "JWT verification failed: Unable to fetch signing keys. "
                    "Check your Supabase configuration."
                ) from e
            raise AuthenticationError("Token verification failed") from e

    def get_user_id(self, token: str) -> str:
        """
        Extract user_id (sub claim) from a Supabase JWT.

        Args:
            token: The JWT token.

        Returns:
            User ID string.

        Raises:
            AuthenticationError: If token is invalid or missing sub claim.
        """
        payload = self.verify_token(token)
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Token missing user ID")
        return cast(str, user_id)

    def get_claims(self, token: str) -> Dict[str, Any]:
        """Return the full decoded JWT payload."""
        return self.verify_token(token)


_jwt_verifier: Optional[SupabaseJWTVerifier] = None


def get_jwt_verifier() -> SupabaseJWTVerifier:
    """Lazily instantiate the JWT verifier to avoid import-time failures."""
    global _jwt_verifier
    if _jwt_verifier is None:
        _jwt_verifier = SupabaseJWTVerifier()
    return _jwt_verifier
