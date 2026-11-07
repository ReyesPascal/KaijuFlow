# NNTP permanent reference

Source pin: `c83a3c733b6394eb140a1c0a1dc500010a9f22e5` (original v1.4.1 import). Every application source link below pins that commit; symbol names are navigation anchors. **Source-observed** means inspection, **tested** means the named bounded synthetic case executed, **proposed** means future work, and **unknown** means evidence is absent. Tested does not imply production verification. Evidence IDs use `test-observed` in JSONL for the same classification.

Evidence map: `EV-KF-REF-001` records this source review; `EV-KF-A4-CLOSURE-001` records the [closed A4 evidence](../../audit/A4-CLOSURE.md); `EV-KF-INT-001` records the separate [integration result](../../audit/INTEGRATION-DISCOVERY-STREAM.md). See [live validation gaps](../../audit/VALIDATION_GAPS.md). No production configurations or credentials were inspected.

## Index

- [Architecture, configuration, protocols and failure handling](ARCHITECTURE.md)
- [Executed evidence, limits, concerns and proposals](EVIDENCE_AND_PROPOSALS.md)
- [Separate performance comparison plan](../../performance/BENCHMARK_PLAN.md), tracked by [Issue #4](https://github.com/ReyesPascal/KaijuFlow/issues/4)

The existing NNTP code verifies availability and retrieves archive metadata. It is not evidence of a complete direct NNTP media-streaming engine: see N01–N13 and P01 below. NzbDAV remains the known-good delivery baseline. KaijuNNTP is a potential future engine boundary, not an implemented replacement established by this audit.
