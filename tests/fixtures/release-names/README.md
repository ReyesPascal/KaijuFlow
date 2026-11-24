# The shared release-name table (#282, spec #279)

`table.tsv`: real release names, each with the title it is matched against and the answers the name rules give it. Both copies of Search Flow's strict rule read it, so they cannot drift: KaijuFlow's (`src/parsers/searchFlow.ts`, `tests/unit/search-flow.test.ts`) and the quick check's (`tools/brain/quickcheck.py`, `right_title`; `tools/brain/test_quickcheck.py`). A change to either rule that changes an answer here must change the other copy too.

Tab-separated, one header line, then one row per release and title:

| Column | What it holds |
|---|---|
| `release` | The release name as the indexer sent it. |
| `type` | `movie` or `series`. |
| `label` | The title as the quick check's draw names it: a film's name, or a show's name and `S01E02`. |
| `date` | A film's release date, or an episode's air date (YYYY-MM-DD). |
| `other` | The title's other names (TMDB's), `\|`-separated; empty when none is needed. |
| `right` | `yes` when the release really is that title, `no` when it is another (judged by hand from the name). |
| `strict` | The strict rule's answer: `pass`, or its why. Both copies must give it word for word. |
| `loose` | The loose rule's answer (KaijuFlow's inherited `isTextSearchMatch`): `keep` or `drop`. KaijuFlow only. |

A row with `right` `yes`, `strict` not `pass` and `loose` `keep` is an obscure real release: Search Flow keeps it as a maybe, never drops it.

Where the names come from, all taken on 2026-11-24, holding no key or login:
- The first 38 rows: the names of `tools/brain/fixtures/2026-11-24-release-names/names.txt` (#278's right-title tests), with the titles those tests match them against.
- The next 19: the release names of `film-tags.tsv` in the same folder not already above, with their film.
- The last 10: names from the store's recordings (`~/kaijuflow-test/store/<list>/*/*.body`, gathered in `~/kaijuflow-notes/diagnosis/briefs/recorded-release-names.txt`) of right films the strict rule does not pass (a German title around the name, `CE`, `SD`, `Remuxed`, `AKA`, a year after the video tags) and of wrong films that contain the name (a sequel, a film of the same name from another year).

New rows go at the end. A maybe that played the right title (#286) adds its release here with the word it offers.
