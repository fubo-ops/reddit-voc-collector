import csv
import importlib.util
import json
import socket
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path); module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module
PLANNER = load("planner", ROOT / "scripts/reddit_query_planner.py")
NORMALIZER = load("normalizer", ROOT / "scripts/normalize_raw_jsonl.py")

class AsinInputTests(unittest.TestCase):
    def test_single_asin(self): self.assertEqual(PLANNER.parse_asin_inputs(asin="B012345678"), ["B012345678"])
    def test_multiple_asins_are_normalized_and_deduped(self):
        self.assertEqual(PLANNER.parse_asin_inputs(asins="b012345678, B087654321,b012345678"), ["B012345678", "B087654321"])
    def test_txt_and_csv_asin_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            txt = Path(tmp)/"a.txt"; txt.write_text("B012345678\nB087654321\n", encoding="utf-8")
            self.assertEqual(PLANNER.parse_asin_inputs(asin_file=txt), ["B012345678", "B087654321"])
            cp = Path(tmp)/"a.csv"
            with cp.open("w", newline="", encoding="utf-8") as f: csv.writer(f).writerows([["asin"], ["B000000001"], ["B000000002"]])
            self.assertEqual(PLANNER.parse_asin_inputs(asin_file=cp), ["B000000001", "B000000002"])

class KeywordTests(unittest.TestCase):
    def test_keyword_cleaning_and_dedupe(self):
        self.assertEqual(PLANNER.clean_keywords([" Dog  Bed ", "dog bed", "DOG BED", "washable\ncover", ""]), ["Dog Bed", "washable cover"])

class CommentTests(unittest.TestCase):
    def sample(self, **updates):
        row={"asin":"B012345678","matched_asins":["B012345678"],"query":"dog bed","matched_keywords":["dog bed"],"subreddit":"dogs","post_id":"p1","post_title":"Bed advice","post_url":"https://reddit.com/r/dogs/comments/p1/x","comment_id":"c1","parent_id":"p1","depth":0,"author":"u","body":"This bed is easy to wash.","score":4,"created_at":"2026-01-01T00:00:00Z","comment_url":"https://reddit.com/r/dogs/comments/p1/x/c1/"}; row.update(updates); return row
    def test_comment_tree_flattening(self):
        rows=NORMALIZER.flatten_comment_tree([{"id":"c1","body":"one","replies":[{"id":"c2","body":"two","replies":[]}]}], {"post_id":"p1"})
        self.assertEqual([(r["comment_id"],r["depth"],r["parent_id"]) for r in rows], [("c1",0,"p1"),("c2",1,"c1")])
    def test_comment_fields_are_normalized(self):
        row=NORMALIZER.normalize_comment(self.sample(), collected_at="2026-02-02T00:00:00Z")
        required={"schema_version","platform","asin","matched_asins","query","matched_keywords","subreddit","post_id","post_title","post_url","comment_id","parent_id","depth","author","body","score","created_at","comment_url","collected_at","relevance_tier","association_reason","evidence_terms","relevance_score","comment_relevance_score","discovery_round","query_family","source_query","community_source","comment_record_status","thread_audit_status","thread_evidence_path"}
        self.assertEqual(set(row),required); self.assertEqual(row["platform"],"reddit")
    def test_comment_id_and_url_dedupe_merges_asins(self):
        rows,stats=NORMALIZER.dedupe_comments([self.sample(),self.sample(asin="B087654321",matched_asins=["B087654321"],query="pet mat")])
        self.assertEqual(len(rows),1); self.assertEqual(rows[0]["matched_asins"],["B012345678","B087654321"]); self.assertEqual(stats["deduplicated"],1)
    def test_deleted_removed_empty_and_bot_notice_are_filtered(self):
        rows=[self.sample(comment_id=f"c{i}",body=body,comment_url=f"https://x/{i}") for i,body in enumerate(["","[deleted]","[removed]","I am a bot, and this action was performed automatically.","useful"])]
        kept,stats=NORMALIZER.prepare_comments(rows); self.assertEqual([r["body"] for r in kept],["useful"]); self.assertEqual(stats["filtered"],4)
    def test_target_comments_counts_valid_unique_comments(self):
        rows=[self.sample(),self.sample(),self.sample(comment_id="c2",comment_url="https://x/c2",body="second")]
        self.assertFalse(NORMALIZER.target_comments_reached(rows,3)); self.assertTrue(NORMALIZER.target_comments_reached(rows,2))

class ContractTests(unittest.TestCase):
    def run_collector_expression(self, expression):
        script=f'''const c=require({json.dumps(str(ROOT / "scripts/reddit_playwright_collector.cjs"))}); console.log(JSON.stringify({expression}))'''
        run=subprocess.run(["node","-e",script],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(run.returncode,0,run.stderr)
        return json.loads(run.stdout)

    def test_selected_chrome_tab_transport_never_uses_cdp(self):
        plan=self.run_collector_expression('c.transportPlan(c.args(["preflight","--session-mode","selected-chrome-tab"]))')
        self.assertEqual(plan,{"mode":"selected-chrome-tab","bridge":"codex-computer-use-extension","requires_cdp":False,"auto_start_cdp":False,"independent_cli":False})

    def test_retry_partial_flags_are_boolean_and_build_24_post_queue(self):
        checkpoint={
            "searched_keywords":["B003ULL1NQ|Cosequin reviews"],
            "selected_visible_threads":{
                **{f"partial-{i}":{"audit_status":"PARTIAL","post_url":f"https://www.reddit.com/comments/p{i}/"} for i in range(24)},
                "pass":{"audit_status":"PASS","post_url":"https://www.reddit.com/comments/pass/"},
            },
        }
        expression=(
            '({parsed:c.args(["collect","--retry-partial","--force-reaudit-partial"]),'
            f'queue:c.partialReauditQueue({json.dumps(checkpoint)},{{retryPartial:true,forceReauditPartial:true}})}})'
        )
        result=self.run_collector_expression(expression)
        self.assertTrue(result["parsed"]["retryPartial"])
        self.assertTrue(result["parsed"]["forceReauditPartial"])
        self.assertEqual(len(result["queue"]),24)
        self.assertTrue(all(item["previous_status"]=="PARTIAL" for item in result["queue"]))

    def test_retry_partial_queue_does_not_depend_on_completed_keywords(self):
        checkpoint={"searched_keywords":["done"],"selected_visible_threads":{"p1":{"status":"PARTIAL","post_url":"https://www.reddit.com/comments/p1/"}}}
        queue=self.run_collector_expression(f'c.partialReauditQueue({json.dumps(checkpoint)},{{retryPartial:true}})')
        self.assertEqual([item["post_id"] for item in queue],["p1"])

    def test_selected_tab_preflight_accepts_only_explicit_extension_binding(self):
        binding={"tab_id":"tab-1","provider_tab_id":"provider-1","browser_type":"extension","explicitly_selected":True}
        snapshot={**binding,"url":"https://www.reddit.com/","title":"Reddit","body":"Home Popular Create Post","reddit_root":True}
        result=self.run_collector_expression(f'c.selectedTabPreflight({json.dumps(binding)},{json.dumps(snapshot)})')
        self.assertEqual(result["status"],"ready")
        self.assertEqual(result["browser"],"selected-chrome-tab")

    def test_selected_tab_identity_change_fails_closed(self):
        binding={"tab_id":"tab-1","provider_tab_id":"provider-1","browser_type":"extension","explicitly_selected":True}
        changed={**binding,"provider_tab_id":"provider-2","url":"https://www.reddit.com/","title":"Reddit","body":"Home","reddit_root":True}
        result=self.run_collector_expression(f'c.selectedTabPreflight({json.dumps(binding)},{json.dumps(changed)})')
        self.assertEqual(result["status"],"stopped")
        self.assertEqual(result["stop_reason"],"selected_tab_identity_changed")

    def test_selected_tab_non_reddit_navigation_stops(self):
        binding={"tab_id":"tab-1","provider_tab_id":"provider-1","browser_type":"extension","explicitly_selected":True}
        snapshot={**binding,"url":"https://example.com/","title":"Example","body":"Example Domain","reddit_root":False}
        result=self.run_collector_expression(f'c.selectedTabPreflight({json.dumps(binding)},{json.dumps(snapshot)})')
        self.assertEqual(result["stop_reason"],"selected_tab_left_reddit")

    def test_selected_tab_frontier_capability_uses_visible_dom_without_fetch(self):
        result=self.run_collector_expression('c.selectedTabCapability({evaluate:true,dom:true,navigation:true,owned_temp_tabs:true,same_origin_fetch:false})')
        self.assertEqual(result["capture_mode"],"visible_dom")
        self.assertFalse(result["json_frontier_available"])

    def test_selected_tab_cli_does_not_probe_9222(self):
        run=subprocess.run(["node",str(ROOT/"scripts/reddit_playwright_collector.cjs"),"preflight","--session-mode","selected-chrome-tab"],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(run.returncode,2,run.stderr)
        result=json.loads(run.stdout)
        self.assertEqual(result["status"],"codex_bridge_required")
        self.assertNotIn("cdp_url",result)

    def test_selected_tab_docs_define_codex_only_boundary(self):
        docs=((ROOT/"SKILL.md").read_text(encoding="utf-8")+"\n"+(ROOT/"references/collection-guide.md").read_text(encoding="utf-8"))
        for phrase in ["selected-chrome-tab","@Chrome","Codex task only","does not probe port 9222","visible-DOM frontier"]:
            self.assertIn(phrase,docs)

    def test_required_files_and_no_old_runtime_dependency(self):
        required=["SKILL.md","agents/openai.yaml","references/collection-guide.md","references/raw-record-schema.md","scripts/reddit_playwright_collector.cjs","scripts/reddit_thread_core.cjs","scripts/audit_thread_evidence.py","scripts/reddit_query_planner.py","scripts/reddit_visible_capture.js","scripts/normalize_raw_jsonl.py","scripts/start_reddit_cdp.ps1"]
        for rel in required: self.assertTrue((ROOT/rel).is_file(),rel)
        forbidden=["reddit-"+"review-collector", "voc-data-"+"collection"]
        for path in ROOT.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                text=path.read_text(encoding="utf-8",errors="ignore"); self.assertFalse(any(x.casefold() in text.casefold() for x in forbidden),str(path))
    def test_access_state_classifier(self):
        script = f'''const c=require({json.dumps(str(ROOT / "scripts/reddit_playwright_collector.cjs"))}); console.log(JSON.stringify([c.classify("Log In"),c.classify("Log in to Reddit"),c.classify("You've been blocked by network security"),c.classify("ok",429),c.classify("HTTP 429 Too Many Requests"),c.classify("HTTP 403 Access denied")]))'''
        run=subprocess.run(["node","-e",script],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(run.returncode,0,run.stderr)
        states=[x["status"] for x in json.loads(run.stdout)]
        self.assertEqual(states,["ready","login_required","network_blocked","ready","rate_limited","access_denied"])
    def test_cdp_is_default_and_requires_endpoint(self):
        script=f'''const c=require({json.dumps(str(ROOT / "scripts/reddit_playwright_collector.cjs"))}); console.log(JSON.stringify(c.args(["preflight"])))'''
        run=subprocess.run(["node","-e",script],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(run.returncode,0,run.stderr)
        parsed=json.loads(run.stdout)
        self.assertEqual(parsed["sessionMode"],"cdp")
        self.assertEqual(parsed["cdpUrl"],"http://127.0.0.1:9222")

    def test_closed_cdp_port_is_not_a_reddit_access_denial(self):
        with socket.socket() as probe:
            probe.bind(("127.0.0.1",0)); port=probe.getsockname()[1]
        script=f'''const c=require({json.dumps(str(ROOT / "scripts/reddit_playwright_collector.cjs"))}); c.probeCdp("http://127.0.0.1:{port}").then(x=>console.log(JSON.stringify(x)))'''
        run=subprocess.run(["node","-e",script],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(run.returncode,0,run.stderr)
        result=json.loads(run.stdout)
        self.assertEqual(result["status"],"cdp_not_listening")
        self.assertNotEqual(result["status"],"access_denied")

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell contract")
    def test_powershell_start_script_syntax(self):
        script=ROOT/"scripts/start_reddit_cdp.ps1"
        command=f'''$e=$null;$t=$null;[System.Management.Automation.Language.Parser]::ParseFile('{script}',[ref]$t,[ref]$e)|Out-Null;if($e.Count){{$e|ForEach-Object{{$_.Message}};exit 1}}'''
        run=subprocess.run(["powershell","-NoProfile","-Command",command],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(run.returncode,0,run.stderr+run.stdout)

    @unittest.skipUnless(sys.platform == "win32", "Windows PowerShell contract")
    def test_listening_port_does_not_start_chrome(self):
        listener=socket.socket(); listener.bind(("127.0.0.1",0)); listener.listen(); port=listener.getsockname()[1]
        try:
            run=subprocess.run(["powershell","-NoProfile","-ExecutionPolicy","Bypass","-File",str(ROOT/"scripts/start_reddit_cdp.ps1"),"-Port",str(port),"-ChromePath","Z:\\missing\\chrome.exe"],capture_output=True,text=True,encoding="utf-8",timeout=30)
        finally: listener.close()
        self.assertEqual(run.returncode,0,run.stderr+run.stdout)
        result=json.loads(run.stdout.strip().splitlines()[-1])
        self.assertEqual(result["status"],"ready")
        self.assertTrue(result["already_listening"])
        self.assertFalse(result["started"])

    def test_collector_uses_existing_cdp_without_http_clients_or_blank_profile(self):
        source=(ROOT/"scripts/reddit_playwright_collector.cjs").read_text(encoding="utf-8")
        self.assertIn("connectOverCDP",source)
        self.assertNotIn("launchPersistentContext",source)
        for forbidden in ["fetch(","https.request", "http.request", "axios", "requests.get", "curl "]:
            self.assertNotIn(forbidden,source)

    def test_help_documents_cdp_connection(self):
        run=subprocess.run(["node",str(ROOT/"scripts/reddit_playwright_collector.cjs"),"--help"],capture_output=True,text=True,encoding="utf-8")
        self.assertEqual(run.returncode,0,run.stderr)
        for value in ["--session-mode cdp","--cdp-url","existing visible Chrome"]:
            self.assertIn(value,run.stdout)
    def test_cli_contracts_and_js_syntax(self):
        commands=[["node","--check",str(ROOT/"scripts/reddit_playwright_collector.cjs")],["node","--check",str(ROOT/"scripts/reddit_thread_core.cjs")],["node","--check",str(ROOT/"scripts/reddit_visible_capture.js")],["node",str(ROOT/"scripts/reddit_playwright_collector.cjs"),"--help"],["node",str(ROOT/"scripts/reddit_thread_core.cjs"),"--help"],[sys.executable,str(ROOT/"scripts/audit_thread_evidence.py"),"--help"],[sys.executable,str(ROOT/"scripts/reddit_query_planner.py"),"--help"],[sys.executable,str(ROOT/"scripts/normalize_raw_jsonl.py"),"--help"]]
        outputs=[]
        for command in commands:
            run=subprocess.run(command,capture_output=True,text=True,encoding="utf-8"); self.assertEqual(run.returncode,0,run.stderr); outputs.append(run.stdout)
        combined="\n".join(outputs)
        for flag in ["--asin","--asins","--asin-file","--target-comments","preflight","outputs/reddit-comments"]: self.assertIn(flag,combined)
if __name__=="__main__": unittest.main()
