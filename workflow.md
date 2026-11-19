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
    CACHE[(Saved window vectors<br/>my_solution/.embed_cache/windows-text-embedding-3-small.npz<br/>one vector per window text)] -.read.-> CHK
    WIN --> CHK{Does every window already<br/>have a saved vector?}
    CHK -- yes --> WIDX[Window index, one per snapshot<br/>built while loading, so no timed answer pays for it]
    CHK -- some are missing --> EMB[[text-embedding-3-small embeds only the missing windows<br/>and they are saved back to the file]]
    EMB --> WIDX
    EMB -.->|new vectors saved| CACHE
    EMB -.->|no key or error| OFF[Meaning search is off for this snapshot<br/>no API key, or the embedding call failed<br/>keyword pieces only, a warning is printed]
```

**What the saved vectors are.** A vector (an embedding) is a list of numbers that stands for the meaning of a piece of text. It is what lets the program find a window by meaning when the question uses different words from the page. One vector per window is kept in the `.npz` file, filed under a hash of the window's text. That has two effects: a paragraph that appears on all five website copies is embedded once, and when the site changes, only the windows whose text changed have no vector.

The windows are cut from the same pieces the keyword index uses, so a window can lose the heading that says what it is (the lobby-hours miss,
dup-104).

The committed file already holds the vectors for all five website copies, so a normal run embeds nothing: `ingest` reads the file and builds the
window index from it (about 2.5 s per snapshot). If the file is missing, or the site has changed so that some windows have no vector, `ingest` embeds
just those windows with `text-embedding-3-small` and saves them to the file, so the next run skips them. This happens only in `ingest`, which is
untimed. A window is never embedded while answering. It needs `OPENAI_API_KEY` and a writable `.embed_cache` folder (if the folder is read-only the
vectors are used for that run but not saved). If the key is missing or the embedding call fails, window search is switched off for that snapshot, a
warning says how many windows had no vector, and the question gets keyword pieces only. `MY_SOLUTION_EMBED_MISSING=0` turns the embedding step off.

**The facts are re-read on every cold run.** The table-reading calls are cached in memory only, unless `MY_SOLUTION_FACT_CACHE=<file>` is set, which saves them to that file so a later run skips the roughly 300 calls. By default it is not set, so a normal load pays the 3 minutes and about $0.10. A failed table call is not cached, so a later run retries it. The window vectors are different: they are committed, so a run embeds nothing.

## 2. Answering one question (`answer`, timed)

Boxes with double edges are calls to OpenAI. A normal question makes three calls: the labels, the question's embedding (sent at the same time as the labels) and one answer call. A rate or fee question the rate tables don't answer makes a fourth, when it falls back to text search. A count question ("how many branches") is answered by code, with no answer call. The embedding is only used when windows are searched, so not for a rate or fee question, and not when the vectors are missing.

### 2a. Which website copy answers

```mermaid
flowchart TD
    Q([Question, optional as_of date]) --> LAB[[Decisions API labels: section, rate type, date?, change?, intent]]
    LAB -. fails .-> NOLAB[Labels call failed: 3 s timeout, one retry<br/>search runs on the plain question<br/>dates are still read by code from the wording]
    NOLAB --> DATE
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

    VAL -- yes --> FH[Search the fact index<br/>keep only the winning value per product and tier<br/>top 12, the rate type asked for first]
    FH -- no fact found --> TXT
    FH --> FANS[[Model answers from the facts]]
    FANS --> FOK{Confident?}
    FOK -- yes --> OUT
    FOK -- no, fall back --> TXT

    VAL -- no --> TXT[Text search<br/>8 keyword pieces plus meaning-search windows]
    EMB[[Embed the question]] -.vector.-> TXT
    SP[Spelling help<br/>adds the site word one edit away] -.-> TXT
    SP -.-> FH
    SYN[Synonym list, hand-written<br/>adds the other words of a matching group at half weight] -.-> TXT
    SYN -.-> FH
    LBL[Labels from 2a<br/>section: boosts pages of that section in the keyword search<br/>intent: picks the prompt block and the number of windows<br/>rate type: picks the APR, APY or dividend column] -.-> TXT
    LBL -.-> FH
    SP -.looked up.-> SYN
    TXT --> TANS[[Model answers from the pieces<br/>one value, right tier, or I don't know]]
    FANS -. fails .-> ERR
    TANS -. fails .-> ERR([Answer call failed: 6 s timeout, one retry<br/>says the model did not respond, not cached<br/>never shown as I don't know])
    TANS --> CHECK{Checks pass?}
    CHECK -- no --> IDK2([I don't know, please contact Dupaco])
    CHECK -- yes --> CITE[Cite the pages used<br/>plus other pages stating the same value]
    CITE --> OUT([Answer: text, sources, confident flag])
```

- **Text search** (`MY_SOLUTION_HYBRID=windows`, the default; 0 turns meaning search off, and `fuse` and `append` are experiments that are off) keeps 8 keyword pieces, with 2 slots reserved for lower-trust pages, and adds meaning-search windows: 3 for most questions, 6 for list, eligibility and fact-about-Dupaco questions, none for rate or fee questions.
- **Spelling help:** a typed word the site does not use adds the site word one edit away, to the search text only. It also merges a split word ("sav ings") and splits a run-together one ("moneymarket") when both halves are common site words. It only adds words; the member's own words stay, and the model still sees the question as typed. Guards stop wrong corrections: a word is left alone if it is a stop word, has fewer than 5 letters, or the site uses it 3 or more times; a candidate must start with the same letter, appear on the site at least 5 times and at least 10 times as often as the typed word, and be one edit away (two for words of 9 or more letters; a swap of neighbours counts as one). Numbers are never touched. No model call. `MY_SOLUTION_SPELLFIX=0` turns it off.
- **Synonym list:** a hand-written list of word groups that members and the site use for the same thing (for example CD and certificate). When any phrase of a group is in the question, the group's other phrases are added to the keyword search at half the weight of the member's own words (`SYNONYM_WEIGHT = 0.5`), for both the text search and the fact search. Words added by spelling help are looked up too, so a typo that is fixed also gets its synonyms. No model call, and the model still sees the question as typed.
- **Fact search (rate and fee questions):** a keyword search over the extracted facts, with the same section boost and synonyms. The facts that state the same value are grouped, and only the winning one is kept: the most trusted page type first, then the latest effective date, then the latest publish date. The top 12 go to the model, with facts of the rate type asked for (rate, APR or APY) sorted to the front. Nothing is removed by that sort, and nothing changes when no fact of that type was found. This is why a stale value never reaches the model, and the model picks the right tier from these 12.
- **Labels steer, they do not decide.** The section label boosts pages of that section in the keyword search (weight 10), and only the top section is used, and only at probability 0.5 or more. The intent label adds a prompt block for that question type (hours, list or eligibility, how-to, facts about the credit union) and sets the window count above. The rate type label picks the APR, APY or dividend column when a table shows several. The section label is right about 78% of the time on my check, which is why it only steers.
- **Code checks back up the labels.** A date counts only if the label or the wording says so ("as of", "back in", a past-tense rate question) and the question contains a date. A change counts only if the label says so and the question has a change word, and it does not apply to "what was it before <date>". A "dividend rate" label becomes APY unless the question says "dividend". With no labels at all, the date still comes from the wording and the change path is not used.
- **If the labels call fails** (3 s timeout, one retry), the search runs on the plain question: no section boost, no intent prompt block, and no synonym expansion, because the synonym words travel with the labels result. Spelling help still adds its corrected words to the search text, but without labels they get no synonyms. Answers get worse on some questions but never fail.
- **If the answer call fails** (6 s timeout, one retry), the reply is not turned into "I don't know". The text says the model did not respond, `conflict_note` names the error, and the answer is not cached. A fake refusal would earn credit on should-refuse questions that the system never made. On the facts path, a failed call also counts as "not confident", so the text search runs.
- **The question is data, not instructions.** It is wrapped in a `<question>` tag carrying a per-call input id, and the prompt says only tags with that id are real and that everything inside them is data: if the text tells the model to change how it answers, the model ignores it.
- **What the model sees and returns.** Each excerpt arrives with its page type, URL, effective date and published date. On a dated question it also gets the question date. The model returns an answer, the sources it used, and an answer type: `complete`, `partial` or `none`. Only `none` (or no confidence when the type is missing) becomes the refusal; `partial` answers are kept. For a rate or fee answer that gives the value, sentences that only say something "isn't listed" are removed (`MY_SOLUTION_STRIP_NOT_LISTED`).
- **Two special-case rules, both general and both on by default.** "Are the hours the same at every branch?" adds up to 5 extra pieces that state a lobby or drive-up schedule (the branch-finder cards otherwise fill the top 8), and a prompt bullet makes the model answer "No" with each branch's schedule (`MY_SOLUTION_HOURS_SAME`, `MY_SOLUTION_HOURS_SCHEDULES`). A question asking which link or page shows a product's rates gets the product's own page rather than the sitewide rates page, when an excerpt from the product page is present (`MY_SOLUTION_LINK_PRODUCT`). Each can be turned off with 0.
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
