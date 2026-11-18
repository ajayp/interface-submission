# Workflow

How the submission in `my_solution/` works, as three diagrams that follow the code: loading the snapshots (`ingest`),
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

Boxes with double edges are calls to OpenAI. Answer calls ask for OpenAI's faster service tier and are retried once on the default tier if the account refuses it. A normal question makes three: the labels, the question's embedding (sent at the same
time as the labels) and one answer call. A rate or fee question the rate tables don't answer makes a fourth, when it falls back to
text search. A count question ("how many branches") is answered by code, with no answer call. The question's embedding is sent for every
question but is only used when windows are searched (not for a rate or fee question, and not when the vectors are missing).

```mermaid
flowchart TD
    Q([Question, optional as_of date]) --> LAB[[Decisions API: labels<br/>section, rate type, past date?, change?, question type]]
    Q -.same time.-> QE[[Embed the question]]
    LAB --> CHG{About a change?<br/>label says so AND the question has a<br/>change word: changed, before, since...}

    CHG -- yes --> HIST[Same search in every snapshot<br/>cut off at as_of if given; a date in the question text does not cut it off<br/>each value tagged with the snapshot dates it was seen in<br/>for page text, not rates or fees, each copy also adds its meaning-search windows]
    HIST --> HANS[[gpt-6-luna answers with the history<br/>e.g. 3.90% in May-Aug, 4.00% in Sep]]
    HANS --> HOK{Confident?}
    HOK -- yes --> OUT
    HOK -- no --> DATE

    CHG -- no --> DATE{Which snapshot?}
    DATE -- date before 2026-05-12 --> IDK1([I don't know: no snapshot that old])
    DATE -- "as_of, or a date in the text AND (the label says<br/>it is about the website on that date, or the words say so:<br/>'as of / back in / at the end of', or a past-tense question on any topic)<br/>a month with no year = the latest such month not after the newest copy<br/>a rate or fee question with a month and no year counts without a past-tense verb unless it looks forward (will / if I / next)" --> PAST[Latest snapshot taken on or before that date]
    DATE -- no date --> NEW[Newest snapshot 2026-09-28]
    PAST --> SD[Answer starts 'As of date,' and says when the year was assumed<br/>not on a what-changed question]
    SD --> CACHE
    NEW --> CACHE{Asked before in this run?}
    CACHE -- yes --> SAME([Same answer as before])
    CACHE -- no --> CNT{How-many question<br/>about Dupaco?}
    CNT -- yes --> CNTA([Count from the most recently<br/>published statement, no model call])
    CNT -- no --> VAL{Rate or fee question?}

    VAL -- yes --> FH[Search the fact index<br/>keep only the winning value per product and tier]
    FH -- no fact found --> TXT
    FH --> FANS[[gpt-6-luna answers from the facts<br/>same checks as the text answer]]
    FANS --> FOK{Confident?<br/>not confident also when a check fails}
    FOK -- yes --> OUT
    FOK -- "no (fallback)" --> TXT

    VAL -- no --> TXT[Text search: 8 keyword pieces<br/>2 slots kept for lower-trust pages<br/>+ meaning-search windows: 3 for most questions,<br/>6 for list, eligibility and fact-about-Dupaco, none for rate or fee]
    QE -.vector.-> TXT
    SP[Spelling help: a typed word the site does not use<br/>adds the site word one edit away to the search text only] -.-> TXT
    SP -.-> FH
    TXT --> TANS[[gpt-6-luna answers from the pieces<br/>prompt G2: one value, right tier, or I don't know]]
    TANS --> CHECK{Checks:<br/>model says none or not confident?<br/>value asked but no new number?}
    CHECK -- fails --> IDK2([I don't know, please contact Dupaco])
    CHECK -- passes --> CITE[Cite the pages used,<br/>plus other pages stating the same value]
    CITE --> OUT([Answer: text, sources, confident flag])
```

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
