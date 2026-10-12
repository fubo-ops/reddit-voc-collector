#!/usr/bin/env python3
"""Offline validation of OpenCLI records, tiers, evidence and exact Excel projections."""
import argparse
import hashlib
import json
import re
import zipfile
from pathlib import Path
from urllib.parse import urlparse
from xml.etree import ElementTree as ET

NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
SHEETS=['Trusted_Comments','Partial_Candidates','Conversation_Map','Query_Performance','Community_Map','Run_Summary']
ILLEGAL=re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
def load(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def body_clean(s):
    s=str(s or '');return ILLEGAL.sub('',s)
def eligible(a):return a.get('status')=='PARTIAL' and bool(a.get('failures')) and set(a['failures'])=={'comment_count_not_reconciled'} and not a.get('orphans') and not a.get('remaining_expand_controls') and not a.get('blocked_state')
def belongs(r,a):return a in (r.get('matched_asins') or [r.get('asin')])
PROJECTION_FIELDS=['schema_version','platform','asin','matched_asins','query','matched_keywords','subreddit','post_id','post_title','post_url','comment_id','parent_id','depth','author','body','score','created_at','comment_url','collected_at','audit_status','semantic_relevance']
def cell_text(v):
    if v is None:return ''
    if isinstance(v,(list,dict)):return json.dumps(v,ensure_ascii=False,separators=(',',':'))
    if isinstance(v,float):return format(v,'.15g')
    return body_clean(str(v))
def projection(rows):return [tuple(cell_text(r.get(k)) for k in PROJECTION_FIELDS) for r in rows]
def excel_rows(z,index,strings):
    sheet=ET.fromstring(z.read(f'xl/worksheets/sheet{index}.xml'));rows=[]
    for row in sheet.findall('s:sheetData/s:row',NS):
        cells={}
        for c in row:
            ref=re.sub(r'\d','',c.get('r',''));v=c.find('s:v',NS)
            cells[ref]=strings[int(v.text)] if c.get('t')=='s' else ''.join(c.find('s:is',NS).itertext()) if c.get('t')=='inlineStr' else v.text if v is not None else ''
        rows.append(cells)
    return sheet,rows

def validate(directory):
    errors=[]
    for f in ('checkpoint.json','manifest.json','audit.json','query_plan.json'):
        if not (directory/f).is_file():errors.append(f+'_missing')
    if errors:return dict(status='FAIL',exit_code=1,errors=errors)
    cp=load(directory/'checkpoint.json');m=load(directory/'manifest.json');audits=load(directory/'audit.json').get('posts',{})
    mode=cp.get('quality_mode','strict');trusted=cp.get('trusted_comments',[]);partial=cp.get('validated_partial_comments',[]) if mode=='relevance' else [];rows=trusted+partial
    if mode not in ('strict','relevance'):errors.append('invalid_quality_mode')
    ids=set();urls=set();baseline=set(cp.get('resume_baseline_comment_ids',[]))
    for r in rows:
        cid=str(r.get('comment_id') or '');url=str(r.get('comment_url') or '').rstrip('/');pid=r.get('post_id');post=cp.get('posts',{}).get(pid,{});a=post.get('audit',{});body=str(r.get('body') or '').strip();u=urlparse(url)
        if not cid or u.scheme!='https' or u.hostname!='www.reddit.com' or f'/comments/{pid}/' not in u.path or not u.path.endswith('/'+cid):errors.append('invalid_comment_identity')
        canonical=u._replace(query='',fragment='').geturl().rstrip('/')
        if cid in ids or canonical in urls:errors.append('duplicate_comment')
        ids.add(cid);urls.add(canonical)
        if not body or body.casefold() in ('[deleted]','[removed]') or re.search(r'i am a bot.*(?:automatically|action|performed)',body,re.I|re.S) or str(r.get('author') or '').casefold()=='automoderator':errors.append('invalid_body_or_bot')
        is_trusted=r in trusted
        if is_trusted:
            if r.get('audit_status')!='PASS' or post.get('audit_status')!='PASS':errors.append('non_PASS_in_trusted')
            if a.get('failures') or a.get('orphans') or a.get('remaining_expand_controls'):errors.append('unsafe_PASS_audit')
        elif r.get('audit_status')!='PARTIAL' or post.get('audit_status')!='PARTIAL' or not eligible(a):errors.append('unsafe_partial_in_effective_comments')
        if pid not in audits or (a and audits[pid]!=a):errors.append('audit_checkpoint_mismatch')
        if r.get('semantic_relevance') not in ('direct_product','competitive_context','unmet_need'):errors.append('missing_semantic_qualification')
        gate=r.get('comment_gate',{})
        if cid not in baseline and (gate.get('status')!='PASS' or gate.get('reasons') or not gate.get('semantic_evidence')):errors.append('new_comment_gate_not_PASS')
        if not is_trusted and gate.get('status')!='PASS':errors.append('partial_record_gate_not_PASS')
        raw=directory/'evidence'/str(pid)/'comments.jsonl'
        if raw.is_file():
            nodes={str(n.get('comment_id')):n for n in [json.loads(x) for x in raw.read_text(encoding='utf-8-sig').splitlines() if x.strip()]}
            frontier=directory/'evidence'/str(pid)/'frontier.json'
            if frontier.is_file():nodes.update({str(n.get('comment_id')):n for n in load(frontier).get('observed_nodes',[])})
            if cid not in nodes:errors.append('comment_not_in_evidence')
            parent=re.sub(r'^t[13]_', '', str(r.get('parent_id') or ''));depth=0;seen={cid}
            while parent!=pid:
                if not parent or parent in seen or parent not in nodes:errors.append('invalid_parent_or_depth');break
                seen.add(parent);parent=re.sub(r'^t[13]_', '', str(nodes[parent].get('parent_id') or ''));depth+=1
            if not isinstance(r.get('depth'),int) or r['depth']!=depth:errors.append('invalid_parent_or_depth')
            ev=directory/'evidence'/str(pid)/'audit.json'
            if not ev.is_file() or load(ev)!=a:errors.append('audit_file_mismatch')
        elif gate.get('version')=='2.1.0':errors.append('comment_evidence_missing')
    target=cp.get('target_comments',500)
    if len(rows)<target:errors.append('target_not_reached')
    if len(rows)>target:errors.append('target_exceeded')
    if cp.get('preflight_status')!='ready':errors.append('preflight_not_ready')
    if m.get('trusted_comments')!=len(trusted):errors.append('manifest_count_mismatch')
    if mode=='relevance' and m.get('validated_partial_comments',len(partial))!=len(partial):errors.append('partial_count_mismatch')
    if m.get('effective_comments',len(trusted))!=len(rows):errors.append('effective_count_mismatch')
    if m.get('version')=='2.1.0':
        statuses=[p.get('audit_status') for p in cp.get('posts',{}).values()]
        for key,status in [('pass_posts','PASS'),('partial_posts','PARTIAL'),('blocked_posts','BLOCKED')]:
            if m.get(key)!=statuses.count(status):errors.append('manifest_audit_count_mismatch')
        if m.get('doctor_status')!='ready' or not cp.get('owned_tab_closed'):errors.append('browser_lifecycle_not_complete')
        for name,expected in [('trusted_comments',trusted),('validated_partial_comments',cp.get('validated_partial_comments',[])),('partial_candidates',cp.get('partial_candidates',[]))]:
            f=directory/(name+'.jsonl')
            if not f.is_file() or [json.loads(x) for x in f.read_text(encoding='utf-8-sig').splitlines() if x.strip()]!=expected:errors.append('jsonl_checkpoint_mismatch')
    files=m.get('workbooks') or [dict(path=m.get('excel_path','missing.xlsx'),asin=cp.get('asin'))];excel_count=0
    for book in files:
        excel=Path(book['path']);asin=book.get('asin');subset=[r for r in rows if not asin or belongs(r,asin)];t=[r for r in trusted if not asin or belongs(r,asin)];p=[r for r in partial if not asin or belongs(r,asin)]
        if not excel.is_file():errors.append('excel_missing');continue
        try:
            with zipfile.ZipFile(excel) as z:
                names=[s.attrib['name'] for s in ET.fromstring(z.read('xl/workbook.xml')).find('s:sheets',NS)];expected=['Comments','Trusted_Comments','Validated_Partial_Comments']+SHEETS[1:] if mode=='relevance' else SHEETS
                if names!=expected:errors.append('excel_sheet_contract')
                strings=[''.join(si.itertext()) for si in ET.fromstring(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
                expected_rows=[subset,t,p] if mode=='relevance' else [t]
                for index,records in enumerate(expected_rows,1):
                    sheet,data=excel_rows(z,index,strings);actual=[tuple(r.get(chr(65+n),'') for n in range(len(PROJECTION_FIELDS))) for r in data[1:]]
                    if actual!=projection(records):errors.append('excel_record_mismatch')
                    if sheet.findall('.//s:f',NS):errors.append('excel_formula_injection')
                    if index==1:excel_count+=len(data)-1
                    if sheet.find('s:sheetViews/s:sheetView/s:pane',NS) is None or sheet.find('s:tableParts',NS) is None:errors.append('excel_filter_or_freeze_missing')
        except (OSError,ValueError,zipfile.BadZipFile,ET.ParseError,KeyError,TypeError):errors.append('excel_invalid')
    deliveries=m.get('deliveries',[])
    for d in deliveries:
        f=Path(d['path']);expected=d.get('sha256')
        if not f.is_file() or hashlib.sha256(f.read_bytes()).hexdigest()!=expected:errors.append('delivery_hash_mismatch')
        source=next((Path(b['path']) for b in files if b.get('asin')==d.get('asin')),None)
        if source is None or not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest()!=expected:errors.append('delivery_source_hash_mismatch')
    return dict(status='PASS' if not errors else 'FAIL',exit_code=int(bool(errors)),errors=sorted(set(errors)),trusted_comments=len(trusted),validated_partial_comments=len(partial),effective_comments=len(rows),partial_candidates=len(cp.get('partial_candidates',[])),excel_effective_rows=excel_count,target_comments=target,excel_path=m.get('excel_path'),data_integrity_passed=not any(e!='target_not_reached' for e in errors))

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--out-dir',type=Path,required=True);parser.add_argument('--read-only',action='store_true');a=parser.parse_args()
    try:result=validate(a.out_dir)
    except (OSError,ValueError,KeyError,TypeError) as e:result=dict(status='FAIL',exit_code=1,errors=['invalid_run:'+str(e)])
    if not a.read_only:(a.out_dir/'validate.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False));return result['exit_code']
if __name__=='__main__':raise SystemExit(main())
