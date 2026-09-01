#!/usr/bin/env python3
"""prop-check (M2 局部属性): 断言契约 output 段 + invariants —— C3 结果正确性的确定性部分。

产物形态经验(来自 run-1 真实产物):用例单元有三种形态——
  a) 组标题挂编号: ### U-1 xxx ｜ REQ-001 (+ 下挂表格是它的详情)
  b) 组下条目:    ### C-1 / - 提交中禁用 ｜ REQ-002
  c) 独立表格行:  | E2E-01 | 场景 | REQ-001/002 | ...
因此编号类不变量的判定语义是【块归属】:
  - 组标题(###/####)匹配 id_pattern -> 整块(含表格行)视为已覆盖
  - 组标题未匹配 -> 块内每个列表项/表格行是独立单元,逐一必须匹配
  - 直接挂在章节(##)下的条目/表格行也是独立单元
  - 表格首行是表头,豁免;分隔行(|---|)豁免
  - 作用域为空的章节(既无单元也无覆盖块) -> WARN(疑似空章节,不当 FAIL)

用法:
  python scripts/prop_check.py --contract <contract.yaml> --ws <workspace>
  python scripts/prop_check.py --contract <contract.yaml> --compare <wsA> <wsB>
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
ITEM = re.compile(r"^\s{0,3}(?:[-*+]|\d+[.、)])\s+(.+)$")
SEP_ROW = re.compile(r"^\|?\s*:?-{2,}[\s:|-]*$")


def norm(s):
    return re.sub(r"\s+", "", s)


def split_md(text):
    """-> [(level, heading|None, norm, lineno)] 按行切块的骨架"""
    out = []
    for i, ln in enumerate(text.splitlines(), 1):
        m = HEADING.match(ln)
        if m:
            out.append((len(m.group(1)), m.group(2), norm(m.group(2)), i))
        else:
            out.append((0, None, ln.strip(), i))
    return out


def parse_units(text, id_pattern):
    """按块归属语义抽取用例单元。
    -> sections: [{heading, norm, level, covered_blocks: n, units: [(lineno, text)], empty: bool}]
       组标题命中 id 的块只计数不展开;未命中的组,其条目/表格行逐一成为单元。
    """
    rx = re.compile(id_pattern)
    sections, cur_sec, cur_grp = [], None, None
    table_first = {}  # 表格首行(表头)豁免: 记每个连续表格段的首行号
    lines = text.splitlines()
    # 标记每个表格段的表头行
    in_table_prev = False
    for i, ln in enumerate(lines):
        is_row = ln.strip().startswith("|")
        if is_row and not in_table_prev:
            table_first[i] = True
        in_table_prev = is_row

    for i, ln in enumerate(lines):
        m = HEADING.match(ln)
        if m:
            lvl = len(m.group(1))
            if lvl <= 2 or cur_sec is None:      # ## 级 = 章节
                cur_sec = {"heading": m.group(2), "norm": norm(m.group(2)), "level": lvl,
                           "covered_blocks": 0, "units": []}
                sections.append(cur_sec)
                cur_grp = None
            else:                                 # ###/#### = 组
                cur_grp = {"heading": m.group(2), "norm": norm(m.group(2)), "level": lvl,
                           "covered": bool(rx.search(m.group(2))), "units": []}
                cur_sec["groups"] = cur_sec.get("groups", [])
                cur_sec["groups"].append(cur_grp)
            continue
        stripped = ln.strip()
        unit_text = None
        mi = ITEM.match(ln)
        if mi:
            unit_text = mi.group(1)
        elif stripped.startswith("|") and not SEP_ROW.match(stripped) and not table_first.get(i):
            unit_text = stripped
        if unit_text is None:
            continue
        if cur_sec is None:
            cur_sec = {"heading": None, "norm": "", "level": 0, "covered_blocks": 0, "units": []}
            sections.append(cur_sec)
            cur_grp = None
        if cur_grp is not None:
            if not cur_grp["covered"]:
                cur_grp["units"].append((i + 1, unit_text))
        else:
            cur_sec["units"].append((i + 1, unit_text))

    for s in sections:
        groups = s.get("groups") or []
        s["covered_blocks"] = sum(1 for g in groups if g["covered"])
        s["all_units"] = list(s["units"]) + [u for g in groups for u in g["units"]]
        s["empty"] = not s["all_units"] and not s["covered_blocks"]
    return sections


def find_artifacts(ws, contract):
    out = contract.get("output") or {}
    globs = out.get("artifacts") or ([out["artifact"]] if out.get("artifact") else ["*"])
    seen = set()
    for g in globs:
        for p in Path(ws).glob(g):
            if p.is_file():
                seen.add(p)
    return sorted(seen)


def check_props(contract, ws):
    out = contract.get("output") or {}
    findings = []
    n_fail = n_warn = 0

    def add(check, target, ok, detail="", warn=False):
        nonlocal n_fail, n_warn
        v = "PASS" if ok else ("WARN" if warn else "FAIL")
        if v == "FAIL":
            n_fail += 1
        if v == "WARN":
            n_warn += 1
        findings.append({"check": check, "target": target, "verdict": v, "detail": detail})

    globs = out.get("artifacts") or ([out["artifact"]] if out.get("artifact") else [])
    per_glob = {g: [p for p in Path(ws).glob(g) if p.is_file()] for g in globs}
    arts = sorted({p for ps in per_glob.values() for p in ps})
    if not arts:
        add("artifact", ",".join(globs) or "*", False, "工作区未找到任何产物")
        return {"layer": "C3-props", "verdict": "FAIL", "n_fail": 1, "n_warn": 0,
                "artifacts": [], "findings": findings}
    for g, ps in per_glob.items():   # 多产物契约:每个 glob 都要有文件(承诺三件套就得三件齐)
        if not ps:
            add("artifact", g, False, "此产物类型缺失")

    reqs = [norm(r) for r in out.get("required_sections") or []]
    id_pats = {}
    for inv in contract.get("invariants") or []:
        if inv.get("id_pattern"):
            id_pats[inv["id"]] = (inv["id_pattern"], inv)

    if reqs:  # 章节断言:声明了才检查(外部 skill 常无章节承诺)
        for art in arts:
            text = art.read_text(encoding="utf-8", errors="replace")
            heads = [s["norm"] for s in parse_units(text, r"\d+") if s["heading"]]
            missing = [r for r in reqs if not any(r in h or h in r for h in heads)]
            add("sections", art.name, not missing, detail="" if not missing else f"缺章节: {missing}")

    contains = out.get("contains") or []
    if contains:  # 文本断言(v1 file_contains 升格进契约):每个正则须命中至少一个产物(并集语义)
        texts = {a.name: a.read_text(encoding="utf-8", errors="replace") for a in arts}
        for rx in contains:
            hit_in = [n for n, t in texts.items() if re.search(rx, t)]
            add("contains", rx, bool(hit_in), detail=f"命中: {hit_in}" if hit_in else "所有产物均未命中")

    for art in arts:
        text = art.read_text(encoding="utf-8", errors="replace")

        for inv_id, (pat, inv) in id_pats.items():
            rx = re.compile(pat)
            sections = parse_units(text, pat)
            scope = [norm(s) for s in (inv.get("sections") or out.get("required_sections") or [])]
            bad = []
            for s in sections:
                if scope and not any(sc in s["norm"] or s["norm"] in sc for sc in scope):
                    continue
                if s["empty"]:
                    add("invariant", f"{art.name}:{inv_id}", True,
                        detail=f"章节「{s['heading']}」无任何用例单元(疑似空章节)", warn=True)
                    continue
                for ln, t in s["all_units"]:
                    if not rx.search(t):
                        bad.append(f"L{ln}:{t[:40]}")
            add("invariant", f"{art.name}:{inv_id}", not bad,
                detail="" if not bad else f"{len(bad)} 个用例单元未挂编号: {bad[:6]}")

    return {"layer": "C3-props", "verdict": "FAIL" if n_fail else "PASS",
            "n_fail": n_fail, "n_warn": n_warn,
            "artifacts": [a.name for a in arts], "findings": findings}


def signature(ws, contract):
    """结构签名:产物名 + [(规范章节名, 覆盖块数, 单元数, ID集合)] —— 幂等比对用,不含措辞。
    章节按匹配到的 required_section 规范名归并(「一、单元测试清单（...）」->「单元」),
    否则标题措辞差异会产生幻影漂移;归不到规范名的章节保留原名。"""
    out = contract.get("output") or {}
    pats = [inv.get("id_pattern") for inv in contract.get("invariants") or [] if inv.get("id_pattern")]
    if (contract.get("trace") or {}).get("emits"):
        pats.append(contract["trace"]["emits"])
    rx = re.compile("|".join(pats) if pats else r"\0")
    reqs = [norm(r) for r in out.get("required_sections") or []]
    sig = []
    for art in find_artifacts(ws, contract):
        sections = parse_units(art.read_text(encoding="utf-8", errors="replace"),
                               pats[0] if pats else r"\0")
        agg = {}
        for s in sections:
            canon = next((r for r in reqs if r and (r in s["norm"] or s["norm"] in r)), None)
            if canon is None:  # 非规约章节(如"待确认问题")标题自由,聚合为一个桶防幻影漂移
                canon = "(其他)" if s["heading"] else "(无标题节)"
            cb, units, ids = agg.get(canon, (0, [], set()))
            ids |= {m for _, t in s["all_units"] for m in rx.findall(t)}
            agg[canon] = (cb + s["covered_blocks"], units + s["all_units"], ids)
        sec_sig = tuple((canon, cb, len(units), tuple(sorted(ids)))
                        for canon, (cb, units, ids) in sorted(agg.items()))
        sig.append((art.name, sec_sig))
    return tuple(sig)


def compare(a_sig, b_sig):
    drifts = []
    for (na, sa), (nb, sb) in zip(a_sig, b_sig):
        if na != nb:
            drifts.append(f"产物名漂移: {na} vs {nb}")
        da = {s: (cb, n, i) for s, cb, n, i in sa}
        db = {s: (cb, n, i) for s, cb, n, i in sb}
        for s in sorted(set(da) | set(db)):
            cba, na_, ia = da.get(s, (0, 0, ()))
            cbb, nb_, ib = db.get(s, (0, 0, ()))
            if cba != cbb:
                drifts.append(f"「{s or '(无标题节)'}」覆盖块 {cba} -> {cbb}")
            if na_ != nb_:
                drifts.append(f"「{s or '(无标题节)'}」单元数 {na_} -> {nb_}")
            if set(ia) != set(ib):
                drifts.append(f"「{s or '(无标题节)'}」ID 集合漂移: {sorted(set(ia) ^ set(ib))}")
    if len(a_sig) != len(b_sig):
        drifts.append(f"产物数量 {len(a_sig)} -> {len(b_sig)}")
    return {"layer": "C3-idempotence", "verdict": "WARN" if drifts else "PASS", "drifts": drifts}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True)
    ap.add_argument("--ws")
    ap.add_argument("--compare", nargs=2, metavar=("wsA", "wsB"))
    a = ap.parse_args()
    contract = yaml.safe_load(Path(a.contract).read_text(encoding="utf-8"))
    if a.compare:
        rep = compare(signature(a.compare[0], contract), signature(a.compare[1], contract))
        print(f"{rep['layer']} [{rep['verdict']}]")
        for d in rep["drifts"]:
            print(f"  漂移: {d}")
        return rep
    rep = check_props(contract, a.ws)
    print(f"{rep['layer']} [{rep['verdict']}] 产物: {rep['artifacts']}  ({rep.get('n_warn', 0)} 警告)")
    for f in rep["findings"]:
        print(f"  [{f['verdict']:>4}] {f['check']}: {f['target']} {f['detail']}")
    return rep


if __name__ == "__main__":
    main()
