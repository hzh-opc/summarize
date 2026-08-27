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

> 本技能**只消费纯文本**：所有「非文本输入 → 文本」的环节都通过外部协同技能完成。因此外部技能缺失只影响「能否获取文本」，不影响「摘要」本身——拿到文本即可摘要，拿不到则明确降级而非崩溃（详见下方「协同技能检测、对接与容错」）。

| 形态 | 取文方式（动态对接，见「协同技能检测、对接与容错」） |
|---|---|
| 直接文本（粘贴/对话） | 直接使用 |
| `.txt` / `.md` 文件 | `Read` 读取或 `summarize.py <文件>` |
| `.docx` / `.pdf` | 检测 `document_text` 能力：命中则调用该技能落地文本；缺失则 `ask` 降级（请用户导出 .txt/.md） |
| 网页 URL | 检测 `web_fetch` 能力：命中则调用，否则回退内置 `WebFetch` 工具（仍需过脱敏协同） |
| 图片 / 扫描件 | 检测 `ocr` 能力：命中则调用 OCR 技能转文字；缺失则 `ask` 降级 |
| 音频 | 检测 `speech_transcription` 能力：命中则转文字；缺失则 `ask` 降级 |
| 视频 | 检测 `video_transcript` 能力：命中则转文字/字幕；缺失则 `ask` 降级 |

## 处理流程（务必遵循）

### 0. 读配置
读取配置（搜索顺序：`<工作区>/summarize.config.yaml` → 本技能 `assets/summarize.config.yaml`）。
配置项含义见 `references/config.md`（按需 Read）。

### 0.5 检测协同技能并完成取文（健壮性关键环节）
按下方「协同技能检测、对接与容错」章节：先用 `skill_bridge.py --exclude summarize` 检测本机已安装能力；再按输入形态分派——命中则调用对应协同技能把输入转为纯文本，缺失则按 `fallback`（`ask`/`tool`/`local`）降级。**拿到纯文本后再进入第 1 步**；若某输入形态降级为 `ask` 且用户无法提供文本，则跳过该输入、不中断整体流程。

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

## 与「协同技能」检测、对接与容错（健壮性核心）

> **设计原则**：本技能**不假定任何协同技能已安装**。开始处理前先动态检测本机/工作区已安装的技能能力，按检测结果决定取文路径与上云前脱敏；任一能力缺失时按 `fallback` 策略降级，**绝不因依赖缺失而报错中断**。检测基于**关键词泛匹配** SKILL.md 的 name/description/tags，**不限定具体技能名**——因此无论用户安装的是 `desensitization-sop`、自研脱敏技能，还是任意第三方 OCR / 语音 / 视频技能，都能被识别并对接（"非限定本机已安装技能"）。

### 1. 协同技能检测（用 skill_bridge.py）

调用零依赖检测脚本（扫描用户级 `~/.workbuddy/skills` 与项目级 `./.workbuddy/skills`，按 `assets/capabilities.json` 关键词泛匹配）：
```bash
PY=<受管 python3 绝对路径，或用系统 python3>
SKILL_DIR=<技能目录>
# 全量检测（txt 易读）
$PY $SKILL_DIR/scripts/skill_bridge.py --map $SKILL_DIR/assets/capabilities.json --exclude summarize --format txt
# 单能力查询（exit 0=可用 / 1=缺失，便于条件分支）
$PY $SKILL_DIR/scripts/skill_bridge.py --exclude summarize --cap ocr --quiet && echo 有OCR || echo 无OCR
```
- `--exclude summarize`：**必须**。排除调用方自身，避免本技能描述中的「输入形态」被误判为自身提供该能力。
- 命中结果给出 `skill`（目录名）、`path`、`score`、以及 `alternatives`（同能力下的其它候选技能）。
- 能力清单与候选关键词定义在 `assets/capabilities.json`（数据驱动、可扩展，见第 5 节）。

### 2. 协同矩阵（能力 → 用途 → 对接方式 → 缺失降级）

| 能力 | 用途 | 命中后对接方式 | 缺失降级 `fallback` |
|---|---|---|---|
| `desensitization` | 上云前脱敏闭环 | 用 **Skill 工具**加载该技能并执行脱敏/回填/复核 | `local`：仅本地处理；强制上云只送 `brief` 并提示风险 |
| `ocr` | 图片/扫描件转文字 | 用 **Skill 工具**加载该 OCR 技能产出文本 | `ask`：请用户贴文本或安装 OCR 技能 |
| `speech_transcription` | 音频转文字 | 用 **Skill 工具**加载该语音技能产出文本 | `ask`：请用户提供文字稿 |
| `video_transcript` | 视频转文字/字幕 | 用 **Skill 工具**加载该视频技能产出文本 | `ask`：请用户提供文字稿/字幕 |
| `document_text` | docx/pdf 落地文本 | 用 **Skill 工具**加载该文档技能（如 `tencent-local-office-edit`） | `ask`：请导出 .txt/.md |
| `web_fetch` | 网页抓文本 | 用 **Skill 工具**加载该技能；未命中则回退内置 `WebFetch` 工具 | `tool`：回退 `WebFetch`（仍过脱敏协同） |

> 对接外部技能的标准动作：用 **Skill 工具**加载其 `SKILL.md` → 遵循其流程产出文本 → 把文本作为本技能 `summarize.py` 的输入。**本技能脚本只消费纯文本**，因此外部技能缺失只阻断「取文」、不阻断「摘要」。

### 3. 取文分派（按输入形态）

1. 直接文本 / `.txt` / `.md` → 直接用 `summarize.py` 处理（无需任何外部技能）。
2. 图片/扫描件 → 检测 `ocr`：可用则调用 OCR 技能转文字；缺失 → `ask` 降级（不强行处理二进制）。
3. 音频 → 检测 `speech_transcription`：可用则转文字；缺失 → `ask` 降级。
4. 视频 → 检测 `video_transcript`：可用则转文字；缺失 → `ask` 降级。
5. `.docx` / `.pdf` → 检测 `document_text`：可用则落地文本；缺失 → `ask` 降级。
6. 网页 URL → 检测 `web_fetch`：可用则调用，否则回退 `WebFetch` 工具。抓取内容可能含敏感信息，须过第 4 节脱敏协同。

### 4. 脱敏协同（通用检测，零耦合）

> **零耦合保证**：本技能的脚本（`scripts/summarize.py`、`scripts/compare.py`、`scripts/skill_bridge.py`）**不导入、不调用**任何外部技能。脱敏协同完全在「智能体层」按条件执行——外部技能缺失时脚本天然不会出错。

在执行任何上云操作前，用 `skill_bridge.py` **泛匹配**检测脱敏能力（兼容任意脱敏技能名，而非硬编码 `desensitization-sop` 目录）：
```bash
$PY $SKILL_DIR/scripts/skill_bridge.py --exclude summarize --cap desensitization --quiet \
  && echo "脱敏可用: $($PY $SKILL_DIR/scripts/skill_bridge.py --exclude summarize --cap desensitization | python3 -c 'import sys,json;print(json.load(sys.stdin)["skill"])')" \
  || echo "脱敏缺失"
```
- **absent（未安装）**：跳过所有脱敏步骤，直接走本地处理（`mode=local` 默认安全，原始文本不出本机）。若用户要求 `cloud`/`hybrid`，仅上云 `summarize.py --brief` 产出的紧凑中间产物，并明确提示用户：未做脱敏、存在隐私风险，需用户自行确认。
- **available（已安装）**：用 **Skill 工具**加载该脱敏技能，按其上云前/后闭环执行「脱敏、处理、回填、复核」：
  1. **上云前**：凡要把任何内容送云端模型，先跑该技能的「输入检测闸门 → 脱敏 → 上云前自查 → 用户确认」。仅可上云的是脱敏副本或 `brief` 紧凑中间产物。
  2. **本地处理豁免**：若 `mode=local` 且声明「仅本地处理·无需外发」，走该技能的「本地处理豁免（三条护栏）」——原始数据留本机、不脱敏、绝不外发。
  3. **任务后**：按该技能模板自动追加脱敏审计（原始文件与映射表永远留本地且分离）。
  4. **回填/复核**：云端结果若需还原映射（去标识回填），在本地完成，云端不留敏感原文。

> 红线：脱敏副本可上云，原始文件与映射表留本地且分离；自动化识别非 100%，禁止「一键脱敏即上云」，必须人工复核。

### 5. 扩展：接入「用户其它已安装技能」

`assets/capabilities.json` 是**开放清单**，本机制天然兼容用户未来安装的任何协同技能：
- **新增能力**：在 JSON 的 `capabilities` 下追加任意键（如 `translation`、`knowledge_base`），给出 `purpose`、`keywords`（候选关键词）、`fallback` 与 `fallback_note`。`skill_bridge.py` 会自动识别匹配到的技能，无需改脚本。
- **触发新能力**：`skill_bridge.py --cap <新能力>` 检测 → 命中则按对应分支用 **Skill 工具**加载该技能并遵循其流程；未命中则按该能力的 `fallback` 降级。
- **关键词调优**：若某技能未被识别（描述措辞不同），只需在其 `keywords` 中补充该技能描述里的特征词即可，零代码改动。
- 这样既"非限定本机已安装技能"，也为未来任意协同技能预留统一入口，持续提升健壮性。

## 跨智能体 / 跨平台说明

- 本技能为纯文本驱动的本地脚本 + 指令，不依赖特定宿主。供 Claude / Codex / OpenClaw 等使用时，复制技能目录（含 `scripts/`、`references/`、`assets/`）即可，运行 `scripts/summarize.py` 需 Python 3.8+。
- 零第三方依赖，Windows/macOS/Linux 均直接 `python3 summarize.py` 运行。

## 可扩展方向（按需补充）

根据日常工作需求，参考市场同类技能，可补充：更长上下文的滑动窗口摘要、多文档联合摘要、按用户画像调节摘要语气、与笔记/知识库联动沉淀要点等。
