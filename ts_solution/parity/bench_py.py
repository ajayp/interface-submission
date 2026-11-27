"""Micro-benchmark of the Python client (openai SDK) with the SAME calls as bench_ts.ts. Usage: bench_py.py [N]
Answer calls are measured twice: as the Python system makes them (service_tier=priority) and without it (the default tier)."""
import json, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "my_solution"))
from llm import AnswerLLM
from decisions_understanding import DecisionsUnderstanding
from prompt import ANSWER_SCHEMA, build_user_message, developer_message_for

n = int(sys.argv[1]) if len(sys.argv) > 1 else 10
def stats(xs):
    s = sorted(xs)
    return {"first_ms": round(xs[0]), "rest_mean_ms": round(sum(xs[1:]) / max(1, len(xs) - 1)), "median_ms": round(s[len(s) // 2]), "max_ms": round(s[-1])}
def timed(f):
    t = time.perf_counter(); f(); return (time.perf_counter() - t) * 1000

llm = AnswerLLM()
dec = DecisionsUnderstanding(llm)          # no warm-up here: the first call includes connection setup, like the TS benchmark
dec_ms = [timed(lambda i=i: dec._decide(f"What is the rate for a {12 + i}-month certificate this week?")) for i in range(n)]
def msg(i):
    q = f"What is the routing number? (variant {i})"
    m = build_user_message(q, [{"n": 1, "page_type": "product_page", "url": "https://www.dupaco.com/x", "text": "Dupaco's routing number is 273976369."}], None)
    return q, m
fast = [timed(lambda i=i: llm.ask(msg(i)[1], instructions=developer_message_for(msg(i)[0], "fact_about_dupaco"))) for i in range(n)]   # priority tier, as the system does
plain = [timed(lambda i=i: llm.ask_json(developer_message_for(msg(i)[0], "fact_about_dupaco"), msg(i + 100)[1], ANSWER_SCHEMA, "member_answer",
                                         "dupaco-answer-v1", max_tokens=600, timeout=6)) for i in range(n)]                               # timeout given -> no priority tier
print(json.dumps({"client": "python-sdk", "decisions": stats(dec_ms), "answer_priority_tier": stats(fast), "answer_default_tier": stats(plain)}))
