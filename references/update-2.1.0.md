# 2.1.0 本地离线验收 — 2026-10-10

## 最新流程
OpenCLI → doctor → 当前ASIN真实商品信息 → 浏览器DOM preflight → ready → 串行递归评论树 → 每条评论独立相关性 → 全局去重/checkpoint → 持久化Excel构建器 → validate实际退出码0 → SHA256集中交付。

默认只控制collector-owned普通Chrome标签页，不调用兼容CDP/Profile/旧桥，不枚举用户标签页或读取认证存储。非ready、加载失败、身份变更、可见访问限制均停止，无刷新/自动重试。

## 质量与续跑
strict默认只计合格PASS。经用户明确允许的relevance仅放宽comment_count_not_reconciled，保留PARTIAL标签并单独计数。其他树、身份、正文、相关性、加载与访问问题均排除。
保留PASS；完成关键词不阻止后续pending轮次与明确的PARTIAL重审；全局两层合计不得超目标。未显式改目标/质量模式时续用checkpoint配置。历史复用上限计新增复用量，0禁用新增PARTIAL复用。多ASIN合并匹配关系后仍只计一次。
B0HHNB798Q事实：438 PASS + 362已校验PARTIAL = 800；362中312复用旧证据、50来自新搜索，不是800 Trusted或800新抓取。

## 离线实际结果
Python全量96/96，JavaScript全量58/58；含strict/relevance/多ASIN真实artifact-tool导出、validate退出码0和交付SHA256验证。19个JavaScript文件node --check、4个PowerShell脚本语法、6个核心CLI --help、内置及Skill Creator quick_validate通过。doctor -Offline = offline_ready，浏览器连接未在离线验收中确认ready。
测试初期旧实现忽略模拟浏览器注入并触发旧预检，已终止和关闭其临时页，没有采集评论；现有新流程测试在模块级禁止真实OpenCLI传输，使用显式模拟浏览器。
历史outputs和集中交付目录516个文件SHA256复核无变化。本轮不删除历史文件，不上传GitHub。

## 交付与限制
默认交付目录：D:\Project\2026\SKILL\reddit评论采集
文件名：ASIN_reddit评论_COUNT条_YYYYMMDDTHHMMSSZ.xlsx。排他创建，不覆盖历史Excel，集中副本SHA256与内部文件一致；manifest记录delivery_excel_path及deliveries。checkpoint/JSONL/证据保留原运行目录。仅实际validate退出0允许报告验证通过与集中交付；未达目标/失败运行保留内部Excel和失败诊断。
relevance保留Comments、Trusted_Comments、Validated_Partial_Comments、Partial_Candidates、Conversation_Map、Query_Performance、Community_Map、Run_Summary。逐行投影核对字段、ASIN关联、父子关系/深度；候选不计入目标。表格筛选、冻结、正文换行、ID文本和公式/非法字符防护已测试。
当前相关性为商品信息驱动的保守词法门禁，并非LLM语义判断；短回复和仅靠上下文的回复可能排除。Amazon/SellerSprite DOM变更可能需要新增选择器；未知卖家精灵界面按缺失来源记录。需要外部OpenCLI CLI/扩展与artifact-tool运行时，登录由人工完成。此次只离线验证实现，没有进行新的真实端到端采集验收。

## 修改/新增文件（仓库相对路径）
```text
.github\workflows\test.yml
README.md
SKILL.md
VERSION
agents\openai.yaml
doctor.ps1
install.ps1
package-lock.json
package.json
pyproject.toml
references\collection-guide.md
references\raw-record-schema.md
scripts\normalize_raw_jsonl.py
scripts\reddit_conversation_discovery.py
scripts\reddit_playwright_collector.cjs
scripts\reddit_visible_capture.js
tests\test_standalone_skill.py
scripts\build_opencli_workbook.mjs
scripts\excel_delivery.cjs
scripts\finalize_opencli_run.cjs
scripts\reddit_opencli_collector.cjs
scripts\reddit_product_rules.cjs
scripts\validate_opencli_run.py
tests\test_excel_delivery.cjs
tests\test_opencli_export.py
tests\test_opencli_transport.cjs
tests\test_opencli_validation.py
tests\test_opencli_workflow.cjs
tests\test_tree_resume.cjs
references\update-2.1.0.md
```
