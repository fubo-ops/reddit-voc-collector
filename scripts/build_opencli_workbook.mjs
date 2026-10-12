import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {createRequire} from 'node:module';
import {pathToFileURL,fileURLToPath} from 'node:url';
import {spawnSync} from 'node:child_process';
const require=createRequire(import.meta.url),delivery=require('./excel_delivery.cjs');
const load=f=>JSON.parse(fs.readFileSync(f,'utf8').replace(/^\uFEFF/,''));
export const clean=v=>typeof v==='string'?(/^\s*[=+@-]/.test(v)?"'":'')+v.replace(/[\x00-\x08\x0b\x0c\x0e-\x1f]/g,''):Array.isArray(v)||v&&typeof v==='object'?JSON.stringify(v):v??null;
export const SHEETS=['Trusted_Comments','Partial_Candidates','Conversation_Map','Query_Performance','Community_Map','Run_Summary'];
export const sheetsFor=mode=>mode==='relevance'?['Comments','Trusted_Comments','Validated_Partial_Comments',...SHEETS.slice(1)]:SHEETS;
const columns=['schema_version','platform','asin','matched_asins','query','matched_keywords','subreddit','post_id','post_title','post_url','comment_id','parent_id','depth','author','body','score','created_at','comment_url','collected_at','audit_status','semantic_relevance','comment_gate_status','semantic_evidence','comment_gate_reasons'];
async function artifact(){
  const modules=process.env.ARTIFACT_NODE_MODULES||path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules');
  let entry;try{entry=require.resolve('@oai/artifact-tool',{paths:[path.dirname(modules)]});}catch{throw Error('artifact_runtime_missing: set ARTIFACT_NODE_MODULES to the bundled Node packages');}
  return import(pathToFileURL(entry).href);
}
const mapped=rows=>rows.map(r=>({...r,comment_gate_status:r.comment_gate?.status||'prior_PASS_preserved',semantic_evidence:r.comment_gate?.semantic_evidence||null,comment_gate_reasons:r.comment_gate?.reasons||[]}));
const belongs=(r,a)=>(r.matched_asins?.length?r.matched_asins:[r.asin]).includes(a);
export async function exportRun(dir,options={}){
  dir=path.resolve(dir);const cp=load(path.join(dir,'checkpoint.json')),m=load(path.join(dir,'manifest.json'));
  const {Workbook,SpreadsheetFile}=await artifact();const mode=cp.quality_mode||'strict',asins=cp.asins||[cp.asin],stamp=new Date().toISOString().replace(/[-:]/g,'').replace(/\.\d{3}Z$/,'Z'),files=[];
  const accepted=mode==='relevance'?[...cp.trusted_comments,...(cp.validated_partial_comments||[])]:cp.trusted_comments;
  for(const asin of asins){const count=accepted.filter(r=>belongs(r,asin)).length,output=path.join(dir,delivery.filename(asin,count,stamp));if(fs.existsSync(output))throw Error('export_destination_exists');files.push({asin,count,path:output,stamp});}
  m.workbooks=files;m.excel_path=files[0].path;m.export_timestamp=stamp;m.validate_status='pending';m.validate_exit_code=null;
  fs.writeFileSync(path.join(dir,'manifest.json'),JSON.stringify(m,null,2));
  const built=[];
  function sheet(wb,name,records,fields){
    const s=wb.worksheets.add(name);s.showGridLines=false;const matrix=[fields,...records.map(r=>fields.map(k=>clean(r[k])))],range=s.getRangeByIndexes(0,0,matrix.length,fields.length);range.values=matrix;
    range.format.font={name:'Arial',size:10,color:'#1F2937'};range.format.verticalAlignment='top';range.format.columnWidth=26;
    s.getRangeByIndexes(0,0,1,fields.length).format={fill:'#1F4E78',font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},wrapText:true,rowHeight:32};
    s.freezePanes.freezeRows(1);s.tables.add(`A1:${String.fromCharCode(64+fields.length)}${matrix.length}`,true,name.replace(/_/g,'')+'Table');
    for(let i=0;i<fields.length;i++){const c=s.getRangeByIndexes(0,i,matrix.length,1);if(fields[i]==='body'){c.format.columnWidth=75;c.format.wrapText=true;}else if(/url|title|reason|value|evidence/.test(fields[i])){c.format.columnWidth=50;c.format.wrapText=true;}else if(/id$/.test(fields[i]))c.setNumberFormat('@');}
    if(records.length)s.getRangeByIndexes(1,0,records.length,fields.length).format.autofitRows();return s;
  }
  for(const f of files){
    const wb=Workbook.create(),trusted=cp.trusted_comments.filter(r=>belongs(r,f.asin)),partial=(cp.validated_partial_comments||[]).filter(r=>belongs(r,f.asin)),candidates=(cp.partial_candidates||[]).filter(r=>belongs(r,f.asin)),product=cp.product_profile?.products[f.asin]||m.products?.[f.asin]||{};
    if(mode==='relevance')sheet(wb,'Comments',mapped([...trusted,...partial]),columns);
    sheet(wb,'Trusted_Comments',mapped(trusted),columns);if(mode==='relevance')sheet(wb,'Validated_Partial_Comments',mapped(partial),columns);sheet(wb,'Partial_Candidates',mapped(candidates),columns);
    sheet(wb,'Conversation_Map',Object.entries(product).map(([field,value])=>({layer:'observed_product_metadata',field,value,asin:f.asin})),['layer','field','value','asin']);
    sheet(wb,'Query_Performance',(cp.queries||[]).filter(q=>!q.asin||q.asin===f.asin),['query','family','discovery_round','generation_source','evidence_comment_ids','used_for_search','completed','posts_found','valid_comments_found']);
    const communities=[...new Set([...trusted,...partial].map(r=>r.subreddit).filter(Boolean))].map(subreddit=>({subreddit,source:'observed_reddit_threads',trusted_comments:trusted.filter(r=>r.subreddit===subreddit).length,validated_partial_comments:partial.filter(r=>r.subreddit===subreddit).length}));sheet(wb,'Community_Map',communities,['subreddit','source','trusted_comments','validated_partial_comments']);
    const summary={...m,workbook_asin:f.asin,workbook_valid_comments:f.count,workbook_trusted_comments:trusted.length,workbook_validated_partial_comments:mode==='relevance'?partial.length:0},entries=Object.entries(summary),s=sheet(wb,'Run_Summary',entries.map(([metric,value])=>({metric,value})),['metric','value']);wb.recalculate();
    // Reserve a new filename; subsequent writes only touch files created in this invocation.
    fs.closeSync(fs.openSync(f.path,'wx'));await(await SpreadsheetFile.exportXlsx(wb)).save(f.path);built.push({wb,s,entries,file:f});
    if(options.preview){const p=path.join(dir,'_workbook_preview',f.asin);fs.mkdirSync(p,{recursive:true});for(const name of sheetsFor(mode)){const img=await wb.render({sheetName:name,range:name==='Run_Summary'?'A1:B16':'A1:D4',scale:1,format:'png'});fs.writeFileSync(path.join(p,name+'.png'),new Uint8Array(await img.arrayBuffer()));}}
  }
  const check=spawnSync(options.python||'python',['-X','utf8',path.join(path.dirname(fileURLToPath(import.meta.url)),'validate_opencli_run.py'),'--out-dir',dir],{encoding:'utf8',windowsHide:true});
  if(check.error)throw check.error;if(check.stdout)process.stdout.write(check.stdout);if(check.stderr)process.stderr.write(check.stderr);const status=check.status??1;m.validate_exit_code=status;m.validate_status=status===0?'PASS':'FAIL';fs.writeFileSync(path.join(dir,'manifest.json'),JSON.stringify(m,null,2));
  for(const b of built){for(const key of ['validate_status','validate_exit_code']){const index=b.entries.findIndex(([k])=>k===key);b.s.getRangeByIndexes(index+1,1,1,1).values=[[m[key]]];}await(await SpreadsheetFile.exportXlsx(b.wb)).save(b.file.path);}
  console.log(JSON.stringify({workbooks:files,validate_exit_code:status}));return status;
}
if(process.argv[1]&&path.resolve(process.argv[1])===fileURLToPath(import.meta.url)){
  if(process.argv.includes('--help')){console.log('Usage: node scripts/build_opencli_workbook.mjs --out-dir RUN_DIR [--python PYTHON] [--preview]\nUses the Codex bundled artifact-tool runtime; never replaces existing exports.');}
  else {const args=process.argv.slice(2),get=k=>args[args.indexOf(k)+1],dir=args.includes('--out-dir')?get('--out-dir'):args[0];if(!dir)throw Error('out_dir_required');exportRun(dir,{python:args.includes('--python')?get('--python'):undefined,preview:args.includes('--preview')}).then(c=>{process.exitCode=c;}).catch(e=>{console.error(e);process.exitCode=1;});}
}
