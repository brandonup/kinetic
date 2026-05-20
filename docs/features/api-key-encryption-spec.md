# API Key Encryption Spec

**Status:** Proposed
**Ticket:** KIN-230
**Author:** Gilfoyle
**Date:** 2026-03-22

---

## Context

Kinetic stores third-party LLM provider API keys (Anthropic, OpenAI, Google, Groq) per user. A compromised key can generate significant charges on the user's provider account. The PRD (§ Security) and `db-schema-spec.md` (§2) define the storage schema. This spec locks the remaining implementation decisions.

## Decisions

### 1. Python Library: `cryptography` (AESGCM)

**Choice:** `cryptography` library, specifically `cryptography.hazmat.primitives.ciphers.aead.AESGCM`.

**Why not Fernet:** Fernet uses AES-128-CBC, not AES-256-GCM. The PRD specifies AES-256-GCM. Using Fernet would require changing the encryption standard or accepting a weaker cipher.

**Why not PyNaCl:** PyNaCl wraps libsodium's `XSalsa20-Poly1305`, not AES-256-GCM. It's a fine cipher, but the PRD, db-schema-spec, and user-facing security statement all specify AES-256-GCM. Switching would create a spec mismatch.

**Package:** `cryptography>=42.0.0` (well-maintained, OpenSSL-backed, already a transitive dependency of most Python web stacks).

### 2. Key Derivation: HKDF Per-User from Master Secret

**Choice:** Derive a per-user encryption key from the master secret using HKDF-SHA256 with the user's `id` (UUID) as the `info` parameter.

```python
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives import hashes

def derive_user_key(master_key: bytes, user_id: str) -> bytes:
    """Derive a 256-bit per-user key from the master secret."""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,  # master_key is already high-entropy
        info=user_id.encode("utf-8"),
    )
    return hkdf.derive(master_key)
```

**Why per-user derivation over raw master key:**
- **Blast radius:** If a single user's derived key is somehow extracted from memory, it cannot decrypt any other user's keys.
- **No schema change:** The derived key is computed at runtime. Nothing changes in the database.
- **Rotation path:** Rotating the master key requires re-encrypting all keys (same as raw master key). Per-user derivation doesn't make rotation harder.

**Why not per-row salt:** Per-row salt stored in the DB adds a column and complexity. The GCM nonce already ensures ciphertext uniqueness per encryption. Per-user derivation via HKDF provides key isolation without additional storage.

### 3. Nonce Handling: 12-Byte Random, Fresh Per Encryption

```python
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt_api_key(plaintext_key: str, master_key: bytes, user_id: str) -> tuple[bytes, bytes]:
    """Returns (ciphertext, nonce)."""
    derived_key = derive_user_key(master_key, user_id)
    aesgcm = AESGCM(derived_key)
    nonce = os.urandom(12)  # 96-bit, standard for GCM
    ciphertext = aesgcm.encrypt(nonce, plaintext_key.encode("utf-8"), None)
    return ciphertext, nonce

def decrypt_api_key(ciphertext: bytes, nonce: bytes, master_key: bytes, user_id: str) -> str:
    """Returns plaintext key."""
    derived_key = derive_user_key(master_key, user_id)
    aesgcm = AESGCM(derived_key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
```

- Nonce stored in `key_nonce` column (bytea, 12 bytes).
- Fresh `os.urandom(12)` on every encrypt call (including key updates).
- No AAD (additional authenticated data) needed — the ciphertext is bound to the row via RLS, not via AAD.

### 4. Secrets Management: Environment Variable (MVP)

**Choice:** `API_KEY_ENCRYPTION_KEY` environment variable. 32-byte (256-bit) base64-encoded value.

**Generation:**
```bash
python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"
```

**Loading:**
```python
import base64, os

def load_master_key() -> bytes:
    raw = os.environ.get("API_KEY_ENCRYPTION_KEY")
    if not raw:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY not set")
    key = base64.b64decode(raw)
    if len(key) != 32:
        raise RuntimeError("API_KEY_ENCRYPTION_KEY must be 32 bytes")
    return key
```

**Migration path to secrets manager:**
1. `load_master_key()` is the single call site. Swap its implementation to read from Doppler/AWS Secrets Manager — zero changes to encryption logic.
2. Add a `KEY_SOURCE` env var (`env` | `doppler` | `aws_sm`) to select the backend. Default: `env`.
3. Cache the loaded key in memory for the process lifetime (secrets managers charge per read).

**Why env var for MVP:** Five users, single deployment. Secrets manager adds a service dependency, SDK, and IAM configuration. The migration is a one-function swap — no reason to pay the complexity cost now.

### 5. Logging Scrub: FastAPI Middleware

**Implementation:** A single middleware that intercepts request/response bodies and redacts sensitive fields before they reach the logger.

**Scrubbed field patterns:**
- `api_key` / `apiKey`
- `key_ciphertext` / `keyCiphertext`
- `key_nonce` / `keyNonce`
- Any field matching `*_key`, `*_secret`, `*_token` (glob pattern)
- Authorization headers

**Approach:**
```python
SCRUB_PATTERNS = re.compile(
    r"(api[_-]?key|key[_-]?ciphertext|key[_-]?nonce|"
    r"\w+[_-](?:key|secret|token)|authorization)",
    re.IGNORECASE,
)

def scrub_dict(d: dict) -> dict:
    """Recursively replace sensitive values with '[REDACTED]'."""
    return {
        k: "[REDACTED]" if SCRUB_PATTERNS.search(k) else
           scrub_dict(v) if isinstance(v, dict) else v
        for k, v in d.items()
    }
```

**Where it runs:** As FastAPI middleware, wrapping the request/response cycle. Applied globally — not per-router. Individual endpoints do not need to remember to scrub.

**What about Supabase logs:** Supabase server-side logs are outside our control. The `key_ciphertext` column is bytea (not human-readable), and RLS prevents cross-user access. Supabase audit logs may record SQL statements — but since we never pass plaintext keys in SQL (we encrypt before the query), this is safe.

### 6. Key Masking Format

**Format:** First 7 characters + `...` + last 4 characters.

**Examples:**
| Provider | Raw key | Masked |
|---|---|---|
| Anthropic | `sk-ant-api03-abc...xyz` | `sk-ant-...xyz` → `sk-ant-...bcXy` |
| OpenAI | `sk-proj-abc123...def456` | `sk-proj...f456` |
| Google | `AIzaSyB...9xQ` | `AIzaSyB...9xQ` |

**Edge case:** If the key is shorter than 12 characters (unlikely for real provider keys), mask everything: `***...***`.

**Implementation:**
```python
def mask_api_key(key: str) -> str:
    if len(key) < 12:
        return "***...***"
    return f"{key[:7]}...{key[-4:]}"
```

**When masking is applied:** Server-side, in the API response serializer. The `key_hint` column stores the masked value at write time so the frontend never needs the plaintext for display.

---

## Encryption Flow Summary

### Save (POST/PUT)

1. User submits plaintext key via HTTPS.
2. **Validate:** Lightweight test call to the provider API. Reject if invalid.
3. **Mask:** Generate `key_hint` from plaintext.
4. **Encrypt:** HKDF-derive per-user key → AES-256-GCM encrypt → get `(ciphertext, nonce)`.
5. **Store:** Write `key_ciphertext`, `key_nonce`, `key_hint`, `validated_at` to `user_api_keys`.
6. **Discard:** Plaintext key leaves memory (no caching, no logging).
7. **Return:** `key_hint` + `provider` + `validated_at` only.

### Use (generation call)

1. Load `key_ciphertext` + `key_nonce` from DB (RLS-scoped to authenticated user).
2. **Decrypt:** HKDF-derive per-user key → AES-256-GCM decrypt → plaintext key in memory.
3. Pass plaintext key to LiteLLM for the generation call.
4. **Discard:** Plaintext key leaves memory after the call completes.

### Delete

1. User requests deletion via API.
2. Hard-delete the row from `user_api_keys`. Ciphertext is permanently gone.
3. No soft-delete — there's no recovery use case for encrypted credentials.

---

## Risks

1. **Master key loss:** If `API_KEY_ENCRYPTION_KEY` is lost, all stored keys become unrecoverable. Users must re-enter their keys. **Mitigation:** Document the key in a secure backup (password manager, not the repo).
2. **Master key compromise:** All user keys are derivable. **Mitigation:** Per-user HKDF derivation means the attacker also needs the user's UUID to derive each key — but UUIDs are not secret. The real mitigation is protecting the env var (deploy config, not source control).
3. **Memory exposure:** Plaintext keys exist in server memory during API calls. **Mitigation:** This is inherent to any system that uses keys on behalf of users. Keep the window short — decrypt, use, discard. No caching.

## Alternatives Considered

| Alternative | Why rejected |
|---|---|
| Fernet (`cryptography.fernet`) | Uses AES-128-CBC, not AES-256-GCM per PRD spec |
| PyNaCl / libsodium | XSalsa20-Poly1305, not AES-256-GCM — spec mismatch |
| Raw master key (no per-user derivation) | Works, but one extracted key decrypts all users. HKDF adds one function call and zero storage |
| Per-row salt column | Adds DB column. GCM nonce + HKDF already ensure ciphertext uniqueness and key isolation |
| Vault / Doppler / AWS SM for MVP | Adds service dependency for 5 users. One-function migration path makes deferral cheap |
| Envelope encryption (AWS KMS wrapping) | Overkill for MVP scale. Consider if Kinetic moves to multi-tenant enterprise |
