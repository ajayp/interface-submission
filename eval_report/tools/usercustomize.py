"""Spend ledger for the independent evaluation. Loaded automatically by Python when this folder is on PYTHONPATH and
EVAL_LEDGER is set; it never changes what a call sends or returns.

Every OpenAI call made through the `openai` package (Responses, Decisions, Embeddings) appends one JSON line to $EVAL_LEDGER:
  {"tag": $EVAL_TAG, "api": ..., "model": ..., "name": json-schema name (responses only), "in": input tokens, "cached": ...,
   "out": output tokens, "chars": characters of the input text, "tier": service tier returned, "s": seconds}
`ledger.py` turns the file into dollars. It is a `usercustomize` (not `sitecustomize`) so the container's own sitecustomize still runs.
"""
import json
import os
import threading
import time

_PATH = os.environ.get("EVAL_LEDGER")
_LOCK = threading.Lock()


def _write(row):
    row["tag"] = os.environ.get("EVAL_TAG", "")
    line = json.dumps(row) + "\n"
    with _LOCK:
        with open(_PATH, "a") as f:
            f.write(line)


def _usage(u, *names):
    for n in names:
        v = getattr(u, n, None) if u is not None else None
        if v is not None:
            return v
    return 0


def _install():
    from openai.resources.decisions import Decisions
    from openai.resources.embeddings import Embeddings
    from openai.resources.responses import Responses

    orig_resp, orig_emb, orig_dec = Responses.create, Embeddings.create, Decisions.create

    def resp_create(self, *a, **kw):
        t = time.time()
        r = orig_resp(self, *a, **kw)
        u = getattr(r, "usage", None)
        det = getattr(u, "input_tokens_details", None)
        inp = kw.get("input")
        fmt = ((kw.get("text") or {}).get("format") or {}) if isinstance(kw.get("text"), dict) else {}
        _write({"api": "responses", "model": kw.get("model"), "name": fmt.get("name"), "in": _usage(u, "input_tokens"),
                "cached": getattr(det, "cached_tokens", 0) or 0, "out": _usage(u, "output_tokens"),
                "chars": len(inp) if isinstance(inp, str) else None, "tier": getattr(r, "service_tier", None),
                "s": round(time.time() - t, 3)})
        return r

    def emb_create(self, *a, **kw):
        t = time.time()
        r = orig_emb(self, *a, **kw)
        u = getattr(r, "usage", None)
        inp = kw.get("input")
        _write({"api": "embeddings", "model": kw.get("model"), "in": _usage(u, "total_tokens", "prompt_tokens"), "cached": 0,
                "out": 0, "n": len(inp) if isinstance(inp, list) else 1, "s": round(time.time() - t, 3)})
        return r

    def dec_create(self, *a, **kw):
        t = time.time()
        r = orig_dec(self, *a, **kw)
        u = getattr(r, "usage", None)
        det = getattr(u, "input_tokens_details", None)
        _write({"api": "decisions", "model": kw.get("model"), "in": _usage(u, "input_tokens", "prompt_tokens"),
                "cached": getattr(det, "cached_tokens", 0) or 0, "out": _usage(u, "output_tokens", "completion_tokens"),
                "s": round(time.time() - t, 3)})
        return r

    Responses.create, Embeddings.create, Decisions.create = resp_create, emb_create, dec_create


if _PATH:
    try:
        _install()
    except Exception as e:  # never break a run because of the ledger
        import sys
        print(f"[eval ledger] not installed: {type(e).__name__}: {e}", file=sys.stderr)
