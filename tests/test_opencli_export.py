"""Real artifact-tool export tests using synthetic data; never browser or historical output."""
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DEPENDENCIES=Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node'
NODE=DEPENDENCIES/'bin'/('node.exe' if os.name=='nt' else 'node')


@unittest.skipUnless(NODE.exists() and (DEPENDENCIES/'node_modules/@oai/artifact-tool').exists(),'Bundled artifact-tool runtime not installed')
class ExportTests(unittest.TestCase):
    def fixture(self,root,mode='relevance',multi=False):
        asins=['B000VAC001','B000VAC002'] if multi else ['B000VAC001']
        rows=[];posts={}
        for i,status in enumerate(['PASS','PARTIAL'] if mode=='relevance' else ['PASS','PASS'],1):
            pid=f'p{i}';cid=f'c{i}'
            audit=dict(status=status,failures=['comment_count_not_reconciled'] if status=='PARTIAL' else [],orphans=[],remaining_expand_controls=0,observed_comment_count=1,platform_comment_count=2 if status=='PARTIAL' else 1)
            row=dict(schema_version='reddit_comment_v1',platform='reddit',asin=asins[0],matched_asins=asins,query='vacuum cleaner',matched_keywords=['vacuum cleaner'],subreddit='VacuumCleaners',post_id=pid,post_title='Vacuum cleaner advice',post_url=f'https://www.reddit.com/r/VacuumCleaners/comments/{pid}/x/',comment_id=cid,parent_id=pid,depth=0,author='[deleted]',body='=My vacuum cleaner works well.\x01' if i==1 else "'My vacuum cleaner battery lasts a long time.",comment_url=f'https://www.reddit.com/r/VacuumCleaners/comments/{pid}/comment/{cid}/',audit_status=status,semantic_relevance='unmet_need',comment_gate=dict(version='2.1.0',status='PASS',reasons=[],semantic_evidence=['vacuum cleaner']))
            rows.append(row);posts[pid]=dict(audit_status=status,audit=audit)
            e=root/'evidence'/pid;e.mkdir(parents=True);(e/'comments.jsonl').write_text(json.dumps(row)+'\n',encoding='utf-8');(e/'audit.json').write_text(json.dumps(audit),encoding='utf-8');(e/'frontier.json').write_text('{}')
        trusted=[r for r in rows if r['audit_status']=='PASS'];partial=[r for r in rows if r['audit_status']=='PARTIAL']
        cp=dict(asin=asins[0],asins=asins,quality_mode=mode,target_comments=2,trusted_comments=trusted,validated_partial_comments=partial,partial_candidates=[],posts=posts,preflight_status='ready',owned_tab_closed=True,queries=[])
        manifest=dict(version='2.1.0',asin=asins[0],asins=asins,trusted_comments=len(trusted),validated_partial_comments=len(partial),effective_comments=2,doctor_status='ready',pass_posts=len(trusted),partial_posts=len(partial),blocked_posts=0)
        for name,value in [('checkpoint',cp),('manifest',manifest),('audit',{'posts':{k:v['audit'] for k,v in posts.items()}}),('query_plan',{})]:(root/(name+'.json')).write_text(json.dumps(value),encoding='utf-8')
        for name,values in [('trusted_comments',trusted),('validated_partial_comments',partial),('partial_candidates',[])]:(root/(name+'.jsonl')).write_text(''.join(json.dumps(v)+'\n' for v in values),encoding='utf-8')

    def execute(self,mode='relevance',multi=False):
        with tempfile.TemporaryDirectory(prefix='voc-export-offline-') as d:
            root=Path(d);self.fixture(root,mode,multi);delivery=root/'delivery'
            run=subprocess.run([str(NODE),str(ROOT/'scripts/reddit_playwright_collector.cjs'),'export','--out-dir',str(root),'--delivery-dir',str(delivery)],capture_output=True,text=True,encoding='utf-8',timeout=120)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            manifest=json.loads((root/'manifest.json').read_text(encoding='utf-8'));self.assertEqual(len(manifest['deliveries']),2 if multi else 1)
            for f in manifest['deliveries']:self.assertTrue(Path(f['path']).name.startswith(f['asin']+'_reddit评论_2条_'))
            check=subprocess.run(['python','-X','utf8',str(ROOT/'scripts/validate_opencli_run.py'),'--out-dir',str(root),'--read-only'],capture_output=True,text=True,encoding='utf-8')
            self.assertEqual(check.returncode,0,check.stdout+check.stderr)

    def test_relevance_eight_sheets_export_validate_and_hash_delivery(self):self.execute()
    def test_strict_six_sheets_export_only_pass(self):self.execute('strict')
    def test_multi_asin_exports_individual_names_with_global_count(self):self.execute(multi=True)
