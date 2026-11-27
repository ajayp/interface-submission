# Lessons (TypeScript port)

- 2026-11-27: Never send OpenAI's fast/priority tier (`service_tier`). The Python `llm.py` requests it; the user said not to use it in the TS port, so the TS client has no such option at all (and the code that retried without it was dropped).
- 2026-11-27: Ports must be checked stage by stage against the original on real data, not just run end to end: the stemmer in the installed PyStemmer differs from the textbook Porter2 (read the current `english.sbl`), and JS `.` does not match U+2028 while Python's does (one heading line lost half its text).
- 2026-11-27: `new Set`/object key order and `list.index()` equality (dataclass equality) differ between languages; compare by content, and keep ordered pairs where Python used a dict (qualifiers).
- 2026-11-27: Heredoc-heavy shell commands were twice refused by the safety check even though they deleted nothing; writing files with the Write tool avoids it.
