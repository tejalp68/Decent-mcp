"""Token counting helper.

Uses tiktoken (cl100k_base) when it can load its encoding; otherwise falls back to
a rough estimate of 1 token per 4 characters. `token_method()` says which one is active
so the README numbers can be labelled honestly.
"""
import math

_enc = None
_method = None


def _load():
    global _enc, _method
    if _method is not None:
        return
    try:
        import tiktoken
        _enc = tiktoken.get_encoding("cl100k_base")
        _method = "tiktoken cl100k_base"
    except Exception:
        _enc = None
        _method = "estimate (chars / 4)"


def count_tokens(text: str) -> int:
    _load()
    if _enc is not None:
        return len(_enc.encode(text))
    return math.ceil(len(text) / 4)


def token_method() -> str:
    _load()
    return _method
