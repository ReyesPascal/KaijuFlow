# LLM diagnosis agents work best when code gathers the evidence, past cases are pasted in as examples, and only proved lessons are kept

Researched 2026-11-24 for the planned diagnosis system: after each real-use check, gather each failure's evidence, match it against a casebook of known causes, confirm each match with that cause's own test, and have a Claude agent diagnose what is new. Classic practice (crash signatures, ITIL known errors, Zeller's scientific debugging, Google SRE troubleshooting) is covered by a separate brief and left out here.

Every claim below links to its source: a paper's own text, an official engineering blog, or source code. Where I go beyond the sources, the text says **(inference)**. Every source except Meta's posts measures its results on its own company's incidents or on public test sets, and none of them was checked by an outside group.

## Short answer

1. **The systems that work split the job.** Code collects the evidence for each kind of alert, and the language model only reads it and names a cause. Microsoft's RCACopilot works this way ([Chen et al.](https://arxiv.org/abs/2305.15778)), and so does Meta's code-change ranker ([Meta, 2024](https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/)). Microsoft's FLASH follows written troubleshooting guides step by step ([Zhang et al., FLASH](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)).
2. **Past incidents help most when the closest ones are pasted into the prompt as worked examples.** Without past incidents, GPT-4 scored 0.026 on RCACopilot's test. With the most similar past incidents in the prompt, it scored 0.766 ([Chen et al.](https://arxiv.org/abs/2305.15778), Table 2). A second Microsoft study found that relevant past incidents beat random ones by about 41% ([Zhang et al., in-context](https://arxiv.org/abs/2401.13810)).
3. **Even then, the model is often wrong.** In one Microsoft test, GPT-4 with the most relevant past incidents was correct 43.4% of the time ([PACE-LM](https://arxiv.org/abs/2309.05833), Table 1). Meta's ranker had the true cause in its top five 42% of the time. So every paper keeps a person or a test as the final judge.
4. **The guardrails that are measured:**
   - make the model quote its evidence, and drop any quote that is not really in the logs ([RCAgent](https://arxiv.org/abs/2310.16340));
   - give it an explicit "this is a new, unseen case" answer ([RCACopilot](https://arxiv.org/abs/2305.15778));
   - let it say "not enough evidence" ([Roy et al.](https://arxiv.org/abs/2403.04123));
   - hold back answers with low confidence ([Meta](https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/)).
5. **A memory of lessons stays correct only when entries are checked before they are stored.** FLASH stores a lesson from a past failure only after re-running the failed step with it proves that it fixes the step ([FLASH](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf), §3.5.3). Research agents keep a running count of how often each entry helped or misled, remove the entries that fall to zero, and merge near-duplicates ([ExpeL](https://arxiv.org/abs/2308.10144), [ACE](https://arxiv.org/abs/2510.04618)).
6. **For KaijuFlow (inference):** at tens to hundreds of failures, the whole casebook fits in one prompt, so no search index is needed at first. Look entries up by exact fields taken from the step lines. Let the agent read the full evidence package. Add an entry to the casebook only when its confirming test has passed.

## Words used here

- **Language model (LLM):** the AI that reads and writes text, such as Claude or GPT-4.
- **Agent:** a language model that runs in a loop. It decides on a step (run a query, read a log), sees the result, and decides the next step. "ReAct" is the common recipe for that loop: think, act, observe, repeat ([Roy et al.](https://arxiv.org/abs/2403.04123), §2.4).
- **In-context examples:** past cases pasted into the prompt, so the model can copy their pattern. No retraining is involved.
- **Fine-tuning:** further training a model on your own examples. It is costly and must be redone as things change.
- **Embedding:** turning a text into a list of numbers so that similar texts get similar numbers. It is how "find the most similar past incident" is usually done.
- **Index:** whatever the system uses to find matching past cases quickly: embeddings, categories, keywords, or exact fields.
- **F1 score:** an accuracy figure from 0 to 1 that punishes both wrong answers and missed ones. "Micro" averages over all incidents. "Macro" averages over the causes, so rare causes count as much as common ones.
- **Top-5 accuracy:** how often the true cause is among the five suggestions.
- **Calibrated confidence:** when the system says "70% sure", it is right 70% of the time.

## 1. Published systems: steps, what they retrieve, how they index it

### RCACopilot (Microsoft, EuroSys 2024)

[Chen et al., "Automatic Root Cause Analysis via Large Language Models for Cloud Incidents"](https://arxiv.org/abs/2305.15778), tested on a year of one Microsoft email service's incidents.

**Steps.**

1. Each incoming alert is matched to an **incident handler** written for its alert type. A handler is a small decision tree of actions: collect this log, run this query, branch on the result, and sometimes suggest a fix. Engineers build handlers by hand from reusable actions. The handlers are versioned in a database, and engineers update them as the system changes (§4.1, §4.1.1).
2. A language model summarizes what the handler collected.
3. The summary is turned into an embedding, and the most similar past incidents are found.
4. The model is shown the new incident and the past ones, each labelled with its cause category. It is asked to pick the past incident with the same cause and explain why. Option A is always **"Unseen incident"** (Figure 9). A predicted category goes to experienced engineers for review (§4).

**Index.** The embeddings come from FastText, a small text model, trained on the team's own past incidents. A pre-trained model was rejected as costly and a poor fit for internal text (§4.2.1). Similarity combines closeness of text with closeness in time. Older incidents count less, because 93.8% of repeat incidents came back within 20 days (Insight 2, §4.2.2). The prompt holds the top K past incidents, drawn from *different* categories, so the model sees a varied set of choices (§4.2.2).

**Scale.** The test set is small. It had 653 incidents, and 24.96% of them had a cause category never seen before (§3). That is close to KaijuFlow's scale.

### Recommending root causes with fine-tuned GPT-3 (Microsoft, ICSE 2023)

[Ahmed et al.](https://arxiv.org/abs/2301.03797) fine-tuned GPT-3 and GPT-3.5 models on 44,340 incidents from 1,759 services. Each model writes a root cause and a fix from only the incident's title and summary, as known when the incident opened (§I, §III).

There is no retrieval at run time: the past incidents live inside the model's weights. The RCACopilot authors list the costs of this choice. A title and summary miss the logs. Fine-tuning needs many examples. And "it is challenging to continuously update a finetuned GPT model … therefore such models are prone to generate more hallucinated results over time" ([Chen et al.](https://arxiv.org/abs/2305.15778), §1).

### GPT-4 with past incidents as in-context examples (Microsoft, FSE 2024)

[Zhang et al., "Automated Root Causing of Cloud Incidents using In-Context Learning with GPT-4"](https://arxiv.org/abs/2401.13810), tested on more than 100,000 incidents.

**Steps.**

1. GPT-3.5 shortens each past incident and its root cause to 5 or 6 sentences. The summary keeps the symptoms, the services involved, "precise error codes, specifics from logs", and the service name. In one example, 864 tokens became 89 (§3.3.1, Figure 3).
2. Each summary is turned into an embedding (the `all-mpnet-base-v2` sentence model) and stored in a FAISS search index (§3.3.2).
3. For a new incident, the closest past incidents are pasted into the prompt as title, summary and root cause, followed by the new incident (§3.3.3, §3.4).

**Two findings that matter here.**

- The format matters. Whole past incidents laid out as examples did better than the same text cut into 128-token chunks, the usual way of feeding documents to a model (§4.2.2, Table 2).
- Relevance matters more than the format. Random past incidents improved on no examples by only 5.9%, while relevant ones improved on it by 49.7% (§4.2.5).

### RCAgent (Alibaba Cloud, CIKM 2024)

[Wang et al.](https://arxiv.org/abs/2310.16340) built an agent that runs on a locally hosted model (Vicuna-13B), so company data never leaves the company (§4.1).

**Steps.** A "controller" agent runs the think-act-observe loop. It can call tools that read logs, read the code of the company's advisor services, and query their history database. It can also call two "expert agents", one for code and one for logs, each a separate language-model call. Only data from before the failure was detected can be read (§3, §4.2.2).

**What it retrieves.** The log expert agent pulls past examples from a history of answers from Flink Advisor, a rule set "distilled from experienced SREs' domain knowledge". It compares log pieces by embedding (§4.2.1, Algorithm 1).

**Results.** It beat a plain ReAct agent on root cause, fix and evidence. Its test set was 161 failed jobs, with no more than two jobs sharing a cause (§4.2.1, §5.1).

### Exploring a ReAct agent for root cause analysis (Microsoft, 2024)

[Roy et al.](https://arxiv.org/abs/2403.04123) gave a ReAct agent tools to search past incidents, by keyword (BM25) or by embedding. They compared it with plain retrieval and with step-by-step reasoning ("chain of thought") on incidents the model had never seen in training (§3.4, §5).

They also ran a case study with an Azure team, giving the agent that team's own database query tool and its knowledge-base articles. Those articles are the team's written guides, and incidents are often tagged with the relevant one when they open (§7.2–7.3). That is the closest published analogue to KaijuFlow's casebook.

### FLASH (Microsoft, 2024)

[Zhang et al., FLASH](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf) ([publication page](https://www.microsoft.com/en-us/research/?p=1090611)) automates *recurring* incidents that already have a written troubleshooting guide.

**Steps.** The agent works through the guide one step at a time. "Status supervision" keeps it on the step the current state calls for (abstract, §3).

**What it retrieves.** "Hindsight": short lessons written from the agent's own past mistakes. They are stored in a FAISS index. At each step's end, the three closest lessons are fetched by embedding, and a language model first answers Yes or No on whether a lesson applies at all (§3.5.4).

**Results.** It was tested on 250 Microsoft incidents in five scenarios. It beat other agents by 13.2% accuracy on average ([publication page](https://www.microsoft.com/en-us/research/?p=1090611)).

### Flow-of-Action (CNIC/Tsinghua and others, WWW 2025)

[Pei et al.](https://arxiv.org/abs/2502.08224) give the agent standard operating procedures: experts' written diagnosis steps. A tool matches the most relevant procedures to the failure. A "JudgeAgent" decides when the root cause has been found. When no procedure matches, the model drafts a new one, using existing procedures as examples (§1, §3). The authors call the drafted procedures "not highly precise" but pointing the right way (Figure 6). Accuracy rose from 35.50% with plain ReAct to 64.01% (abstract).

### Meta: AI-assisted root cause analysis (2024) and DrP (2025)

**The ranker.** [Meta's 2024 post](https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/) describes a system that names the code change that probably caused an investigation.

- **Narrowing by rules.** Rules first cut thousands of recent changes to a few hundred, using code and directory ownership and the runtime code graph of the affected systems.
- **Ranking by the model.** A Llama 2 (7B) model then ranks the rest "through election": groups of 20 changes, the top five from each kept, repeated until five are left.
- **Learning from the past.** The past enters through fine-tuning on about 5,000 examples from past investigations with known root causes. Meta calls this "the biggest lever" in reaching its 42% top-5 accuracy, measured at the moment each investigation opened.

**DrP.** [Meta's DrP post](https://engineering.fb.com/2025/12/19/data-infrastructure/drp-metas-root-cause-analysis-platform-at-scale/) describes the platform around it, which is not itself an AI system.

- Engineers write investigation playbooks as code, called "analyzers". The analyzers go through code review with automated backtesting before they ship. They run automatically when an alert fires.
- Meta reports more than 300 teams, 2,000 analyzers and 50,000 analyses a day, with time to resolve cut by 20–80%.
- A "DrP Insights" job ranks the top alert causes over time.
- Meta says DrP is meant to "evolve into an AI-native platform".

## 2. How they keep the agent from inventing a cause

| Guardrail | Where | What the source says |
|---|---|---|
| **Quote the evidence, and drop quotes that are not real** | RCAgent | The log expert must support its analysis "by directly copying log content". If the quoted evidence "cannot be fuzzy-matched to the chunk", the result is discarded ([§3.2.2, Algorithm 1](https://arxiv.org/abs/2310.16340)). |
| **Warn the agent when it stops early** | RCAgent | The controller is sent an error message on "early finalizing without thorough investigation", on repeated identical tool calls, and on trivial input to an expert ([§3.3](https://arxiv.org/abs/2310.16340)). |
| **Run it several times and take the majority** | RCAgent | Several final answers are sampled and the one closest to the majority is chosen. This raised every score. Letting the early steps run with randomness made the agent unstable: its pass rate fell to 70.19% ([§3.4, §5.3–5.4](https://arxiv.org/abs/2310.16340)). |
| **An explicit "unseen" answer** | RCACopilot | The first option in every prompt is "Unseen incident". For such cases the model writes a new category label with an explanation, which goes to engineers for review ([Figure 9, §4, §5](https://arxiv.org/abs/2305.15778)). |
| **"Not enough evidence" counts as an answer** | Roy et al. | The scoring has an "Insufficient Evidence" outcome: the model "refrains from making a prediction". For the ReAct agent, this was 39 of its 63 wrong answers, which is why it had the fewest made-up facts ([Tables 1, 3](https://arxiv.org/abs/2403.04123)). |
| **Hold back answers with low confidence** | Meta | "We also rely on confidence measurement methodologies to detect low confidence answers and avoid recommending them to the users – sacrificing reach in favor of precision" ([Meta](https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/)). |
| **Results people can reproduce** | Meta | Features "prioritize closed feedback loops and explainability", so responders "can independently reproduce the results" ([Meta](https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/)). |
| **A confidence score checked against past cases** | PACE-LM | A second model asks two questions: "do the past incidents give enough to judge this?" and "is the suggested cause true, supported by those past incidents, and specific enough?" A fitting step then turns the two answers into a calibrated score ([§4](https://arxiv.org/abs/2309.05833)). |
| **A test before a lesson is kept** | FLASH | A lesson written after a failure is checked by rolling the agent back to the failed step and retrying with the lesson. "If successful, the hindsight is stored … if unsuccessful, the process of generating hindsight is repeated" ([§3.5.3](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)). |
| **Ask whether a lesson applies before using it** | FLASH | Before using a fetched lesson, the model answers Yes or No on whether it applies, because reflection "may lead to incorrect outcomes if misapplied" ([§3.5.4](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)). |
| **A judge decides when to stop** | Flow-of-Action | A JudgeAgent tells the main agent whether the root cause has been found yet ([§1](https://arxiv.org/abs/2502.08224)). |
| **Code review and backtesting of each playbook** | Meta DrP | Analyzers "are tested and sent for code review", with "automated backtesting integrated into code review tools" ([DrP](https://engineering.fb.com/2025/12/19/data-infrastructure/drp-metas-root-cause-analysis-platform-at-scale/)). |

Two 2026 studies say what these guards should catch.

**Which reasoning errors predict a wrong answer.** [Riddell et al.](https://arxiv.org/abs/2601.22208) ran 48,000 simulated failures through six open models. They listed 16 kinds of reasoning error; the first is "fabricated evidence", which asserts logs or alerts that are not there (Table 1). The errors that most predicted a wrong answer were:

- anchoring on a first idea;
- repeating or stalling;
- picking evidence arbitrarily;
- not changing one's mind when new evidence arrives.

Each cut the chance of a correct answer by at least 45%. The authors conclude that "hypotheses should not be trusted at face value", and that systems need "evidence sufficiency checks" and "temporal ordering validators" (checks that a cause comes before its effects) before a hypothesis is accepted (Observations 10–12).

**Right answers can still rest on poor reasoning.** [Lu et al.](https://arxiv.org/abs/2608.21310) studied 5,000 agent runs. They found that "correct localization can hide deficiencies in causal reconstruction". Failed runs drifted to unrelated services, repeated shallow queries, left out evidence, misread it, or reasoned without support. A small guard aimed at those three failure families raised accuracy by 3.5–35.1 points (abstract).

## 3. How the memory of past incidents grows and stays correct

| System | Who writes new entries | Review | Duplicates | Stale entries |
|---|---|---|---|---|
| RCACopilot | Engineers build and edit handlers. Experienced engineers label every cause category by hand. The model can propose a new label for an unseen incident ([§4.1.1, §6](https://arxiv.org/abs/2305.15778)). | A predicted category is "presented to experienced OCEs for review" ([§4](https://arxiv.org/abs/2305.15778)). Some handlers stay off "under development and rigorous testing" ([§5.5](https://arxiv.org/abs/2305.15778)). | Not described. | Handlers are versioned. Older incidents count less in the search through a time-decay term ([§4.1.1, §4.2.2](https://arxiv.org/abs/2305.15778)). |
| GPT-4 in-context | Resolved incidents, whose root causes their owners wrote, go into the search corpus after a model shortens them ([§3.3](https://arxiv.org/abs/2401.13810)). | I found no review step in the paper. | Not described. | Not described. |
| Ahmed et al.; Meta ranker | Past incidents and investigations with known causes become training data ([Ahmed](https://arxiv.org/abs/2301.03797), [Meta](https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/)). | Not described. | Not described. | Only by retraining, which RCACopilot's authors say is hard to keep doing ([§1](https://arxiv.org/abs/2305.15778)). |
| FLASH | The agent writes a lesson from each failure it makes on a labelled past case. Human feedback can be added too ([§3.4–3.5](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)). | Automatic: the lesson must fix the failed step on retry ([§3.5.3](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)). | Not described. | Not described. |
| Meta DrP | Engineers write analyzers. Other teams reuse them, "compounding the shared knowledge base" ([DrP](https://engineering.fb.com/2025/12/19/data-infrastructure/drp-metas-root-cause-analysis-platform-at-scale/)). | Code review plus automated backtesting ([DrP](https://engineering.fb.com/2025/12/19/data-infrastructure/drp-metas-root-cause-analysis-platform-at-scale/)). | Not described. | Not described. |
| Flow-of-Action | Experts write procedures. The model drafts new ones when none match ([§3](https://arxiv.org/abs/2502.08224)). | Not described. | Not described. | Not described. |
| ExpeL (general research agent) | The agent writes "insights" from pairs of failed and successful attempts ([§4.2](https://arxiv.org/abs/2308.10144)). | Votes. Each insight starts with an importance of 2. Agreement or an edit adds 1, disagreement takes 1 away, and at 0 the insight "will be removed", because "even successful trajectories can be suboptimal and mislead" ([§4.2](https://arxiv.org/abs/2308.10144)). Insights are plain text, so people can "inspect, modify, or remove" them ([§4.5](https://arxiv.org/abs/2308.10144)). | Through edits and votes. | Through down-votes. |
| ACE (general research agent) | A "Reflector" writes lessons. A "Curator" adds them as small new items and never rewrites the whole list ([§3–3.1](https://arxiv.org/abs/2510.04618)). | Each item counts how often it was marked helpful or harmful ([§3.1](https://arxiv.org/abs/2510.04618)). | "A de-duplication step then prunes redundancy by comparing bullets via semantic embeddings", after each change or only when the list gets too long ([§3.2](https://arxiv.org/abs/2510.04618)). | Through the helpful and harmful counts. Items are edited in place, which avoids "context collapse": a model that rewrites the whole memory each time loses detail ([§2.2, §3.1](https://arxiv.org/abs/2510.04618)). |

Across these sources, nobody has published a full answer to merging and retiring entries. The incident-management papers rely on engineers and versioning. The general agent-memory papers rely on vote counts and embedding-based deduplication, and were tested on puzzles and app tasks, not on incidents.

## 4. Measured gains from using past incidents, and failure modes

### Gains

- **RCACopilot.** GPT-4 without past incidents scored 0.026 micro-F1. With them it scored 0.766 micro-F1 and 0.533 macro-F1, ahead of fine-tuned GPT-3.5 (0.103) and of classic learning methods ([Table 2](https://arxiv.org/abs/2305.15778)). Shortening the collected diagnostics first added 0.077 ([Table 3](https://arxiv.org/abs/2305.15778)). The prediction step took about 4.2 seconds per incident; collecting the diagnostics took 15 to 841 seconds, depending on the team ([§5.4–5.5](https://arxiv.org/abs/2305.15778)).
- **GPT-4 in-context.** Past incidents in the prompt gave 49.7% over no examples and 24.8% over fine-tuned GPT-3. Incident owners scored correctness 43.5% higher than for the fine-tuned model. Relevant examples beat random ones by about 41.2%. The order of the examples barely mattered ([abstract, §4.2.5–4.2.6](https://arxiv.org/abs/2401.13810)).
- **FLASH.** Past-failure lessons added 6% and 7.5% in two scenarios, over the same agent without them. Reflection *without* those lessons was 2% worse in one scenario than no reflection at all. That test is tiny: five past incidents to learn from and five to test on, per scenario ([§4.3](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)). On time: engineers reviewing 15 incidents judged 11 diagnoses correct. They rated the agent's 5.3-minute diagnosis against an average mitigation time of 90 minutes ([§4.2, Table 3](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)). The agent was close to 90% accurate where the guide was detailed, and about 50% where it needed tools the agent could not use ([§4.2](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)).
- **Meta.** Fine-tuning on past investigations was "the biggest lever" to 42% top-5 accuracy ([Meta](https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/)). DrP's codified playbooks cut time to resolve by 20–80% ([DrP](https://engineering.fb.com/2025/12/19/data-infrastructure/drp-metas-root-cause-analysis-platform-at-scale/)).
- **Flow-of-Action.** Matched procedures took accuracy from 35.50% to 64.01% ([abstract](https://arxiv.org/abs/2502.08224)).
- **ExpeL.** The agent got steadily better as it collected experience ([abstract](https://arxiv.org/abs/2308.10144)).

### Failure modes

- **Often wrong, even with the past to hand.** GPT-4 with the most relevant past incidents was correct 43.4% of the time ([PACE-LM, Table 1](https://arxiv.org/abs/2309.05833)). Incident owners gave the best fine-tuned models a mean correctness of 2.88 out of 5 for root causes ([Ahmed, Table VIII](https://arxiv.org/abs/2301.03797)).
- **Retrieval can feed made-up details.** The plain retrieval baseline put made-up facts into 26% of its *correct* answers and 49% of its wrong ones. Many wrong answers were "plausible based on historical incidents but incorrect" ([Roy et al., §6.1](https://arxiv.org/abs/2403.04123)).
- **Wrong suggestions cost time.** An engineer's concern, quoted in the paper: "if the suggestion is incorrect, on-call engineers may take longer time to investigate the problem" ([Ahmed, §V](https://arxiv.org/abs/2301.03797)). Owners also doubted the models on rare incidents ([§VI.D](https://arxiv.org/abs/2301.03797)).
- **More input can hurt.** Adding the raw alert text to the diagnostics lowered RCACopilot's score ([Table 3](https://arxiv.org/abs/2305.15778)). Adding engineers' discussion comments did not help the ReAct agent ([Roy et al., §6.2](https://arxiv.org/abs/2403.04123)).
- **No handler, no help.** RCACopilot cannot help when no handler exists for an alert, and its results depend on the quality of human-written labels ([§6](https://arxiv.org/abs/2305.15778)).
- **A guide is only as good as its writing.** Of 52 real troubleshooting guides, FLASH's authors found six kinds of defect that stopped an agent from following them: ambiguous or missing steps, tools the agent cannot call, near-empty documents, and guides that point to other guides without saying how ([§4.4, Table 4](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)).
- **Steps multiply errors.** FLASH notes that at 85% per step, five steps succeed only 44% of the time. Its lessons need hand-labelled, step-by-step cases, which costs human effort ([§1, §6](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)).
- **Hard, many-part failures defeat current models.** On OpenRCA, 335 failures with 68 GB of logs, metrics and traces, the best setup (Claude 3.5 with an agent) fully solved 11.34%. Accuracy at least halved when a cause had two parts instead of one, and no method solved any three-part case ([OpenRCA, Tables 2–3](https://proceedings.iclr.cc/paper_files/paper/2025/file/d29b8d53678015079e1d245c023e49d2-Paper-Conference.pdf)).
- **A fixed script can skip the decisive line.** [Bi et al.](https://arxiv.org/abs/2610.35767) compared approaches on 90 checked cases. Simple setups that let the model choose what to read were correct 65–77% of the time on mid-tier models; one of them was a single call over a prepared evidence package. Published hand-built agents were correct 16–53% of the time. The reason: "when the program decides what to read, it can skip the decisive evidence, such as a log line". More reasoning effort "changes little" (§1). This points the other way from Flow-of-Action's gain from fixed procedures. Both are single studies on different test sets.
- **Reasoning errors.** Anchoring, stalling, arbitrary evidence and not updating beliefs predict wrong answers ([Riddell et al.](https://arxiv.org/abs/2601.22208)).

## 5. Applied to KaijuFlow

Everything in this section is **inference** from the sources above, fitted to what a quick check already writes ([formats: Check folder](../../../tools/brain/docs/formats.md#check-folder)) and to the words in [GLOSSARY](../../../GLOSSARY.md).

### Why the small scale changes the design

RCACopilot's whole test set was 653 incidents, and in it a few past cases per category were enough ([§3, §5.4](https://arxiv.org/abs/2305.15778)). KaijuFlow will have tens to hundreds of failures. A few hundred short casebook entries fit in one prompt.

So the first version needs no embeddings, no search index and no fine-tuning. Fine-tuning also goes stale ([Chen et al., §1](https://arxiv.org/abs/2305.15778)). Use exact fields to find candidates, and let Claude read the whole package. This is what the simple setups in [Bi et al.](https://arxiv.org/abs/2610.35767) did. Add embeddings only if the casebook outgrows one prompt.

### The routine, per failure (fail or check miss)

1. **Gather the evidence with code, not the agent** (like RCACopilot's handlers and Meta's DrP analyzers). From the check folder, build one **evidence package** per failure:
   - the title's outcome in `raw.json`: `why`, `release`, `checked`, `check_misses`;
   - the visit's step lines: `play_check`, `played`, `play_failed`, `list_filter`;
   - AltMount's import lines;
   - the scrubbed container log lines for that title;
   - the check's `meta.json` commit and `settings.json`.

   Keep the exact log lines. Do not let a model paraphrase them, because the quotes in step 4 are checked against them.
2. **Compute a signature with code.** A signature is a few exact fields: the outcome kind (fail, check miss), the step where it failed, AltMount's refusal reason or error text with numbers and names stripped out, the kind of release (season pack, archive type), the indexer slug and the commit. This plays the role of RCACopilot's "alert type", which picks the handler ([§4.1](https://arxiv.org/abs/2305.15778)).
3. **Match, then confirm with the cause's own test.**
   - **Matched and confirmed.** For each casebook entry whose signature matches, run that entry's confirming test on this failure's evidence. A confirmed match is a **known cause**, and the report names it with no model in the loop.
   - **Matched but not confirmed.** A match whose test says no is *not* a match. Record it as "looked like case N, but case N's test said no". This is the evidence-first rule from Riddell et al. ([Observation 10](https://arxiv.org/abs/2601.22208)).
4. **Diagnose what is left with a fixed routine.** For an unmatched or unconfirmed failure, Claude gets the evidence package, the whole casebook, and these rules:
   - List two or three candidate causes, including "a known case, changed", and "new", which is RCACopilot's "Unseen incident" option.
   - For each candidate, quote the exact evidence lines that support it and the lines that would contradict it. Code then checks that every quote is really in the package, and throws out any candidate that quotes something which is not there (RCAgent's filter).
   - Check the time order: a cause must come before its effect (Riddell et al.).
   - Pick one candidate, or answer **"not enough evidence: here is what to capture next time"**. The second is a valid answer (Roy et al.'s "Insufficient Evidence").
   - Propose the **confirming test**: a check over the captured log lines, kept as a fixture so it can be re-run, plus a **drill-down** that plays the title again live after the fix.

   Run the diagnosis twice. If the two runs name different causes, treat the result as "not enough evidence" (RCAgent's majority vote, cut to two runs at this scale).
5. **Prove before storing** (FLASH's rule). The entry enters the casebook only when two things hold:
   - its confirming test passes on this failure's captured evidence and fails on a captured failure with a different cause;
   - the fix's drill-down plays the title.

   Until then the failure stays an **open case**: its evidence, the agent's best guess marked as unproved, and the ticket text the report already writes.
6. **Write the entry.** Each entry holds:
   - the signature;
   - a one-paragraph plain description;
   - the cause;
   - the quoted evidence lines;
   - the confirming test (command and fixture);
   - the ticket and the fix commit;
   - the date first seen and the date last matched;
   - three counts: how often it matched, how often its test confirmed, how often its test said no.

   FLASH's study of faulty guides suggests that an entry should be complete and runnable on its own, with no "see the other entry" ([§4.4](https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf)).

   The counts copy ACE's helpful and harmful counters and ExpeL's votes ([§3.1](https://arxiv.org/abs/2510.04618), [§4.2](https://arxiv.org/abs/2308.10144)). Plain text in the repository keeps every entry readable and correctable by a person ([ExpeL §4.5](https://arxiv.org/abs/2308.10144)).

### Keeping the casebook correct

- **Who writes:** the agent drafts. The confirming test decides whether a cause is proved, as DrP's backtesting does for analyzers. A second reviewer agent then reads the draft against `docs/agents/review-standards.md`, and the owner accepts it in plain words. RCACopilot also has people review every new category ([§4](https://arxiv.org/abs/2305.15778)).
- **Merging duplicates:** when one failure is confirmed by two entries' tests, flag those two entries to be merged. Because entries are looked up by exact signature, overlapping tests are a clearer sign of a duplicate than similar wording. Wording similarity is ACE's method, which suits a list too large to read ([§3.2](https://arxiv.org/abs/2510.04618)). Merge by editing one entry in place and pointing the other at it. Never rewrite the whole casebook: ACE's "context collapse" warning ([§2.2](https://arxiv.org/abs/2510.04618)).
- **Retiring:** an entry whose fix has shipped is marked **fixed in <commit>**, not deleted. RCACopilot keeps versions too ([§4.1.1](https://arxiv.org/abs/2305.15778)). A later confirmed match of a fixed entry is reported as a **regression**. An entry whose test says no far more often than it confirms has a test that no longer fits the code: send it back for review, as ExpeL removes insights at zero ([§4.2](https://arxiv.org/abs/2308.10144)).
- **Recency:** at this scale every entry is read, so no time decay is needed in a search. But show the agent each entry's last-matched date and fix commit, because RCACopilot found that repeats cluster in time ([Insight 2](https://arxiv.org/abs/2305.15778)) and KaijuFlow's code changes between checks.

### Guardrails, in one list

1. No cause enters the casebook without a passing confirming test and a drill-down.
2. Every claim quotes evidence lines, and code checks that each quote exists.
3. "Not enough evidence" and "new, unseen" are always allowed. Count them in the report; never hide them.
4. Report the steps that passed (matched, test confirmed, drill-down played), not a confidence percentage. A calibrated percentage needs many labelled cases to fit ([PACE-LM §4–5](https://arxiv.org/abs/2309.05833)), and KaijuFlow will not have them for a long time.
5. Watch for anchoring on the casebook. Retrieval made answers "plausible based on historical incidents but incorrect" ([Roy et al.](https://arxiv.org/abs/2403.04123)). The agent must name what in this failure's evidence would contradict the matched case.

### What to measure, so "faster and smarter" can be shown

Per check, report:

- how many failures were known causes confirmed with no model;
- how many were diagnosed and proved;
- how many stayed open, and how many of those were "not enough evidence";
- how many matches a test disproved;
- the time from the end of the check to a named cause.

The published gains come from comparing with and without past cases ([Chen et al.](https://arxiv.org/abs/2305.15778), [Zhang et al.](https://arxiv.org/abs/2401.13810)). The same comparison here is the share of failures the casebook settles without the agent, check after check.

## Sources

- Chen et al., RCACopilot, EuroSys 2024: https://arxiv.org/abs/2305.15778
- Ahmed et al., ICSE 2023: https://arxiv.org/abs/2301.03797
- Zhang et al., GPT-4 in-context root causing, FSE 2024: https://arxiv.org/abs/2401.13810
- Zhang et al., PACE-LM confidence estimation, FSE 2024: https://arxiv.org/abs/2309.05833
- Roy et al., ReAct agents for root cause analysis, 2024: https://arxiv.org/abs/2403.04123
- Wang et al., RCAgent, CIKM 2024: https://arxiv.org/abs/2310.16340
- Zhang et al., FLASH, 2024: https://www.microsoft.com/en-us/research/wp-content/uploads/2024/10/FLASH_Paper.pdf (page: https://www.microsoft.com/en-us/research/?p=1090611)
- Pei et al., Flow-of-Action, WWW 2025: https://arxiv.org/abs/2502.08224
- Meta, "Leveraging AI for efficient incident response", 2024: https://engineering.fb.com/2024/06/24/data-infrastructure/leveraging-ai-for-efficient-incident-response/
- Meta, "DrP: Meta's Root Cause Analysis Platform at Scale", 2025: https://engineering.fb.com/2025/12/19/data-infrastructure/drp-metas-root-cause-analysis-platform-at-scale/
- Xu et al., OpenRCA, ICLR 2025: https://proceedings.iclr.cc/paper_files/paper/2025/file/d29b8d53678015079e1d245c023e49d2-Paper-Conference.pdf
- Riddell et al., "Stalled, Biased, and Confused", FORGE 2026: https://arxiv.org/abs/2601.22208
- Lu et al., "Beyond Fault Localization", 2026: https://arxiv.org/abs/2608.21310
- Bi et al., "Free to Look, Free to Reason", 2026: https://arxiv.org/abs/2610.35767
- Zhao et al., ExpeL, AAAI 2024: https://arxiv.org/abs/2308.10144
- Zhang et al., ACE, ICLR 2026: https://arxiv.org/abs/2510.04618
