import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "scripts/reddit_thread_core.cjs"
AUDITOR = ROOT / "scripts/audit_thread_evidence.py"
URL = "https://www.reddit.com/r/dogs/comments/p1/example"


def t1(cid, parent="t3_p1", body="body", author="user", replies="", link="t3_p1"):
    return {"kind":"t1","data":{"id":cid,"name":"t1_"+cid,"parent_id":parent,"link_id":link,"body":body,"author":author,"permalink":f"/r/dogs/comments/p1/example/{cid}/","created_utc":1,"depth":0,"score":1,"replies":replies}}


def more(ids, parent="t3_p1"):
    return {"kind":"more","data":{"id":"m","name":"more","count":len(ids),"parent_id":parent,"children":ids,"depth":0}}


def listing(children, after=None):
    return {"kind":"Listing","data":{"after":after,"before":None,"children":children}}


def thread(children, declared, after=None):
    post={"kind":"t3","data":{"id":"p1","name":"t3_p1","title":"Example","permalink":"/r/dogs/comments/p1/example/","num_comments":declared,"subreddit":"dogs","selftext":"","created_utc":1}}
    return [listing([post]),listing(children,after)]


def response(payload=None, state="done", status=200):
    row={"state":state,"http_status":status,"cleanup_verified":True}
    if payload is not None: row["public_response"]=payload
    return row


def run_fixture(responses, max_requests=40):
    if not CORE.is_file(): raise AssertionError("reddit_thread_core.cjs missing")
    temp=tempfile.TemporaryDirectory(); root=Path(temp.name); fixture=root/"fixture.json"; out=root/"evidence"
    fixture.write_text(json.dumps({"post_url":URL,"responses":responses}),encoding="utf-8")
    run=subprocess.run(["node",str(CORE),"fixture","--fixture",str(fixture),"--out",str(out),"--max-requests",str(max_requests)],capture_output=True,text=True,encoding="utf-8")
    summary=json.loads(run.stdout.strip().splitlines()[-1])
    return temp,out,run,summary


def load_auditor():
    if not AUDITOR.is_file(): raise AssertionError("audit_thread_evidence.py missing")
    spec=importlib.util.spec_from_file_location("thread_audit",AUDITOR); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod); return mod


class FrontierCollectionTests(unittest.TestCase):
    def test_initial_listing_comments_are_parsed(self):
        temp,out,run,s=run_fixture([response(thread([t1("c1")],1))]); self.addCleanup(temp.cleanup)
        self.assertEqual((run.returncode,s["status"],s["unique_total"]),(0,"PASS",1))

    def test_listing_after_is_followed(self):
        temp,out,run,s=run_fixture([response(thread([t1("c1")],2,"cursor")),response(thread([t1("c2")],2))]); self.addCleanup(temp.cleanup)
        self.assertEqual((s["status"],s["unique_total"],s["request_count"]),("PASS",2,2))

    def test_morechildren_completes_discovered_ids(self):
        payload={"errors":[],"things":[t1("c2")]}
        temp,out,run,s=run_fixture([response(thread([t1("c1"),more(["c2"])],2)),response(payload)]); self.addCleanup(temp.cleanup)
        self.assertEqual((s["status"],s["remaining_child_ids"]),("PASS",[]))

    def test_empty_children_continuation_requires_subtree_progress(self):
        replies=listing([more([],"t1_c1")])
        temp,out,run,s=run_fixture([response(thread([t1("c1",replies=replies)],2)),response(thread([t1("c2","t1_c1")],2))]); self.addCleanup(temp.cleanup)
        self.assertEqual((s["status"],s["unique_total"]),("PASS",2))

    def test_continuation_without_progress_is_partial(self):
        replies=listing([more([],"t1_c1")])
        temp,out,run,s=run_fixture([response(thread([t1("c1",replies=replies)],1)),response(thread([],1))]); self.addCleanup(temp.cleanup)
        self.assertEqual(s["status"],"PARTIAL"); self.assertIn("continue_no_progress",json.dumps(s["issues"]))

    def test_unreturned_id_is_not_invented_as_tombstone(self):
        empty_more={"errors":[],"things":[]}
        temp,out,run,s=run_fixture([response(thread([more(["ghost"])],0)),response(empty_more),response(listing([]))]); self.addCleanup(temp.cleanup)
        self.assertEqual(s["status"],"PARTIAL"); self.assertNotIn("ghost",json.loads((out/"ids.json").read_text()))

    def test_conflicting_comment_id_is_partial(self):
        temp,out,run,s=run_fixture([response(thread([t1("c1",body="one"),t1("c1",body="two")],1))]); self.addCleanup(temp.cleanup)
        self.assertEqual(s["status"],"PARTIAL"); self.assertIn("conflicting_duplicate",json.dumps(s["issues"]))

    def test_foreign_post_comment_is_rejected(self):
        temp,out,run,s=run_fixture([response(thread([t1("c1",link="t3_other")],1))]); self.addCleanup(temp.cleanup)
        self.assertEqual(s["status"],"PARTIAL")

    def test_request_budget_exhaustion_is_partial(self):
        temp,out,run,s=run_fixture([response(thread([more(["c2"])],1))],max_requests=1); self.addCleanup(temp.cleanup)
        self.assertEqual(s["status"],"PARTIAL"); self.assertIn("safety_budget_exhausted",json.dumps(s["issues"]))

    def test_http_403_and_429_are_blocked(self):
        for status in (403,429):
            with self.subTest(status=status):
                temp,out,run,s=run_fixture([response(state="blocked",status=status)]); self.addCleanup(temp.cleanup); self.assertEqual(s["status"],"BLOCKED")

    def test_login_or_html_challenge_is_blocked(self):
        temp,out,run,s=run_fixture([response(state="non_json",status=200)]); self.addCleanup(temp.cleanup)
        self.assertEqual(s["status"],"BLOCKED")


class IndependentAuditTests(unittest.TestCase):
    def passing(self): return run_fixture([response(thread([t1("c1")],1))])

    def test_raw_sha256_tamper_is_detected(self):
        temp,out,run,s=self.passing(); self.addCleanup(temp.cleanup); raw=next((out/"raw").glob("*.json")); raw.write_text("{}",encoding="utf-8")
        report=load_auditor().audit(out); self.assertEqual(report["status"],"PARTIAL"); self.assertIn("raw_hash_mismatch",json.dumps(report["failures"]))

    def test_evidence_path_escape_is_rejected(self):
        temp,out,run,s=self.passing(); self.addCleanup(temp.cleanup); ledger=json.loads((out/"requests.json").read_text()); ledger[0]["body_path"]="../outside.json"; (out/"requests.json").write_text(json.dumps(ledger),encoding="utf-8")
        report=load_auditor().audit(out); self.assertIn("unsafe_evidence_path",report["failures"])

    def test_orphan_and_parent_cycle_are_detected(self):
        for mode in ("orphan","cycle"):
            with self.subTest(mode=mode):
                temp,out,run,s=run_fixture([response(thread([t1("c1"),t1("c2")],2))]); self.addCleanup(temp.cleanup)
                raw=next((out/"raw").glob("*.json")); payload=json.loads(raw.read_text()); nodes=payload[1]["data"]["children"]
                nodes[0]["data"]["parent_id"]="t1_missing" if mode=="orphan" else "t1_c2"
                if mode=="cycle": nodes[1]["data"]["parent_id"]="t1_c1"
                data=json.dumps(payload,separators=(",",":")); raw.write_text(data,encoding="utf-8")
                ledger=json.loads((out/"requests.json").read_text()); ledger[0]["sha256"]=hashlib.sha256(data.encode()).hexdigest(); (out/"requests.json").write_text(json.dumps(ledger),encoding="utf-8")
                report=load_auditor().audit(out); self.assertEqual(report["status"],"PARTIAL"); self.assertTrue(report["orphans"] if mode=="orphan" else report["cycles"])

    def test_deleted_and_removed_counter_semantics(self):
        temp,out,run,s=run_fixture([response(thread([t1("r",body="[removed]"),t1("d",body="[deleted]",author="[deleted]")],1))]); self.addCleanup(temp.cleanup)
        report=load_auditor().audit(out); self.assertEqual((report["status"],report["platform_counter_nodes"],report["tombstones"]["removed"],report["tombstones"]["deleted"]),("PASS",1,1,1))


class BatchAggregationTests(unittest.TestCase):
    def node(self, expression):
        script=f'''const c=require({json.dumps(str(CORE))}); console.log(JSON.stringify({expression}))'''
        run=subprocess.run(["node","-e",script],capture_output=True,text=True,encoding="utf-8"); self.assertEqual(run.returncode,0,run.stderr); return json.loads(run.stdout)

    def test_only_pass_threads_count_toward_target(self):
        entries=[{"audit":{"status":"PASS"},"comments":[{"id":"c1","body":"ok","author":"u"}]},{"audit":{"status":"PARTIAL"},"comments":[{"id":"c2","body":"partial","author":"u"}]}]
        result=self.node(f'c.aggregateAuditedComments({json.dumps(entries)},10)'); self.assertEqual([x["comment_id"] for x in result],["c1"])

    def test_multi_asin_global_dedupe_merges_matches(self):
        rows=[{"comment_id":"c1","comment_url":"https://reddit.com/c1","body":"ok","asin":"B012345678","matched_asins":["B012345678"],"matched_keywords":["one"]},{"comment_id":"c1","comment_url":"https://reddit.com/c1","body":"ok","asin":"B087654321","matched_asins":["B087654321"],"matched_keywords":["two"]}]
        collector=ROOT/"scripts/reddit_playwright_collector.cjs"; script=f'''const c=require({json.dumps(str(collector))}); console.log(JSON.stringify(c.merge({json.dumps(rows)}).rows[0]))'''; run=subprocess.run(["node","-e",script],capture_output=True,text=True,encoding="utf-8"); row=json.loads(run.stdout)
        self.assertEqual(row["matched_asins"],["B012345678","B087654321"]); self.assertEqual(row["matched_keywords"],["one","two"])

    def test_pass_checkpoint_skips_revisit(self):
        result=self.node('c.shouldVisitThread({thread_audits:{"https://www.reddit.com/r/dogs/comments/p1/example":"PASS"}},"https://www.reddit.com/r/dogs/comments/p1/example")'); self.assertFalse(result)

    def test_request_scope_allows_only_bound_post_and_discovered_ids(self):
        target='c.normalizePostUrl("https://www.reddit.com/r/dogs/comments/p1/example")'
        allowed=self.node(f'c.validateRequestTarget("https://www.reddit.com/r/dogs/comments/p1/example.json?raw_json=1&limit=100&sort=old",{target},"listing",[])')
        denied=self.node(f'c.validateRequestTarget("https://www.reddit.com/r/cats/comments/other/example.json?raw_json=1&limit=100&sort=old",{target},"listing",[])')
        foreign=self.node(f'c.validateRequestTarget("https://www.reddit.com/api/morechildren.json?api_type=json&raw_json=1&link_id=t3_other&children=c1&sort=old&limit_children=false",{target},"morechildren",["c1"])')
        self.assertTrue(allowed); self.assertFalse(denied); self.assertFalse(foreign)

    def test_public_projection_removes_unapproved_fields_and_post_body(self):
        payload=thread([t1("c1")],1); payload[0]["data"]["children"][0]["data"].update({"selftext":"post body","secret":"x"}); payload[1]["data"]["children"][0]["data"]["secret"]="x"
        projected=self.node(f'c.projectPublicResponse({json.dumps(payload)})')
        post=projected[0]["data"]["children"][0]["data"]; comment=projected[1]["data"]["children"][0]["data"]
        self.assertNotIn("selftext",post); self.assertNotIn("secret",post); self.assertNotIn("secret",comment)

    def test_invalid_comment_permalink_target_is_rejected(self):
        result=self.node('(()=>{try{c.normalizePostUrl("https://www.reddit.com/r/dogs/comments/p1/example/c1/");return false}catch{return true}})()')
        self.assertTrue(result)


if __name__=="__main__": unittest.main()
