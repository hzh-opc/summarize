# summarize · 智能摘要技能

为长文本 / 文档 / 网页 / OCR 稿 / 音频转录稿 / 视频文案提取稿自动生成摘要、提取要点与关键词，支持自定义摘要长度。

- **本地优先（离线、零依赖、跨平台）**：`scripts/summarize.py` 纯 Python 标准库实现，Windows / macOS / Linux 直接 `python3 summarize.py` 运行。
- **云端取方法、本地处理信息**：`--brief` 模式仅把「关键词 + 候选句 + 结构骨架」紧凑中间产物交云端大模型，原始长文不出本机、省 TOKEN。
- **质量评估与改进闭环**：`--eval` 输出压缩比/关键词覆盖/综合评分；`scripts/compare.py` 对比云端与本地结果并记录改进建议。

## 目录

```
summarize/
├── SKILL.md                    # 技能主指令（供 WorkBuddy 等智能体加载）
├── scripts/
│   ├── summarize.py            # 本地抽取式摘要 + 关键词 + 质量评估
│   ├── compare.py              # 云端×本地对比与改进建议
│   └── skill_bridge.py         # 协同技能检测与对接（零依赖，关键词泛匹配）
├── references/
│   ├── config.md               # 配置项说明
│   └── quality-eval.md         # 质量评估方法
└── assets/
    ├── summarize.config.yaml   # 默认配置模板
    └── capabilities.json       # 协同能力清单（可扩展，不限定具体技能名）
```

## 快速使用

```bash
# 单文档 + 质量评估
python3 scripts/summarize.py 输入.txt --length 3 --keywords 8 --eval --format md

# 多文档联合摘要（跨文档统一关键词，输出标注 [文档N]）
python3 scripts/summarize.py 文档1.txt 文档2.txt --length 5 --format md

# 超长文本：超过 --max-input-chars 自动滑动窗口分块抽取后合并
python3 scripts/summarize.py 长文.txt --max-input-chars 200000 --ratio 0.2

# 取紧凑中间产物送云端（云端取方法、本地处理信息）；可指定语气
python3 scripts/summarize.py 输入.txt --brief --tone concise --format json

# 云端×本地对比与改进建议
python3 scripts/compare.py --local 本地摘要.txt --cloud 云端摘要.txt --original 原文.txt --format md
```

- **可选 jieba**：运行环境装了 `jieba` 则中文分词自动升级；未装则回退内置二元/三元组分词，功能不受影响、零依赖。
- **零耦合脱敏**：脚本不依赖 `desensitization-sop`；该技能缺失时由智能体层跳过脱敏步骤，脚本本身不会出错。

## 协同技能检测、对接与容错（健壮性核心）

本技能不假定任何外部技能已安装。`scripts/skill_bridge.py` 扫描用户级/项目级技能目录，按 `assets/capabilities.json` 的关键词泛匹配各技能 SKILL.md 描述，判定 `desensitization` / `ocr` / `speech_transcription` / `video_transcript` / `document_text` / `web_fetch` 等能力是否可用——**不限定具体技能名**，故用户安装的任意脱敏/OCR/转录技能都能被识别对接：

```bash
# 全量检测（排除调用方自身，避免描述中的输入形态被误判为自身能力）
python3 scripts/skill_bridge.py --map assets/capabilities.json --exclude summarize --format txt

# 单能力查询（exit 0=可用 / 1=缺失）
python3 scripts/skill_bridge.py --exclude summarize --cap ocr --quiet && echo 有OCR || echo 无OCR
```

- **对接**：命中后用 Skill 工具加载对应技能产出文本，作为 `summarize.py` 的输入（本技能脚本只消费纯文本）。
- **容错降级**：每个能力有 `fallback` 策略——`local`（脱敏→仅本地处理）、`ask`（OCR/语音/视频/文档缺失→请用户提供文本）、`tool`（网页缺失→回退内置 WebFetch）。**外部技能缺失只阻断「取文」、不阻断「摘要」。**
- **可扩展**：在 `capabilities.json` 追加任意能力键（如 `translation`）即自动生效，无需改脚本。

供 Claude / Codex / OpenClaw 使用时，复制本目录即可；运行需 Python 3.8+。详见 `SKILL.md`。
