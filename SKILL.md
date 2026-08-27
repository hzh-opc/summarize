---
name: summarize
description: "为长文本、文档、网页、OCR 识别稿、音频转录稿、视频文案提取稿等自动生成摘要、提取要点与关键词，支持自定义摘要长度。优先本地离线处理（零依赖、跨平台），并支持「云端取方法、本地处理信息」以省 TOKEN、护隐私；可与 desensitization-sop 协同完成脱敏/处理/回填/复核闭环。当用户要求「总结/摘要/概括/提炼要点/提取关键词/归纳」任意形态的长内容时，应使用本技能。"
version: "1.0.0"
agent_created: true
---

# 智能摘要技能（summarize）

> 版本 v1.0.0 · 署名 hzh.opc（由 WorkBuddy 协助实现） · 兼容智能体：WorkBuddy / Claude / Codex / OpenClaw 等 · 跨平台：Windows / macOS / Linux。

## 定位与目标

自动为长内容生成摘要、提取要点与关键词，让用户在更少时间内理解信息、减少冗余干扰。两条核心诉求：

1. **把正确的（紧凑）中间结果交给智能体/云端处理**，在取得正确结果的前提下节约 TOKEN。
2. **把摘要交给用户阅读**，减少冗余信息干扰。

设计铁律：**完整的本地处理能力（离线、零依赖）优先**；云端仅用于「取方法/做抽象」，原始长文默认不出本机。

## 何时使用

- 用户要求「总结 / 摘要 / 概括 / 提炼要点 / 提取关键词 / 归纳」长文本、文档、网页、OCR 稿、音视频转录/文案提取稿。
- 用户希望缩短阅读时间、去除冗余、抓住核心结论。
- 需要在离线环境或对隐私敏感的场景下做摘要。

## 支持的信息形态与取文方式

| 形态 | 取文方式 |
|---|---|
| 直接文本（粘贴/对话） | 直接使用 |
| `.txt` / `.md` 文件 | `Read` 读取或 `summarize.py <文件>` |
| `.docx` / `.pdf` | 优先用 `tencent-local-office-edit` 或 PDF 技能落地为文本后再处理；无对应技能时提示用户导出文本 |
| 网页 URL | `WebFetch` 抓为文本（注意：抓取内容可能含敏感信息，见脱敏协同） |
| OCR 识别稿 / 音频转录稿 / 视频文案提取稿 | 作为纯文本输入处理 |

## 处理流程（务必遵循）

### 0. 读配置
读取配置（搜索顺序：`<工作区>/summarize.config.yaml` → 本技能 `assets/summarize.config.yaml`）。
配置项含义见 `references/config.md`（按需 Read）。

### 1. 本地优先：抽取式摘要 + 关键词（离线、零依赖）
运行本技能脚本（纯标准库，Windows/macOS/Linux 通用；**未安装 jieba 时自动回退内置分词，不报错**）：
```bash
PY=<受管 python3 绝对路径，或用系统 python3>
$PY <技能目录>/scripts/summarize.py <输入1> [<输入2> ...] \
    [--length N | --ratio R | --chars C] [--keywords K] \
    [--lang auto|zh|en] [--tone neutral|concise|professional|casual] \
    [--max-input-chars N] [--format json|md|txt] [--eval] [--brief] [--out PATH]
```
- `<输入>`：一个或多个文本文件路径；或 `-` 表示读 stdin（多文档时每个位置独立）。多文档将跨文档统一提取关键词与候选句，产出联合摘要并标注 `[文档N]` 来源。
- 长度三选一：`--length`(句数) / `--ratio`(比例) / `--chars`(字数)。
- `--tone`：调节喂给云端模型的摘要语气（neutral/concise/professional/casual），影响 `brief.instruction`。
- `--max-input-chars N`：超长文本阈值（默认 200000）。输入超过该长度时**自动滑动窗口分块抽取后合并**，全程离线。
- `--eval`：输出质量评估（压缩比、关键词覆盖、综合评分 0~100，方法见 `references/quality-eval.md`）。
- `--brief`：**关键**。输出「关键词 + 候选句(含分值) + 结构骨架」的紧凑中间产物，仅此中间产物送云端——实现「云端取方法、本地处理信息」。

### 2. 模式分支（由 `mode` 决定）
- **local**（默认）：第 1 步结果即最终摘要，直接呈现用户。原始文本全程不出本机。
- **cloud / hybrid**：用第 1 步的 `--brief` 中间产物提交云端大模型，要求其产出连贯的**抽象式**摘要（指出核心结论与要点），并明确「不要复述原文、不要引入候选句之外的未核实信息」。hybrid 额外保留本地副本用于对比。
  - 此步**仅上云 brief（紧凑中间产物），原始长文不上云**——省 TOKEN 且护隐私。

### 3. 呈现与质量评估
- 向用户输出：摘要正文 + 关键词 +（可选）质量评估。
- 质量评估指标与评分见 `references/quality-eval.md`。

### 4. 云端结果对比与改进闭环（可选，建议开启）
若 `compare_cloud: true` 或曾走 cloud/hybrid，运行：
```bash
$PY <技能目录>/scripts/compare.py --local <本地摘要> --cloud <云端摘要> \
    [--original <原文>] [--format md] [--feedback <feedback_dir>/fb_YYYYMMDD.json]
```
- 产出关键词 Jaccard、本地独有/云端独有项、可执行改进建议。
- 改进建议落盘 `feedback_dir`，周期可打包反馈开发者（`feedback_email`，默认 `hzh.opc@foxmail.com`）。
- 依据建议迭代 `scripts/summarize.py` 的打分权重/停用词/候选词规则，使本地能力逐步逼近云端。

## 与「信息脱敏」技能协同（desensitization=auto 时必做）

> **零耦合保证**：本技能的脚本（`scripts/summarize.py`、`scripts/compare.py`）**不导入、不调用** `desensitization-sop` 或任何外部技能。脱敏协同完全在「智能体层」按条件执行——技能脚本本身在脱敏技能缺失时**天然不会出错**。

### 0.5 脱敏技能可用性检测（避免依赖缺失致错）
在执行任何上云操作前，先检测 `desensitization-sop` 是否安装：
```bash
test -d "$HOME/.workbuddy/skills/desensitization-sop" && echo installed || echo absent
```
- **absent（未安装）**：跳过所有脱敏步骤，直接走本地处理（`mode=local` 默认安全，原始文本不出本机）。若用户要求 `cloud`/`hybrid`，仅上云 `summarize.py --brief` 产出的紧凑中间产物，并明确提示用户：未做脱敏、存在隐私风险，需用户自行确认。
- **installed（已安装）**：按下方闭环执行。

若环境已安装 `desensitization-sop`，按其上云前/后闭环执行，确保「脱敏、处理、回填、复核」不出错：

1. **上云前**：凡要把任何内容送云端模型，先跑 `desensitization-sop` 的「输入检测闸门 → 脱敏 → 上云前自查清单(12 项) → 用户确认」。仅可上云的是脱敏副本或 brief 紧凑中间产物。
2. **本地处理豁免**：若 `mode=local` 且声明「仅本地处理·无需外发」，可走 `desensitization-sop` 的「本地处理豁免（三条护栏）」——原始数据留本机、不脱敏、绝不外发。
3. **任务后**：按 `desensitization-sop` 模板自动追加脱敏审计（原始文件与映射表永远留本地且分离）。
4. **回填/复核**：云端结果若需还原映射（去标识回填），在本地用 `desensitize.py restore` 完成，云端不留敏感原文。

> 红线：脱敏副本可上云，原始文件与映射表留本地且分离；自动化识别非 100%，禁止「一键脱敏即上云」，必须人工复核。

## 跨智能体 / 跨平台说明

- 本技能为纯文本驱动的本地脚本 + 指令，不依赖特定宿主。供 Claude / Codex / OpenClaw 等使用时，复制技能目录（含 `scripts/`、`references/`、`assets/`）即可，运行 `scripts/summarize.py` 需 Python 3.8+。
- 零第三方依赖，Windows/macOS/Linux 均直接 `python3 summarize.py` 运行。

## 可扩展方向（按需补充）

根据日常工作需求，参考市场同类技能，可补充：更长上下文的滑动窗口摘要、多文档联合摘要、按用户画像调节摘要语气、与笔记/知识库联动沉淀要点等。
