Captured on Brain on 2026-11-20 for the preflight's machine readers (#217, `test_preflight.py` `MachineReadersTest`, `MachineWiringTest`):

- `ip-addr.json`: `ip -j addr show`, scrubbed: the interfaces' hardware addresses replaced by `02:00:00:00:00:0N`, the Wi-Fi interface's altname (named after its hardware address) by `wlx020000000001`, and the link-local IPv6 addresses made from a hardware address (`…ff:fe…`) by `fe80::ff:fe00:N`.
- `dig-newshosting.txt`: `dig +short +time=3 +tries=2 news.newshosting.com @192.168.4.1` (what `brainrun.read_dns` runs), a good answer (CNAMEs, then addresses).
- `dig-unreachable.txt`: the same lookup at `192.0.2.1`, a documentation address no server answers on; dig printed this and exited with code 9.
