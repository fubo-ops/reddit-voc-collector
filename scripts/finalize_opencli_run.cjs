#!/usr/bin/env node
'use strict';
const fs=require('node:fs'),path=require('node:path'),os=require('node:os'),{spawnSync}=require('node:child_process');
async function finalize(o={}){
  const pythonBundle=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/python',process.platform==='win32'?'python.exe':'bin/python3');const python=o.python||process.env.REDDIT_PYTHON||(fs.existsSync(pythonBundle)?pythonBundle:'python');
  const dir=path.resolve(o.outDir||'outputs/reddit-comments'),bundled=path.join(os.homedir(),'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin',process.platform==='win32'?'node.exe':'node');
  const runtime=process.env.ARTIFACT_NODE|| (fs.existsSync(bundled)?bundled:process.execPath);
  const run=spawnSync(runtime,[path.join(__dirname,'build_opencli_workbook.mjs'),'--out-dir',dir,'--python',python,...(o.preview?['--preview']:[])],{stdio:'inherit',windowsHide:true});if(run.error)throw run.error;if(run.status!==0)return run.status??1;
  const check=spawnSync(python,['-X','utf8',path.join(__dirname,'validate_opencli_run.py'),'--out-dir',dir],{stdio:'inherit',windowsHide:true});if(check.status!==0)return check.status??1;
  const deliveries=require('./excel_delivery.cjs').deliver(dir,o.deliveryDir);console.log(JSON.stringify({status:'validated_and_delivered',deliveries}));return 0;
}
module.exports={finalize};
if(require.main===module){const core=require('./reddit_playwright_collector.cjs'),args=process.argv.slice(2);if(args[0]&&!args[0].startsWith('--')&&args[0]!=='export')args.unshift('--out-dir');finalize(core.args(args)).then(c=>process.exitCode=c).catch(e=>{console.error(e);process.exitCode=1;});}
