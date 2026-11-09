# KaijuFlow streams only through Backends

KaijuFlow never reads video from Usenet itself: it finds and checks Sources, then hands the chosen one to a Backend (NzbDAV, AltMount, InfiniDysk) that prepares it and serves the file. The earlier idea of a built-in NNTP streamer (KaijuNNTP, roadmap phase E) is dropped, because NzbDAV and Usenet Ultimate are unmaintained and the priority is supporting maintained Backends, not owning a streaming engine.

## Consequences

- Each supported Backend must reach Parity with NzbDAV before it counts as supported.
- Exactly one Backend is active at a time, chosen in settings; running several at once with fallback between them is a later idea, not a requirement.
