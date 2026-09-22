import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


DISCOVERY = load("conversation_discovery", ROOT / "scripts/reddit_conversation_discovery.py")


class ConversationDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.product = {
            "asin": "B003ULL1NQ", "brand": "Nutramax", "product_name": "Cosequin DS",
            "aliases": ["Cosequin", "Cosequin DS"], "product_types": ["dog joint supplement"],
            "ingredients": ["glucosamine", "chondroitin"], "functions": ["joint mobility"],
            "competitor_brands": ["Dasuquin"], "competitor_products": ["Dasuquin MSM"],
            "problems": ["dog arthritis", "stiff joints", "struggling to get up"],
            "contexts": ["senior dog", "large breed dog"],
        }
        self.comments = [
            {"comment_id": "c1", "body": "My senior dog struggled to get up. Dasuquin helped after Cosequin upset her stomach.", "subreddit": "seniordogs"},
            {"comment_id": "c2", "body": "What does your vet recommend for dog arthritis?", "subreddit": "dogs"},
        ]

    def test_conversation_map_has_five_layers(self):
        cmap = DISCOVERY.build_conversation_map(self.product, evidence_comments=self.comments)
        self.assertEqual(set(cmap["layers"]), {"product_entities", "user_problems", "usage_contexts", "decision_conversations", "community_language"})

    def test_seed_plan_contains_seven_query_families(self):
        cmap = DISCOVERY.build_conversation_map(self.product)
        plan = DISCOVERY.generate_seed_queries(cmap, "B003ULL1NQ")
        self.assertEqual({q["query_family"] for q in plan}, set(DISCOVERY.QUERY_FAMILIES))

    def test_next_round_queries_come_from_real_comments(self):
        cmap = DISCOVERY.build_conversation_map(self.product)
        queries = DISCOVERY.generate_next_round_queries(cmap, self.comments, round_number=2)
        self.assertTrue(any("struggled to get up" in q["query"].lower() for q in queries))

    def test_expanded_query_keeps_evidence_comment_ids(self):
        cmap = DISCOVERY.build_conversation_map(self.product)
        queries = DISCOVERY.generate_next_round_queries(cmap, self.comments, round_number=2)
        self.assertTrue(all(q["generation_source"] == "observed_reddit_comment" and q["evidence_comment_ids"] for q in queries))

    def test_semantic_drift_filters_generic_post(self):
        cmap = DISCOVERY.build_conversation_map(self.product)
        relevant = DISCOVERY.score_post_relevance({"title": "Cosequin for senior dog arthritis", "body": "joint mobility", "subreddit": "dogs"}, cmap)
        generic = DISCOVERY.score_post_relevance({"title": "My dog is cute", "body": "weekend photos", "subreddit": "pics"}, cmap)
        self.assertGreater(relevant["score"], generic["score"])
        self.assertFalse(generic["qualified"])

    def test_three_relevance_tiers(self):
        cmap = DISCOVERY.build_conversation_map(self.product)
        samples = [
            "Cosequin helped my old dog", "We switched to Dasuquin MSM", "My senior dog has stiff joints and cannot stand up",
        ]
        tiers = [DISCOVERY.classify_comment_relevance({"body": x}, cmap)["relevance_tier"] for x in samples]
        self.assertEqual(tiers, ["direct_product", "competitive_context", "unmet_need"])

    def test_irrelevant_comment_is_filtered_even_in_relevant_post(self):
        cmap = DISCOVERY.build_conversation_map(self.product)
        result = DISCOVERY.classify_comment_relevance({"body": "The weather is nice today"}, cmap, {"post_relevance_score": 0.95})
        self.assertFalse(result["qualified"])

    def test_partial_comment_goes_to_partial_candidates(self):
        trusted, partial, excluded = DISCOVERY.partition_comment_records("PARTIAL", [{"comment_id":"c1","comment_url":"https://redd.it/c1","body":"Cosequin helped","parent_id":"p1","depth":0}], DISCOVERY.build_conversation_map(self.product))
        self.assertEqual(len(partial), 1); self.assertFalse(trusted); self.assertFalse(excluded)

    def test_pass_comment_goes_to_trusted_comments(self):
        trusted, partial, excluded = DISCOVERY.partition_comment_records("PASS", [{"comment_id":"c1","comment_url":"https://redd.it/c1","body":"Cosequin helped","parent_id":"p1","depth":0}], DISCOVERY.build_conversation_map(self.product))
        self.assertEqual(len(trusted), 1); self.assertFalse(partial); self.assertFalse(excluded)

    def test_old_partial_can_be_forced_to_reaudit(self):
        cp = {"selected_visible_threads":{"p1":{"audit_status":"PARTIAL","post_url":"https://reddit.com/comments/p1"}}, "searched_keywords":["done"]}
        migrated = DISCOVERY.migrate_checkpoint(cp)
        self.assertEqual(DISCOVERY.partial_reaudit_queue(migrated, True), ["p1"])

    def test_checkpoint_version_upgrade_preserves_pass(self):
        cp = {"selected_visible_threads":{"p1":{"audit_status":"PASS"}}, "trusted_comments":[{"comment_id":"c1"}]}
        migrated = DISCOVERY.migrate_checkpoint(cp)
        self.assertEqual(migrated["trusted_comments"], cp["trusted_comments"])
        self.assertEqual(migrated["collector_version"], DISCOVERY.VERSIONS["collector_version"])

    def test_semantic_saturation_stops_after_two_low_yield_rounds(self):
        decision = DISCOVERY.evaluate_stop([{"new_trusted":5,"duplicate_rate":0.2},{"new_trusted":4,"duplicate_rate":0.3}], trusted_total=20, target_comments=100, max_rounds=5, min_new=10, duplicate_stop=0.85)
        self.assertEqual(decision["stop_reason"], "semantic_saturation_low_yield")

    def test_duplicate_rate_stops_after_two_rounds(self):
        decision = DISCOVERY.evaluate_stop([{"new_trusted":20,"duplicate_rate":0.9},{"new_trusted":12,"duplicate_rate":0.91}], trusted_total=32, target_comments=100, max_rounds=5, min_new=10, duplicate_stop=0.85)
        self.assertEqual(decision["stop_reason"], "duplicate_rate_saturation")

    def test_target_comments_stops(self):
        decision = DISCOVERY.evaluate_stop([], trusted_total=100, target_comments=100, max_rounds=5, min_new=10, duplicate_stop=0.85)
        self.assertEqual(decision["stop_reason"], "target_comments_reached")

    def test_parent_id_and_depth_remain_intact(self):
        comments = [{"comment_id":"c1","parent_id":"p1","depth":0,"body":"Cosequin helped","comment_url":"u1"},{"comment_id":"c2","parent_id":"c1","depth":1,"body":"Same for my senior dog","comment_url":"u2"}]
        trusted, _, _ = DISCOVERY.partition_comment_records("PASS", comments, DISCOVERY.build_conversation_map(self.product))
        self.assertEqual([(x["comment_id"],x["parent_id"],x["depth"]) for x in trusted], [("c1","p1",0),("c2","c1",1)])

    def test_community_map_uses_only_observed_subreddits(self):
        cmap = DISCOVERY.build_community_map([{"subreddit":"dogs","qualified":True,"valid_comments":3},{"subreddit":"seniordogs","qualified":True,"valid_comments":2}])
        self.assertEqual({x["subreddit"] for x in cmap}, {"dogs","seniordogs"})
        self.assertNotIn("AskVet", {x["subreddit"] for x in cmap})


class CliContractTests(unittest.TestCase):
    def test_cli_help_lists_iterative_flags(self):
        run = subprocess.run(["python", str(ROOT / "scripts/reddit_conversation_discovery.py"), "--help"], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(run.returncode, 0, run.stderr)
        for flag in ["--discovery-mode", "--max-discovery-rounds", "--min-new-comments-per-round", "--duplicate-rate-stop"]:
            self.assertIn(flag, run.stdout)


if __name__ == "__main__":
    unittest.main()
