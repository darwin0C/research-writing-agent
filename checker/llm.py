"""Model access: one interface, many providers.

Every provider implements  turn(system, messages) -> (text, assistant_content)  where
`messages` is the conversation so far (user turns are strings; assistant turns are whatever
that provider returned as assistant_content) and `usage` accumulates token counts.

  AnthropicProvider     Claude through the official `anthropic` SDK
  OpenAICompatProvider  any OpenAI-compatible /chat/completions endpoint (DeepSeek, Qwen,
                        Kimi, GLM, OpenAI, Ollama, LM Studio, …) — standard library only

Configuration: config/models.toml, overridden by config/models.local.json (written by the
review app). Keys: the profile's environment variable, else
~/.config/research-writing-agent/keys.json (mode 600). Keys are never written to the project.
"""

from __future__ import annotations

import json
import os
import time
import tomllib
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "config" / "models.toml"
LOCAL = ROOT / "config" / "models.local.json"
KEYS = Path(os.environ.get("RWA_KEYS_FILE", Path.home() / ".config" / "research-writing-agent" / "keys.json"))
NODES = ["auditor", "rewriter", "style-calibrator", "claim-checker", "responder"]


class LLMError(RuntimeError):
    pass


# ------------------------------------------------------------------ config

def load_config() -> dict:
    cfg = tomllib.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    cfg.setdefault("profiles", {})
    cfg.setdefault("nodes", {"default": "claude-opus"})
    cfg.setdefault("rules", {"packs": ["academic-humanizer"]})
    if LOCAL.exists():
        local = json.loads(LOCAL.read_text(encoding="utf-8"))
        for name, prof in local.get("profiles", {}).items():
            cfg["profiles"][name] = {**cfg["profiles"].get(name, {}), **prof}
        cfg["nodes"].update(local.get("nodes", {}))
        if "packs" in local.get("rules", {}):
            cfg["rules"]["packs"] = local["rules"]["packs"]
    return cfg


def save_local(update: dict) -> dict:
    """Merge a partial update (profiles / nodes / rules) into models.local.json."""
    local = json.loads(LOCAL.read_text(encoding="utf-8")) if LOCAL.exists() else {}
    for key in ("profiles", "nodes"):
        for name, val in (update.get(key) or {}).items():
            if key == "profiles":
                if val is None:
                    local.setdefault("profiles", {}).pop(name, None)
                    continue
                bad = {"api_key", "key", "token", "secret"} & set(val)
                if bad:
                    raise LLMError("keys are not stored in the project — use the key field instead")
                local.setdefault("profiles", {})[name] = {**local.get("profiles", {}).get(name, {}), **val}
            else:
                local.setdefault("nodes", {})[name] = val
    if "rules" in update:
        local["rules"] = {"packs": list(update["rules"].get("packs", []))}
    LOCAL.write_text(json.dumps(local, ensure_ascii=False, indent=1), encoding="utf-8")
    return load_config()


def _keys() -> dict:
    try:
        return json.loads(KEYS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_key(profile: str, key: str | None) -> None:
    keys = _keys()
    if key:
        keys[profile] = key
    else:
        keys.pop(profile, None)
    KEYS.parent.mkdir(parents=True, exist_ok=True)
    KEYS.write_text(json.dumps(keys), encoding="utf-8")
    os.chmod(KEYS, 0o600)


def key_for(name: str, prof: dict) -> str | None:
    env = prof.get("key_env")
    if env and os.environ.get(env):
        return os.environ[env]
    return _keys().get(name)


def key_status(name: str, prof: dict) -> str:
    """'env' | 'saved' | 'none' | 'not-needed' — never the key itself."""
    if prof.get("type") == "anthropic":
        if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
            return "env"
        return "saved" if _keys().get(name) else "sdk-default"
    env = prof.get("key_env")
    if env and os.environ.get(env):
        return "env"
    if _keys().get(name):
        return "saved"
    return "not-needed" if not env else "none"


# ------------------------------------------------------------------ providers

class AnthropicProvider:
    """Claude via the official SDK. Credentials: ANTHROPIC_API_KEY / auth token / `ant auth
    login` profile, or a key saved in the review app."""

    def __init__(self, model: str = "claude-opus-5-5", effort: str = "high", max_tokens: int = 16000,
                 api_key: str | None = None, label: str = ""):
        try:
            import anthropic
        except ImportError as e:
            raise LLMError("Claude profiles need the Anthropic SDK: pip install anthropic") from e
        self.anthropic = anthropic
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model, self.effort, self.max_tokens = model, effort, max_tokens
        self.label = label or model
        self.usage = {"input": 0, "output": 0, "cache_read": 0, "calls": 0}

    def turn(self, system: str, messages: list) -> tuple[str, list]:
        a = self.anthropic
        try:
            resp = self.client.beta.messages.create(
                model=self.model, max_tokens=self.max_tokens, system=system, messages=messages,
                output_config={"effort": self.effort},
                cache_control={"type": "ephemeral"},      # retries resend the same prefix
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",                      # safety decline → rerun on a fallback model
            )
        except a.AuthenticationError as e:
            raise LLMError("Claude: no valid credentials (ANTHROPIC_API_KEY, `ant auth login`, or save a key)") from e
        except a.BadRequestError as e:
            raise LLMError(f"Claude: request rejected: {e.message}") from e
        except a.RateLimitError as e:
            raise LLMError("Claude: rate limited — try again later or use fewer workers") from e
        except a.APIStatusError as e:
            raise LLMError(f"Claude: API error {e.status_code}: {e.message}") from e
        except a.APIConnectionError as e:
            raise LLMError("Claude: network error") from e
        except TypeError as e:
            if "authentication" in str(e).lower():
                raise LLMError("Claude: no credentials found — set ANTHROPIC_API_KEY (e.g. in ~/.zshrc) "
                               "or run `ant auth login`") from e
            raise
        u = resp.usage
        self.usage["calls"] += 1
        self.usage["input"] += u.input_tokens or 0
        self.usage["output"] += u.output_tokens or 0
        self.usage["cache_read"] += getattr(u, "cache_read_input_tokens", 0) or 0
        if resp.stop_reason == "refusal":
            raise LLMError("Claude declined this request (refusal)")
        if resp.stop_reason == "max_tokens":
            raise LLMError("Claude: response hit max_tokens before finishing")
        text = "".join(b.text for b in resp.content if b.type == "text")
        return text, resp.content  # thinking blocks go back unchanged on the next turn


class OpenAICompatProvider:
    """POST {base_url}/chat/completions — DeepSeek, Qwen, Kimi, GLM, OpenAI, Ollama, …"""

    def __init__(self, base_url: str, model: str, api_key: str | None = None, max_tokens: int = 8192,
                 temperature: float | None = None, max_tokens_param: str = "max_tokens",
                 timeout: float = 600, label: str = "", extra: dict | None = None):
        if not model:
            raise LLMError(f"{label or base_url}: no model name set for this profile")
        self.url = base_url.rstrip("/") + "/chat/completions"
        self.model, self.key, self.max_tokens = model, api_key, max_tokens
        self.temperature, self.mt_param, self.timeout = temperature, max_tokens_param, timeout
        self.extra = extra or {}
        self.label = label or model
        host = urllib.parse.urlparse(self.url).hostname or ""
        # a local model server must never be routed through an HTTP proxy, whatever
        # HTTP(S)_PROXY / NO_PROXY the process happens to inherit
        self.local = host in ("localhost", "127.0.0.1", "::1") or host.endswith(".local")
        self.opener = (urllib.request.build_opener(urllib.request.ProxyHandler({})) if self.local
                       else urllib.request.build_opener())
        self.usage = {"input": 0, "output": 0, "cache_read": 0, "calls": 0}

    def turn(self, system: str, messages: list) -> tuple[str, str]:
        msgs = [{"role": "system", "content": system}]
        for m in messages:
            c = m["content"]
            msgs.append({"role": m["role"], "content": c if isinstance(c, str) else json.dumps(c)})
        body = {"model": self.model, "messages": msgs, self.mt_param: self.max_tokens, **self.extra}
        if self.temperature is not None:
            body["temperature"] = self.temperature
        headers = {"Content-Type": "application/json"}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"
        req = urllib.request.Request(self.url, json.dumps(body).encode("utf-8"), headers)
        try:
            with self.opener.open(req, timeout=self.timeout) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")[:300]
            hint = {401: "invalid or missing API key", 403: "access denied", 404: "wrong base_url or model",
                    429: "rate limited / quota exhausted"}.get(e.code, "")
            raise LLMError(f"{self.label}: HTTP {e.code} {hint} — {detail}") from e
        except urllib.error.URLError as e:
            hint = " — is the local model server running?" if self.local else ""
            raise LLMError(f"{self.label}: cannot reach {self.url} ({e.reason}){hint}") from e
        except TimeoutError as e:
            raise LLMError(f"{self.label}: timed out") from e
        try:
            choice = data["choices"][0]
            text = choice["message"].get("content") or ""
        except (KeyError, IndexError, TypeError) as e:
            raise LLMError(f"{self.label}: unexpected response: {str(data)[:200]}") from e
        u = data.get("usage") or {}
        self.usage["calls"] += 1
        self.usage["input"] += u.get("prompt_tokens") or 0
        self.usage["output"] += u.get("completion_tokens") or 0
        self.usage["cache_read"] += (u.get("prompt_tokens_details") or {}).get("cached_tokens") or u.get(
            "prompt_cache_hit_tokens") or 0
        if choice.get("finish_reason") == "length":
            raise LLMError(f"{self.label}: response cut off at max_tokens — raise max_tokens in the profile")
        if choice.get("finish_reason") == "content_filter":
            raise LLMError(f"{self.label}: response blocked by the provider's content filter")
        return text, text


def make_provider(name: str, cfg: dict | None = None):
    cfg = cfg or load_config()
    prof = cfg["profiles"].get(name)
    if prof is None:
        raise LLMError(f"unknown model profile '{name}' (see config/models.toml)")
    label = prof.get("label") or name
    if prof.get("type") == "anthropic":
        return AnthropicProvider(model=prof.get("model", "claude-opus-5-5"), effort=prof.get("effort", "high"),
                                 max_tokens=int(prof.get("max_tokens", 16000)),
                                 api_key=_keys().get(name), label=label)
    if prof.get("type") == "openai":
        key = key_for(name, prof)
        if prof.get("key_env") and not key:
            raise LLMError(f"{label}: no API key — set {prof['key_env']} or save one in the review app")
        return OpenAICompatProvider(base_url=prof["base_url"], model=prof.get("model", ""), api_key=key,
                                    max_tokens=int(prof.get("max_tokens", 8192)),
                                    temperature=prof.get("temperature"),
                                    max_tokens_param=prof.get("max_tokens_param", "max_tokens"),
                                    label=label, extra=prof.get("extra"))
    raise LLMError(f"profile '{name}': type must be 'anthropic' or 'openai'")


def providers_for_nodes(cfg: dict | None = None, override: str | None = None) -> dict:
    """{node: provider}; one provider instance per profile, shared between nodes."""
    cfg = cfg or load_config()
    made: dict = {}
    out = {}
    for node in NODES + ["default"]:
        name = override or cfg["nodes"].get(node) or cfg["nodes"].get("default")
        if name not in made:
            made[name] = make_provider(name, cfg)
        out[node] = made[name]
    return out


def test_profile(name: str) -> dict:
    """One tiny request; returns ok/latency or the error message (never the key)."""
    t0 = time.time()
    try:
        p = make_provider(name)
        text, _ = p.turn("You are a connectivity check. Reply with the single word: OK",
                         [{"role": "user", "content": "ping"}])
        return {"ok": True, "ms": int((time.time() - t0) * 1000), "reply": text.strip()[:40],
                "model": getattr(p, "model", "")}
    except LLMError as e:
        return {"ok": False, "error": str(e)}
    except Exception as e:  # keep the settings page alive whatever the provider does
        return {"ok": False, "error": f"{type(e).__name__}: {e}"}
