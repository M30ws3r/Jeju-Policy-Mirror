"""로컬/센터 PC 용 자체 서명 TLS 인증서 생성 (localhost, 127.0.0.1). 운영 배포에서는 플랫폼이 발급하는 인증서를 쓴다.

사용: python scripts/gen_dev_cert.py   →  certs/localhost.pem, certs/localhost-key.pem
"""
import datetime
import ipaddress
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

out = Path(__file__).resolve().parent.parent / "certs"
out.mkdir(exist_ok=True)
key = ec.generate_private_key(ec.SECP256R1())
name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
now = datetime.datetime.now(datetime.timezone.utc)
cert = (
    x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
    .serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(minutes=5))
    .not_valid_after(now + datetime.timedelta(days=365))
    .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost"),
                                                x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
    .sign(key, hashes.SHA256())
)
(out / "localhost-key.pem").write_bytes(key.private_bytes(serialization.Encoding.PEM,
                                                           serialization.PrivateFormat.PKCS8,
                                                           serialization.NoEncryption()))
(out / "localhost.pem").write_bytes(cert.public_bytes(serialization.Encoding.PEM))
print(f"생성 완료: {out}")
