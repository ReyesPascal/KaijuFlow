# F-KF-SEC-001 — NNTP TLS peer certificate verification is disabled

| Field | Value |
| --- | --- |
| Finding ID | `F-KF-SEC-001` |
| Subsystem | `KF-S07`: NNTP article verification |
| Classification | `source-observed` |
| Review status | **Confirmed source fact; remediation and runtime effects untested** |
| Potential severity | **High** for sensitive NNTP credentials or traffic on an untrusted network; requires threat-model validation |
| Confidence in source fact | High |
| Source commit | `c83a3c733b6394eb140a1c0a1dc500010a9f22e5` |
| Source Git blob SHA | `270b6bb5d2c2df2ce2e29d2a8fc6549d7f314fac` |
| Evidence ID | `EV-KF-SEC-TLS-001` |
| First recorded | 2026-11-07 |

**Exact source anchor:** [src/health/nntpConnection.ts lines 27–30](https://github.com/ReyesPascal/KaijuFlow/blob/c83a3c733b6394eb140a1c0a1dc500010a9f22e5/src/health/nntpConnection.ts#L27-L30).

## Direct observation

The `connectToUsenet` function chooses the TLS path when `provider.useTLS` is true. Its `tls.connect` options include `rejectUnauthorized: false`, which tells Node's TLS client not to reject an untrusted server certificate. The call is in the original imported source, not introduced by KaijuFlow's audit branch.

This was independently re-read from the exact pinned source in GitHub. No production NNTP connection was attempted, no credentials were accessed, and no runtime interception/exploit was demonstrated.

## Impact (risk inference, not test result)

The source setting weakens peer authentication and can allow a machine-in-the-middle to impersonate an NNTP server when the rest of the connection permits it. The degree of practical risk depends on provider/network TLS posture and whether credentials are sent after connection. This audit does **not** claim actual exposure or a successful attack.

## Proposed isolated validation

Create a synthetic NNTP-like server with a self-signed certificate and fabricated credentials; assert current behavior in an isolated test, then separately test the proposed verification-enabled connection with provider-compatible trusted CA/certificate settings. Verify timeout, auth, and cleanup cases for both paths. Determine backwards compatibility and migration behavior before any source patch or production configuration change.

## Disposition and rollback

Keep the unchanged v1.4.1 import as the baseline. Track remediation in Phase B security work on a separate reviewed patch PR, with synthetic regression tests. No code changes, no deployments and no Brain production changes are authorized by this finding.
