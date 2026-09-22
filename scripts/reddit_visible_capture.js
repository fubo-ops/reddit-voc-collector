(function (root) {
  "use strict";
  const EXPAND_LABELS=["more replies","more comments","view more replies","continue this thread","load more comments","show more","查看更多回复","更多评论","继续此讨论串"];
  const normalize=value=>String(value||"").replace(/\s+/g," ").trim();
  const stripKind=value=>normalize(value).replace(/^t[13]_/ ,"");
  const isUsefulBody=body=>{const value=normalize(body);return !!value&&!/^\[(deleted|removed)\]$/i.test(value)&&!/\bi am a bot\b.*\b(action|performed|automatically)\b/is.test(value)};
  const isExpandLabel=value=>{const t=normalize(value).toLowerCase();return EXPAND_LABELS.some(x=>t===x||t.startsWith(`${x} `))||/^(view|load|show)\s+\d+\s+more\s+(replies|comments)/i.test(t)||/^另外\s*\d+\s*条回复$/.test(t)};
  const isContinue=value=>/^(continue this thread|继续此讨论串)/i.test(normalize(value));
  const visibleBlock=value=>{const text=normalize(value);if(/blocked by network security/i.test(text))return"network_blocked";if(/captcha|robot check/i.test(text))return"captcha";if(/too many requests|http\s*429/i.test(text))return"rate_limited";if(/log in to reddit|you need to log in|sign in to reddit/i.test(text))return"login_required";if(/access denied|http\s*403/i.test(text))return"access_denied";return null};
  const absolute=(value,base)=>{try{return value?new URL(value,base||(typeof location!=="undefined"?location.href:undefined)).href:null}catch{return null}};
  const text=(el,selectors)=>{for(const selector of selectors){const node=el.querySelector(selector),value=normalize(node&&node.textContent);if(value)return value}return null};
  function dedupeComments(rows){const out=[],ids=new Set(),urls=new Set();for(const row of rows){const id=stripKind(row.comment_id),url=String(row.comment_url||"").replace(/\/$/,"");if(!id||ids.has(id)||(url&&urls.has(url)))continue;ids.add(id);if(url)urls.add(url);out.push({...row,comment_id:id})}return out}
  function captureRedditCommentTree(doc=document,context={}){
    const modern=Array.from(doc.querySelectorAll("shreddit-comment"));
    const legacy=modern.length?[]:Array.from(doc.querySelectorAll(".comment[data-fullname], [data-testid='comment']"));
    const rows=[...modern,...legacy].map(el=>{
      const id=stripKind(el.getAttribute("thingid")||el.getAttribute("data-fullname")||el.id);
      const parentEl=modern.length?null:el.parentElement?.closest?.(".comment[data-fullname], [data-testid='comment']");
      const parent=stripKind(el.getAttribute("parentid")||el.getAttribute("data-parent-id")||parentEl?.getAttribute("data-fullname")||context.post_id);
      const permalink=el.getAttribute("permalink")||el.querySelector("a[data-testid='comment_timestamp'], a.bylink, a[href*='/comment/']")?.getAttribute("href");
      const depthAttr=el.getAttribute("depth")||el.getAttribute("data-depth");
      return {...context,comment_id:id,parent_id:parent,depth:depthAttr==null?Math.max(0,Number(parentEl?.getAttribute("data-depth"))+1||0):Number.parseInt(depthAttr,10)||0,author:el.getAttribute("author")||text(el,["[slot='authorName']","a[data-testid='comment_author_link']",".author"]),body:text(el,["[slot='comment']","[data-testid='comment']",".md"]),score:Number.parseInt(el.getAttribute("score")||text(el,["[slot='vote-count']",".score.unvoted"])||"",10)||null,created_at:el.getAttribute("created-timestamp")||el.querySelector("time")?.getAttribute("datetime")||null,comment_url:absolute(permalink,context.post_url)};
    }).filter(row=>isUsefulBody(row.body));
    return dedupeComments(rows);
  }
  function findExpandControls(doc=document,context={},completed=[]){
    const done=new Set(completed),tree=doc.querySelector("#comment-tree, comment-tree, shreddit-comment-tree, .commentarea, [data-testid='comment-tree']");
    if(!tree)return[];
    return Array.from(tree.querySelectorAll("button, a[href]")).map((el,index)=>{const label=normalize(el.getAttribute("aria-label")||el.textContent),href=el.getAttribute("href"),owner=stripKind(el.closest?.("shreddit-comment, .comment[data-fullname], [data-testid='comment']")?.getAttribute("thingid")||el.closest?.(".comment[data-fullname]")?.getAttribute("data-fullname")),key=el.getAttribute("data-key")||[owner||context.post_id||"post",label.toLowerCase(),href||index].join("|");return{control_key:key,label,href:absolute(href,context.post_url),kind:isContinue(label)?"continue_thread":"expand_inline",owner_comment_id:owner||null}}).filter(x=>isExpandLabel(x.label)&&!done.has(x.control_key));
  }
  function platformCount(doc){const node=doc.querySelector("[data-comment-count]"),raw=node?.getAttribute("data-comment-count")||node?.textContent||"",match=String(raw).replace(/,/g,"").match(/\d+/);return match?Number(match[0]):null}
  function snapshotVisibleThread(doc=document,context={},completed=[]){const nodes=Array.from(doc.querySelectorAll("shreddit-comment, .comment[data-fullname], [data-testid='comment']")).map(el=>({comment_id:stripKind(el.getAttribute("thingid")||el.getAttribute("data-fullname")||el.id),parent_id:stripKind(el.getAttribute("parentid")||el.getAttribute("data-parent-id")||context.post_id)}));return{post_id:context.post_id||null,post_url:context.post_url||null,comments:captureRedditCommentTree(doc,context),observed_nodes:nodes,observed_comment_count:new Set(nodes.map(x=>x.comment_id).filter(Boolean)).size,expand_controls:findExpandControls(doc,context,completed),platform_comment_count:platformCount(doc),blocked_state:visibleBlock(doc.body?.innerText||doc.body?.textContent||"")}}
  function auditVisibleThread(snapshot,termination={}){
    const comments=dedupeComments(snapshot.comments||[]),nodes=snapshot.observed_nodes||comments,ids=new Set(nodes.map(x=>stripKind(x.comment_id))),orphans=nodes.filter(x=>x.parent_id&&stripKind(x.parent_id)!==snapshot.post_id&&!ids.has(stripKind(x.parent_id))).map(x=>stripKind(x.comment_id)),failures=[];
    if(snapshot.blocked_state)return{status:"BLOCKED",failures:[snapshot.blocked_state],orphans,captured_comments:comments.length};
    if((snapshot.expand_controls||[]).length)failures.push("unprocessed_expand_controls");
    if((termination.stable_rounds||0)<2)failures.push("two_stable_rounds_not_reached");
    if(orphans.length)failures.push("orphan_parent_ids");
    const observed=snapshot.observed_comment_count??ids.size;if(snapshot.platform_comment_count==null||snapshot.platform_comment_count!==observed)failures.push("comment_count_not_reconciled");
    if(["max_expand_actions","thread_timeout","max_comments_per_post","comment_load_failed"].includes(termination.stop_reason))failures.push(termination.stop_reason);
    return{status:failures.length?"PARTIAL":"PASS",failures:[...new Set(failures)],orphans,captured_comments:comments.length,observed_comment_count:observed,platform_comment_count:snapshot.platform_comment_count,max_depth:Math.max(0,...comments.map(x=>Number(x.depth)||0))};
  }
  async function expandVisibleThread(adapter,options={}){
    const maxActions=Number(options.max_expand_actions??100),maxComments=Number(options.max_comments_per_post??500),timeoutMs=Number(options.thread_timeout??600)*1000,started=adapter.now?adapter.now():Date.now();
    const checkpoint={...(options.checkpoint||{}),post_id:options.post_id,expanded_control_keys:[...(options.checkpoint?.expanded_control_keys||[])],collected_comment_ids:[...(options.checkpoint?.collected_comment_ids||[])],incomplete_frontier:[],expansion_actions:[...(options.checkpoint?.expansion_actions||[])],stable_rounds:0,scan_count:0,stop_reason:null};
    const commentMap=new Map(),nodeMap=new Map(),owned=[];let snapshot=await adapter.snapshot(checkpoint.expanded_control_keys),stopReason=null;checkpoint.scan_count++;
    const mergeSnapshot=value=>{for(const row of value.comments||[])if(!commentMap.has(row.comment_id))commentMap.set(row.comment_id,row);for(const node of value.observed_nodes||[])if(node.comment_id&&!nodeMap.has(node.comment_id))nodeMap.set(node.comment_id,node)};mergeSnapshot(snapshot);
    while(true){
      if(snapshot.blocked_state){stopReason=snapshot.blocked_state;break}
      if((adapter.now?adapter.now():Date.now())-started>=timeoutMs){stopReason="thread_timeout";break}
      if(commentMap.size>=maxComments){stopReason="max_comments_per_post";break}
      const controls=(snapshot.expand_controls||[]).filter(x=>!checkpoint.expanded_control_keys.includes(x.control_key));
      if(!controls.length){const before=commentMap.size;await adapter.scrollComments?.();await adapter.waitForStable?.(options.expand_delay_min??1,options.expand_delay_max??3);snapshot=await adapter.snapshot(checkpoint.expanded_control_keys);checkpoint.scan_count++;mergeSnapshot(snapshot);checkpoint.stable_rounds=commentMap.size===before?checkpoint.stable_rounds+1:0;const stableNeeded=options.min_stable_rounds??4,minScans=options.min_scan_count??8;if(checkpoint.stable_rounds>=stableNeeded&&checkpoint.scan_count>=minScans){stopReason="idle";break}continue}
      if(checkpoint.expanded_control_keys.length>=maxActions){stopReason="max_expand_actions";break}
      checkpoint.stable_rounds=0;const control=controls[0],before=commentMap.size;
      if(control.kind==="continue_thread"){const ownedTab=await adapter.openOwnedTab(control);if(!ownedTab){stopReason="comment_load_failed";break}owned.push(ownedTab);checkpoint.owned_temp_tabs=owned.slice()}else await adapter.click(control);
      checkpoint.expanded_control_keys.push(control.control_key);await adapter.waitForStable?.(options.expand_delay_min??1,options.expand_delay_max??3);await adapter.scrollComments?.();snapshot=await adapter.snapshot(checkpoint.expanded_control_keys);checkpoint.scan_count++;mergeSnapshot(snapshot);
      checkpoint.expansion_actions.push({control_key:control.control_key,label:control.label,kind:control.kind,new_comment_ids:commentMap.size-before,current_comment_total:commentMap.size,current_max_depth:Math.max(0,...[...commentMap.values()].map(x=>Number(x.depth)||0))});
      checkpoint.collected_comment_ids=[...commentMap.keys()];checkpoint.incomplete_frontier=(snapshot.expand_controls||[]).filter(x=>!checkpoint.expanded_control_keys.includes(x.control_key));await adapter.saveCheckpoint?.(checkpoint);
    }
    checkpoint.stop_reason=stopReason;checkpoint.collected_comment_ids=[...commentMap.keys()];checkpoint.incomplete_frontier=(snapshot.expand_controls||[]).filter(x=>!checkpoint.expanded_control_keys.includes(x.control_key));await adapter.saveCheckpoint?.(checkpoint);for(const tab of owned)await adapter.closeOwnedTab?.(tab);
    snapshot={...snapshot,comments:[...commentMap.values()],observed_nodes:[...nodeMap.values()],observed_comment_count:nodeMap.size,expand_controls:checkpoint.incomplete_frontier};const audit=auditVisibleThread(snapshot,{stable_rounds:checkpoint.stable_rounds,stop_reason:stopReason});return{status:audit.status,comments:snapshot.comments,expansion_log:checkpoint.expansion_actions,checkpoint,audit,owned_temp_tabs:owned};
  }
  function fixtureSnapshot(html,context={},completed=[]){
    const attr=(source,name)=>new RegExp(`${name}="([^"]*)"`,"i").exec(source)?.[1]||"",comments=[],observed=[];let match;const commentRe=/<shreddit-comment\b([^>]*)>([\s\S]*?)<\/shreddit-comment>/gi;
    while((match=commentRe.exec(html))){const body=/<(?:div|span)\b[^>]*slot="comment"[^>]*>([\s\S]*?)<\/(?:div|span)>/i.exec(match[2])?.[1]?.replace(/<[^>]+>/g,"")||"",row={...context,comment_id:stripKind(attr(match[1],"thingid")),parent_id:stripKind(attr(match[1],"parentid")||context.post_id),depth:Number(attr(match[1],"depth"))||0,author:attr(match[1],"author")||null,body:normalize(body),score:null,created_at:null,comment_url:absolute(attr(match[1],"permalink"),context.post_url)};observed.push({comment_id:row.comment_id,parent_id:row.parent_id});if(isUsefulBody(row.body))comments.push(row)}
    const controls=[],buttonRe=/<(?:button|a)\b([^>]*)>([\s\S]*?)<\/(?:button|a)>/gi;while((match=buttonRe.exec(html))){const label=normalize(match[2].replace(/<[^>]+>/g,"")),key=attr(match[1],"data-key")||label.toLowerCase();if(isExpandLabel(label)&&!completed.includes(key))controls.push({control_key:key,label,kind:isContinue(label)?"continue_thread":"expand_inline",href:absolute(attr(match[1],"href"),context.post_url),owner_comment_id:null})}
    const count=/data-comment-count="(\d+)"/i.exec(html)?.[1],observedIds=new Set(observed.map(x=>x.comment_id).filter(Boolean));return{post_id:context.post_id||null,post_url:context.post_url||null,comments:dedupeComments(comments),observed_nodes:observed,observed_comment_count:observedIds.size,expand_controls:controls,platform_comment_count:count==null?null:Number(count),blocked_state:visibleBlock(html.replace(/<[^>]+>/g," "))};
  }
  async function runFixtureExpansion(states,options={}){let index=0,time=0;const context={post_id:options.post_id||"p1",post_url:"https://www.reddit.com/r/dogs/comments/p1/x/"};return expandVisibleThread({snapshot:done=>fixtureSnapshot(states[Math.min(index,states.length-1)],context,done),click:async()=>{index=Math.min(index+1,states.length-1)},openOwnedTab:async control=>{index=Math.min(index+1,states.length-1);return`owned:${control.control_key}`},closeOwnedTab:async()=>{},scrollComments:async()=>{if(options.advance_on_scroll)index=Math.min(index+1,states.length-1)},waitForStable:async()=>{time+=1000},saveCheckpoint:async()=>{},now:()=>time},options)}
  const api={EXPAND_LABELS,isUsefulBody,isExpandLabel,visibleBlock,captureRedditCommentTree,findExpandControls,snapshotVisibleThread,auditVisibleThread,expandVisibleThread,fixtureSnapshot,runFixtureExpansion};root.VOCRedditVisibleCapture=api;if(typeof module!=="undefined")module.exports=api;
})(typeof window!=="undefined"?window:globalThis);
