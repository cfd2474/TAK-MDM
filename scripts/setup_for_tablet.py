# Copyright 2026 TAK-Solutions LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Make the local server reachable from a tablet on the same Wi-Fi.

Three things have to line up before a device can talk to a server running on a
laptop, and each fails differently and confusingly:

1. The TLS certificate must list the PC's LAN address. The default dev certificate
   covers only ``localhost``, so a tablet gets a verification failure.
2. Windows Firewall must allow inbound 8443.
3. ``TAKMDM_SERVER_URL`` must be the LAN address, because that value is baked into
   enrollment QR codes — a tablet that reads "localhost" will try to phone itself.

This script handles 1 and 3, and prints the command for 2.

    python scripts/setup_for_tablet.py
"""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.cli import _write_dev_server_cert  # noqa: E402


def detect_lan_address() -> str | None:
    """Find the address this machine uses to reach the local network.

    Opening a UDP socket to a public address performs no traffic but makes the OS
    pick the outbound interface, which is the address a tablet on the same Wi-Fi
    can actually reach.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        probe.connect(("8.8.8.8", 80))
        return probe.getsockname()[0]
    except OSError:
        return None
    finally:
        probe.close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--address", help="LAN IP to use instead of auto-detecting")
    parser.add_argument("--pki-dir", default="pki")
    parser.add_argument("--port", type=int, default=8443)
    args = parser.parse_args(argv)

    address = args.address or detect_lan_address()
    if not address:
        print(
            "Could not work out this machine's network address.\n"
            "Find it with `ipconfig` (look for IPv4 Address) and re-run with\n"
            "  python scripts/setup_for_tablet.py --address 192.168.1.50",
            file=sys.stderr,
        )
        return 1

    pki_dir = Path(args.pki_dir)
    if not (pki_dir / "ca.crt").exists():
        print(
            f"No PKI found in {pki_dir}. Start the stack first:\n"
            "  docker compose up -d --build",
            file=sys.stderr,
        )
        return 1

    cert_path, _ = _write_dev_server_cert(pki_dir, address, extra_sans=[])
    base_url = f"https://{address}:{args.port}"

    managed = {
        "TAKMDM_SERVER_URL": base_url,
        # Used by docker-compose so a rebuilt PKI is valid for this address too.
        "TAKMDM_LAN_ADDRESS": address,
    }
    env_path = REPO_ROOT / ".env"
    lines = []
    if env_path.exists():
        lines = [
            line
            for line in env_path.read_text().splitlines()
            if not any(line.startswith(f"{key}=") for key in managed)
        ]
    lines.extend(f"{key}={value}" for key, value in managed.items())
    env_path.write_text("\n".join(line for line in lines if line.strip()) + "\n")

    print("Set up for tablet testing")
    print("=" * 46)
    print(f"  This PC on the network : {address}")
    print(f"  Server address         : {base_url}")
    print(f"  TLS certificate        : {cert_path}")
    print(f"  Wrote                  : {env_path}")
    print()
    print("Next, in order:")
    print()
    print("1. Allow the port through Windows Firewall.")
    print("   Open PowerShell AS ADMINISTRATOR and paste:")
    print()
    print(f'     New-NetFirewallRule -DisplayName "ATLAS {args.port}" '
          f"-Direction Inbound -LocalPort {args.port} -Protocol TCP -Action Allow")
    print()
    print("2. Restart the server so it picks up the new certificate and address.")
    print("   The proxy needs an explicit restart: it reads the certificate once")
    print("   at startup, and `up -d` will not restart it on its own.")
    print()
    print("     docker compose up -d")
    print("     docker compose restart proxy")
    print()
    print("3. On the tablet, connect to the SAME Wi-Fi as this PC, then open")
    print(f"   this in the tablet's browser:")
    print()
    print(f"     {base_url}/healthz")
    print()
    print('   You should see:  {"status":"ok"}')
    print("   A certificate warning is expected — this is a self-signed dev")
    print("   certificate. Tap Advanced, then Proceed.")
    print()
    print("   If the page does not load at all, the firewall rule in step 1 is")
    print("   the usual reason.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
