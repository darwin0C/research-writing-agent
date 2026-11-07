import json
import os
import stat
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from checker import app, llm, rules
from checker.audit import audit
from checker.invariants import compare
from checker.latex_mask import text_format
from checker.runner import Runner, _system

ROOT = Path(__file__).resolve().parent.parent


class FakeOpenAI(BaseHTTPRequestHandler):
    """Mimics /v1/chat/completions. The model name selects the behaviour."""
    seen = []

    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOpenAI.seen.append({"auth": self.headers.get("Authorization"), "body": body})
        if self.headers.get("Authorization") == "Bearer wrong":
            return self._out(401, {"error": {"message": "invalid api key"}})
        finish = "length" if body["model"] == "short" else "stop"
        self._out(200, {"choices": [{"message": {"role": "assistant", "content": "OK"},
                                     "finish_reason": finish}],
                        "usage": {"prompt_tokens": 11, "completion_tokens": 1}})

    def _out(self, code, obj):
        data = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ModelLayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeOpenAI)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}/v1"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self._saved = (llm.LOCAL, llm.KEYS)
        llm.LOCAL = Path(self.tmp.name) / "models.local.json"
        llm.KEYS = Path(self.tmp.name) / "keys.json"
        os.environ.pop("FAKE_KEY", None)

    def tearDown(self):
        llm.LOCAL, llm.KEYS = self._saved
        self.tmp.cleanup()

    def add_fake(self, name="fake", model="m1", key_env="FAKE_KEY"):
        llm.save_local({"profiles": {name: {"type": "openai", "base_url": self.base, "model": model,
                                            "key_env": key_env, "label": name}}})

    def test_openai_compatible_roundtrip(self):
        self.add_fake()
        os.environ["FAKE_KEY"] = "k-123"
        p = llm.make_provider("fake")
        text, content = p.turn("sys", [{"role": "user", "content": "hi"}])
        self.assertEqual((text, content), ("OK", "OK"))
        req = FakeOpenAI.seen[-1]
        self.assertEqual(req["auth"], "Bearer k-123")
        self.assertEqual(req["body"]["messages"][0], {"role": "system", "content": "sys"})
        self.assertEqual(p.usage["input"], 11)

    def test_errors_are_readable(self):
        self.add_fake()
        os.environ["FAKE_KEY"] = "wrong"
        with self.assertRaisesRegex(llm.LLMError, "401 invalid or missing API key"):
            llm.make_provider("fake").turn("s", [{"role": "user", "content": "x"}])
        self.add_fake(model="short")
        os.environ["FAKE_KEY"] = "k"
        with self.assertRaisesRegex(llm.LLMError, "cut off"):
            llm.make_provider("fake").turn("s", [{"role": "user", "content": "x"}])
        llm.save_local({"profiles": {"down": {"type": "openai", "base_url": "http://127.0.0.1:9/v1",
                                              "model": "m", "key_env": ""}}})
        r = llm.test_profile("down")
        self.assertFalse(r["ok"])
        self.assertIn("cannot reach", r["error"])

    def test_missing_key_and_model(self):
        self.add_fake()
        with self.assertRaisesRegex(llm.LLMError, "set FAKE_KEY"):
            llm.make_provider("fake")
        os.environ["FAKE_KEY"] = "k"
        self.add_fake(model="")
        with self.assertRaisesRegex(llm.LLMError, "no model name"):
            llm.make_provider("fake")

    def test_saved_key_file_is_private_and_never_shown(self):
        self.add_fake()
        llm.save_key("fake", "secret-xyz")
        self.assertEqual(stat.S_IMODE(os.stat(llm.KEYS).st_mode), 0o600)
        self.assertEqual(llm.key_status("fake", llm.load_config()["profiles"]["fake"]), "saved")
        self.assertEqual(llm.make_provider("fake").key, "secret-xyz")
        self.assertNotIn("secret-xyz", json.dumps(app.models_view()))
        self.assertNotIn("secret-xyz", llm.LOCAL.read_text())

    def test_keys_never_go_into_project_config(self):
        with self.assertRaises(llm.LLMError):
            llm.save_local({"profiles": {"x": {"type": "openai", "api_key": "s"}}})

    def test_nodes_share_instances_and_override(self):
        self.add_fake()
        self.add_fake(name="fake2")
        os.environ["FAKE_KEY"] = "k"
        llm.save_local({"nodes": {"default": "fake", "rewriter": "fake2"}})
        ps = llm.providers_for_nodes()
        self.assertIs(ps["auditor"], ps["claim-checker"])
        self.assertIsNot(ps["auditor"], ps["rewriter"])
        ps = llm.providers_for_nodes(override="fake2")
        self.assertTrue(all(p is ps["default"] for p in ps.values()))

    def test_local_endpoint_ignores_proxy(self):
        self.add_fake(key_env="")
        old = {k: os.environ.get(k) for k in ("HTTP_PROXY", "http_proxy", "NO_PROXY", "no_proxy")}
        try:
            os.environ["HTTP_PROXY"] = os.environ["http_proxy"] = "http://127.0.0.1:9"  # dead proxy
            for k in ("NO_PROXY", "no_proxy"):
                os.environ.pop(k, None)
            r = llm.test_profile("fake")
            self.assertTrue(r["ok"], r)
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_test_profile_ok(self):
        self.add_fake()
        os.environ["FAKE_KEY"] = "k"
        r = llm.test_profile("fake")
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["reply"], "OK")


class RunnerNodeRoutingTest(unittest.TestCase):
    def test_each_node_uses_its_provider(self):
        class Rec:
            def __init__(self):
                self.systems = []
                self.usage = {"input": 1, "output": 1, "cache_read": 0, "calls": 1}

            def turn(self, system, messages):
                self.systems.append(system[:3000])
                return "", ""
        a, b = Rec(), Rec()
        r = Runner({"default": a, "rewriter": b}, log=lambda *_: None, packs=[])
        self.assertIs(r._llm("auditor"), a)
        self.assertIs(r._llm("rewriter"), b)
        self.assertEqual(r.usage()["calls"], 2)


class RulesTest(unittest.TestCase):
    def test_pack_available_with_license(self):
        packs = {p["name"]: p for p in rules.available()}
        self.assertIn("academic-humanizer", packs)
        self.assertTrue(packs["academic-humanizer"]["license"])
        self.assertEqual(packs["academic-humanizer"]["version"], "0.3.3")

    def test_system_prompt_composition(self):
        s = _system("rewriter")
        self.assertIn("Layer 4: Claim-evidence discipline", s)
        self.assertIn("[[EVIDENCE:", s)
        self.assertLess(s.index("You rewrite exactly one paragraph"), s.index("Rule pack: academic-humanizer"))
        self.assertNotIn("Before you start, read the active rule packs", s)
        self.assertNotIn("Rule pack:", _system("rewriter", []))


class Junbolian_ChecksTest(unittest.TestCase):
    def test_evidence_marker_warns_and_numbers_inside_ignored(self):
        o = "Our method is more robust than the baseline."
        r = "Our method is more robust than the baseline [[EVIDENCE: accuracy drop under shift for 3 datasets]]."
        rep = compare(o, r)
        self.assertTrue(rep.passed, rep.to_dict())
        self.assertIn("L4-evidence", {f.layer for f in rep.findings})

    def test_formal_environment_locked(self):
        o = "\\begin{theorem}The bound holds for all $n$.\\end{theorem}\nWe use it below."
        r = "\\begin{theorem}The bound holds for every $n$.\\end{theorem}\nWe use it below."
        self.assertIn("L1-ENV", {f.layer for f in compare(o, r).findings if f.level == "error"})

    def test_preamble_frozen(self):
        from checker import pipeline
        src = ("\\documentclass{article}\n\\usepackage{amsmath}\n\\begin{document}\n"
               "In recent years, boiling has attracted increasing attention from many groups worldwide.\n"
               "\n\\end{document}\n")
        with tempfile.TemporaryDirectory() as t:
            st = pipeline.split(src, Path(t) / "r", name="p", journal="", level="light")
            head = (Path(t) / "r" / "units" / st["units"][0]["id"] / "original.tex").read_text()
        self.assertEqual(st["units"][0]["kind"], "frozen")
        self.assertTrue(head.startswith("\\documentclass") and head.rstrip().endswith("\\begin{document}"))
        self.assertEqual(st["units"][1]["kind"], "prose")

    def test_em_dash_flagged_in_english_only(self):
        self.assertTrue(any("—" in h["term"] or "---" in h["term"] for h in
                            audit("The method — unlike prior work — scales.")["hits"]))
        with text_format("text"):
            zh = audit("该方法——与以往工作不同——具有可扩展性。")
        self.assertFalse(any("—" in h["term"] for h in zh["hits"]))


class AppModelsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls._saved = (llm.LOCAL, llm.KEYS)
        llm.LOCAL = Path(cls.tmp.name) / "models.local.json"
        llm.KEYS = Path(cls.tmp.name) / "keys.json"
        cls.srv = app.make_server(Path(cls.tmp.name) / "runs", 0)
        cls.base = f"http://127.0.0.1:{cls.srv.server_address[1]}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()
        llm.LOCAL, llm.KEYS = cls._saved
        cls.tmp.cleanup()

    def post(self, path, body):
        req = urllib.request.Request(self.base + path, json.dumps(body).encode(), {"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            return {"status": e.code, **json.loads(e.read())}

    def test_models_endpoints(self):
        with urllib.request.urlopen(self.base + "/api/models") as r:
            m = json.loads(r.read())
        self.assertIn("deepseek", {p["name"] for p in m["profiles"]})
        self.assertEqual(set(m["nodes"]), set(llm.NODES))
        r = self.post("/api/models", {"nodes": {"rewriter": "deepseek"}, "packs": []})
        self.assertEqual(r["nodes"]["rewriter"], "deepseek")
        self.assertEqual(r["active_packs"], [])
        r = self.post("/api/models/key", {"profile": "deepseek", "key": "sk-test-1"})
        self.assertEqual(next(p for p in r["profiles"] if p["name"] == "deepseek")["key"], "saved")
        self.assertNotIn("sk-test-1", json.dumps(r))
        self.assertEqual(self.post("/api/models", {"nodes": {"rewriter": "nope"}})["status"], 400)
        self.assertEqual(self.post("/api/models", {"profiles": {"x": {"type": "openai", "api_key": "s"}}})
                         .get("status", 200), 200)  # unknown fields are dropped, not stored
        self.assertNotIn("api_key", llm.LOCAL.read_text())


if __name__ == "__main__":
    unittest.main()
