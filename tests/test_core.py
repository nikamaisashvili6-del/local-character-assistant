"""
Fast tests: no model, no GPU. Run with:   python3 -m unittest -v

They pin down the behaviour we fixed by hand, so a later change can't quietly
undo it: routing, the "no tool for that" detector, opener trimming, the
cache-friendly prompt, and the lorebook.
"""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import assistant  # noqa: E402
import brain      # noqa: E402
import router     # noqa: E402

# Never ask a model during tests: a tie returns "no tool" so we notice it.
router.ask_llama = lambda task, candidates: None
TOOLS = router.load_tools()


def routed(message):
    return [tool["name"] for _, tool in router.route(message, TOOLS)]


class Routing(unittest.TestCase):
    CASES = {
        "pause the music and lock the screen": ["desktop/music/pause", "desktop/system/lock"],
        "play some music": ["desktop/music/play"],
        "change music to the clash": ["desktop/music/play"],
        "skip this song": ["desktop/music/next"],
        "what song is this": ["desktop/music/now"],
        "turn the volume to 40": ["desktop/sound/volume"],
        "search google for openwakeword": ["desktop/browser/google"],
        "watch punk rock on youtube": ["desktop/browser/youtube"],
        "lock the screen": ["desktop/system/lock"],
        "dark mode": ["desktop/system/theme"],
        "remind me in 10 minutes to stretch": ["life/reminders/remind"],
        "cancel the alarm": ["life/reminders/alarms"],
        "search my notes for punk": ["notes/vault/search"],
        "how much ram is the pc using": ["pc/health/health"],
    }
    CHAT = ["i love that song", "what do you think about punk", "hey there",
            "check my calendar", "my plan is to start a band"]

    def test_tools_found(self):
        for message, expected in self.CASES.items():
            with self.subTest(message=message):
                self.assertEqual(routed(message), expected)

    def test_chat_stays_chat(self):
        for message in self.CHAT:
            with self.subTest(message=message):
                self.assertEqual(routed(message), [])

    def test_verb_carries_over(self):
        plan = router.route("open vs code and file manager", TOOLS)
        self.assertEqual(len(plan), 1)                     # same tool, run once
        self.assertIn("file manager", plan[0][0])          # with both parts


class RequestDetector(unittest.TestCase):
    def test_commands(self):
        for t in ["check my calendar", "can you open spotify", "how many emails do i have",
                  "please send it", "what's on my schedule"]:
            self.assertTrue(assistant.REQUEST.search(t), t)

    def test_not_commands(self):
        for t in ["what do you think about my plan to start a project",
                  "i want to stop procrastinating", "hey"]:
            self.assertFalse(assistant.REQUEST.search(t), t)


class OpenerTrim(unittest.TestCase):
    def test_trims(self):
        name = assistant.config.USER_NAME
        self.assertEqual(assistant.cut_opener(f"{name}, you're up early"), "You're up early")
        self.assertEqual(assistant.cut_opener(f"Hey {name}. What now?"), "What now?")
        self.assertEqual(assistant.cut_opener(f"{assistant.SHORT}: hello"), "hello")

    def test_leaves_normal_text(self):
        self.assertEqual(assistant.cut_opener("Nothing to trim here"), "Nothing to trim here")


class Prompt(unittest.TestCase):
    def test_system_first_and_stable(self):
        """The fixed part must come first and earlier turns must not change
        between calls: that's what lets Ollama reuse its cache."""
        hist = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
        p1 = assistant.build_mistral_prompt("SYS", hist, "c (time 10:00)")
        p2 = assistant.build_mistral_prompt("SYS", hist, "c (time 10:01)")
        self.assertTrue(p1.startswith("[INST]SYS"))
        prefix = "[INST]SYS\n\na[/INST] b</s>"
        self.assertTrue(p1.startswith(prefix) and p2.startswith(prefix))


class Lorebook(unittest.TestCase):
    def test_core_always_triggered_only_on_words(self):
        sections = brain.load_lore()
        core = brain.core_lore(sections)
        self.assertTrue(core)
        self.assertEqual(brain.lore_for("hello there", sections), "")
        self.assertTrue(brain.lore_for("tell me about the band", sections))


if __name__ == "__main__":
    unittest.main()


class FollowUps(unittest.TestCase):
    def test_short_follow_up_borrows_last_topic(self):
        self.assertEqual([t["name"] for _, t in router.route("next", TOOLS, "music")],
                         ["desktop/music/next"])

    def test_no_topic_no_tool(self):
        self.assertEqual(routed("next"), [])

    def test_long_chat_doesnt_borrow_topic(self):
        self.assertEqual(router.route("what do you think about the next step in my plan",
                                      TOOLS, "music"), [])

    def test_increase_volume_routes(self):
        self.assertEqual(routed("increase volume"), ["desktop/sound/volume"])

    def test_fake_tool_output_detected(self):
        self.assertTrue(assistant.FAKE_TOOL.search("desktop/music/next:\nnow: Some Band - Song"))
        self.assertTrue(assistant.FAKE_TOOL.search("volume: 100%"))
        self.assertFalse(assistant.FAKE_TOOL.search("Sure, what do you want to hear?"))
