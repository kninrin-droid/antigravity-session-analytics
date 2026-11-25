import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "sidecars" / "stats"))

import session_analyzer as sa  # noqa: E402


class SessionAnalyzerTests(unittest.TestCase):
    def _write_transcript(self, tmpdir: str, events: list[dict]) -> pathlib.Path:
        p = pathlib.Path(tmpdir) / "transcript.jsonl"
        p.write_text("\n".join(json.dumps(e) for e in events), encoding="utf-8")
        return p

    def test_analyze_multi_step_session(self) -> None:
        events = [
            {
                "step_index": 0,
                "type": "USER_INPUT",
                "created_at": "2026-11-25T10:00:00Z",
                "content": "<USER_REQUEST>Check project build</USER_REQUEST>",
            },
            {
                "step_index": 1,
                "type": "PLANNER_RESPONSE",
                "model": "gemini-4-neon-medium",
                "created_at": "2026-11-25T10:00:05Z",
                "input_tokens": 20000,
                "cache_read_tokens": 0,
                "output_tokens": 500,
                "tool_calls": [{"name": "read_file", "args": {"Path": "src/app.py"}}],
                "content": "Inspecting app.py",
            },
            {
                "step_index": 2,
                "type": "PLANNER_RESPONSE",
                "model": "gemini-4-neon-medium",
                "created_at": "2026-11-25T10:00:10Z",
                "input_tokens": 4000,
                "cache_read_tokens": 20000,
                "output_tokens": 800,
                "content": "Done",
            },
        ]
        with tempfile.TemporaryDirectory() as td:
            tp = self._write_transcript(td, events)
            res = sa.analyze_transcript(tp, "11111111-2222-3333-4444-555555555555")

        self.assertEqual(res["title"], "Check project build")
        self.assertEqual(res["user_turn_count"], 1)
        self.assertEqual(res["token_step_count"], 2)
        self.assertEqual(res["tool_call_count"], 1)
        self.assertEqual(res["totals"]["uncached_input_tokens"], 24000)
        self.assertEqual(res["totals"]["cached_tokens"], 20000)
        self.assertEqual(res["totals"]["output_tokens"], 1300)
        self.assertEqual(res["totals"]["peak_context"], 24000)
        self.assertGreater(res["totals"]["total_cost"], 0)
        self.assertGreater(res["totals"]["cache_saved"], 0)
        self.assertEqual(res["optimum"]["state"], "wait")
        self.assertEqual(res["optimum"]["score"], 100)
        self.assertEqual(res["tools"][0], {"name": "read_file", "count": 1})

    def test_high_context_low_cache_triggers_new_session_warning(self) -> None:
        events = [{"step_index": 0, "type": "USER_INPUT", "content": "<USER_REQUEST>Big task</USER_REQUEST>"}]
        for i in range(1, 16):
            events.append({
                "step_index": i,
                "type": "PLANNER_RESPONSE",
                "model": "claude-opus-4",
                "input_tokens": 140000 + i * 5000,
                "cache_read_tokens": 20000,
                "output_tokens": 1200,
            })
        with tempfile.TemporaryDirectory() as td:
            tp = self._write_transcript(td, events)
            res = sa.analyze_transcript(tp, "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")

        self.assertEqual(res["optimum"]["state"], "new")
        self.assertLess(res["optimum"]["score"], 25)
        self.assertEqual(len(res["steps"]), 15)


if __name__ == "__main__":
    unittest.main()
