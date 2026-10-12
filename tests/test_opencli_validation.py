import importlib.util
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('opencli_validation', ROOT / 'scripts/validate_opencli_run.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class RelevanceValidationTests(unittest.TestCase):
    def fixture(self, root):
        row = dict(comment_id='c1', comment_url='https://www.reddit.com/r/dogs/comments/p1/x/c1/',
                   body='My dog uses a lick bowl for frozen food.', post_id='p1', asin='B0HHNB798Q',matched_asins=['B0HHNB798Q'],parent_id='p1',depth=0,
                   audit_status='PARTIAL', semantic_relevance='unmet_need',
                   comment_gate=dict(status='PASS', reasons=[], semantic_evidence='lick bowl'))
        cp = dict(quality_mode='relevance', trusted_comments=[], validated_partial_comments=[row],
                  target_comments=1, preflight_status='ready', resume_baseline_comment_ids=['old'],
                  posts={'p1': dict(audit_status='PARTIAL', audit=dict(status='PARTIAL',
                                    failures=['comment_count_not_reconciled']))})
        names = ['Comments', 'Trusted_Comments', 'Validated_Partial_Comments', 'Partial_Candidates',
                 'Conversation_Map', 'Query_Performance', 'Community_Map', 'Run_Summary']
        xlsx = root / 'test.xlsx'
        from xml.sax.saxutils import escape
        with zipfile.ZipFile(xlsx,'w') as z:
            z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheets>'+''.join(f'<sheet name="{name}"/>' for name in names)+'</sheets></workbook>')
            for i in range(1,9):
                records=[row] if i in (1,3) else []
                cells=lambda r: ''.join(f'<c r="{chr(65+n)}2" t="inlineStr"><is><t>{escape(module.cell_text(r.get(key)))}</t></is></c>' for n,key in enumerate(module.PROJECTION_FIELDS))
                z.writestr(f'xl/worksheets/sheet{i}.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetViews><sheetView><pane state="frozen"/></sheetView></sheetViews><sheetData><row r="1"/>'+''.join('<row r="2">'+cells(r)+'</row>' for r in records)+'</sheetData><tableParts/></worksheet>')
        (root/'manifest.json').write_text(json.dumps(dict(excel_path=str(xlsx),trusted_comments=0,effective_comments=1)))
        (root/'audit.json').write_text(json.dumps({'posts':{'p1':cp['posts']['p1']['audit']}}))
        (root/'query_plan.json').write_text('{}')
        return cp

    def check(self, mutate=None):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            cp = self.fixture(root)
            if mutate:
                mutate(cp)
            (root / 'checkpoint.json').write_text(json.dumps(cp))
            return module.validate(root)

    def test_relevant_partial_counts_without_relabeling_pass(self):
        result = self.check()
        self.assertEqual(result['exit_code'], 0)
        self.assertEqual(result['trusted_comments'], 0)
        self.assertEqual(result['validated_partial_comments'], 1)

    def test_unfinished_frontier_is_not_eligible(self):
        result = self.check(lambda cp: cp['posts']['p1']['audit']['failures'].append('unprocessed_expand_controls'))
        self.assertIn('unsafe_partial_in_effective_comments', result['errors'])

    def test_duplicate_partial_is_rejected(self):
        result = self.check(lambda cp: cp['validated_partial_comments'].append(cp['validated_partial_comments'][0].copy()))
        self.assertIn('duplicate_comment', result['errors'])

    def test_unrelated_excel_body_is_rejected(self):
        def mutate(cp):
            cp['validated_partial_comments'][0]['body']='Different content not in the workbook'
        self.assertIn('excel_record_mismatch',self.check(mutate)['errors'])

    def test_extra_effective_rows_exceeding_target_are_rejected(self):
        self.assertIn('target_exceeded',self.check(lambda cp: cp.update(target_comments=0))['errors'])

    def test_foreign_comment_url_is_rejected(self):
        self.assertIn('invalid_comment_identity',self.check(lambda cp: cp['validated_partial_comments'][0].update(comment_url='https://example.com/c1/'))['errors'])

    def test_missing_semantic_evidence_is_rejected(self):
        result = self.check(lambda cp: cp['validated_partial_comments'][0]['comment_gate'].pop('semantic_evidence'))
        self.assertIn('new_comment_gate_not_PASS', result['errors'])

    def test_excel_parent_and_depth_must_match_checkpoint(self):
        result = self.check(lambda cp: cp['validated_partial_comments'][0].update(parent_id='wrong', depth=2))
        self.assertIn('excel_record_mismatch', result['errors'])

    def test_excel_matched_asins_must_match_checkpoint(self):
        result = self.check(lambda cp: cp['validated_partial_comments'][0].update(matched_asins=['B000VAC001']))
        self.assertIn('excel_record_mismatch', result['errors'])
