'use strict';
const clean=xs=>[...new Map((xs||[]).flat(Infinity).filter(x=>typeof x==='string'&&x.trim()).map(x=>[x.trim().toLowerCase(),x.trim()])).values()];
const words=text=>String(text||'').toLowerCase().normalize('NFKC').replace(/[^\p{L}\p{N}]+/gu,' ').trim().split(/\s+/).filter(Boolean).map(w=>w.length>4&&w.endsWith('s')?w.slice(0,-1):w);
const STOP=new Set('the a an with for and or of to from by on in at my your this that it its is are was as new original pack count size inch ml cm oz all more product products'.split(' '));
const tokens=t=>words(t).filter(x=>!STOP.has(x)&&!/^\d+$/.test(x));
const has=(text,term)=>{const w=new Set(words(text)),t=tokens(term);return t.length>0&&t.every(x=>w.has(x));};
const USE=/\b(use|uses|used|using|work|works|worked|love|loves|enjoy|enjoys|bought|buy|recommend|review|battery|break|broke|leak|leaks|slip|slips|spill|clean|cleaning|wash|washable|stuck|suction|noisy|noise|weak|last|lasts|lasted|struggle|struggles|problem|issue|cost|price|worth|safe|unsafe|help|helps|helped|return|returned|stop|stopped|prefer|try|tried|instead|vs|versus)\b|使用|好用|不好用|清洗|漏|坏|推荐|噪音|续航|效果|价格/i;
function buildProfile(metadata={},asin){
  const inputs=metadata.products||metadata.product&&{[metadata.product.asin||asin]:metadata.product}||{};
  const products={};
  for(const [id,p]of Object.entries(inputs)){
    if(!/^[A-Z0-9]{10}$/.test(id))throw Error('invalid_product_asin');
    if(p.asin&&p.asin!==id)throw Error('product_asin_mismatch');
    const names=clean([p.common_names||[],p.aliases||[],p.product_name||'',p.product_types||[],p.category||'']);
    if(!clean([p.common_names||[],p.aliases||[],p.product_name||'']).length&&p.title)names.push(tokens(p.title).filter(t=>!has(p.brand,t)).slice(0,6).join(' '));
    const keywords=metadata.seller_keywords?.[id]||{};
    products[id]={...p,asin:id,names,anchors:clean(names),brand:p.brand||'',model_terms:clean(p.model_terms||[]),competitors:clean([p.competitor_brands||[],p.competitor_products||[],keywords.competitor||[]]),problems:clean([p.problems||[],p.pain_points||[],p.user_problems||[]]),contexts:clean([p.contexts||[],p.use_scenarios||[]]),features:clean([p.functions||[],p.attributes||[],p.features||[]]),seller_keywords:keywords};
  }
  return {schema_version:'reddit_product_rules_v1',products,asins:Object.keys(products)};
}
function productMatch(text,p){
  const hits=p.anchors.filter(a=>has(text,a));
  const distinct=clean(p.anchors.flatMap(tokens)).filter(t=>has(text,t));
  // Single common words alone are ambiguous; require an observed category token pair.
  return hits.some(h=>tokens(h).length>=2||(tokens(h).length===1&&tokens(h)[0].length>=5&&!['device','accessory','equipment','item','product'].includes(tokens(h)[0])))||distinct.length>=2;
}
function semantics(row,profile){
  const body=String(row.body||''),matches=[];
  if(body.trim().length<20||!(USE.test(body)||words(body).some(w=>USE.test(w))))return {tier:null,evidence:[],matched_asins:[]};
  for(const p of Object.values(profile?.products||{})){
    const linked=productMatch(body,p),competitor=p.competitors.find(t=>has(body,t));
    const direct=(p.brand&&has(body,p.brand))||p.model_terms.some(t=>has(body,t));
    const categorySeen=p.anchors.flatMap(tokens).some(t=>has(body,t));
    if(!(linked||competitor||(direct&&categorySeen)))continue;
    const tier=direct?'direct_product':competitor?'competitive_context':'unmet_need';
    const evidence=clean([...(direct?[p.brand,...p.model_terms.filter(t=>has(body,t))]:[]),...(competitor?[competitor]:[]),...p.anchors.filter(t=>has(body,t)),...p.anchors.flatMap(tokens).filter(t=>has(body,t))]);
    matches.push({asin:p.asin,tier,evidence});
  }
  const best=matches.find(x=>x.tier==='direct_product')||matches.find(x=>x.tier==='competitive_context')||matches[0];
  return {tier:best?.tier||null,evidence:clean(matches.flatMap(x=>x.evidence)),matched_asins:matches.map(x=>x.asin)};
}
function relevantPost(title,_url='',profile){return Object.values(profile?.products||{}).some(p=>productMatch(title,p)||p.competitors.some(t=>has(title,t))||(p.brand&&has(title,p.brand)));}
function qualify(row,_threadRelevant,profile){return semantics(row,profile).tier;}
function seeds(profile){
  const out=[];
  for(const p of Object.values(profile?.products||{})){
    const add=(query,family,source='amazon_visible_product')=>{if(query?.trim())out.push({asin:p.asin,query:query.trim(),family,discovery_round:1,generation_source:source,source_terms:[query.trim()],evidence_comment_ids:[],source_url:p.source_url||null,completed:false});};
    for(const n of p.names.slice(0,4)){add(n,'category_solution');if(p.brand)add(`${p.brand} ${n}`,'product_entity');add(`${n} reviews worth it`,'decision_intent');}
    for(const t of p.problems)add(t,'problem_symptom');for(const t of p.contexts)add(`${p.names[0]||p.title} ${t}`,'usage_context');
    for(const [kind,values]of Object.entries(p.seller_keywords))if(Array.isArray(values))for(const t of values)add(t,kind==='competitor'?'competitor':'product_entity','sellersprite_visible_keywords');
  }
  return [...new Map(out.map(q=>[`${q.asin}|${q.query.toLowerCase()}`,q])).values()];
}
function evidencedQueries(rows,existing,round,profile){
  const used=new Set(existing.map(q=>q.query.toLowerCase())),out=[];
  for(const row of rows){if(!semantics(row,profile).tier)continue;
    for(const sentence of String(row.body||'').split(/[.!?\n]+/)){
      const w=sentence.replace(/[^\p{L}\p{N}' -]+/gu,' ').trim().split(/\s+/);
      for(let i=0;i<w.length;i++){
        const phrase=w.slice(i,i+7).join(' ');
        if(phrase.length<15||!semantics({body:phrase},profile).tier)continue;
        const query=phrase.toLowerCase();if(used.has(query))break;
        const match=semantics({body:phrase},profile);out.push({query,asin:match.matched_asins[0],family:'community_language',discovery_round:round,generation_source:'observed_reddit_comments',source_terms:[phrase],evidence_comment_ids:[row.comment_id],semantic_link:match.evidence.join(' | '),completed:false});used.add(query);break;
      }
      if(out.length>=12)return out;
    }
  }
  return out;
}
function learnCommunity(profile,rows){
  for(const row of rows){const match=semantics(row,profile);if(!match.tier||!row.comment_id)continue;const text=String(row.body||'');
    const candidates=[...text.matchAll(/\b([A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z0-9][A-Za-z0-9-]*){0,2})\s+(?:instead of|versus|vs\.?)/g),...text.matchAll(/(?:instead of|versus|vs\.?)\s+(?:the\s+|a\s+)?([A-Z][A-Za-z0-9-]{2,}(?:\s+[A-Z0-9][A-Za-z0-9-]*){0,2})/g)].map(x=>x[1]);
    for(const id of match.matched_asins){const p=profile.products[id];for(const term of candidates){if(has(p.brand,term)||p.anchors.some(a=>has(a,term))||p.competitors.includes(term)||p.competitors.length>=30)continue;p.competitors.push(term);p.competitor_evidence=p.competitor_evidence||[];p.competitor_evidence.push({term,comment_id:row.comment_id,asin:id,source_quote:text.slice(0,240)});}}
  }
  return profile;
}
module.exports={buildProfile,relevantPost,qualify,semantics,seeds,evidencedQueries,learnCommunity,clean,has};
