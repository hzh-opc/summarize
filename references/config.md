# summarize 技能 · 配置项说明（references/config.md）

所有可选项均可在配置文件 `summarize.config.yaml` 中设置（或由智能体在对话中协助设置）。
配置文件搜索顺序：`<当前工作区>/summarize.config.yaml` → `~/.workbuddy/skills/summarize/assets/summarize.config.yaml`（默认模板）。

## 顶层字段

| 字段 | 取值 | 默认 | 说明 |
|---|---|---|---|
| `mode` | `local` \| `cloud` \| `hybrid` | `local` | 处理模式。local=纯本地离线；cloud=仅把本地提炼的「紧凑中间产物(brief)」交给云端模型产出抽象摘要；hybrid=本地抽取+云端润色 |
| `language` | `auto` \| `zh` \| `en` | `auto` | 文本语种；auto 按 CJK/拉丁字符占比自动判定 |
| `summary_length` | 对象 | 见下 | 摘要长度控制（三选一） |
| `keywords_count` | 整数 | `8` | 提取关键词数量 |
| `quality_eval` | 布尔 | `true` | 是否输出质量评估 |
| `keep_local_copy` | 布尔 | `true` | 是否保留本地抽取副本（用于与云端结果对比） |
| `compare_cloud` | 布尔 | `false` | 云端处理后是否自动触发 compare.py 记录差异与改进建议 |
| `desensitization` | `auto` \| `off` | `auto` | 脱敏协同：auto=若已安装 `desensitization-sop` 则按其上云前/后闭环执行；off=不协同（仅本地、不外发时可选） |
| `feedback_email` | 字符串 | `hzh.opc@foxmail.com` | 改进建议反馈收件人 |
| `feedback_dir` | 字符串 | `./.summarize_feedback` | 改进建议/对比报告的本地落盘目录 |
| `max_input_chars` | 整数 | `200000` | 超长输入截断阈值（避免极端耗时），截断前保留首尾 |

## summary_length 子字段

```yaml
summary_length:
  strategy: ratio      # count(句数) | ratio(比例) | chars(字数)
  count: 5             # strategy=count 时生效
  ratio: 0.3           # strategy=ratio 时生效（0~1）
  chars: 600           # strategy=chars 时生效
```

## 各模式说明

- **local**：脚本 `scripts/summarize.py` 纯本地抽取式摘要，零依赖、离线、跨平台。原始文本不出本机。
- **cloud**：智能体先本地运行 `summarize.py --brief` 得到「关键词+候选句+结构骨架」紧凑中间产物，仅将该中间产物提交云端大模型，由其产出连贯的抽象式摘要。达到「云端取方法、本地处理信息」——省 TOKEN、护隐私。原始长文不上云。
- **hybrid**：在 local 基础上，把 brief 交给云端做一次润色/抽象化，再保留本地副本用于对比。

## 与信息脱敏技能协同（desensitization=auto 时）

若环境已安装 `desensitization-sop`：
1. **上云前**：凡要把任何内容送云端模型，先按 `desensitization-sop` 执行「输入检测闸门 → 脱敏 → 上云前自查清单 → 用户确认」；仅可上云的是脱敏副本/紧凑中间产物。
2. **本地处理豁免**：若 `mode=local` 且声明「仅本地处理·无需外发」，可走 `desensitization-sop` 的「本地处理豁免（三条护栏）」，原始数据留本机、不脱敏、不外发。
3. **任务后**：自动生成脱敏审计（按 `desensitization-sop` 模板追加到 `desensitize_audit.md`）。
4. **回填/复核**：云端结果若需还原映射（去标识回填），经 `desensitize.py restore` 在本地完成，云端不留敏感原文。

> 红线：脱敏副本可上云，原始文件与映射表永远留本地且分离；自动化识别非 100%，禁止「一键脱敏即上云」，必须人工复核。
