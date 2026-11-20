# KaijuFlow streams only through Backends

KaijuFlow never reads video from Usenet itself: it finds and checks Sources, then hands the chosen one to a Backend (NzbDAV, AltMount, InfiniDysk) that prepares it and serves the file. The earlier idea of a built-in NNTP streamer (KaijuNNTP, roadmap phase E) is dropped, because NzbDAV and Usenet Ultimate are unmaintained and the priority is supporting maintained Backends, not owning a streaming engine.

## Consequences

- Each supported Backend must reach Parity with NzbDAV before it counts as supported.
- Exactly one Backend is active at a time, chosen in settings; running several at once with fallback between them is a later idea, not a requirement.

**Amended 2026-11-20** (spec #183, #188). AltMount is KaijuFlow's only Backend: NzbDAV, its settings and its features were removed in #188, InfiniDysk was never built, and there is no Backend choice in settings (an old config naming NzbDAV is read as AltMount). The decision itself stands: KaijuFlow never reads video from Usenet itself and streams through the Backend slot (`src/backends/`). Parity is now measured against the fake AltMount (`tests/integration/parity/`), not against NzbDAV; a second Backend would come back through the same slot and reach Parity there first.
