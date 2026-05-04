from __future__ import annotations

import base64
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey


def load_private_key(pem_string: str) -> RSAPrivateKey:
    return serialization.load_pem_private_key(pem_string.encode(), password=None)


def sign_request(key: RSAPrivateKey, *, timestamp_ms: str, method: str, path: str) -> str:
    msg = f"{timestamp_ms}{method}{path}".encode()
    signature = key.sign(msg, padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.DIGEST_LENGTH,
    ), hashes.SHA256())
    return base64.b64encode(signature).decode()
