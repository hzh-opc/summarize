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
│   └── compare.py              # 云端×本地对比与改进建议
├── references/
│   ├── config.md               # 配置项说明
│   └── quality-eval.md         # 质量评估方法
└── assets/
    └── summarize.config.yaml   # 默认配置模板
```

## 快速使用

```bash
python3 scripts/summarize.py 输入.txt --length 3 --keywords 8 --eval --format md
python3 scripts/summarize.py 输入.txt --brief --format json   # 取紧凑中间产物送云端
python3 scripts/compare.py --local 本地摘要.txt --cloud 云端摘要.txt --original 原文.txt --format md
```

供 Claude / Codex / OpenClaw 使用时，复制本目录即可；运行需 Python 3.8+。详见 `SKILL.md`。
