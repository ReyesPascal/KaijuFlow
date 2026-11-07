# NzbDAV permanent reference

Source pin: `c83a3c733b6394eb140a1c0a1dc500010a9f22e5` (original v1.4.1 import). Every application source link below pins this commit and names the relevant symbol. **Source-observed** means inspected code; **tested** means only the named synthetic case executed; **proposed** means future work; **unknown** means missing evidence. JSONL uses `test-observed` for tested results. No production configuration, credentials, private NZBs or Brain services were accessed.

Evidence: `EV-KF-REF-001` for this source review; `EV-KF-A4-CLOSURE-001` for [A4 closure](../../audit/A4-CLOSURE.md); `EV-KF-INT-001` for [the separate integration](../../audit/INTEGRATION-DISCOVERY-STREAM.md). See [live-validation gaps](../../audit/VALIDATION_GAPS.md).

## Index

- [Architecture, APIs, delivery, caches and security](ARCHITECTURE.md)
- [Executed evidence, unresolved behavior and proposals](EVIDENCE_AND_PROPOSALS.md)
- [Separate performance milestone plan](../../performance/BENCHMARK_PLAN.md), [Issue #4](https://github.com/ReyesPascal/KaijuFlow/issues/4)
- [NNTP architecture and verification reference](../nntp/README.md)

NzbDAV remains the known-good delivery solution under the project decision recorded in Issue #2. This audit demonstrates bounded synthetic interactions with fake services; it does not independently establish real NzbDAV processing speed or original-quality 4K playback performance. Direct/hybrid NNTP is a potential comparison candidate, not a replacement approved by this reference.
