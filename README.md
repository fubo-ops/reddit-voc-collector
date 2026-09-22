# Reddit VOC Collector

一套可独立运行、也可作为 Codex Skill 使用的公开 Reddit VOC 评论采集器。输入 Amazon ASIN 后生成语义查询计划，发现相关 Reddit 帖子、展开公开评论树、审计完整性，并输出 comments-only JSONL、CSV 和 Excel。

## 支持环境

- Windows 10/11
- Python 3.10–3.13
- Node.js 20+
- Google Chrome

GitHub Actions 在 Python 最低、最高支持版本上运行 Python、Node、PowerShell及扩展清单检查。

## 安装

```powershell
git clone https://github.com/fubo-ops/reddit-voc-collector.git
cd reddit-voc-collector
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm ci
```

安装为 Codex Skill：

```powershell
powershell -ExecutionPolicy Bypass -File .\install.ps1
powershell -ExecutionPolicy Bypass -File .\doctor.ps1
```

安装器会显示扩展目录。在 `chrome://extensions/` 启用开发者模式并“加载已解压的扩展程序”。固定扩展 ID：`edpfinibjpbkdnognnhealnfepkeopem`。

## 运行

在 Codex 中调用 `$reddit-voc-collector`。`collector-owned-tab` 模式由 Codex 创建并只控制一个临时 Reddit 标签页；扩展识别短期 RUN_ID 后自动采集，无需逐帖点击、配对码或 CDP。

独立 CLI 使用专用 Chrome CDP 配置：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\start_reddit_cdp.ps1
node scripts\reddit_playwright_collector.cjs preflight --session-mode cdp --cdp-url http://127.0.0.1:9222
node scripts\reddit_playwright_collector.cjs collect --asin B003ULL1NQ --target-comments 100 --session-mode cdp --cdp-url http://127.0.0.1:9222
```

完整参数：

```powershell
node scripts\reddit_playwright_collector.cjs --help
```

默认输出到当前工作目录的 `outputs/reddit-comments`。输出包含评论 JSONL/CSV/Excel、query plan、manifest、checkpoint 和逐帖 evidence；不生成独立帖子记录。

## 数据与安全边界

- 只处理公开可见 Reddit 内容。
- 不读取、导出或提交 Cookie、密码、Token、浏览器 Profile 或历史记录。
- 不自动登录、不处理验证码、不绕过登录墙、私有社区、年龄限制或平台风控。
- CAPTCHA、403、429、network security block 或访问拒绝时停止。
- 扩展权限为空，仅允许 `https://www.reddit.com/*` 与本机 bridge。
- `outputs`、浏览器资料、断点结果、Excel、日志、缓存及环境文件均由 `.gitignore` 排除。

详细流程见 `SKILL.md` 与 `references/collection-guide.md`；字段见 `references/raw-record-schema.md`。

## 测试

```powershell
python -m unittest discover -s tests -v
npm test
npm run check
python scripts/quick_validate.py .
```

## 许可证

MIT，见 `LICENSE`。
