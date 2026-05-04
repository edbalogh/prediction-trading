import base64
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes, serialization

from adapters.kalshi.http.auth import sign_request, load_private_key


def _make_test_key() -> tuple[bytes, bytes]:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.TraditionalOpenSSL,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_key = private_key.public_key()
    return private_pem, public_key


def test_sign_request_returns_base64_string():
    private_pem, _ = _make_test_key()
    key = load_private_key(private_pem.decode())
    signature = sign_request(key, timestamp_ms="1234567890000", method="GET", path="/markets/KXBTC15M")
    decoded = base64.b64decode(signature)
    assert len(decoded) == 256  # RSA-2048 produces 256-byte signatures


def test_sign_request_is_verifiable():
    private_pem, public_key = _make_test_key()
    key = load_private_key(private_pem.decode())
    timestamp_ms = "1234567890000"
    method = "POST"
    path = "/portfolio/orders"
    signature = sign_request(key, timestamp_ms=timestamp_ms, method=method, path=path)
    msg = f"{timestamp_ms}{method}{path}".encode()
    public_key.verify(base64.b64decode(signature), msg, padding.PSS(
        mgf=padding.MGF1(hashes.SHA256()),
        salt_length=padding.PSS.DIGEST_LENGTH,
    ), hashes.SHA256())  # raises if invalid


def test_load_private_key_from_pem_string():
    private_pem, _ = _make_test_key()
    key = load_private_key(private_pem.decode())
    assert key is not None
