import json
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CAPTURE = ROOT / "scripts/reddit_visible_capture.js"
COLLECTOR = ROOT / "scripts/reddit_playwright_collector.cjs"


def node(expression):
    script = f"const v=require({json.dumps(str(CAPTURE))}); const c=require({json.dumps(str(COLLECTOR))}); Promise.resolve({expression}).then(x=>console.log(JSON.stringify(x))).catch(e=>{{console.error(e.stack);process.exit(1)}})"
    run = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8")
    if run.returncode:
        raise AssertionError(run.stderr)
    return json.loads(run.stdout)


def html(comments, controls=(), count=None):
    rows = []
    for cid, parent, depth, author, body in comments:
        rows.append(f'<shreddit-comment thingid="t1_{cid}" parentid="{parent}" depth="{depth}" author="{author}" permalink="/r/dogs/comments/p1/x/comment/{cid}/"><div slot="comment">{body}</div></shreddit-comment>')
    buttons = "".join(f'<button data-key="{key}">{label}</button>' for key, label in controls)
    counter = "" if count is None else f'<span data-comment-count="{count}">{count} comments</span>'
    return f'<main data-post-id="p1">{counter}<div id="comment-tree">{"".join(rows)}{buttons}</div></main>'


class VisibleFixtureTests(unittest.TestCase):
    def snapshot(self, source):
        return node(f'v.fixtureSnapshot({json.dumps(source)},{{post_id:"p1",post_url:"https://www.reddit.com/r/dogs/comments/p1/x/"}})')

    def test_two_reply_levels_flatten_with_parent_and_depth(self):
        snap = self.snapshot(html([("c1", "t3_p1", 0, "u1", "top"), ("c2", "t1_c1", 1, "u2", "reply"), ("c3", "t1_c2", 2, "u3", "deep")], count=3))
        self.assertEqual([(x["comment_id"], x["parent_id"], x["depth"]) for x in snap["comments"]], [("c1", "p1", 0), ("c2", "c1", 1), ("c3", "c2", 2)])

    def test_multiple_more_replies_are_processed_one_at_a_time(self):
        states = [html([("c1", "t3_p1", 0, "u", "one")], [("a", "more replies"), ("b", "查看更多回复")]), html([("c1", "t3_p1", 0, "u", "one"), ("c2", "t1_c1", 1, "u", "two")], [("b", "查看更多回复")]), html([("c1", "t3_p1", 0, "u", "one"), ("c2", "t1_c1", 1, "u", "two"), ("c3", "t1_c1", 1, "u", "three")], count=3)]
        result = node(f'v.runFixtureExpansion({json.dumps(states)},{{post_id:"p1",max_expand_actions:10,thread_timeout:60}})')
        self.assertEqual([x["control_key"] for x in result["expansion_log"]], ["a", "b"])
        self.assertEqual(result["status"], "PASS")

    def test_localized_numbered_more_replies_label_is_recognized(self):
        self.assertTrue(node('v.isExpandLabel("\\u53e6\\u5916 19 \\u6761\\u56de\\u590d")'))

    def test_new_ids_during_scroll_reset_two_round_stability(self):
        states = [html([("c1", "t3_p1", 0, "u", "one")], count=2)] + [html([("c1", "t3_p1", 0, "u", "one"), ("c2", "t1_c1", 1, "u", "two")], count=2)] * 3
        result = node(f'v.runFixtureExpansion({json.dumps(states)},{{post_id:"p1",thread_timeout:60,advance_on_scroll:true}})')
        self.assertGreaterEqual(result["checkpoint"]["scan_count"], 4)
        self.assertEqual(result["status"], "PASS")

    def test_continue_thread_uses_owned_temporary_tab_and_keeps_original_post(self):
        states = [html([("c1", "t3_p1", 0, "u", "one")], [("continue", "continue this thread")]), html([("c1", "t3_p1", 0, "u", "one"), ("c2", "t1_c1", 1, "u", "two")], count=2)]
        result = node(f'v.runFixtureExpansion({json.dumps(states)},{{post_id:"p1",max_expand_actions:10,thread_timeout:60}})')
        self.assertEqual(result["owned_temp_tabs"], ["owned:continue"])
        self.assertTrue(all(x["post_id"] == "p1" for x in result["comments"]))

    def test_deleted_author_with_visible_body_is_kept(self):
        snap = self.snapshot(html([("c1", "t3_p1", 0, "[deleted]", "useful body")], count=1))
        self.assertEqual([(x["author"], x["body"]) for x in snap["comments"]], [("[deleted]", "useful body")])

    def test_deleted_removed_and_empty_bodies_are_filtered(self):
        snap = self.snapshot(html([("c1", "t3_p1", 0, "u", "[deleted]"), ("c2", "t3_p1", 0, "u", "[removed]"), ("c3", "t3_p1", 0, "u", ""), ("c4", "t3_p1", 0, "u", "keep")], count=4))
        self.assertEqual([x["comment_id"] for x in snap["comments"]], ["c4"])
        self.assertEqual(snap["observed_comment_count"], 4)
        audit = node(f'v.auditVisibleThread({json.dumps(snap)},{{stable_rounds:2,stop_reason:"idle"}})')
        self.assertEqual(audit["status"], "PASS")

    def test_duplicate_reply_is_deduped_by_id_and_url(self):
        snap = self.snapshot(html([("c1", "t3_p1", 0, "u", "one"), ("c1", "t3_p1", 0, "u", "one")], count=1))
        self.assertEqual(len(snap["comments"]), 1)

    def test_unprocessed_expand_control_is_partial(self):
        snap = self.snapshot(html([("c1", "t3_p1", 0, "u", "one")], [("a", "more comments")], count=2))
        audit = node(f'v.auditVisibleThread({json.dumps(snap)},{{stable_rounds:2,stop_reason:"idle"}})')
        self.assertEqual(audit["status"], "PARTIAL")
        self.assertIn("unprocessed_expand_controls", audit["failures"])

    def test_complete_tree_with_closed_frontier_is_pass(self):
        snap = self.snapshot(html([("c1", "t3_p1", 0, "u", "one"), ("c2", "t1_c1", 1, "u", "two")], count=2))
        audit = node(f'v.auditVisibleThread({json.dumps(snap)},{{stable_rounds:2,stop_reason:"idle"}})')
        self.assertEqual(audit["status"], "PASS")
        self.assertEqual(audit["orphans"], [])

    def test_orphan_parent_is_partial(self):
        snap = self.snapshot(html([("c1", "t1_missing", 1, "u", "orphan")], count=1))
        audit = node(f'v.auditVisibleThread({json.dumps(snap)},{{stable_rounds:2,stop_reason:"idle"}})')
        self.assertEqual(audit["status"], "PARTIAL")
        self.assertEqual(audit["orphans"], ["c1"])

    def test_action_limit_and_timeout_save_incomplete_frontier(self):
        states = [html([("c1", "t3_p1", 0, "u", "one")], [("a", "show more")], count=3), html([("c1", "t3_p1", 0, "u", "one"), ("c2", "t1_c1", 1, "u", "two")], [("b", "more replies")], count=3)]
        limited = node(f'v.runFixtureExpansion({json.dumps(states)},{{post_id:"p1",max_expand_actions:1,thread_timeout:60}})')
        timed = node(f'v.runFixtureExpansion({json.dumps(states)},{{post_id:"p1",max_expand_actions:10,thread_timeout:0}})')
        self.assertEqual((limited["status"], limited["checkpoint"]["stop_reason"]), ("PARTIAL", "max_expand_actions"))
        self.assertEqual((timed["status"], timed["checkpoint"]["stop_reason"]), ("PARTIAL", "thread_timeout"))
        self.assertTrue(limited["checkpoint"]["incomplete_frontier"])

    def test_visible_security_challenge_is_blocked(self):
        snap = self.snapshot('<main data-post-id="p1"><div id="comment-tree"></div><p>You have been blocked by network security</p></main>')
        audit = node(f'v.auditVisibleThread({json.dumps(snap)},{{stable_rounds:0}})')
        self.assertEqual((audit["status"], audit["failures"]), ("BLOCKED", ["network_blocked"]))


class SelectedModeContractTests(unittest.TestCase):
    def test_selected_mode_defaults_and_help(self):
        parsed = node('c.selectedTabExpansionOptions(c.args(["collect","--session-mode","selected-chrome-tab"]))')
        self.assertEqual(parsed, {"max_expand_actions":100,"max_comments_per_post":500,"expand_delay_min":1,"expand_delay_max":3,"thread_timeout":600})
        run = subprocess.run(["node", str(COLLECTOR), "--help"], capture_output=True, text=True, encoding="utf-8")
        for flag in ("--max-expand-actions", "--max-comments-per-post", "--expand-delay-min", "--expand-delay-max", "--thread-timeout"):
            self.assertIn(flag, run.stdout)

    def test_skill_documents_recursive_visible_dom_frontier(self):
        docs = (ROOT / "SKILL.md").read_text(encoding="utf-8") + (ROOT / "references/collection-guide.md").read_text(encoding="utf-8") + (ROOT / "references/raw-record-schema.md").read_text(encoding="utf-8")
        for phrase in ("max-expand-actions", "expanded_control_keys", "incomplete_frontier", "连续两轮", "continue this thread", "作者为 `[deleted]`"):
            self.assertIn(phrase, docs)


if __name__ == "__main__":
    unittest.main()
