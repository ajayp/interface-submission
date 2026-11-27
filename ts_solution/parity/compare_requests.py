"""Diffs the HTTP requests the Python system and the TS port send for the same answer call and the same Decisions call.
A local mock server records them (no network, no cost). Usage: compare_requests.py"""
import json, os, subprocess, sys, threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
log = []

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", 0))) or b"null")
        log.append({"src": os.environ.get("SRC"), "path": self.path, "body": body, "headers": {k.lower(): v for k, v in self.headers.items()}})
        out = ({"answers": []} if "decisions" in self.path else
               {"id": "r", "object": "response", "status": "completed", "model": "m",
                "output": [{"type": "message", "id": "m", "role": "assistant", "status": "completed",
                            "content": [{"type": "output_text", "text": '{"answer":"x","confident":true,"used_excerpts":[1],"conflict_note":null}', "annotations": []}]}],
                "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2, "input_tokens_details": {"cached_tokens": 0}, "output_tokens_details": {"reasoning_tokens": 0}}})
        data = json.dumps(out).encode()
        self.send_response(200); self.send_header("content-type", "application/json"); self.send_header("content-length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def log_message(self, *a): pass

srv = HTTPServer(("127.0.0.1", 0), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = f"http://127.0.0.1:{srv.server_port}/v1"
env = {**os.environ, "OPENAI_BASE_URL": base, "OPENAI_API_KEY": "test-key"}

# Python side: the same calls the system makes
os.environ.update(env); os.environ["SRC"] = "py"
sys.path.insert(0, str(ROOT / "my_solution"))
from llm import AnswerLLM
from decisions_understanding import DecisionsUnderstanding
from prompt import build_user_message, developer_message_for
q = "What is the routing number?"
msg = build_user_message(q, [{"n": 1, "page_type": "product_page", "url": "https://www.dupaco.com/x", "text": "Dupaco's routing number is 273976369."}], None)
llm = AnswerLLM()
llm.ask(msg, instructions=developer_message_for(q, "fact_about_dupaco"))
try: DecisionsUnderstanding(llm)._decide(q)
except Exception: pass   # the mock returns no labels; only the request matters

# TS side
env["SRC"] = "ts"
os.environ["SRC"] = "ts"
subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(ROOT / "ts_solution/parity/capture_ts.ts")], env=env, cwd=ROOT / "ts_solution", check=False, capture_output=True)

def norm(x):  # the input id differs by construction (a hash of the request); everything else must match
    import re
    s = json.dumps(x, sort_keys=True, ensure_ascii=False)
    for n in set(re.findall(r"Input id: ([0-9a-f]{12})", s)):
        s = s.replace(n, "NONCE")
    return json.loads(s)
def find(src, kind):
    return next(r for r in log if r["src"] == src and (kind in r["path"]))
for kind in ("responses", "decisions"):
    a, b = find("py", kind), find("ts", kind)
    pa, pb = norm(a["body"]), norm(b["body"])
    print(f"== {kind}: body {'IDENTICAL' if pa == pb else 'DIFFERS'}")
    for k in sorted(set(pa) | set(pb)):
        if pa.get(k) != pb.get(k): print(f"   body key '{k}': python={json.dumps(pa.get(k))[:120]}  ts={json.dumps(pb.get(k))[:120]}")
    ha, hb = a["headers"], b["headers"]
    for k in sorted(set(ha) | set(hb)):
        if k.startswith("x-stainless") or k in ("user-agent", "content-length", "host", "authorization"): continue
        if ha.get(k) != hb.get(k): print(f"   header '{k}': python={ha.get(k)}  ts={hb.get(k)}")
print("python-only extras: service_tier ->", "service_tier" in find("py", "responses")["body"], "| ts has service_tier ->", "service_tier" in find("ts", "responses")["body"])
a, b = norm(find("py", "responses")["body"]), norm(find("ts", "responses")["body"])
print("PY schema:", json.dumps(a["text"], sort_keys=True))
print("TS schema:", json.dumps(b["text"], sort_keys=True))
print("other keys equal:", all(a[k] == b[k] for k in a if k not in ("text", "service_tier")), sorted(k for k in a if k != "input" and k != "instructions"))
