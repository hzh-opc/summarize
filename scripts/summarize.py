#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
summarize.py — 本地抽取式摘要与关键词提取引擎（纯标准库，离线，跨平台）

设计原则（对应技能定位）：
  - 完整的本地处理能力（离线）：不依赖任何第三方包，Windows / macOS / Linux 均可运行。
  - 云端取方法、本地处理信息：通过 `--brief` 模式仅把「关键词 + 候选句 + 结构」
    这一紧凑中间产物交给云端大模型，原始长文不出本机、省 TOKEN。
  - 可定制摘要长度：--length（句数）/ --ratio（比例）/ --chars（字数）。
  - 质量评估：压缩比、关键词覆盖、句数缩减、可读性启发式，输出 0~100 评分。

用法：
  python3 summarize.py INPUT [--length N | --ratio R | --chars C]
                           [--keywords K] [--lang auto|zh|en]
                           [--format json|md|txt] [--eval] [--brief] [--out PATH]

  INPUT 可为：文本文件路径；或 `-` 表示从 stdin 读取。
  --brief   输出「喂给云端模型的紧凑中间产物」（关键词 + 候选句 + 结构骨架）。
  --eval    在输出中附带质量评估。
"""

import sys
import os
import re
import json
import argparse
import math

# ---------------------------------------------------------------------------
# 停用词（内置，覆盖中英常用功能词；可按需扩展）
# ---------------------------------------------------------------------------
ZH_STOP = set("""
的 了 和 是 在 我 有 也 就 不 人 都 一 一个 上 也 你 他 她 它 这 那 这个 那个 这些 那些
我们 你们 他们 自己 之 与 及 或 而 但 却 因为 所以 但是 由于 对于 关于 通过 以及 能够
进行 方面 问题 情况 目前 已经 可能 应该 需要 认为 表示 一种 一些 这样 那样 如果 虽然
为了 从而 并且 或者 然后 此外 例如 比如 按照 根据 由于 加以 予以 使得 成为 作为 位于
可以 不可 没有 不是 只是 这里 那里 怎么 什么 为什么 如何 多少 一种 一项 一名 一位
其 其其 其中 其他 其余 本身 各自 同样 相反 如此 这么 那么 多少 几 许多 一切 任何
""".split())

EN_STOP = set("""
the a an and or but if then else when while for to of in on at by with from as is are was were
be been being it its this that these those we you they he she i my your our their his her them
can could should would may might must do does did have has had will shall not no yes so because
however therefore thus also more most other another such than into about over under again
further what which who whom whose how why where there here all any each every both either neither
one two three first second last new old get got use used using using see seen make made like
just only very can't don't won't isn't aren't doesn't didn't won't
""".split())

# 中文字符范围
CJK = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]")
CJK_RUN = re.compile(r"[\u4e00-\u9fff\u3400-\u4dbf]+")
# 句子切分符
SENT_SPLIT = re.compile(r"(?<=[。！？!?；;…])|(?<=[\n\r])")
# 拉丁词
LATIN_WORD = re.compile(r"[A-Za-z0-9][A-Za-z0-9'+\-./]*")


def is_cjk(ch):
    return bool(CJK.match(ch))


# ---------------------------------------------------------------------------
# 文本预处理
# ---------------------------------------------------------------------------
def read_text(path):
    if path == "-":
        if hasattr(sys.stdin, "reconfigure"):
            try:
                sys.stdin.reconfigure(encoding="utf-8")
            except Exception:
                pass
        return sys.stdin.read()
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        return f.read()


def split_sentences(text):
    """按中英文标点切分句子，保留非空、去首尾空白。"""
    raw = SENT_SPLIT.split(text)
    out = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        # 去掉行内多余空白
        s = re.sub(r"\s+", " ", s)
        out.append(s)
    return out


def detect_lang(text, sentences):
    cjk = sum(len(CJK_RUN.findall(s)) for s in sentences)
    latin = sum(len(LATIN_WORD.findall(s)) for s in sentences)
    if cjk > latin:
        return "zh"
    if latin > cjk and latin > 0:
        return "en"
    return "zh" if cjk >= latin else "en"


# ---------------------------------------------------------------------------
# 关键词提取
# ---------------------------------------------------------------------------
def cjk_bigrams(text):
    """对 CJK 连续段生成二元组作为候选词，统计词频与文档频。"""
    tf = {}
    df = {}
    for run in CJK_RUN.findall(text):
        if len(run) < 2:
            continue
        grams = set()
        for i in range(len(run) - 1):
            g = run[i:i + 2]
            tf[g] = tf.get(g, 0) + 1
            grams.add(g)
        for g in grams:
            df[g] = df.get(g, 0) + 1
    return tf, df


def cjk_trigrams(text):
    """三元组候选词（更可能是真实词，跨词边界噪声更低）。"""
    tf = {}
    df = {}
    for run in CJK_RUN.findall(text):
        if len(run) < 3:
            continue
        grams = set()
        for i in range(len(run) - 2):
            g = run[i:i + 3]
            tf[g] = tf.get(g, 0) + 1
            grams.add(g)
        for g in grams:
            df[g] = df.get(g, 0) + 1
    return tf, df


def extract_keywords(text, sentences, lang, top_k=8):
    """返回 [(keyword, weight), ...] 已排序。

    中文采用「二元组 + 三元组」候选，并强制关键词至少在 2 个句中复现
    （df>=2，短文本放宽到 1），以滤除跨词边界的一次性噪声（如「工智」「键词」）。
    """
    kw = {}

    if lang == "zh":
        bi_tf, bi_df = cjk_bigrams(text)
        tri_tf, tri_df = cjk_trigrams(text)
        n_sent = max(1, len(sentences))
        min_df = 2 if n_sent >= 3 else 1
        for g, freq in bi_tf.items():
            if g in ZH_STOP or bi_df[g] < min_df:
                continue
            # 评分：词频 * log(1+文档频)，偏向跨句出现的词
            kw[g] = kw.get(g, 0) + freq * (1.0 + math.log(1 + bi_df[g]))
        for g, freq in tri_tf.items():
            if g in ZH_STOP or tri_df[g] < min_df:
                continue
            # 三元组更可能是真实词，加权
            kw[g] = kw.get(g, 0) + freq * (1.0 + math.log(1 + tri_df[g])) * 1.3
    else:
        # 拉丁：分词 + 词频
        tokens = [w.lower() for w in LATIN_WORD.findall(text)]
        for w in tokens:
            if w in EN_STOP or len(w) <= 1:
                continue
            kw[w] = kw.get(w, 0) + 1.0
        # 二元组短语（提升质量，如 "machine learning"）
        for i in range(len(tokens) - 1):
            a, b = tokens[i].lower(), tokens[i + 1].lower()
            if a in EN_STOP or b in EN_STOP:
                continue
            if len(a) > 2 and len(b) > 2:
                kw["%s %s" % (a, b)] = kw.get("%s %s" % (a, b), 0) + 0.8

    ranked = sorted(kw.items(), key=lambda x: x[1], reverse=True)
    return ranked[:top_k]


# ---------------------------------------------------------------------------
# 句子打分（抽取式）
# ---------------------------------------------------------------------------
def score_sentences(sentences, keywords, lang):
    kw_map = {k.lower(): w for k, w in keywords}
    total_kw_weight = sum(kw_map.values()) or 1.0
    n = len(sentences)
    scored = []
    for i, s in enumerate(sentences):
        low = s.lower()
        # 1) 关键词覆盖
        kcov = 0.0
        for k, w in kw_map.items():
            if k in low:
                kcov += w
        kcov_norm = kcov / total_kw_weight

        # 2) 位置权重（首尾句略加权，模拟 lead/lag bias）
        pos = 0.0
        if i == 0:
            pos = 1.0
        elif i == n - 1:
            pos = 0.7
        elif i <= max(1, n // 5):
            pos = 0.6
        else:
            pos = 0.3

        # 3) 长度偏好（中等长度最佳）
        L = len(s)
        if lang == "zh":
            if 15 <= L <= 80:
                len_score = 1.0
            elif L < 15:
                len_score = 0.4
            else:
                len_score = max(0.4, 1.0 - (L - 80) / 200.0)
        else:
            words = len(s.split())
            if 8 <= words <= 35:
                len_score = 1.0
            elif words < 8:
                len_score = 0.4
            else:
                len_score = max(0.4, 1.0 - (words - 35) / 80.0)

        # 4) 句首信号（含「总之/因此/结论/本文/研究」等提示词）
        signal = 0.0
        signals = ["总之", "因此", "结论", "综上", "本文", "研究", "发现", "建议",
                   "in conclusion", "therefore", "however", "we propose", "our findings",
                   "this paper", "the result", "importantly"]
        if any(sig in low for sig in signals):
            signal = 0.4

        score = 0.55 * kcov_norm + 0.22 * pos + 0.15 * len_score + 0.08 * signal
        scored.append((i, s, score))
    return scored


# ---------------------------------------------------------------------------
# 摘要长度解析
# ---------------------------------------------------------------------------
def select_sentences(scored, n_total, length=None, ratio=None, chars=None):
    if chars:
        chosen = []
        total = 0
        for i, s, sc in sorted(scored, key=lambda x: x[2], reverse=True):
            if total + len(s) > chars:
                if not chosen:
                    chosen.append((i, s, sc))
                break
            chosen.append((i, s, sc))
            total += len(s)
        return sorted(chosen, key=lambda x: x[0])
    if ratio is not None:
        k = max(1, int(round(n_total * ratio)))
    elif length is not None:
        k = length
    else:
        # 默认：约 30% 或最多 5 句
        k = max(1, min(5, int(round(n_total * 0.3))))
    k = min(k, n_total)
    top = sorted(scored, key=lambda x: x[2], reverse=True)[:k]
    return sorted(top, key=lambda x: x[0])


# ---------------------------------------------------------------------------
# 质量评估
# ---------------------------------------------------------------------------
def quality_eval(original, summary, keywords, chosen_idx, n_total):
    orig_chars = len(original)
    sum_chars = len(summary)
    compression = 1.0 - (sum_chars / orig_chars) if orig_chars else 0.0
    sent_red = 1.0 - (len(chosen_idx) / n_total) if n_total else 0.0

    # 关键词覆盖：摘要中出现的关键词占比
    low_sum = summary.lower()
    covered = sum(1 for k, _ in keywords if k.lower() in low_sum)
    kw_cov = covered / len(keywords) if keywords else 0.0

    # 可读性启发式：平均句长（中文字数）落在 25~70 视为佳
    sents = [s for _, s, _ in chosen_idx]
    avg_len = (sum(len(s) for s in sents) / len(sents)) if sents else 0
    if 25 <= avg_len <= 70:
        read = 1.0
    elif avg_len < 25:
        read = 0.6
    else:
        read = max(0.5, 1.0 - (avg_len - 70) / 150.0)

    score = int(round(100 * (0.35 * compression + 0.30 * kw_cov +
                             0.20 * sent_red + 0.15 * read)))
    return {
        "compression_ratio": round(compression, 3),
        "sentence_reduction": round(sent_red, 3),
        "keyword_coverage": round(kw_cov, 3),
        "keywords_covered": covered,
        "keywords_total": len(keywords),
        "avg_sentence_len": round(avg_len, 1),
        "score": max(0, min(100, score)),
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def summarize(text, length=None, ratio=None, chars=None, keywords_k=8,
              lang="auto", do_eval=True, brief=False):
    sentences = split_sentences(text)
    if not sentences:
        return {"summary": "", "keywords": [], "eval": None, "brief": None,
                "lang": lang, "sentence_count": 0}
    if lang == "auto":
        lang = detect_lang(text, sentences)
    keywords = extract_keywords(text, sentences, lang, keywords_k)
    scored = score_sentences(sentences, keywords, lang)
    chosen = select_sentences(scored, len(sentences), length, ratio, chars)
    chosen_idx = [i for i, s, _ in chosen]
    summary = "".join(s + ("。" if lang == "zh" and not s.endswith(("。", "！", "？", "!", "?", "；", ";")) else "") for i, s, _ in chosen)
    # 英文用空格连接
    if lang == "en":
        summary = " ".join(s for _, s in chosen)

    result = {
        "lang": lang,
        "sentence_count": len(sentences),
        "summary": summary,
        "keywords": [k for k, _ in keywords],
        "keyword_weights": {k: round(w, 2) for k, w in keywords},
        "chosen_sentences": [{"index": i, "text": s} for i, s, _ in chosen],
    }

    if do_eval:
        result["eval"] = quality_eval(text, summary, keywords, chosen, len(sentences))

    if brief:
        # 喂给云端模型的紧凑中间产物：关键词 + 候选句（含分值）+ 结构骨架
        result["brief"] = {
            "keywords": [k for k, _ in keywords],
            "candidate_sentences": [
                {"index": i, "score": round(sc, 3), "text": s}
                for i, s, sc in sorted(scored, key=lambda x: x[2], reverse=True)[:min(10, len(scored))]
            ],
            "total_sentences": len(sentences),
            "char_count": len(text),
            "instruction": (
                "基于上方关键词与候选句（已脱敏/仅本地信息），"
                "生成一段连贯的抽象式摘要，指出核心结论与要点；"
                "不要复述原始长文，不要引入候选句之外的未核实信息。"
            ),
        }
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(description="本地抽取式摘要与关键词提取（离线/零依赖）")
    ap.add_argument("input", help="文本文件或 - (stdin)")
    ap.add_argument("--length", type=int, default=None, help="摘要句数")
    ap.add_argument("--ratio", type=float, default=None, help="摘要占原文比例 0~1")
    ap.add_argument("--chars", type=int, default=None, help="摘要字数上限")
    ap.add_argument("--keywords", type=int, default=8, help="关键词数量")
    ap.add_argument("--lang", default="auto", choices=["auto", "zh", "en"])
    ap.add_argument("--format", default="json", choices=["json", "md", "txt"])
    ap.add_argument("--eval", action="store_true", help="附带质量评估")
    ap.add_argument("--brief", action="store_true", help="输出喂给云端模型的紧凑中间产物")
    ap.add_argument("--out", default=None, help="输出文件路径")
    args = ap.parse_args()

    text = read_text(args.input)
    if not text.strip():
        sys.stderr.write("错误：输入为空。\n")
        sys.exit(2)

    res = summarize(text, length=args.length, ratio=args.ratio, chars=args.chars,
                    keywords_k=args.keywords, lang=args.lang,
                    do_eval=args.eval or True, brief=args.brief)

    if args.format == "json":
        out = json.dumps(res, ensure_ascii=False, indent=2)
    elif args.format == "md":
        lines = []
        lines.append("## 摘要")
        lines.append(res["summary"])
        lines.append("")
        lines.append("## 关键词")
        lines.append("、".join(res["keywords"]))
        if res.get("eval"):
            e = res["eval"]
            lines.append("")
            lines.append("## 质量评估")
            lines.append(f"- 综合评分：{e['score']}/100")
            lines.append(f"- 压缩比：{e['compression_ratio']}")
            lines.append(f"- 句数缩减：{e['sentence_reduction']}")
            lines.append(f"- 关键词覆盖：{e['keyword_coverage']}（{e['keywords_covered']}/{e['keywords_total']}）")
        out = "\n".join(lines)
    else:  # txt
        out = res["summary"] + "\n\n关键词：" + "、".join(res["keywords"])

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out)
        sys.stderr.write(f"已写入：{args.out}\n")
    else:
        sys.stdout.write(out + "\n")


if __name__ == "__main__":
    main()
