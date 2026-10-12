# Network requirements

What the network around ATLAS has to allow, and the settings that break it without an obvious error. Share this page with whoever runs the firewall, gateway or load balancer in front of your ATLAS server.

## Inbound: what tablets and operators connect to

- **443 (HTTPS): the console**, in a browser. Ordinary HTTPS.
- **8449 (HTTPS): every managed tablet.** Pass it through as plain TCP/TLS, end to end. Tablets sign in with a client certificate, so nothing may decrypt, inspect or re-sign this traffic.
- **80 (HTTP): tablets during QR setup.** Serves the ATLAS app to a tablet being provisioned. Android's setup downloads it over plain HTTP.

## ⚠️ Timeouts on port 8449: at least 135 seconds, 180 recommended

Each tablet keeps one connection to ATLAS open for **up to 2 minutes** while it waits to hear about changes. That is how a policy reaches a tablet within seconds without the tablet polling constantly.

Any **gateway, load balancer, firewall or proxy** between the tablets and ATLAS must allow a connection on 8449 to stay open that long. Set its idle or connection timeout for 8449 to **at least 135 seconds; 180 is recommended.**

Tablets send a small keepalive every 25 seconds, which covers most idle timers. They cannot outlast a device that closes connections after a fixed time.

**What it looks like when the timeout is too short:** nothing fails outright. Tablets check in far more often than every 2 minutes (for example every 41 seconds behind a 20-second limit), and the tablet's own log shows *"wait failed: stream was reset: CANCEL"* just before each check-in. Battery and data use go up with it.

**A known case:** an **Azure Application Gateway** with a TCP listener for 8449 has a backend setting called **Time-out (seconds)**, which defaults to 20. Raise it to 180.

## Outbound: what the ATLAS server connects to

ATLAS fetches app catalogs, maps and downloads from the internet. If your network **inspects HTTPS** (Zscaler, Palo Alto, Fortinet or a similar product), exempt the ATLAS server from inspection. ATLAS checks every certificate against the public certificate authorities, so a re-signed connection is refused with *"certificate verify failed"*.

- **TAKWERX plugin catalog:** mapdepot.takwerx.org, github.com, objects.githubusercontent.com
- **TAK.gov plugin catalog:** tak.gov, auth.tak.gov
- **Third-party app repositories:** f-droid.org, apt.izzysoft.de, apkpure.com
- **Google Play imports:** play.google.com and Google's download servers
- **Maps and address search:** tile.openstreetmap.org, nominatim.openstreetmap.org, photon.komoot.io

Some downloads redirect to the provider's own download hosts, so exempting the ATLAS server as a whole is simpler than listing destinations.
