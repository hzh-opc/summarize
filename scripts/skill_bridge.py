#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""skill_bridge.py — 协同技能检测与对接（零依赖、离线、跨平台）。

扫描用户级 / 项目级技能目录，按 capabilities 关键词泛匹配 SKILL.md 的
name/description/tags，判定各能力是否可用，并返回最佳匹配技能信息。

设计目标（提升健壮性）：
- 不限定具体技能名：无论用户安装的是 desensitization-sop、自研脱敏技能，
  还是任意第三方 OCR / 语音 / 视频技能，只要其 SKILL.md 描述含候选关键词，
  都能被识别 —— 因此「非限定本机已安装技能」也能对接。
- 完全离线、纯标准库：不 import 任何外部技能或第三方包，缺失时不报错。
- 数据驱动：能力清单与关键词在 assets/capabilities.json 中可扩展；
  脚本内置同一份默认，确保该文件缺失仍可运行。

用法：
  python3 skill_bridge.py [--map assets/capabilities.json] [--roots DIR1,DIR2]
                          [--cap 能力名] [--format json|txt] [--quiet]

  --cap 模式：仅检测单个能力，exit 0=可用 / 1=缺失（配合 --quiet 只返回码）。
"""

import argparse
import json
import os
import re
import sys

# ---- 内置默认能力清单（与 assets/capabilities.json 保持一致；文件缺失时回退）----
DEFAULT_CAPS = {
    "capabilities": {
        "desensitization": {
            "purpose": "上云前对敏感信息脱敏（脱敏/处理/回填/复核闭环）",
            "keywords": ["脱敏", "desensitiz", "隐私", "敏感信息", "sensitive", "去标识", "脱敏网关"],
            "fallback": "local",
            "fallback_note": "缺失时仅本地处理，原始文本不出本机；若用户强制上云仅送 brief 紧凑中间产物并提示隐私风险",
        },
        "ocr": {
            "purpose": "图片 / 扫描件 / 截图转文字",
            "keywords": ["ocr", "光学字符", "图片转文字", "图像文字", "识别文字", "image to text", "截图转文字", "扫描件"],
            "fallback": "ask",
            "fallback_note": "缺失时请用户直接提供文本，或安装 OCR 技能",
        },
        "speech_transcription": {
            "purpose": "音频 / 语音转文字（ASR）",
            "keywords": ["语音", "转录", "转写", "speech", "transcription", "asr", "音频转文字", "听写", "字幕生成"],
            "fallback": "ask",
            "fallback_note": "缺失时请用户提供文字稿，或安装语音转录技能",
        },
        "video_transcript": {
            "purpose": "视频转文字 / 字幕 / 文案提取",
            "keywords": ["视频", "文案提取", "字幕", "视频转文字", "video", "transcript", "口播", "短视频文案", "视频文稿"],
            "fallback": "ask",
            "fallback_note": "缺失时请用户提供文字稿或字幕，或安装视频文案提取技能",
        },
        "document_text": {
            "purpose": "docx / pdf / office / ppt 文档落地为文本",
            "keywords": ["docx", "word", "文档", "office", "pdf", "排版", "幻灯片", "ppt", "wps"],
            "fallback": "ask",
            "fallback_note": "缺失时请用户导出为 .txt/.md 或安装文档处理技能",
        },
        "web_fetch": {
            "purpose": "网页抓取为文本",
            "keywords": ["网页抓取", "web fetch", "fetch url", "url抓取", "爬虫", "crawler", "联网抓取", "联网搜索"],
            "fallback": "tool",
            "fallback_note": "缺失时回退到内置 WebFetch 工具直接抓取（抓取内容可能含敏感信息，仍需过脱敏协同）",
        },
    }
}


def expand(path):
    """展开 ~ 与 $ENV。"""
    if not path:
        return path
    # 先展开环境变量，再展开 ~
    expanded = os.path.expandvars(path)
    return os.path.expanduser(expanded)


def load_caps(map_path):
    """优先加载外部 capabilities.json；失败或缺失则回退内置默认。"""
    if map_path:
        mp = expand(map_path)
        if os.path.exists(mp):
            try:
                with open(mp, encoding="utf-8") as f:
                    data = json.load(f)
                caps = data.get("capabilities")
                if isinstance(caps, dict) and caps:
                    return caps
            except Exception:
                pass
    return DEFAULT_CAPS["capabilities"]


def default_roots():
    """默认扫描：用户级技能目录 + 当前工作区项目级技能目录。"""
    roots = []
    home = os.path.expanduser("~")
    roots.append(os.path.join(home, ".workbuddy", "skills"))
    # 项目级：支持 $WORKSPACE 与当前 cwd
    ws = os.environ.get("WORKSPACE")
    if ws:
        roots.append(os.path.join(expand(ws), ".workbuddy", "skills"))
    try:
        roots.append(os.path.join(os.getcwd(), ".workbuddy", "skills"))
    except Exception:
        pass
    return roots


def read_frontmatter(skill_md_path):
    """读取 SKILL.md 的 name / description / tags（容错：无 frontmatter 也尽力解析）。"""
    name = desc = tags = ""
    try:
        with open(skill_md_path, encoding="utf-8", errors="ignore") as f:
            text = f.read()
    except Exception:
        return name, desc, tags
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
    block = m.group(1) if m else text[:3000]
    for line in block.splitlines():
        low = line.lower().lstrip()
        if low.startswith("name:"):
            name = line.split(":", 1)[1].strip().strip('"').strip("'")
        elif low.startswith("description:"):
            desc = line.split(":", 1)[1].strip().strip('"').strip("'")
        elif low.startswith("tags:"):
            tags = line.split(":", 1)[1].strip()
    return name, desc, tags


def scan_skills(roots, exclude=None):
    """扫描所有技能目录，返回 [{dir,name,description,tags,hay,path}]。
    exclude: 需排除的技能目录名集合（调用方自身，避免其描述中的输入形态被误判为自身能力）。
    """
    skills = []
    excl = set((exclude or "").split(","))
    excl = {e.strip() for e in excl if e.strip()}
    for root in roots:
        if not root or not os.path.isdir(root):
            continue
        try:
            entries = sorted(os.listdir(root))
        except Exception:
            continue
        for d in entries:
            if d in excl:
                continue
            dp = os.path.join(root, d)
            if not os.path.isdir(dp):
                continue
            sk = os.path.join(dp, "SKILL.md")
            if not os.path.exists(sk):
                continue
            name, desc, tags = read_frontmatter(sk)
            hay = " ".join([d, name, desc, tags]).lower()
            skills.append({
                "dir": d,
                "path": dp,
                "name": name,
                "description": desc,
                "hay": hay,
            })
    return skills


def detect(caps, skills):
    """对每个能力做关键词泛匹配，返回 {cap: {available, skill, ...}}。"""
    result = {}
    for cap, cfg in caps.items():
        keywords = [str(k).lower() for k in cfg.get("keywords", [])]
        best = None
        alts = []
        for s in skills:
            score = sum(s["hay"].count(k) for k in keywords)
            if score > 0:
                rec = {
                    "skill": s["dir"],
                    "name": s["name"],
                    "path": s["path"],
                    "score": score,
                }
                alts.append(rec)
                if best is None or score > best["score"]:
                    best = rec
        base = {
            "fallback": cfg.get("fallback", "ask"),
            "purpose": cfg.get("purpose", ""),
            "fallback_note": cfg.get("fallback_note", ""),
        }
        if best:
            info = dict(base)
            info.update({
                "available": True,
                "skill": best["skill"],
                "name": best["name"],
                "path": best["path"],
                "score": best["score"],
                "alternatives": [a for a in alts if a["skill"] != best["skill"]],
            })
        else:
            info = dict(base)
            info["available"] = False
        result[cap] = info
    return result


def main():
    ap = argparse.ArgumentParser(description="协同技能检测与对接（零依赖）")
    ap.add_argument("--map", help="capabilities JSON 路径（覆盖内置默认）")
    ap.add_argument("--roots", help="额外技能根目录（逗号分隔，支持 $HOME/$WORKSPACE 等环境变量）")
    ap.add_argument("--exclude", help="排除的技能目录名（逗号分隔；通常是调用方自身，如 summarize，避免其描述中的「输入形态」被误判为自身提供该能力）")
    ap.add_argument("--cap", help="仅检测单个能力，返回可用与否（exit 0=可用,1=缺失）")
    ap.add_argument("--format", default="json", choices=["json", "txt"])
    ap.add_argument("--quiet", action="store_true", help="--cap 模式仅返回 exit code")
    args = ap.parse_args()

    caps = load_caps(args.map)
    roots = default_roots()
    if args.roots:
        for r in args.roots.split(","):
            r = r.strip()
            if r:
                roots.append(expand(r))
    # 去重
    seen, uniq = set(), []
    for r in roots:
        er = expand(r)
        if er and er not in seen:
            seen.add(er)
            uniq.append(er)

    skills = scan_skills(uniq, exclude=args.exclude)
    det = detect(caps, skills)

    # 单能力查询模式
    if args.cap:
        cap = args.cap
        info = det.get(cap)
        if info and info.get("available"):
            if args.quiet:
                sys.exit(0)
            payload = {
                "capability": cap,
                "available": True,
                "skill": info["skill"],
                "name": info.get("name", ""),
                "path": info["path"],
                "score": info["score"],
                "fallback": info["fallback"],
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.format == "json"
                  else "{}: available -> {} ({})".format(cap, info["skill"], info["path"]))
            sys.exit(0)
        else:
            fb = caps.get(cap, {}).get("fallback", "ask") if cap in caps else "ask"
            note = caps.get(cap, {}).get("fallback_note", "") if cap in caps else ""
            if args.quiet:
                sys.exit(1)
            payload = {
                "capability": cap,
                "available": False,
                "fallback": fb,
                "fallback_note": note,
            }
            print(json.dumps(payload, ensure_ascii=False, indent=2) if args.format == "json"
                  else "{}: absent (fallback={})".format(cap, fb))
            sys.exit(1)

    # 全量输出
    if args.format == "txt":
        for cap, info in det.items():
            if info.get("available"):
                line = "[可用] {}: {}  (score={})  fallback={}".format(
                    cap, info["skill"], info["score"], info["fallback"])
                print(line)
                if info.get("alternatives"):
                    print("        备选: " + ", ".join(a["skill"] for a in info["alternatives"]))
            else:
                print("[缺失] {}: fallback={}  -> {}".format(
                    cap, info.get("fallback", "ask"), info.get("fallback_note", "")))
    else:
        print(json.dumps({
            "capabilities": det,
            "scanned_skills": len(skills),
            "roots": uniq,
        }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
