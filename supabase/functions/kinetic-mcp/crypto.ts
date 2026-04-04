/**
 * BYOK Crypto Module — KIN-428.
 *
 * Port of Python encryption.py + user_keys.py to Deno Web Crypto API.
 * HKDF-SHA256 key derivation + AES-256-GCM decryption.
 *
 * Critical: Python's HKDF(salt=None) = 32 zero bytes (RFC 5869 §2.2).
 * See docs/spike-crypto-port-deno.md for full compatibility analysis.
 *
 * Source: packages/api/app/services/encryption.py
 * Schema ref: db-schema-spec.md §2 (user_api_keys: key_ciphertext, key_nonce)
 */

const HASH_LEN = 32; // SHA-256 output length in bytes

/**
 * Load master key from base64-encoded environment variable.
 *
 * Matches Python: load_master_key() in encryption.py
 * Key must be exactly 32 bytes after base64 decode.
 */
export function loadMasterKey(): Uint8Array {
  const raw = Deno.env.get("API_KEY_ENCRYPTION_KEY");
  if (!raw) {
    throw new Error(
      "API_KEY_ENCRYPTION_KEY not set. " +
      'Generate with: python -c "import os, base64; print(base64.b64encode(os.urandom(32)).decode())"'
    );
  }

  const decoded = Uint8Array.from(atob(raw), (c) => c.charCodeAt(0));
  if (decoded.length !== 32) {
    throw new Error(
      `API_KEY_ENCRYPTION_KEY must be 32 bytes after base64 decode, got ${decoded.length}`
    );
  }
  return decoded;
}

/**
 * Derive a per-user 256-bit key using HKDF-SHA256.
 *
 * Matches Python: derive_user_key(master_key, user_id) in encryption.py
 *
 * HKDF params:
 *   - hash: SHA-256
 *   - salt: 32 zero bytes (Python salt=None → RFC 5869 §2.2)
 *   - info: user_id encoded as UTF-8
 *   - output: 32 bytes (256 bits)
 */
export async function deriveUserKey(
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
 * Derive raw key bits for test vector comparison.
 *
 * Same as deriveUserKey but returns exportable bytes instead of CryptoKey.
 * Used only by test-vectors/validate_test_vectors.ts.
 */
export async function deriveUserKeyBits(
  masterKey: Uint8Array,
  userId: string
): Promise<Uint8Array> {
  const keyMaterial = await crypto.subtle.importKey(
    "raw",
    masterKey,
    "HKDF",
    false,
    ["deriveBits"]
  );

  const bits = await crypto.subtle.deriveBits(
    {
      name: "HKDF",
      hash: "SHA-256",
      salt: new Uint8Array(HASH_LEN),
      info: new TextEncoder().encode(userId),
    },
    keyMaterial,
    256 // 32 bytes
  );

  return new Uint8Array(bits);
}

/**
 * Decrypt a BYOK API key encrypted by the Python backend.
 *
 * Matches Python: decrypt_api_key(ciphertext, nonce, master_key, user_id) in encryption.py
 *
 * AES-256-GCM params:
 *   - nonce (iv): 12 bytes
 *   - no AAD (additionalData omitted — matches Python AAD=None)
 *   - ciphertext includes appended GCM tag (last 16 bytes)
 */
export async function decryptApiKey(
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
 * Supabase/PostgREST returns bytea columns as '\x'-prefixed hex strings.
 * Matches Python: to_bytes() in user_keys.py
 *
 * Handles:
 *   - '\x'-prefixed hex (standard PostgREST format)
 *   - Plain hex string (safety fallback)
 */
export function byteaToUint8Array(val: string): Uint8Array {
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

/**
 * Convert Uint8Array to hex string.
 * Used by test vectors for comparison.
 */
export function bytesToHex(bytes: Uint8Array): string {
  return Array.from(bytes)
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}
