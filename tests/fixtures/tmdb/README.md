# TMDB replies

`movie-amelie.json`: TMDB's real replies to the two requests KaijuFlow makes for a film's name, runtime, premiere year and other names (`src/idResolver.ts`), taken on 2026-11-24 with the test copy's key through `tools/brain/pool.py`'s `tmdb_getter` (the key never in the file), as `{path: [status, JSON]}`: `/find/tt0211915?external_source=imdb_id` and `/movie/194?append_to_response=release_dates%2Calternative_titles` (Amélie, 2001). `tests/unit/tmdb-other-names.test.ts` answers KaijuFlow's TMDB requests with them. When TMDB changes its replies, capture new ones here.
