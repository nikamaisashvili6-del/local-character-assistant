"""
Skills tests: drafting, matching and installing, with a fake model and a
throwaway folder. No GPU, no reviewer.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import router     # noqa: E402
import skills     # noqa: E402

skills.ping = lambda *a: None      # no desktop notifications from tests

DRAFT = """# restart-docker
keywords: restart, docker, server, stack
shelf: docker, server
when: Docker is down or acting up

1. check the status first
2. restart the service

```bash
systemctl --user restart docker
```
"""


class Skills(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        skills.DIR, skills.PENDING = root, root / "pending"
        skills.REJECTED, skills.TOOLS = root / "rejected", root / "tools"

    def tearDown(self):
        self.tmp.cleanup()

    def test_parse(self):
        info = skills.parse(DRAFT)
        self.assertEqual(info["name"], "restart-docker")
        self.assertEqual(info["keywords"], {"restart", "docker", "server", "stack"})
        self.assertIn("systemctl", info["script"])

    def test_draft_saved_only_when_model_found_something(self):
        history = [{"role": "user", "content": "restart docker"}]
        self.assertIsNone(skills.draft(history, lambda m: "NONE"))
        path = skills.draft(history, lambda m: DRAFT)
        self.assertTrue(path.exists() and path.parent == skills.PENDING)

    def test_notes_need_two_keyword_hits(self):
        (skills.DIR / "restart-docker.md").write_text(DRAFT)
        loaded = skills.load()
        self.assertEqual(skills.for_text("the server is slow today", loaded), "")
        self.assertIn("restart the service", skills.for_text("restart the docker server", loaded))

    def test_install_script_becomes_tool_that_asks_first(self):
        path = skills.draft([{"role": "user", "content": "x"}], lambda m: DRAFT)
        skills.install(path)
        self.assertFalse(path.exists())
        tools = router._load_tree(skills.TOOLS)
        self.assertEqual([t["name"] for t in tools], ["restart-docker/restart-docker"])
        self.assertTrue(tools[0]["confirm"])
        self.assertEqual(router.score("restart the docker server", tools[0]) > 0, True)

    def test_reject_keeps_a_copy(self):
        path = skills.draft([{"role": "user", "content": "x"}], lambda m: DRAFT)
        dest = skills.reject(path, "too vague")
        self.assertFalse(path.exists())
        self.assertIn("too vague", dest.read_text())


if __name__ == "__main__":
    unittest.main()


class Aliases(unittest.TestCase):
    ALIAS = "# spotify-volume-up\nsay: increase volume\ndo: spotify volume up\nkeywords: increase, volume\n"

    def test_alias_rewrites_before_routing(self):
        s = [skills.parse(self.ALIAS)]
        self.assertEqual(skills.apply_aliases("increase volume", s), "spotify volume up")
        self.assertEqual(skills.apply_aliases("lower the volume", s), "lower the volume")

    def test_rule_message_runs_no_tool(self):
        tools = router.load_tools()
        self.assertEqual(router.route("next time i say increase volume up, run spotify volume up", tools), [])


class Junk(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        skills.DIR, skills.PENDING = root, root / "pending"

    def tearDown(self):
        self.tmp.cleanup()

    def test_tool_output_only_draft_is_dropped(self):
        junk = ("# volume-control\nkeywords: volume, spotify\nwhen: volume\n"
                "(1. desktop/sound/volume: volume: 100%)\n\nshelf: audio\n```bash\n"
                "desktop/sound/volume: set volume to 80%\nvolume: 80%\n```\n")
        self.assertIsNone(skills.draft([{"role": "user", "content": "x"}], lambda m: junk))

    def test_real_draft_kept(self):
        self.assertIsNotNone(skills.draft([{"role": "user", "content": "x"}], lambda m: DRAFT))
