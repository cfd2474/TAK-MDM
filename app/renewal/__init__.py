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

"""The renewal container (W458): short TAK enrollment passwords, against proof.

A TAK client certificate expires every two years, and stock TAK Server signs a
new one only for a username and password on 8446. TAK Portal's QR password is an
Authentik app password; this container makes the same kind, for ten minutes,
for the user named in the certificate the device already holds.

⚠️ **It runs apart from ATLAS's API on purpose.** It holds an Authentik
superuser token (Authentik lets only a superuser make a token for another
user), and it trusts nothing the API says about who a user is. The device signs
a challenge with the connection's private key; the certificate must chain to
the TAK root CA InfraTAK wrote beside the token; the username is that
certificate's CN. A compromised API therefore cannot get a login for a user
whose key it does not hold.

W461: nor does a certificate TAK Server has revoked get one. InfraTAK copies
TAK Server's revoked list and CRLs here, and without a fresh copy renewal is
refused (`revocation`).

Not imported by `app.main`: this package runs as its own process
(`uvicorn app.renewal.service:app`).
"""
