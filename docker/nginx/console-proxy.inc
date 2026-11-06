# Shared by both console listeners: 9443, and 443 for mdm.tak-solutions.com (W100).
#
# ⚠️ **This file is the authentication boundary.** The app closes the door when
# X-Authentik-Username is absent and trusts it completely when present, so the
# whole guard is "only this proxy can set that header". Two things enforce it:
# the app is published on 127.0.0.1 only and is reachable by nothing but nginx,
# and `proxy_set_header` REPLACES a client's value rather than appending to it.
#
# ⚠️ **It exists as one file precisely because it is duplicated logic.** Two
# copies of these lines could drift, and the copy that got weakened would still
# look like a working console — a listener quietly trusting a header the client
# controls is the whole attack. One file cannot drift from itself.
#
# The empty-string assignments are belt and braces for the headers not otherwise
# set: an unset header nobody thought about is how this goes wrong.

proxy_pass       http://takmdm_api;
proxy_set_header Host              $host;
proxy_set_header X-Real-IP         $remote_addr;
proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto https;

# The identity the app will trust. $remote_user is set by auth_basic and cannot
# be influenced by the client.
proxy_set_header X-Authentik-Username $remote_user;
proxy_set_header X-Authentik-Name     $remote_user;
proxy_set_header X-Authentik-Groups   "takmdm-admins";
proxy_set_header X-Authentik-Email    "";

# Long-poll and big uploads.
proxy_read_timeout    330s;
proxy_send_timeout    330s;
proxy_request_buffering off;
