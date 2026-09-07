"""Check the provisioning QR describes this server and this agent.

Every one of these is a thing Android verifies and then reports only as
"Something went wrong", after a download and a factory reset.
"""
import json
import pathlib

from app.config import get_settings
from app.services import provisioning
from app.artifacts.apk import inspect_apk

settings = get_settings()
payload = provisioning.qr_payload(settings, secret="probe-only")

CHECKSUM = "android.app.extra.PROVISIONING_DEVICE_ADMIN_SIGNATURE_CHECKSUM"
DOWNLOAD = "android.app.extra.PROVISIONING_DEVICE_ADMIN_PACKAGE_DOWNLOAD_LOCATION"
COMPONENT = "android.app.extra.PROVISIONING_DEVICE_ADMIN_COMPONENT_NAME"

print("QR payload:")
for key in (COMPONENT, CHECKSUM, DOWNLOAD):
    print(f"  {key.rsplit('.', 1)[-1]:24} {payload[key]}")

# Fetched from the URL the QR itself names, so this tests the payload end to
# end rather than a file someone put here by hand.
import urllib.request

with urllib.request.urlopen(payload[DOWNLOAD], timeout=120) as response:
    served = inspect_apk(response.read())
print()
print("the APK that URL serves:")
print(f"  package                  {served.package_name} {served.version_code}")
print(f"  signing checksum         {served.provisioning_checksum}")

ok = True
if payload[CHECKSUM] != served.provisioning_checksum:
    print("\n  MISMATCH: the QR's checksum is not this APK's signing key")
    ok = False
component = payload[COMPONENT].split("/")[-1]
component = component if not component.startswith(".") else served.package_name + component
if component not in served.receivers:
    print(f"\n  MISMATCH: the APK declares no receiver {component}")
    ok = False

extras = provisioning.admin_extras(settings, "probe-only")
print()
print("what the agent is handed:")
print(f"  server_url               {extras['server_url']}")
print(f"  server_ca_pem            {'present' if extras.get('server_ca_pem') else 'ABSENT'}")

# The CA the agent is given has to be valid for the host it is told to call, or
# the first check-in fails TLS and provisioning reports the same opaque error.
host = extras["server_url"].split("//", 1)[1].split(":", 1)[0]
cert = extras.get("server_ca_pem", "")
if cert:
    from cryptography import x509

    parsed = x509.load_pem_x509_certificate(cert.encode())
    sans = parsed.extensions.get_extension_for_class(
        x509.SubjectAlternativeName
    ).value.get_values_for_type(x509.IPAddress)
    names = [str(s) for s in sans]
    print(f"  cert covers              {names}")
    if host not in names:
        print(f"\n  MISMATCH: the certificate does not cover {host}")
        ok = False

print()
print("QR is internally consistent" if ok else "QR WOULD FAIL ON DEVICE")
