"""
Cross-language crypto test vector generator — KIN-428 (CS.1–CS.5).

Generates deterministic test vectors from Python (the source of truth)
for validation by the Deno crypto port.

Run: python generate_test_vectors.py > vectors.json

Prerequisites: pip install cryptography
"""

import base64
import json

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

# Fixed inputs — deterministic, not real secrets
MASTER_KEY = base64.b64decode("dGVzdC1tYXN0ZXIta2V5LTMyLWJ5dGVzIQ==")  # 32 bytes
USER_ID = "550e8400-e29b-41d4-a716-446655440000"
PLAINTEXT = "sk-test-1234567890abcdef"
NONCE = bytes.fromhex("aabbccddeeff00112233aabb")  # fixed 12-byte nonce

# Derive key (HKDF-SHA256, salt=None = 32 zero bytes per RFC 5869 §2.2)
hkdf = HKDF(
    algorithm=hashes.SHA256(),
    length=32,
    salt=None,
    info=USER_ID.encode("utf-8"),
)
derived_key = hkdf.derive(MASTER_KEY)

# Encrypt (AES-256-GCM, no AAD)
aesgcm = AESGCM(derived_key)
ciphertext = aesgcm.encrypt(NONCE, PLAINTEXT.encode("utf-8"), None)

# Also generate the bytea format that Supabase would return
bytea_ciphertext = "\\x" + ciphertext.hex()
bytea_nonce = "\\x" + NONCE.hex()

vectors = {
    "description": "KIN-428 cross-language crypto test vectors",
    "master_key_b64": base64.b64encode(MASTER_KEY).decode(),
    "user_id": USER_ID,
    "plaintext": PLAINTEXT,
    "nonce_hex": NONCE.hex(),
    "derived_key_hex": derived_key.hex(),
    "ciphertext_hex": ciphertext.hex(),
    "bytea_ciphertext": bytea_ciphertext,
    "bytea_nonce": bytea_nonce,
}

print(json.dumps(vectors, indent=2))
