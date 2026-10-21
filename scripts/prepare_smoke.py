"""Generate local-only TLS smoke credentials without replacing existing files."""
from pathlib import Path
from datetime import datetime, timedelta, timezone
from ipaddress import ip_address
import secrets
from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa

root = Path(__file__).resolve().parent.parent
env = root / ".env.production"
if not env.exists():
    text = (root / ".env.production.example").read_text()
    replacements = {
        "replace-with-an-independent-strong-random-secret-at-least-50-characters": secrets.token_urlsafe(60),
        "replace-with-a-random-database-secret": secrets.token_urlsafe(32),
        "replace-with-a-random-url-safe-redis-secret": secrets.token_urlsafe(32),
        "https://shop.example.com": "https://127.0.0.1:8443",
        "DJANGO_ALLOWED_HOSTS=shop.example.com": "DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    env.write_text(text, encoding="utf-8")
folder = root / "deploy" / "certs"
folder.mkdir(parents=True, exist_ok=True)
if not (folder / "privkey.pem").exists() and not (folder / "fullchain.pem").exists():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost smoke test")])
    now = datetime.now(timezone.utc)
    cert = x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key()).serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1)).not_valid_after(now+timedelta(days=2)).add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip_address("127.0.0.1")), x509.DNSName("localhost")]), critical=False).sign(key, hashes.SHA256())
    (folder / "privkey.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
    (folder / "fullchain.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
print("Local-only smoke environment prepared. No production credentials generated or printed.")
