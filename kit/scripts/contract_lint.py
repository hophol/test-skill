#!/usr/bin/env python3
"""contract-lint: 校验 tests/contract.yaml 自身结构 + 与 SKILL.md 的一致性(防漂移)。

两层职责:
  结构:   契约各段字段完整、正则可编译、只引用已实现的检查原语
  漂移:   contract 与 SKILL.md 互相承诺的 步骤数/工具/产物名/编号规范 必须对得上——
          契约是双份维护,这道 lint 就是防"改了 SKILL.md 忘了契约"(反之亦然)

退出码非 0 = 有错误。用法:
  python scripts/contract_lint.py [--root skills-sample/.claude/skills] [skillDir ...]
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

# Windows 控制台默认 GBK,避免中文乱码
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 下游检查器已实现的原语。契约引用未实现项 = 报错(契约不许承诺兑现不了的检查)
KNOWN_INVARIANT_CHECKS = {"every_case_references_id", "every_item_numbered"}
KNOWN_TRACE_RULES = {"every_upstream_id_covered_ge_1", "no_phantom_ids"}


def parse_frontmatter(text: str):
    if not text.startswith("---"):
        return None, ["缺 frontmatter(应以 --- 开头)"]
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None, ["frontmatter 结构不完整"]
    try:
        return yaml.safe_load(parts[1]), []
    except yaml.YAMLError as e:
        return None, [f"frontmatter YAML 解析失败: {e}"]


def flow_steps(text: str):
    """数 SKILL.md「流程」章节的编号条数;没有该章节返回 None"""
    in_flow, n = False, 0
    for ln in text.splitlines():
        m = re.match(r"^(#{1,6})\s*(.*?)\s*$", ln)
        if m:
            in_flow = (m.group(2) == "流程")
            continue
        if in_flow and re.match(r"^\s*\d+[.、)]", ln):
            n += 1
    return n or None


def glob_prefix(g: str) -> str:
    """glob 的字面前缀(首个 * 之前),用于 SKILL.md 出现性哨兵"""
    return g.split("*")[0]


def id_prefix(rx: str) -> str:
    """ID 正则(如 REQ-\\d+)的字面 ID 前缀(REQ-)"""
    m = re.match(r"[A-Za-z][A-Za-z0-9]*-", rx)
    return m.group(0) if m else ""


def lint_contract(d: Path):
    errs, warns = [], []
    cpath = d / "tests" / "contract.yaml"
    if not cpath.exists():
        return [], [f"缺 tests/contract.yaml (v2 组织规则: 主测 skill 必须有契约)"]
    sk = d / "SKILL.md"
    if not sk.exists():
        return ["缺 SKILL.md"], []
    sk_text = sk.read_text(encoding="utf-8")
    fm, fm_errs = parse_frontmatter(sk_text)
    errs += fm_errs
    fm = fm or {}
    allowed = {t.strip() for t in re.split(r"[,\s]+", str(fm.get("allowed-tools") or "")) if t.strip()}

    try:
        c = yaml.safe_load(cpath.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as e:
        return [f"contract.yaml 解析失败: {e}"], []
    if not isinstance(c, dict):
        return ["contract.yaml 顶层不是映射"], []

    def tool_entries(sec):
        return c.get("process", {}).get(sec) or [] if isinstance(c.get("process"), dict) else []

    def check_tool_args(sec, entry):
        args = entry.get("args")
        if args is None:
            return
        if not isinstance(args, dict):
            errs.append(f"process.{sec}[{entry.get('tool')}].args 须为 参数名->正则 映射")
            return
        for k, v in args.items():
            if not isinstance(v, str):
                errs.append(f"process.{sec}[{entry.get('tool')}].args.{k} 值须为正则字符串")
                continue
            try:
                re.compile(v)
            except re.error as e:
                errs.append(f"process.{sec}[{entry.get('tool')}].args.{k} 正则非法: {v} ({e})")

    # ---- process ----
    proc = c.get("process")
    if not isinstance(proc, dict) or not proc:
        errs.append("缺 process 段")
        mu, su = [], []
    else:
        steps = proc.get("steps")
        if steps is None:
            warns.append("process.steps 未声明(跳过步骤数漂移哨兵;外部 skill 无「流程」章节时可接受)")
        elif not isinstance(steps, int) or steps < 1:
            errs.append("process.steps 须为正整数")
        else:
            n_flow = flow_steps(sk_text)
            if n_flow is None:
                errs.append("SKILL.md 无「流程」章节, steps 漂移哨兵失效")
            elif steps != n_flow:
                errs.append(f"漂移: contract.steps={steps} 但 SKILL.md 流程有 {n_flow} 步 —— 两边谁对?必须人工裁决")
        entries = {}
        for sec in ("must_use", "should_use"):
            entries[sec] = [e for e in (proc.get(sec) or []) if isinstance(e, dict)]
            for e in entries[sec]:
                if not e.get("tool"):
                    errs.append(f"process.{sec} 条目缺 tool")
                    continue
                check_tool_args(sec, e)
        mu = [e["tool"] for e in entries["must_use"] if e.get("tool")]
        su = [e["tool"] for e in entries["should_use"] if e.get("tool")]
        if not mu:
            errs.append("process.must_use 至少 1 条")
        for chain in (proc.get("ordered") or []):
            if not (isinstance(chain, list) and len(chain) >= 2):
                errs.append(f"ordered 条目须为 >=2 个工具的数组: {chain}")
                continue
            for t in chain:
                if t not in mu:
                    errs.append(f"ordered 引用的 {t} 不在 must_use 中(顺序断言只对必用工具有意义)")
        forb = proc.get("forbidden") or []
        clash = set(forb) & (set(mu) | set(su))
        if clash:
            errs.append(f"forbidden 与 must/should_use 冲突: {sorted(clash)}")
        if allowed:
            outside = [t for t in mu + su if t not in allowed]
            if outside:
                errs.append(f"must/should_use 引用了 allowed-tools 之外的 {outside}: agent 根本调不动,契约写错")
            leak = set(forb) & allowed
            if leak:
                errs.append(f"forbidden {sorted(leak)} 与 allowed-tools 矛盾(又允许又禁止)")

    # ---- output ----
    out = c.get("output")
    if not isinstance(out, dict) or not out:
        errs.append("缺 output 段")
    else:
        naming = out.get("naming", "skill")
        if naming not in ("skill", "task"):
            errs.append(f"output.naming 取值须为 skill|task,当前 {naming}")
        arts = out.get("artifacts") or ([out["artifact"]] if out.get("artifact") else [])
        if not arts or not all(isinstance(x, str) and x for x in arts):
            errs.append("output.artifact(单个 glob) 或 output.artifacts(glob 列表) 至少提供一个")
        # 注:精确文件名(无 *)合法——任务钉死名字的场景;含 * 即 glob,支持 **/ 递归
        else:
            if naming == "skill":  # task 模式:命名由任务指定,SKILL.md 不承诺,跳过哨兵
                for art in arts:
                    if "*" not in art:
                        continue  # 精确文件名无前缀语义
                    pre = glob_prefix(art)
                    if len(pre) >= 3 and pre not in sk_text:
                        errs.append(f"漂移: artifact 前缀「{pre}」未出现在 SKILL.md —— 产物文件名改了一边忘了另一边?")
        if out.get("required_sections") is None:
            if naming == "skill":
                warns.append("output 未声明 required_sections(章节断言不可用)")
        elif not (isinstance(out.get("required_sections"), list) and out.get("required_sections")):
            errs.append("output.required_sections 须为非空列表")
        for rx in (out.get("contains") or []):
            if not isinstance(rx, str):
                errs.append(f"output.contains 条目须为正则字符串: {rx!r}")
                continue
            try:
                re.compile(rx)
            except re.error as e:
                errs.append(f"output.contains 正则非法: {rx} ({e})")

    # ---- trace ----
    tr = c.get("trace")
    if tr is not None:
        if not isinstance(tr, dict):
            errs.append("trace 段须为映射")
        else:
            if not (tr.get("emits") or tr.get("consumes")):
                errs.append("trace 声明了但 emits/consumes 至少要有一个")
            if tr.get("emits"):
                try:
                    re.compile(tr["emits"])
                except re.error as e:
                    errs.append(f"trace.emits 正则非法: {e}")
                else:
                    pre = id_prefix(tr["emits"])
                    if pre and pre not in sk_text:
                        errs.append(f"漂移: emits 前缀「{pre}」未出现在 SKILL.md —— 下游要引用的编号规范,上游没承诺")
            for g in (tr.get("consumes") or []):
                if not isinstance(g, str) or "*" not in g:
                    errs.append(f"trace.consumes[{g}] 须为含 * 的 glob")
            bad = set(tr.get("rules") or []) - KNOWN_TRACE_RULES
            if bad:
                errs.append(f"trace.rules 引用未实现规则: {sorted(bad)}")

    # ---- invariants ----
    seen = set()
    for e in (c.get("invariants") or []):
        if not isinstance(e, dict) or not e.get("id") or not e.get("check"):
            errs.append(f"invariant 条目缺 id/check: {e}")
            continue
        if e["id"] in seen:
            errs.append(f"invariant id 重复: {e['id']}")
        seen.add(e["id"])
        if e["check"] not in KNOWN_INVARIANT_CHECKS:
            errs.append(f"invariant[{e['id']}].check 未实现: {e['check']}")
        if e.get("id_pattern"):
            try:
                re.compile(e["id_pattern"])
            except re.error as ex:
                errs.append(f"invariant[{e['id']}].id_pattern 正则非法: {ex}")
            else:
                pre = id_prefix(e["id_pattern"])
                if pre and pre not in sk_text:
                    errs.append(f"漂移: invariant[{e['id']}] 的编号前缀「{pre}」未出现在 SKILL.md")

    # ---- metamorphic ----
    for e in (c.get("metamorphic") or []):
        for k in ("id", "transform", "expect"):
            if not (isinstance(e, dict) and e.get(k)):
                errs.append(f"metamorphic 条目缺 {k}: {e}")

    # ---- SKILL.md 内部引用存在性(2026-09-01 夜三次野生悬空:Trail of Bits/ui-ux-pro-max/Angular 官方) ----
    # 只查技能资产目录下的引用(references/ scripts/ 等),文档示例路径(src/ tests/)与 URL 跳过;
    # ../ 开头(跨出技能目录)降 WARN;契约 lint_waivers 可豁免已知缺陷(降 WARN,诚实留痕)
    ASSET_DIRS = ("references", "scripts", "templates", "resources", "workflows", "data",
                  "assets", "examples", "themes", "fonts", "commands", "playbooks")
    waivers = [w for w in ((c.get("lint_waivers") if isinstance(c, dict) else None) or [])]
    refs = set()
    for m in re.finditer(r"(?:\{baseDir\}/)?([\w./\\-]+/[\w./\\-]+\.(?:md|py|sh|js|ts|json|ya?ml|csv|txt))\b", sk_text):
        refs.add(m.group(1).replace("\\", "/"))
    for ref in sorted(refs):
        if ref.startswith(("http", "https", "www.", "//")) or ":" in ref:
            continue
        if ref.startswith("../"):
            warns.append(f"SKILL.md 引用技能目录外文件: {ref}(独立分发时断链)")
            continue
        first = ref.split("/")[0]
        if first not in ASSET_DIRS:
            continue  # src/tests/pages 等用户工程示例路径,非技能资产
        if not (d / ref).exists():
            msg = f"SKILL.md 引用的文件不存在: {ref}"
            if any(w in msg for w in waivers):
                warns.append(f"[已知缺陷豁免] {msg}")
            else:
                errs.append(msg)

    return errs, warns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    ap.add_argument("dirs", nargs="*")
    args = ap.parse_args()
    targets = [Path(p) for p in args.dirs]
    if not targets and args.root:
        targets = sorted(p for p in Path(args.root).iterdir() if p.is_dir())
    if not targets:
        ap.error("要么给 --root,要么列出 skill 目录")

    total_err = 0
    for d in targets:
        errs, warns = lint_contract(d)
        print(f"[{'PASS' if not errs else 'FAIL'}] {d.name}")
        for e in errs:
            print(f"    错误: {e}")
        for w in warns:
            print(f"    警告: {w}")
        total_err += len(errs)
    print(f"\n结果: {'全部通过' if total_err == 0 else f'{total_err} 个错误'}")
    sys.exit(1 if total_err else 0)


if __name__ == "__main__":
    main()
