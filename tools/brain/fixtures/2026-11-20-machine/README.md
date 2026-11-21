Captured on Brain on 2026-11-20 for the preflight's machine readers (#217, `test_preflight.py` `MachineReadersTest`):

- `ip-addr.json`: `ip -j addr show`, the interfaces' hardware addresses replaced by `02:00:00:00:00:0N`.
- `dig-newshosting.txt`: `dig +short +time=3 +tries=1 news.newshosting.com @192.168.4.1`, a good answer (CNAMEs, then addresses).
