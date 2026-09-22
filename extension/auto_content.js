"use strict";
(async()=>{
  const route=RedditSessionCore.routeMarkedUrl(location.href);
  if(route.action==="ignore")return;
  if(route.action==="reject")return;
  const runId=route.run_id,send=message=>chrome.runtime.sendMessage({...message,run_id:runId});
  let auth=await send({type:"bridge-authorize"});if(auth?.status!=="ready")return;
  if(route.action==="idle")return;
  const cleanUrl=RedditSessionCore.stripFragment(location.href),parts=new URL(cleanUrl).pathname.split("/").filter(Boolean),postId=parts[parts.indexOf("comments")+1]||"";
  const allCheckpoints=auth.checkpoint?.posts||{},initialCheckpoint=allCheckpoints[postId]||auth.checkpoint?.post_id===postId&&auth.checkpoint||null;
  let latestCheckpoint=initialCheckpoint;
  const context={platform:"reddit",post_id:postId,post_url:cleanUrl};
  const bridgeCheckpoint=async checkpoint=>{latestCheckpoint={...checkpoint,post_id:postId,page_url:cleanUrl};const result=await send({type:"bridge-submit",path:"/v1/checkpoint",payload:latestCheckpoint});if(result?.status==="error")throw Error(result.error);return result};
  const bridgeCapture=async(final,audit,checkpoint,comments)=>{const payload=RedditCaptureCore.captureDocument(document,cleanUrl);payload.comments=comments||payload.comments;payload.final=!!final;payload.audit=audit||null;payload.checkpoint=checkpoint||latestCheckpoint;const result=await send({type:"bridge-submit",path:"/v1/capture",payload});if(result?.status==="error")throw Error(result.error);return result};
  const locate=control=>{const tree=document.querySelector("#comment-tree, comment-tree, shreddit-comment-tree, .commentarea, [data-testid='comment-tree']");if(!tree)return null;const norm=value=>String(value||"").replace(/\s+/g," ").trim();return[...tree.querySelectorAll("button, a[href]")].find(el=>{const label=norm(el.getAttribute("aria-label")||el.textContent),href=el.getAttribute("href");let absolute=null;try{absolute=href?new URL(href,cleanUrl).href:null}catch{}return label===control.label&&(!control.href||absolute===control.href)})||null};
  const adapter={
    snapshot:completed=>VOCRedditVisibleCapture.snapshotVisibleThread(document,context,completed),
    click:async control=>{const el=locate(control);if(!el)throw Error("comment_load_failed");el.click()},
    openOwnedTab:async control=>{
      if(!control.href)return null;
      const snap=VOCRedditVisibleCapture.snapshotVisibleThread(document,context,[...(latestCheckpoint?.expanded_control_keys||[]),control.control_key]);
      const checkpoint={...(latestCheckpoint||{}),post_id:postId,expanded_control_keys:[...new Set([...(latestCheckpoint?.expanded_control_keys||[]),control.control_key])],collected_comment_ids:[...new Set(snap.comments.map(x=>x.comment_id))],incomplete_frontier:snap.expand_controls,expansion_actions:[...(latestCheckpoint?.expansion_actions||[]),{control_key:control.control_key,label:control.label,kind:"continue_thread",new_comment_ids:0,current_comment_total:snap.comments.length,current_max_depth:Math.max(0,...snap.comments.map(x=>Number(x.depth)||0))}],stable_rounds:0,stop_reason:"continue_navigation"};
      await bridgeCheckpoint(checkpoint);await bridgeCapture(false,{status:"PARTIAL",failures:["continue_navigation"]},checkpoint,snap.comments);
      location.href=RedditSessionCore.withRunFragment(control.href,runId);return new Promise(()=>{});
    },
    scrollComments:async()=>{const nodes=document.querySelectorAll("shreddit-comment, .comment[data-fullname], [data-testid='comment']");nodes[nodes.length-1]?.scrollIntoView?.({block:"end"});window.scrollBy(0,Math.max(600,Math.floor(window.innerHeight*.8)))},
    waitForStable:async(min,max)=>{const seconds=Math.max(Number(min)||1,Math.min(Number(max)||3,(Number(min)||1)+Math.random()*((Number(max)||3)-(Number(min)||1))));await new Promise(resolve=>setTimeout(resolve,seconds*1000))},
    saveCheckpoint:bridgeCheckpoint,
    now:()=>Date.now()
  };
  try{
    const result=await VOCRedditVisibleCapture.expandVisibleThread(adapter,{post_id:postId,checkpoint:initialCheckpoint,max_expand_actions:100,max_comments_per_post:500,expand_delay_min:1,expand_delay_max:3,thread_timeout:600,min_stable_rounds:4,min_scan_count:8});
    const root=auth.root_url&&RedditSessionCore.stripFragment(auth.root_url),isRoot=!root||root===cleanUrl;
    await bridgeCapture(isRoot,result.audit,result.checkpoint,result.comments);
    if(!isRoot)location.href=RedditSessionCore.withRunFragment(root,runId);
  }catch(error){
    const blocked={...(latestCheckpoint||{}),post_id:postId,stop_reason:String(error.message||error),incomplete_frontier:latestCheckpoint?.incomplete_frontier||[]};
    try{await bridgeCheckpoint(blocked);await bridgeCapture(false,{status:"BLOCKED",failures:[blocked.stop_reason]},blocked,[])}catch{}
  }
})();
