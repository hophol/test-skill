#!/usr/bin/env python3
"""trace-assert (M4 步骤合同): 从 stream-json 转录断言契约 process 段 —— C2 过程正确性。

判定纪律(继承 v1 教训,区分「没做」和「没拿到证据」):
  - skill 未触发        -> C2 = UNKNOWN(C1 的故障,先修触发再谈过程)
  - 会话被截断(无 result)-> C2 = UNKNOWN(证据可能不完整,不能定罪)

用法:
  python scripts/trace_assert.py --contract <skillDir>/tests/contract.yaml --transcript t.jsonl --skill-name <name>
  或 from trace_assert import assert_trace
"""
import argparse
import json
import re
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load_events(path):
    events = []
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return events


def tool_calls(events):
    """按出现顺序返回 [(tool, input)]"""
    calls = []
    for ev in events:
        content = (ev.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for b in content:
            if isinstance(b, dict) and b.get("type") == "tool_use":
                calls.append((b.get("name") or "", b.get("input") or {}))
    return calls


def entry_matches(call, entry):
    tool, inp = call
    if tool != entry.get("tool"):
        return False
    for param, rx in (entry.get("args") or {}).items():
        v = inp.get(param)
        if not isinstance(v, str) or not re.search(rx, v):
            return False
    return True


def fmt_entry(entry):
    args = " ".join(f"{k}=/{v}/" for k, v in (entry.get("args") or {}).items())
    return f"{entry.get('tool')} {args}".strip()


def assert_trace(contract, transcript_path, skill_name):
    events = load_events(transcript_path)
    calls = tool_calls(events)
    result_ev = next((ev for ev in events if ev.get("type") == "result"), None)
    # max-turns 截断时 CLI 也会发 result 事件(subtype=error_max_turns,文本为空)——不算完整
    has_result = bool(result_ev) and result_ev.get("subtype") != "error_max_turns"
    proc = contract.get("process") or {}
    findings = []
    n_fail = n_warn = 0

    def add(check, target, ok, soft=False, detail=""):
        nonlocal n_fail, n_warn
        v = "PASS" if ok else ("WARN" if soft else "FAIL")
        if v == "FAIL":
            n_fail += 1
        if v == "WARN":
            n_warn += 1
        findings.append({"check": check, "target": target, "verdict": v, "detail": detail})

    for entry in (proc.get("must_use") or []):
        ok = any(entry_matches(c, entry) for c in calls)
        add("must_use", fmt_entry(entry), ok,
            detail="" if ok else "转录中无「工具名+参数正则」均匹配的调用")

    for entry in (proc.get("should_use") or []):
        ok = any(entry_matches(c, entry) for c in calls)
        add("should_use", fmt_entry(entry), ok, soft=True,
            detail="" if ok else "条件步骤未观测到(仅提醒,不算失败)")

    for chain in (proc.get("ordered") or []):
        first = {}
        for t in set(chain):
            idxs = [i for i, (tool, _) in enumerate(calls) if tool == t]
            first[t] = idxs[0] if idxs else None
        if any(first[t] is None for t in chain):
            findings.append({"check": "ordered", "target": " -> ".join(chain), "verdict": "SKIP",
                             "detail": "链上有工具未出现,由 must_use 报告"})
        else:
            ok = all(first[a] < first[b] for a, b in zip(chain, chain[1:]))
            add("ordered", " -> ".join(chain), ok,
                detail="" if ok else f"首现顺序: {first}")

    hits = [(t, inp) for t, inp in calls if t in (proc.get("forbidden") or [])]
    add("forbidden", ",".join(proc.get("forbidden") or []), not hits,
        detail="" if not hits else f"违规调用: {[t for t, _ in hits]}")

    # C1 证据:skill 是否被调用。只记录不计失败——C1 归 L1 探针管
    invoked = any(re.search(r"(?i)skill", t) and skill_name in str(inp) for t, inp in calls)

    # 事故分类(v1 经验三:证据丢失 ≠ 没触发;infra 事故不能算到 C1 头上)
    api_error = False
    for ev in events:
        content = (ev.get("message") or {}).get("content")
        if isinstance(content, list):
            for b in content:
                if isinstance(b, dict) and b.get("type") == "text" and \
                        re.search(r"API Error|429|使用上限|rate limit", b.get("text") or "", re.I):
                    api_error = True

    if not events:
        verdict, reason = "UNKNOWN", "转录无任何事件(会话未启动/超时被杀/转录丢失) —— 基础设施事故,非 C1"
    elif api_error:
        verdict, reason = "UNKNOWN", "会话因 API 错误(429/限额/网络)未执行 —— 基础设施事故,非 C1"
    elif not invoked:
        verdict, reason = "UNKNOWN", f"skill「{skill_name}」未触发 —— C1 故障,先修触发(L1)再评过程"
    elif not has_result:
        verdict, reason = "UNKNOWN", ("会话被 max-turns 截断(result.subtype=error_max_turns),证据不完整"
                                      if result_ev else "会话被截断(有事件无 result),证据可能不完整")
    elif n_fail:
        verdict, reason = "FAIL", f"{n_fail} 项过程断言失败"
    else:
        verdict, reason = "PASS", "过程断言全过" + (f"({n_warn} 项软提醒)" if n_warn else "")

    return {"layer": "C2", "verdict": verdict, "reason": reason,
            "skill_invoked": invoked,
            "evidence_incomplete": bool(not events or api_error or not has_result),
            "n_tool_calls": len(calls), "tools": sorted({t for t, _ in calls}),
            "n_fail": n_fail, "n_warn": n_warn, "findings": findings}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract", required=True)
    ap.add_argument("--transcript", required=True)
    ap.add_argument("--skill-name", required=True)
    a = ap.parse_args()
    contract = yaml.safe_load(Path(a.contract).read_text(encoding="utf-8"))
    rep = assert_trace(contract, a.transcript, a.skill_name)
    print(f"C2 [{rep['verdict']}] {rep['reason']}")
    for f in rep["findings"]:
        print(f"  [{f['verdict']:>4}] {f['check']}: {f['target']} {f['detail']}")
    return rep


if __name__ == "__main__":
    main()
