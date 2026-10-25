# Reddit VOC 评论采集器

## 一眼看懂

- 这是什么：按商品编号采集 Reddit 上相关公开评论。
- 什么时候用：想找 Reddit 上某款商品的公开评论时。
- 给它什么：商品编号，或一份商品编号清单文件。
- 它给你什么：一个 Excel，含评论、回复关系和采集过程记录。

## 项目简介

`reddit-voc-collector` 是由 Amazon ASIN 驱动的 Reddit 公开评论采集工具和 Agent Skill，当前版本 `2.1.0`。默认通过 OpenCLI 操作采集器创建的普通 Chrome 标签页，用商品信息生成查询，逐条判断评论相关性，保留回复关系与断点，最终生成经独立校验的 Excel。

仓库只覆盖采集编排、规则判断、导出与校验：OpenCLI CLI / Chrome 扩展、已登录的 Chrome 和 artifact-tool 运行时都是外部前置条件；Playwright / CDP、选定标签页和 RC1 扩展桥属于显式选择的兼容路径。Agent 运行约定见根目录 `SKILL.md`。

## 核心功能

- 🧭 **查询规划**：按商品信息生成 Reddit 查询
- 🌲 **评论树采集**：串行展开评论与回复关系
- 🎯 **相关性判定**：三类规则区分有效 VOC
- 🔁 **断点续采**：checkpoint 支持续采与重审
- 🧮 **分层计数**：严格模式与放宽模式分别计数
- 📊 **Excel 交付**：六表或八表并校验一致性
- 🔐 **交付校验**：退出码 0 才生成交付副本

## 技术栈

| 层级 | 技术 | 版本 |
| --- | --- | --- |
| 运行时 | Python（`.python-version` 固定） | 3.12.13 |
| 默认编排 | Node.js ≥20、OpenCLI | — |
| 数据与工作簿 | openpyxl | ≥3.1,<4 |
| 工作簿导出 | `@oai/artifact-tool`（外部运行时） | — |
| 兼容浏览器 | Playwright、Chrome 扩展 | ≥1.55.0 <2 |
| 测试 | unittest、Node test | — |
| CI | GitHub Actions | — |

版本取自 `.python-version`、`requirements.txt`、`pyproject.toml` 与 `package.json`；OpenCLI、artifact-tool 等外部运行时不在依赖文件中，因此记「—」。

## 快速开始

需要 Python ≥3.10 且 <3.14、Node.js ≥20；真实采集还需要安装好的 OpenCLI CLI / Chrome 扩展和人工登录的 Chrome，Excel 生成需要外部 artifact-tool 运行时。以下命令在仓库根目录执行，系统命令名为 `python3` 时可替换 `python`。

1. 克隆仓库并进入目录

   ```bash
   git clone https://github.com/fubo-ops/reddit-voc-collector.git
   cd reddit-voc-collector
   ```

2. 安装 Python 依赖并跑 Skill 格式检查

   ```bash
   python -m pip install -r requirements.txt
   python -B scripts/quick_validate.py .
   ```

3. 检查浏览器采集环境与商品预检

   ```bash
   node scripts/reddit_playwright_collector.cjs doctor
   node scripts/reddit_playwright_collector.cjs preflight --asin ASIN --out-dir outputs/run-001
   ```

4. 串行采集评论，写入独立运行目录

   ```bash
   node scripts/reddit_playwright_collector.cjs collect --asin ASIN --target-comments 500 --out-dir outputs/run-001 --delivery-dir outputs/delivery
   ```

5. 导出工作簿并做独立校验

   ```bash
   node scripts/reddit_playwright_collector.cjs export --out-dir outputs/run-001 --delivery-dir outputs/delivery
   node scripts/reddit_playwright_collector.cjs validate --out-dir outputs/run-001
   ```

6. 跑离线测试（不访问真实平台）

   ```bash
   python -B -X utf8 -m unittest discover -s tests -v
   npm test
   npm run check
   ```

把 `ASIN` 换成目标商品编号；多 ASIN 可用 `--asins ASIN1,ASIN2` 或 `--asin-file FILE`。续跑使用同一 `--out-dir`，不要换空目录冒充续采。

## 项目结构

只列两层，完整文件清单见文末《详细说明》。

```text
reddit-voc-collector/
├── .github/                    # GitHub 配置目录
│   └── workflows/              # CI：三平台离线测试
├── .gitignore                  # 忽略运行目录与生成产物
├── .python-version             # 固定 Python 3.12.13
├── LICENSE                     # MIT 许可证
├── README.md                   # 项目总览与快速开始
├── SKILL.md                    # Agent Skill 入口与运行约定
├── VERSION                     # 当前版本号
├── agents/                     # Skill 展示配置
├── docs/                       # 归档文档目录
│   └── archive/                # 历史验收与升级记录
├── extension/                  # 兼容路径：Chrome 扩展桥
├── local_bridge/               # 兼容路径：本地 Python 桥
├── package.json                # Node 依赖与测试脚本
├── package-lock.json           # Node 依赖锁定
├── pyproject.toml              # Python 打包与依赖声明
├── references/                 # 采集指南与原始记录契约
├── requirements.txt            # Python 依赖
├── scripts/                    # 采集、导出与校验脚本
├── tests/                      # 离线测试与合成页面
├── install.ps1                 # Windows 安装脚本
├── doctor.ps1                  # Windows 离线环境检查
└── uninstall.ps1               # Windows 卸载脚本
```

## 架构图

默认链路串行执行，遇到登录墙或访问限制即停止，不自动切兼容路径：

```text
【输入】
┌────────────────────────────────────┐
│ ASIN / ASIN 清单 / 可选商品记录     │
└─────────────────┬──────────────────┘
                  ▼
┌────────────────────────────────────┐
│ doctor + preflight 环境与页面预检   │
└─────────────────┬──────────────────┘
                  ▼
┌────────────────────────────────────┐
│ 商品规则 + 查询计划（Python）       │
└─────────────────┬──────────────────┘
                  ▼
┌────────────────────────────────────┐
│ 采集器自有的普通 Chrome 标签页      │
│ 帖子发现 → 递归展开评论与回复       │
└─────────────────┬──────────────────┘
                  ▼
┌────────────────────────────────────┐
│ 逐条相关性判定 + 树审计 + 全局去重  │
└─────────────────┬──────────────────┘
                  ▼
┌────────────────────────────────────┐
│ checkpoint / JSONL / 证据落盘       │
└─────────────────┬──────────────────┘
                  ▼
┌────────────────────────────────────┐
│ artifact-tool 构建分层工作簿        │
└─────────────────┬──────────────────┘
                  ▼
┌────────────────────────────────────┐
│ Python 独立校验（退出码 0 才继续）  │
└─────────────────┬──────────────────┘
                  ▼
┌────────────────────────────────────┐
│ 按 ASIN 命名交付 + SHA-256 核对     │
└────────────────────────────────────┘
```

兼容 CDP / 选定标签页 / RC1 扩展桥需要显式选择，不在默认链路内。

## 开发计划

### Phase 1: 采集底座

- ✅ OpenCLI 编排与 doctor / preflight
- ✅ 商品规则与查询计划
- ✅ 串行帖子发现与递归评论展开

### Phase 2: 质量与续采

- ✅ 三类相关性规则判定（direct / competitive / unmet）
- ✅ checkpoint 续采与 PARTIAL 证据重审
- ✅ 跨帖子、跨 ASIN 去重

### Phase 3: 导出与校验

- ✅ 分层 Excel（strict 6 表 / relevance 8 表）
- ✅ Python 独立校验与计数一致性检查
- ✅ 交付命名、SHA-256 核对与历史交付保护

### Phase 4: 工程化与验收

- ✅ 三平台 CI（Windows / macOS / Linux）
- ✅ 离线 unittest 与 `npm run check`
- ⬜ 当前版本最新在线验收记录
- ⬜ 独立发布排期与负责人

## 文档

- [Skill 入口](SKILL.md) / [展示配置](agents/openai.yaml)
- [采集指南](references/collection-guide.md) — 环境变量与操作方式
- [原始记录与质量契约](references/raw-record-schema.md) — 记录字段与计数口径
- [兼容扩展桥设计](references/extension-bridge-design.md)
- [历史验收记录](docs/archive/README.md)
- [CI 配置](.github/workflows/test.yml) — 三平台离线测试

## 许可证

代码采用 [MIT License](LICENSE)。评论内容与外部平台的授权范围不由本仓库代码许可证授予。

---

原 README 里的环境准备、Windows 安装、完整采集命令、工作簿表结构、计数口径、项目文件清单、历史验收与开发状态等细节，已全部迁移到 [docs/详细说明.md](docs/详细说明.md)。
