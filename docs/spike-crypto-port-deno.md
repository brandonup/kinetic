# Spike: HKDF + AES-256-GCM Crypto Port (Python → Deno)

**Author:** Gilfoyle
**Date:** 2026-03-29
**Status:** Complete
**Ticket:** (pre-implementation spike — no ticket)
**Related:** ADR-008, `docs/specs/remote-mcp-server-spec.md`

---

## Question

Can Kinetic's BYOK key decryption (HKDF-SHA256 key derivation + AES-256-GCM decryption) be ported from Python (`cryptography` library) to Deno (Web Crypto API) with bit-exact output?

## Why This Matters

The remote MCP server (Supabase Edge Function, Deno runtime) must decrypt user API keys stored in `user_api_keys.key_ciphertext`. These were encrypted by the Python backend. If the Deno implementation produces different derived keys, every BYOK-dependent tool fails silently — no embeddings, no framework selection, no KB search.

## Source Implementation (Python)

**File:** `packages/api/app/services/encryption.py`

```python
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

def derive_user_key(master_key: bytes, user_id: str) -> bytes:
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,        # <-- critical: None = zero-filled salt of hash length
        info=user_id.encode("utf-8"),
    )
    return hkdf.derive(master_key)

def decrypt_api_key(ciphertext: bytes, nonce: bytes, master_key: bytes, user_id: str) -> str:
    derived_key = derive_user_key(master_key, user_id)
    aesgcm = AESGCM(derived_key)
    return aesgcm.decrypt(nonce, ciphertext, None).decode("utf-8")
```

**Key parameters:**
- HKDF: SHA-256, salt=None, info=user_id (UTF-8), output=32 bytes
- AES-256-GCM: 12-byte nonce, no AAD (associated authenticated data = None)
- Master key: 32 bytes, loaded from base64-encoded env var

## Compatibility Risk: `salt=None`

This is the #1 risk. Python's `cryptography` library interprets `salt=None` as **a zero-filled byte string of length equal to the hash output** (32 bytes for SHA-256). From the [RFC 5869](https://tools.ietf.org/html/rfc5869) spec:

> If not provided, [salt] is set to a string of HashLen zeros.

Deno's Web Crypto HKDF requires an explicit `salt` parameter in `deriveKey()` / `deriveBits()`. Passing an empty `ArrayBuffer` (0 bytes) is **not the same** as passing 32 zero bytes. The correct Deno equivalent:

```typescript
// CORRECT — matches Python's salt=None
const salt = new Uint8Array(32); // 32 zero bytes (SHA-256 hash length)

// WRONG — empty salt, different HKDF output
const salt = new Uint8Array(0);
```

## Target Implementation (Deno / Web Crypto)

```typescript
// crypto.ts — for Supabase Edge Function

const HASH_LEN = 32; // SHA-256 output length

/**
 * Load master key from base64-encoded environment variable.
 */
function loadMasterKey(): Uint8Array {
  const raw = Deno.env.get("API_KEY_ENCRYPTION_KEY");
  if (!raw) throw new Error("API_KEY_ENCRYPTION_KEY not set");

  const decoded = Uint8Array.from(atob(raw), (c) => c.charCodeAt(0));
  if (decoded.length !== 32) {
    throw new Error(`Master key must be 32 bytes, got ${decoded.length}`);
  }
  return decoded;
}

/**
 * Derive a per-user 256-bit key using HKDF-SHA256.
 *
 * Matches Python: HKDF(algorithm=SHA256, length=32, salt=None, info=user_id)
 * Python salt=None = 32 zero bytes (RFC 5869 §2.2).
 */
async function deriveUserKey(
  masterKey: Uint8Array,
  userId: string
): Promise<CryptoKey> {
  // Import the master key as HKDF key material
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    masterKey,
    "HKDF",
    false,
    ["deriveKey"]
  );

  // Derive the per-user AES-GCM key
  return crypto.subtle.deriveKey(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: new Uint8Array(HASH_LEN), // 32 zero bytes — matches Python salt=None
      info: new TextEncoder().encode(userId),
    },
    keyMaterial,
    { name: "AES-GCM", length: 256 },
    false,
    ["decrypt"]
  );
}

/**
 * Decrypt a BYOK API key encrypted by the Python backend.
 *
 * Matches Python: AESGCM(derived_key).decrypt(nonce, ciphertext, None)
 */
async function decryptApiKey(
  ciphertext: Uint8Array,
  nonce: Uint8Array,
  masterKey: Uint8Array,
  userId: string
): Promise<string> {
  const key = await deriveUserKey(masterKey, userId);

  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: nonce }, // no additionalData — matches Python AAD=None
    key,
    ciphertext
  );

  return new TextDecoder().decode(plaintext);
}

/**
 * Convert Supabase bytea hex string to Uint8Array.
 *
 * Supabase/PostgREST returns bytea as '\x'-prefixed hex strings.
 * Matches Python: user_keys.py to_bytes()
 */
function byteaToUint8Array(val: string): Uint8Array {
  let hex = val;
  if (hex.startsWith("\\x")) {
    hex = hex.slice(2);
  }
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) {
    bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  }
  return bytes;
}

export { loadMasterKey, deriveUserKey, decryptApiKey, byteaToUint8Array };
```

## Test Vector Protocol

Before integrating into the Edge Function, validate cross-language compatibility with a deterministic test.

### Step 1: Generate test vectors from Python (the source of truth)

```python
# generate_test_vectors.py
import base64, json, os
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Fixed inputs (deterministic)
master_key = base64.b64decode("dGVzdC1tYXN0ZXIta2V5LTMyLWJ5dGVzIQ==")  # 32 bytes
user_id = "550e8400-e29b-41d4-a716-446655440000"
plaintext = "sk-test-1234567890abcdef"
nonce = bytes.fromhex("aabbccddeeff00112233aabb")  # fixed 12-byte nonce

# Derive key
hkdf = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=user_id.encode())
derived_key = hkdf.derive(master_key)

# Encrypt
aesgcm = AESGCM(derived_key)
ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)

print(json.dumps({
    "master_key_b64": base64.b64encode(master_key).decode(),
    "user_id": user_id,
    "plaintext": plaintext,
    "nonce_hex": nonce.hex(),
    "derived_key_hex": derived_key.hex(),
    "ciphertext_hex": ciphertext.hex(),
}, indent=2))
```

### Step 2: Validate in Deno

```typescript
// validate_test_vectors.ts
// Run: deno run validate_test_vectors.ts

const vectors = {
  // Paste output from Python script here
  master_key_b64: "...",
  user_id: "550e8400-e29b-41d4-a716-446655440000",
  plaintext: "sk-test-1234567890abcdef",
  nonce_hex: "aabbccddeeff00112233aabb",
  derived_key_hex: "...",
  ciphertext_hex: "...",
};

// Decode inputs
const masterKey = Uint8Array.from(atob(vectors.master_key_b64), c => c.charCodeAt(0));
const nonce = hexToBytes(vectors.nonce_hex);
const ciphertext = hexToBytes(vectors.ciphertext_hex);

// Derive key (export-capable for comparison)
const keyMaterial = await crypto.subtle.importKey("raw", masterKey, "HKDF", false, ["deriveBits"]);
const derivedBits = await crypto.subtle.deriveBits(
  {
    name: "HKDF",
    hash: "SHA-256",
    salt: new Uint8Array(32),
    info: new TextEncoder().encode(vectors.user_id),
  },
  keyMaterial,
  256
);
const derivedHex = bytesToHex(new Uint8Array(derivedBits));

console.log("Derived key match:", derivedHex === vectors.derived_key_hex);

// Decrypt
const key = await crypto.subtle.importKey("raw", new Uint8Array(derivedBits), "AES-GCM", false, ["decrypt"]);
const decrypted = await crypto.subtle.decrypt({ name: "AES-GCM", iv: nonce }, key, ciphertext);
const result = new TextDecoder().decode(decrypted);

console.log("Decrypt match:", result === vectors.plaintext);
console.log("Decrypted value:", result);

function hexToBytes(hex: string): Uint8Array {
  const bytes = new Uint8Array(hex.length / 2);
  for (let i = 0; i < hex.length; i += 2) bytes[i / 2] = parseInt(hex.substring(i, i + 2), 16);
  return bytes;
}
function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes).map(b => b.toString(16).padStart(2, "0")).join("");
}
```

### Step 3: Pass/fail criteria

| Check | Expected |
|---|---|
| `derived_key_hex` matches Python output | Must match exactly |
| `decryptApiKey()` returns original plaintext | Must match exactly |
| `byteaToUint8Array("\\xaabb...")` parses correctly | Must match raw bytes |

**If derived key doesn't match:** The salt handling is wrong. Try `new Uint8Array(0)` as an alternative (some HKDF implementations treat empty salt differently). If neither works, the port is blocked — fall back to proxying decryption through the FastAPI backend.

## Findings

### 1. Port is feasible — Web Crypto API supports all required primitives

- `crypto.subtle.deriveKey()` supports HKDF with SHA-256 ✓
- `crypto.subtle.decrypt()` supports AES-256-GCM ✓
- Deno runtime includes Web Crypto natively (no npm packages needed) ✓

### 2. The `salt=None` → 32-zero-bytes mapping is the critical compatibility point

This is documented in RFC 5869 and Python's `cryptography` library source code. The Deno implementation must use `new Uint8Array(32)`, not `new Uint8Array(0)`. Getting this wrong produces a valid but different derived key — decryption silently fails with an `InvalidTag` error (AES-GCM authentication failure).

### 3. `bytea` format handling needs exact port

Supabase returns `bytea` as `\x`-prefixed hex strings via PostgREST. The Python `to_bytes()` helper handles three formats: raw bytes, `\x`-prefixed hex, and plain hex. The Deno port only needs to handle `\x`-prefixed hex (Edge Function always goes through PostgREST), but should handle plain hex as a safety measure.

### 4. No AAD (additional authenticated data) simplifies the port

Python passes `None` for AAD. Web Crypto's `decrypt()` omits the `additionalData` field when not used. No compatibility concern here.

### 5. AES-GCM tag is appended to ciphertext in Python's `cryptography` library

Python's `AESGCM.encrypt()` returns `ciphertext || tag` (tag appended). Web Crypto's `decrypt()` expects the same format — the tag is the last 16 bytes of the input. No splitting or rearranging needed.

## Recommendation

**Proceed with the Deno port.** All primitives are available. The only real risk is the HKDF salt handling, which is well-documented and testable.

**Implementation order:**
1. Run `generate_test_vectors.py` to get deterministic test values
2. Run `validate_test_vectors.ts` in Deno to confirm bit-exact match
3. If vectors match: integrate `crypto.ts` into the Edge Function
4. If vectors don't match: investigate salt handling, try alternatives, report back before proceeding

**Fallback if port fails:** Proxy decryption through a thin FastAPI endpoint (`POST /internal/decrypt-key`) that accepts `user_id` + `provider` and returns the plaintext key. This adds ~100ms latency per embedding call but unblocks the project. The endpoint must be internal-only (not exposed to the internet — use Supabase service role auth or a shared secret).

## Files Produced

| File | Purpose |
|---|---|
| `docs/spike-crypto-port-deno.md` | This spike report |
| (to be created by Dinesh) `kinetic-brain/supabase/functions/kinetic-mcp/crypto.ts` | Production crypto module |
| (to be created by Dinesh) `kinetic-brain/supabase/functions/kinetic-mcp/test-vectors/` | Cross-language validation scripts |
