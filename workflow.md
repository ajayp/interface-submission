# Workflow

How the submission in `my_solution/` works, as diagrams that follow the code: loading the snapshots (`ingest`),
answering one question (`answer`), and listing contradictions (`conflicts`). The written description is in `NOTES.md`.

## 1. Loading the snapshots (`ingest`, once per snapshot, untimed)

The scorer calls `ingest` five times, oldest snapshot first.

```mermaid
flowchart TD
    S[One website snapshot<br/>about 635-705 pages] --> SPLIT[Split each page by heading<br/>every table row is its own piece]
    SPLIT --> BM[Keyword index BM25<br/>one per snapshot]
    SPLIT --> VOC[Site vocabulary: lowercase words with counts<br/>for spelling help, no model call]
    S --> RANK[Page trust, from the page address<br/>rate sheet > product page > promotion page > everything else]
    S --> TABLES[Every distinct rate table]
    TABLES --> LLM1[[gpt-6-luna reads each table once<br/>about 300 calls, one per distinct table]]
    LLM1 --> FACTS[Facts: product, term, tier, rate type, value,<br/>page, page type, dates, snapshot]
    FACTS --> FIDX[Fact index<br/>one per snapshot]
    S --> COUNTS[Counts about Dupaco<br/>branches, employees, members, assets, counties]
    SPLIT --> WIN[600-character windows cut from those pieces<br/>a new window every 400 characters]
    WIN --> WIDX[Window index, one per snapshot<br/>built while loading, so no timed answer pays for it]
    EMB[(Embedding vectors<br/>read from the committed my_solution/.embed_cache)] -.looked up, never computed.-> WIDX
```

The windows are cut from the same pieces the keyword index uses, so a window can lose the heading that says what it is (the lobby-hours miss,
dup-104). Nothing is embedded during `ingest` in the default mode: the vectors were built beforehand and are committed, and the window index
is assembled from them while loading. A window whose vector is not in the file is never embedded while answering; if any window of a snapshot is
missing, window search is switched off for that snapshot with no warning, and the question gets keyword pieces only. The vectors cover all five
website copies. If the snapshots change, they must be rebuilt (the build script is not part of this hand-in).

## 2. Answering one question (`answer`, timed)

Boxes with double edges are calls to OpenAI. Answer calls ask for OpenAI's faster service tier and are retried once on the default tier if the account refuses it. A normal question makes three calls: the labels, the question's embedding (sent at the same time as the labels) and one answer call. A rate or fee question the rate tables don't answer makes a fourth, when it falls back to text search. A count question ("how many branches") is answered by code, with no answer call. The embedding is only used when windows are searched, so not for a rate or fee question, and not when the vectors are missing.

### 2a. Which website copy answers

```mermaid
flowchart TD
    Q([Question, optional as_of date]) --> LAB[[Decisions API: labels<br/>section, rate type, date?, change?, question type]]
    LAB --> CHG{About a change?}
    CHG -- yes --> HIST[Same search in every snapshot<br/>each value tagged with the dates it was seen]
    HIST --> HANS[[Model answers with the history<br/>e.g. 3.90% in May-Aug, 4.00% in Sep]]
    HANS --> HOK{Confident?}
    HOK -- yes --> OUT([Answer: text, sources, confident flag])
    HOK -- no --> DATE
    CHG -- no --> DATE{Is a date asked?}
    DATE -- before 2026-05-12 --> IDK1([I don't know: no snapshot that old])
    DATE -- yes --> PAST[Latest snapshot on or before that date<br/>answer starts 'As of date,']
    DATE -- no --> NEW[Newest snapshot, 2026-09-28]
    PAST --> NEXT([Continue with 2b])
    NEW --> NEXT
```

- **A change question** is one where the label says so and the question has a change word such as changed, before or since. The search is cut off at `as_of` if one is given; a date written in the question does not cut it off. For page text, not rates or fees, each copy also adds its meaning-search windows.
- **A date is asked** when `as_of` is given, or when the question contains a date and either the label says it is about the website on that date or the words say so ("as of", "back in", "at the end of", or a past-tense question on any topic).
- **A month with no year** means the latest such month not after the newest copy. A rate or fee question with a month and no year counts as dated even without a past-tense verb, unless it looks forward (will, if I, next).
- **A dated answer** starts "As of <date>," and says when the year was assumed. A change question does not get that start, because its date is the start of a comparison.

### 2b. How the answer is produced

```mermaid
flowchart TD
    START([Question and chosen snapshot]) --> CACHE{Asked before in this run?}
    CACHE -- yes --> SAME([Same answer as before])
    CACHE -- no --> CNT{How-many question about Dupaco?}
    CNT -- yes --> CNTA([Count from the most recently published statement, no model call])
    CNT -- no --> VAL{Rate or fee question?}

    VAL -- yes --> FH[Search the fact index<br/>keep only the winning value per product and tier]
    FH -- no fact found --> TXT
    FH --> FANS[[Model answers from the facts]]
    FANS --> FOK{Confident?}
    FOK -- yes --> OUT
    FOK -- no, fall back --> TXT

    VAL -- no --> TXT[Text search<br/>8 keyword pieces plus meaning-search windows]
    EMB[[Embed the question]] -.vector.-> TXT
    SP[Spelling help<br/>adds the site word one edit away] -.-> TXT
    SP -.-> FH
    TXT --> TANS[[Model answers from the pieces<br/>one value, right tier, or I don't know]]
    TANS --> CHECK{Checks pass?}
    CHECK -- no --> IDK2([I don't know, please contact Dupaco])
    CHECK -- yes --> CITE[Cite the pages used<br/>plus other pages stating the same value]
    CITE --> OUT([Answer: text, sources, confident flag])
```

- **Text search** keeps 8 keyword pieces, with 2 slots reserved for lower-trust pages, and adds meaning-search windows: 3 for most questions, 6 for list, eligibility and fact-about-Dupaco questions, none for rate or fee questions.
- **Spelling help:** a typed word the site does not use adds the site word one edit away, to the search text only. The model still sees the question as typed.
- **The checks** turn the answer into the standard refusal when the model says it cannot answer, or when a value was asked for and the answer has no new number. On the facts path, a failed check also counts as "not confident", so the text search runs.

## 3. Listing contradictions (`conflicts`, once at the end)

Only the newest snapshot is read. A value that changed between snapshots, with no old copy left in the newest one, is history,
not a conflict, and is not listed.

```mermaid
flowchart TD
    N[Newest snapshot] --> T[Rate tables read by code, cell by cell]
    N --> SEN[Sentences that state a rate]
    SEN --> SL[[gpt-6-luna labels each sentence once, read together with<br/>the sentence or line before it; about 77 calls]]
    N --> CT[Counts about Dupaco: branches, employees, members,<br/>assets, counties. Fixed sentence patterns]
    T --> MATCH{Same fact?<br/>rate type, term, tier, model years<br/>and product words agree<br/>never decided by the numbers}
    SL --> MATCH
    MATCH -- two or more values --> WINR[Pick the winner:<br/>rate sheet > product page > promotion > other,<br/>then later effective date, then later fetch date;<br/>an offer the page says has ended always loses]
    CT --> LATEST[Most recently published count wins]
    WINR --> C([Conflict: topic, values, sources,<br/>resolution, reason])
    LATEST --> C
```
