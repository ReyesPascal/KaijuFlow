# How mature teams diagnose failures and learn from them

Research date: 2026-11-24. Planning evidence for a KaijuFlow diagnosis system. Nothing here was run against KaijuFlow; no product or tool changes.

**What this answers.** The owner wants every fail, check miss, fallback and slow play from a [Real-use check](../../../GLOSSARY.md) diagnosed the same way every time, with a growing **casebook** of known causes. Each cause must be proved each time, even when it matches a casebook entry. This note collects what published practice says about each part of that: grouping failures by a **signature** (a short label computed from the evidence, so that failures with the same cause get the same label), keeping a record of known causes, a fixed routine for finding a cause, confirming that a match is real, and keeping the catalogue accurate over time. The last section applies it to KaijuFlow.

**How to read it.** Every claim about a source has a link to the page it came from; quotes are verbatim. Sentences marked **(inference)** are this note's own reasoning, not something a source says.

**What could not be read.**
- ITIL's own text (the IT service management guidance from AXELOS/PeopleCert) is sold, not public: the glossary page returned no text. ITIL's ideas are covered below through ServiceNow's product documentation, which says it "supports the ITIL process"; that is one vendor's implementation, not ITIL itself.
- Alan Card's paper "The problem with '5 whys'" returned "403 Forbidden" every time. Only its title, citation and a US government summary were read.
- Socorro's rule source code (`rules.py`) was not opened; its rules are described from Socorro's own documentation.

## The short answer

1. **Signatures.** Every system read builds its label from the few facts that best point at the cause and throws away facts that vary between occurrences of the same cause (addresses, numbers, file names). All of them accept that a label is a guess: it can put two causes under one label (too coarse) or split one cause across many labels (too fine), and each has a way to correct it later.
2. **Known causes.** A known-cause record holds at least the root cause and the workaround (ServiceNow), and is linked to the label rules that find it and to the fix (WER, LUCI Analysis). Records are reopened when the problem comes back.
3. **Routine.** Zeller's scientific debugging and Google SRE's troubleshooting chapter agree: write down observations, state each hypothesis with a prediction that could prove it wrong, test it, and log every result, including the negative ones. Fault trees force you to consider several causes together; the "5 whys" is criticised for following a single chain.
4. **Confirming.** A label is never the proof. The systems read confirm a cause with a test that can fail: a hypothesis check run over many saved reports (WER), re-running the saved failing input on the fixed build (ClusterFuzz, syzbot), and Zeller's rule that a diagnosis must explain both how the failure came to be and what is wrong.
5. **Learning.** Label rules are changed by hand, often (WER added about one rule a week), and old reports are re-labelled with the new rules. A cause that returns after its fix is treated as a new bug or as evidence that the fix did not work.

## 1. Failure signatures and grouping

### Microsoft Windows Error Reporting (WER)

WER is the system that collects crash reports from Windows computers; the paper describing its first ten years is Glerum et al., "Debugging in the (Very) Large", SOSP 2009 ([PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/sosp153-glerum-web.pdf)).

- **What a bucket is.** "bucket (noun): A collection of error reports likely caused by the same bug." The ideal is "orthogonality: one bug per bucket and one bucket per bug" (section 2.1, [PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/sosp153-glerum-web.pdf)).
- **Two stages.** First errors are *labelled* on the user's computer "based on immediate evidence available at the client"; then they are *classified* on Microsoft's servers, "assigned to new buckets as additional data is analyzed" (section 2.1). "In WER, bucketing is progressive. As additional data related to an error report is collected ... the report is associated with a new bucket" (section 2.1).
- **What goes into a label.** The main client label is built from "the faulting program, module, and offset of the program counter within the module" (section 3.1): which program, which part of it, and where in that part the crash happened. A program can supply its own permanent tags instead: Office gives each assert (a check written into the code) "a unique permanent tag", so "all instances of a single assert are assigned to a single bucket even as the assert moves in the source over time" (section 3.1).
- **Too coarse versus too fine.** Rules are sorted by effect: "expanding heuristics increase the number of buckets with the goal that no two bugs are assigned to the same bucket; condensing heuristics decrease the number of buckets with the goal that no two buckets contain error reports from the same bug" (section 3). "An expanding heuristic should not introduce new buckets for the same bug. A condensing heuristic should not put two bugs into one bucket" (section 3).
- **Skipping irrelevant frames.** The server picks the code most likely to be the cause by giving each place in the call history a priority; code "known never to be the root cause of an error, such as memcpy, memset, and strcpy" gets the lowest (section 3.2). In plain terms: ignore the generic helpers that appear in every failure.
- **Filtering failures nobody can fix.** Some rules tag reports "unlikely to be debugged", such as corrupted memory, known malware, out-of-date drivers or "hardware known to cause memory or computation errors" (section 3.2, figure 5).
- **How well it works.** The paper says no perfect algorithm is known (section 6.3). Reports in buckets holding a single report ("one-hit wonders") are assumed mis-bucketed, because "real bugs are always encountered more than once"; for PowerPoint "as many as 37% of all errors reports may be incorrectly bucketed due to poor condensing heuristics" (section 6.3).
- **Mistakes correct themselves with volume.** "even if we made some mistakes, such as incorrectly diagnosing two errors as having the same root cause, once we fixed the first then the occurrences of the second would reappear and dominate future samples" (section 2.1).

### Mozilla Socorro (Firefox crash reports)

Socorro builds a crash signature from the crashing thread's call stack ([Signature generation](https://socorro.readthedocs.io/en/latest/signaturegeneration.html)):

- It walks down the stack, skips frames on an "Irrelevant Signatures" list, keeps adding frames while they match a "Prefix Signatures" list (generic frames that say little alone), normalises each frame, and joins them with `|`.
- Where a frame goes: a symbol "that isn't helpful in summarizing the cause of the crash" goes on the irrelevant list, as do symbols in crash-handling code that runs after the crash; otherwise it goes on the prefix list.
- Special rules add a prefix that names the kind of crash, for example `OOM | <size>` for out-of-memory, `shutdownhang`, `stackoverflow` or `bad hardware` (the default rule set on the same page).
- **Too coarse versus too fine.** A signature that is too coarse groups "crash reports that have nothing to do with one another"; one too fine leaves "crash reports ... in very small groups which are unlikely to be looked at" ("Philosophy", same page). Socorro sometimes splits a signature on purpose with a temporary change to study one class of crashes (same page).

### Chromium's LUCI Analysis (test failure clustering)

LUCI Analysis groups Chromium's failing tests. Its failure-reason grouping removes the parts of an error message that vary between occurrences: "This algorithm removes ips, temp file names, numbers and other such tokens to cluster similar reasons together." The masking pattern replaces any run of digits, long hexadecimal strings and base64-like strings ([source, pinned](https://chromium.googlesource.com/infra/luci/luci-go/+/9842823d885581589e03904472c86e97539c1387/analysis/internal/clustering/algorithms/failurereason/failurereason.go)). From one example failure it writes a ready-made rule of the form `reason LIKE "..."` (same file, `FailureAssociationRule`).

Rules are short expressions a person can read and edit, a subset of SQL. The documented example is `reason LIKE "% exited with code 5 %" AND NOT ( test = "arc.Boot" OR test = "arc.StartStop" )`, over fields such as `test`, `reason` and `variant.<key>` ([rule language](https://pkg.go.dev/go.chromium.org/luci/analysis/internal/clustering/rules/lang)). Two rules can be merged into one with OR (`Merge`, same page).

There are three kinds of cluster: by failure reason, by test name, and clusters "backed by a failure association rule" linked to a bug (`IsBugCluster`, [clustering package](https://pkg.go.dev/go.chromium.org/luci/analysis/internal/clustering)). In plain terms: the machine proposes groups, and a person turns a group into a rule tied to a ticket.

### ClusterFuzz and syzbot (crashes found by automated testing)

- ClusterFuzz groups crashes by a "crash state": "A signature that we generate from the crash stacktrace for deduplication purposes", kept apart from the "crash type" such as Heap-use-after-free or Timeout ([glossary](https://google.github.io/clusterfuzz/reference/glossary/)). When it later finds "a reliably reproducible testcase for the same crash state, it creates a new report and deletes the older report with the unreliable testcase" ([fixing a bug](https://google.github.io/clusterfuzz/using-clusterfuzz/workflows/fixing-a-bug/)).
- syzbot (Google's Linux kernel test robot) merges crashes by their look: "while a bug is considered open all similarly-looking crashes are merged into the existing bug" ([syzbot docs](https://github.com/google/syzkaller/blob/master/docs/syzbot.md), read 2026-11-24). People correct the grouping by hand with `#syz dup: exact-subject-of-another-report` and `#syz invalid` (same page).

**What the sources agree a good signature is.** (Summary of the above.) It is built from the evidence nearest the cause (the faulting place in WER, the top relevant frames in Socorro, the error message in LUCI); it drops what varies between occurrences of one cause (numbers, addresses, file names, generic helper code); it names the kind of failure apart from its location (WER's exception code, Socorro's `OOM |` prefix, ClusterFuzz's crash type); and it is held as editable rules, because the first version is always wrong for some cases.

## 2. Known-error records

**ITIL, through ServiceNow.** ServiceNow's problem management "supports the ITIL process used to find and fix the root cause of issues that result in incidents" ([Exploring Problem Management](https://www.servicenow.com/docs/bundle/yokohama-it-service-management/page/product/problem-management/concept/exploring-problem-management.html)). Here an *incident* is a failure a user sees, a *problem* is its underlying cause, and a *known error* is a problem whose root cause and workaround are written down. What ServiceNow's pages say:

- **What the record holds.** "The known error articles document the root cause and the workaround of the problem to help with deflecting incidents" ([Create known error article](https://www.servicenow.com/docs/bundle/yokohama-it-service-management/page/product/problem-management/task/create-known-error-from-problem.html)). A *workaround* is a way to lessen the harm before a real fix: "Document and communicate a workaround to restore service failures and lessen the impact of a problem" ([Exploring](https://www.servicenow.com/docs/bundle/yokohama-it-service-management/page/product/problem-management/concept/exploring-problem-management.html)).
- **Linked to the problem.** The article is made from the problem record and stored in its "Primary Known Error article" field ([Create known error article](https://www.servicenow.com/docs/bundle/yokohama-it-service-management/page/product/problem-management/task/create-known-error-from-problem.html)).
- **Avoiding duplicates.** "Click Search for Duplicates to search for existing known error articles" (same page).
- **Closing and reopening.** "When the change request is completed, resolve the problem. If no new incidents come in, close the problem." If the problem manager is "not satisfied with the analysis after resolving or closing the problem, or the problem resurfaces, you can decide to reanalyze the problem", and "the state is changed to Root Cause Analysis" ([Exploring](https://www.servicenow.com/docs/bundle/yokohama-it-service-management/page/product/problem-management/concept/exploring-problem-management.html)). "It's a good idea to review risk-accepted problems periodically" (same page).

**WER's link from bucket to fix.** "The WER service maintains a mapping from buckets to solutions", and one solution "can be applied to one or more buckets with a simple regular expression matching mechanism" (section 2.5, [PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/sosp153-glerum-web.pdf)). "Programmers are notified only after WER determines that an error report does not match any previously resolved bugs" (section 2.3).

**Google SRE postmortems** are the other well-documented record of a failure and its cause. The book's example lists Summary, Impact, Root Causes, Trigger, Resolution, Detection, Action Items (each with a type, an owner and a bug), Lessons Learned ("What went well", "What went wrong", "Where we got lucky") and a Timeline ([Example Postmortem](https://sre.google/sre-book/example-postmortem/)). It keeps the root cause and the *trigger* (what set the latent fault off, e.g. "Latent bug triggered by sudden increase in traffic") apart (same page). Records are reviewed: "An unreviewed postmortem might as well never have existed" ([Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)); "Without a formal tracking process, action items from postmortems are often forgotten" ([Workbook, Postmortem Culture](https://sre.google/workbook/postmortem-culture/)); and "Mature postmortem cultures often add machine-readable tags (and other metadata) to enable downstream analytics" (same Workbook page).

## 3. A routine for finding a cause

### Zeller's scientific debugging

Andreas Zeller (author of *Why Programs Fail*) teaches debugging as the scientific method ([Introduction to Debugging](https://www.debuggingbook.org/html/Intro_Debugging.html)):

1. "Formulate a question".
2. "Invent a hypothesis based on knowledge obtained while formulating the question, that may explain the observed behavior."
3. "formulate a prediction that can support or refute the hypothesis. Ideally, the prediction would distinguish the hypothesis from likely alternatives."
4. "Test the prediction (and thus the hypothesis) in an experiment."
5. "Repeat Steps 2–4 until there are no discrepancies between hypothesis and predictions and/or observations."

"Debugging is a game of falsifying assumptions" (same page): a hypothesis is kept only while experiments fail to disprove it.

**Write it down.** "Remember how we wrote down every experiment in a table? How we numbered every hypothesis? This is not just for teaching. Writing these things down explicitly allow you to keep track of all your observations and hypotheses over time." The log's columns are Input, Expectation, Output and Outcome. "Every time you come up with a new hypothesis, you can immediately check it against your earlier observations"; the log also lets you "hand over the log to someone else, stating your findings so far" ("Keep a Log", same page).

**When a diagnosis is good enough to fix.** A diagnosis must show two things ("Checking Diagnoses", same page):
- "Causality. Your diagnosis should explain why and how the failure came to be. Hence, it induces a fix that, when applied, should make the failure disappear."
- "Incorrectness. Your diagnosis should explain why and how the code is incorrect".

A change that makes the failure go away without knowing why "may apply only to the symptom rather than the source"; a defect found but not tied to the failure "may not address the failure". After the fix "the failure should be gone, and no other failure should occur. If the failure persists, this should come as a surprise" (same page).

The book's chapter list names the larger steps: "Tracking Problems", "Reproducing Problems", "Simplifying Problems", "Scientific Debugging", "Deducing Errors", "Tracking Origins", "Isolating Failure Causes", "Fixing the Defect" ([table of contents](http://www.whyprogramsfail.com/toc.php)).

**Delta debugging** narrows a cause mechanically. It "keeps on cutting away smaller and smaller chunks from the input" while the failure still happens, until every part left "is required to produce the error" ([Reducing Failure-Inducing Inputs](https://www.debuggingbook.org/html/DeltaDebugger.html); paper: Zeller and Hildebrandt 2002, [doi:10.1109/32.988498](https://doi.org/10.1109/32.988498)). It needs a test that gives the same answer each time it is run (same page).

### Google SRE, "Effective Troubleshooting"

The SRE book calls troubleshooting "an application of the hypothetico-deductive method: given a set of observations about a system and a theoretical basis for understanding system behavior, we iteratively hypothesize potential causes for the failure and try to test those hypotheses" ([chapter 12](https://sre.google/sre-book/effective-troubleshooting/)). Its steps are Problem Report, Triage, Examine, Diagnose, Test and Treat, and Cure (same page). What it says about each step that matters here:

- **The report.** "An effective report should tell you the expected behavior, the actual behavior, and, if possible, how to reproduce the behavior. Ideally, the reports should have a consistent form and be stored in a searchable location".
- **Diagnose.** "Simplify and reduce": work "from one end of the stack" toward the other, checking the data between components. "What touched it last": "Recent changes to a system can be a productive place to start".
- **Test and Treat.** "An ideal test should have mutually exclusive alternatives, so that it can rule one group of hypotheses in and rule another set out." Test "in decreasing order of likelihood". Watch for "confounding factors", tests whose side effects "change future test results", and tests that "may not be definitive, only suggestive".
- **Notes.** "Take clear notes of what ideas you had, which tests you ran, and the results you saw."
- **Negative results.** "Negative results should not be ignored or discounted. ... Experiments with negative results are conclusive."
- **Cure.** "we'd like to prove that it's the actual cause. Definitively proving that a given factor caused a problem—by reproducing it at will—can be difficult to do in production systems; often, we can only find probable causal factors".
- **Pitfalls**, directly relevant to a casebook: "latching on to causes of past problems, reasoning that since it happened once, it must be happening again"; "Hunting down spurious correlations"; "correlation is not causation"; and, the other way, "when you hear hoofbeats, think of horses not zebras" (common causes first).

### Fault trees and the "5 whys"

- **Fault tree.** The US Nuclear Regulatory Commission's handbook: fault tree analysis "focuses on one particular undesired event and ... provides a method for determining causes of this event"; the tree is "a graphic model of the various parallel and sequential combinations of faults that will result in the occurrence of the predefined undesired event" (NUREG-0492, 1981, chapters III–IV, [PDF](https://www.nrc.gov/docs/ML1007/ML100780465.pdf)). Its two basic joins: an OR-gate means the event happens if any one input happens; an AND-gate means it happens "only if all the input faults occur" (chapter IV). It warns that a tree "is not a model of all possible system failures" and covers "only the most credible faults as assessed by the analyst" (chapter IV), and that the top event must be neither "too general" nor "too specific" (chapter III).
- **"5 whys"** (asking "why?" repeatedly down one chain). Card's paper argues against using it for root cause analysis ([BMJ Quality & Safety 2017;26:671–677](https://qualitysafety.bmj.com/content/26/8/671); the text could not be fetched). The US Agency for Healthcare Research and Quality summarises it: the author "highlights its value as a teaching tool but notes that its use for root cause analysis in health care may be misguided as it tends to simplify complex problems and limit understanding of how processes fail" ([PSNet summary](https://psnet.ahrq.gov/issue/problem-5-whys)). **(inference)** The fault tree's AND-gate is the direct answer to that weakness: a fail may need two causes together (for example a Source with missing articles *and* a check that said it was fine), and a single "why" chain names only one.

## 4. Confirming that a new failure really has the known cause

None of the systems read treats a matching label as proof:

- **A test run over the evidence.** WER tests a hypothesis by constructing "a debugger test function that can evaluate a hypothesis on a memory dump, and then apply it to thousands of memory dumps to verify that the hypothesis is not violated" (section 4, [PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/sosp153-glerum-web.pdf)). In one case the test pulled out "the current holder of the lock" across 10,000 dumps; the result was a fix and "the creation of a new heuristic for !analyze" (same section). So a confirmed test can become a new grouping rule.
- **Re-running the failing case.** ClusterFuzz: "Once a day, ClusterFuzz re-runs testcases against the latest build until it detects them as fixed", then records the "Fixed Revision Range" ([fixing a bug](https://google.github.io/clusterfuzz/using-clusterfuzz/workflows/fixing-a-bug/)). syzbot "aims at providing stand-alone C reproducers for all reported bugs" and tests a proposed fix with `#syz test` against the reproducer ([syzbot docs](https://github.com/google/syzkaller/blob/master/docs/syzbot.md)).
- **Finding where it started.** ClusterFuzz's regression range "shows the range of commits in which the issue was introduced", "available only for reliably reproducible crashes" ([triaging new crashes](https://google.github.io/clusterfuzz/using-clusterfuzz/workflows/triaging-new-crashes/)). syzbot's bisection is useful but fallible: "A single incorrect decision during bisection leads to an incorrect result" ([syzbot docs](https://github.com/google/syzkaller/blob/master/docs/syzbot.md)).
- **Causality and incorrectness** (Zeller, section 3 above), and the SRE "Cure" step: prove by "reproducing it at will", and say so when only a "probable" cause could be shown ([chapter 12](https://sre.google/sre-book/effective-troubleshooting/)).

## 5. Learning over time

- **Rules change often, by hand, from real cases.** WER's server rules "were derived empirically and continue to evolve": "roughly 100,000 lines of code implementing some 500 bucketing heuristics ... with roughly one heuristic added per week" (section 3.2, [PDF](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/02/sosp153-glerum-web.pdf)). Its few condensing rules "were derived empirically for common cases where a single bug produced many buckets" (section 3). Duplicates are found when "a second bucket was triaged by programmers and found to be caused by the same bug as the first bucket" (section 6.3).
- **Old reports are re-labelled when rules change.** WER: "whenever we update classifying heuristics we run !analyze on the affected portion of the minidump archive to re-bucket reports" (section 6.3). Socorro: rule changes go through review, where the reviewer should "Verify with the author that the changes occur as intended", existing reports are sent for reprocessing, and `socorro-cmd signature CRASHID` shows a crash's old and new signature side by side ([Signature generation](https://socorro.readthedocs.io/en/latest/signaturegeneration.html)). LUCI Analysis keeps a version number for each grouping method, raised "whenever existing test results may be clustered differently", and changes to configuration "should trigger re-clustering of test results" ([source](https://chromium.googlesource.com/infra/luci/luci-go/+/9842823d885581589e03904472c86e97539c1387/analysis/internal/clustering/algorithms/failurereason/failurereason.go); [clustering package](https://pkg.go.dev/go.chromium.org/luci/analysis/internal/clustering)).
- **Counts decide what to look at first.** "Programmers sort their buckets and start debugging with the bucket with largest volume of error reports" (WER section 4).
- **A fix is checked against later failures.** WER watches "error report volumes over time to determine if a software fix had the desired effect" and around releases "to quickly identify and resolve new errors" (section 4). LUCI Analysis computes whether a bug's closure is invalid, which "means we have evidence that shows the bug was not actually fixed at the time a user closed the bug", checked 1, 3 and 7 days after closing ([bugs package](https://pkg.go.dev/go.chromium.org/luci/analysis/internal/bugs)); it raises and lowers its thresholds by different amounts "to help implement hysteresis" (so one stray failure does not flip a bug open and shut; same page).
- **A cause that returns after its fix.** syzbot considers a bug closed only once the fix "reaches all builds", and after that "new similarly-looking crashes create a new bug" ([syzbot docs](https://github.com/google/syzkaller/blob/master/docs/syzbot.md)). Fix bisection is tried only once "The bug must not have occurred for at least 30 days" (same page). ServiceNow reopens a problem that "resurfaces" (section 2 above).
- **The archive is searchable and tagged.** SRE: finished postmortems go into "a team or organization repository of past incidents" ([Postmortem Culture](https://sre.google/sre-book/postmortem-culture/)), with "machine-readable tags (and other metadata) to enable downstream analytics" ([Workbook](https://sre.google/workbook/postmortem-culture/)).
- **Ask for more evidence only where needed.** WER's "progressive data collection" starts with "no more than a simple bucket identifier", and asks for a small dump, then a full one, only "If additional data is needed" (section 2.2).

## 6. What this suggests for KaijuFlow

Everything in this section is **(inference)** unless it cites a source: it is this note's reading of how the practices above fit KaijuFlow's evidence. KaijuFlow facts come from [`GLOSSARY.md`](../../../GLOSSARY.md), [`tools/brain/docs/rules.md`](../../../tools/brain/docs/rules.md) ("Real-use checks") and [`tools/brain/docs/formats.md`](../../../tools/brain/docs/formats.md) ("Step lines").

### 6.1 The evidence KaijuFlow already has

A quick check keeps, per title: the outcome (`fail`, `played`, `nothing to play`) with `why`, `fallbacks`, `check_misses` and `checked` in `raw.json`; KaijuFlow's step lines `play_check` (with `status`: `verified`, `verified_stored`, `blocked` or `error`), `played` and `play_failed` (with `reason`, KaijuFlow's words without addresses); AltMount's `imports`; both containers' logs per title; `settings.json`; and the image's `commit` ([formats](../../../tools/brain/docs/formats.md)). The prepare-side step lines (`nzb_fetch`, `unscramble`, `upload`, `import_wait`, `first_byte`) carry `ok` and the release title. That is the first-level evidence, like WER's client label. Container logs, AltMount's own messages and a repeat play are the second level, collected only when the first level does not settle the cause (WER's progressive collection).

### 6.2 The signature

Built the way WER, Socorro and LUCI build theirs:

- **Kind of failure** (expanding, like WER's exception code or Socorro's `OOM |` prefix): the check's own outcome words, `fail`, `check miss`, `fallback`, `slow play`, plus for a fail which kind (no list, no Best entry, no video in 300 s, failure video, wrong title).
- **Where it failed** (expanding, like WER's module and offset): the last step line before the failure and whether it was `ok`; for a check miss, the `play_check` status that passed and the step that then failed.
- **Why, with variable parts masked** (condensing, like LUCI's masking): the `play_failed` reason with numbers, job ids, sizes, release names and times replaced by a placeholder.
- **Left out** (Socorro's irrelevant list): the title, the indexer's name, the release name, timings, the order of Sources. They differ between occurrences of one cause. They stay in the evidence, not in the signature.

Example shape: `fail | no video | import_wait not ok | AltMount refused: <n> segments missing`. Keep signature rules in one file, numbered with a rule version, so a change can be re-run over every stored failure (WER, Socorro, LUCI). A single-occurrence signature is not suspicious in a five-title check the way WER's one-hit wonders are; the scale is too small for that test. The risk here is the other one: a coarse signature hiding two causes. Section 6.4 covers how that shows up.

### 6.3 The casebook entry

Fields drawn from ServiceNow's known error article, WER's bucket-to-solution link, LUCI's rule-to-bug link, the SRE postmortem and syzbot's status tracking:

| Field | What it holds | Source it follows |
|---|---|---|
| `id`, `title` | A short id and one plain sentence naming the cause | syzbot bug title |
| `match` | One or more signature rules (readable expressions over the evidence fields), with the rule version | LUCI failure association rule; WER's regular-expression solution mapping |
| `signs` | What is always seen with this cause, and what would rule it out | Zeller's observation table; SRE "mutually exclusive alternatives" |
| `confirm` | The confirming test: a concrete check on this failure's own evidence, or an experiment, whose result differs when the cause is present and when it is absent | WER hypothesis test over dumps; Zeller's prediction |
| `root_cause` | How the failure came to be and what is wrong, with the component (per [A3](../A3_STATIC_ARCHITECTURE.md)) | Zeller's causality and incorrectness; ServiceNow root cause |
| `trigger` | What set it off this time, kept apart from the cause (a gone article, a slow provider) | SRE example postmortem |
| `whose` | KaijuFlow, AltMount, the indexer, Usenet: who can fix it | WER's filters for failures nobody can debug |
| `workaround` | What lessens it before a fix, or "none" | ServiceNow |
| `fix` | Ticket, commit, and the drill-down that proved it | ClusterFuzz fixed range; syzbot `#syz fix` |
| `status` | open, fix in progress, fixed (awaiting proof), proved fixed, reopened | ServiceNow states; syzbot; LUCI verification |
| `occurrences` | Each check folder, title and date it was confirmed in, so counts and first/last seen follow | WER bucket counts |
| `ruled_out` | Hypotheses tested and rejected, with the test | SRE "Negative results are magic"; Zeller's log |
| `history` | Merged from, split into, rule changes, review dates | WER re-bucketing; LUCI `Merge` |

An occurrence is added to an entry only after its `confirm` test passed on that failure. A signature match without a passing confirm is a lead, recorded as such.

### 6.4 The routine, step by step

1. **Gather** (automatic). Collect 6.1's first-level evidence into one file per failure, with the check folder, commit and settings. Write the problem statement in the SRE form: expected, actual, and how to repeat it (the title, its kind, Best).
2. **Sign** (automatic). Compute the signature with the current rule version.
3. **Look up** (automatic). List every casebook entry whose `match` fits, most frequent first ("horses not zebras"). Each is a hypothesis, not an answer: the SRE pitfall "latching on to causes of past problems" is exactly what a casebook makes easy.
4. **Confirm a match.** Run each candidate's `confirm` test on this failure. Pass: record the occurrence, go to step 8. Fail: record it under that entry's `ruled_out` for this failure and continue as unknown. A match whose confirm fails is also a sign the entry's `match` rule is too coarse (6.6).
5. **Unknown: open a log** (the agent's fixed routine). A table of observations, then numbered hypotheses, each with the prediction that would refute it (Zeller). Consider more than one cause at once, AND as well as OR (fault tree), rather than one chain of whys (Card).
6. **Narrow.** Follow the play along its path (list, `play_check`, `nzb_fetch`, `unscramble`, `upload`/`import_wait`, `first_byte`) and find the first step whose output is wrong (SRE "simplify and reduce"). Check what changed since the last check that passed: commit, settings, AltMount version (SRE "what touched it last"). When a known-good and a known-bad commit exist and the failure repeats, halve the commits between them (bisection, delta debugging); when it does not repeat, say so: syzbot warns one wrong step gives a wrong answer.
7. **Test each hypothesis.** Choose tests that split the hypotheses (SRE "mutually exclusive alternatives"), most likely first, and note anything that could confound them (a Source that is gone by the time it is played again, an indexer at its limit). Log every result, negative ones too. Stop when one hypothesis is left that explains how the failure came to be and what is wrong (Zeller's two checks). If it cannot be repeated at will, mark the cause *probable*, not *proved* (SRE "Cure").
8. **Record.** A new cause becomes a casebook entry with a `match` rule and a `confirm` test written from this case; a known one gets the occurrence. The rejected hypotheses go into `ruled_out`.
9. **Fix and prove.** The fix is proved by a [Drill-down](../../../GLOSSARY.md) on the failed title (ClusterFuzz's fixed testing, syzbot's `#syz test`). The entry moves to *proved fixed* only after the drill-down plays; the failure should be gone and no other failure appear (Zeller).
10. **Watch.** Every later check signs its failures against the casebook. A match on a *proved fixed* entry whose confirm passes reopens it as a regression (syzbot, ServiceNow "resurfaces", LUCI closure invalidation).

### 6.5 The confirming test and reproduction

A confirming test should be a check a program can run on one failure's evidence and get yes or no, like WER's test function on a dump. Examples of the shape, not proposals: "AltMount's import line for this job says segments are missing and the `play_check` line for the same release said `verified`" confirms a check miss from missing articles; seeing the same `reason` with every article present refutes it. Where evidence alone cannot decide, the test is an experiment: play the Source again, or the title on a commit before the suspected change.

KaijuFlow's live, cold, new-title check is hard to repeat by design: the Source can disappear and the indexer answers change. Two existing pieces can make repetition easier. The stand-in already records real indexer answers and replays them ([GLOSSARY](../../../GLOSSARY.md), "Recording", "Stand-in"); a quick check's answers are deleted after it ([formats](../../../tools/brain/docs/formats.md)). Keeping the answers for a failed title would give something like syzbot's reproducer: the same list and NZBs, replayed. Usenet itself would still be live, so it repeats the KaijuFlow side, not the providers.

### 6.6 Keeping the casebook accurate

- **Too coarse** (two causes under one entry). Signs: a confirm test that fails on a failure the `match` caught; a *proved fixed* entry whose signature keeps appearing but whose confirm fails (WER: "once we fixed the first then the occurrences of the second would reappear"). Response: split, adding an expanding field to the signature.
- **Too fine** (one cause under several entries). Signs: two entries with the same `root_cause` and `confirm`. Response: merge, OR-ing their rules (LUCI `Merge`), keeping both histories.
- **Re-sign after every rule change.** Store each failure's evidence, so a new rule version can be run over all of it and old and new signatures compared, as Socorro's `socorro-cmd signature` does. Record the rule version on every occurrence.
- **Review.** Look again at entries that stay *open* or *probable* (ServiceNow's periodic review of risk-accepted problems), and at entries not seen for a long time: syzbot waits 30 days before trying to find what fixed a bug that stopped happening.

### 6.7 The index

For fast lookup by a program, one machine-readable file (JSON, say) beside the human-readable entries, holding per entry its `id`, `match` rules, `status`, rule version and occurrence count. Lookup is: compute the signature, evaluate every entry's rules (small enough at KaijuFlow's scale to try them all), return the matches by count. Machine-readable tags on each entry and each occurrence (kind, component, `whose`) let the casebook answer "which causes are AltMount's" or "which came back" without reading the text, as SRE's tagged postmortems do. A failure with no match is the signal to start step 5.
