"use strict";
const test=require("node:test"), assert=require("node:assert/strict");
const collector=require("../scripts/reddit_playwright_collector.cjs");

test("iterative CLI defaults",()=>{
  const value=collector.args(["collect","--asin","B003ULL1NQ"]);
  assert.equal(value.discoveryMode,"iterative"); assert.equal(value.maxDiscoveryRounds,"5");
});

test("checkpoint migration preserves trusted rows and versions",()=>{
  const source={comments:[{comment_id:"c1"}],selected_visible_threads:{p1:{audit_status:"PASS"},p2:{audit_status:"PARTIAL"}}};
  const value=collector.migrateDiscoveryCheckpoint(source);
  assert.deepEqual(value.trusted_comments,source.comments); assert.deepEqual(value.partial_reaudit_frontier,["p2"]);
  assert.equal(value.conversation_map_version,"1.0");
});

test("two low yield rounds stop discovery",()=>{
  const value=collector.discoveryStop([{new_trusted:4,duplicate_rate:.2},{new_trusted:3,duplicate_rate:.3}],7,{targetComments:100,minNewCommentsPerRound:10});
  assert.equal(value.stop_reason,"semantic_saturation_low_yield");
});

test("target comments stop discovery",()=>{
  assert.equal(collector.discoveryStop([],100,{targetComments:100}).stop_reason,"target_comments_reached");
});
