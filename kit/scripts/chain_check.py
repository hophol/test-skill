#!/usr/bin/env python3
"""chain-check (M5 链路追溯): 上游产物 vs 下游产物的 ID 集合运算 —— 全确定性。

  上游 ID 集 = 按生产者契约 trace.emits 正则,从上游产物全文抽取(生产者发了哪些号)
  下游引用集 = 同一正则,从下游产物全文抽取(消费者挂了哪些号)
  规则(来自消费者契约 trace.rules):
    every_upstream_id_covered_ge_1  每个 REQ ≥1 条用例覆盖,漏覆盖 = FAIL
    no_phantom_ids                  下游引用了上游不存在的编号 = FAIL(幻觉编号)
  输出: 逐 ID 追溯矩阵 + 覆盖率 + 判定

用法:
  python scripts/chain_check.py --producer-contract <pc.yaml> --producer-ws <wsP> \
                                --consumer-contract <cc.yaml> --consumer-ws <wsC>
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def artifacts(ws, contract):
    pattern = (contract.get("output") or {}).get("artifact") or "*"
    return sorted(p for p in Path(ws).glob(pattern) if p.is_file())


def extract_ids(paths, pattern):
    rx = re.compile(pattern)
    ids = {}
    for p in paths:
        for m in rx.findall(p.read_text(encoding="utf-8", errors="replace")):
            ids.setdefault(m, []).append(p.name)
    return ids


def check_chain(p_contract, p_ws, c_contract, c_ws, link_name=""):
    pat = (p_contract.get("trace") or {}).get("emits")
    if not pat:
        return {"layer": "chain", "link": link_name, "verdict": "UNKNOWN",
                "reason": "生产者契约无 trace.emits,无编号规范可查"}
    rules = set((c_contract.get("trace") or {}).get("rules") or [])

    up_ids = extract_ids(artifacts(p_ws, p_contract), pat)
    down_ids = extract_ids(artifacts(c_ws, c_contract), pat)

    uncovered = [i for i in sorted(up_ids) if i not in down_ids]
    phantoms = [i for i in sorted(down_ids) if i not in up_ids]
    covered = {i: len(down_ids[i]) for i in sorted(up_ids) if i in down_ids}

    fails = []
    if "every_upstream_id_covered_ge_1" in rules and uncovered:
        fails.append(f"漏覆盖 {len(uncovered)} 个: {uncovered}")
    if "no_phantom_ids" in rules and phantoms:
        fails.append(f"幻觉编号 {len(phantoms)} 个: {phantoms}")

    n = len(up_ids)
    cov_pct = round(100 * len(covered) / n, 1) if n else 0.0
    return {
        "layer": "chain", "link": link_name,
        "verdict": "FAIL" if fails else "PASS",
        "reason": "; ".join(fails) if fails else f"链路追溯通过: {len(covered)}/{n} 覆盖, 0 幻觉",
        "id_pattern": pat, "rules": sorted(rules),
        "upstream_ids": sorted(up_ids), "downstream_refs": {k: len(v) for k, v in sorted(down_ids.items())},
        "matrix": [{"id": i, "upstream": True, "refs": covered.get(i, 0),
                    "status": "covered" if i in covered else "UNCOVERED"} for i in sorted(up_ids)]
                  + [{"id": i, "upstream": False, "refs": len(down_ids[i]), "status": "PHANTOM"} for i in phantoms],
        "coverage_pct": cov_pct,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--producer-contract", required=True)
    ap.add_argument("--producer-ws", required=True)
    ap.add_argument("--consumer-contract", required=True)
    ap.add_argument("--consumer-ws", required=True)
    ap.add_argument("--link", default="")
    a = ap.parse_args()
    pc = yaml.safe_load(Path(a.producer_contract).read_text(encoding="utf-8"))
    cc = yaml.safe_load(Path(a.consumer_contract).read_text(encoding="utf-8"))
    rep = check_chain(pc, a.producer_ws, cc, a.consumer_ws, a.link)
    print(f"链路 [{rep['verdict']}] {rep['link']}  覆盖率 {rep['coverage_pct']}%  {rep['reason']}")
    for row in rep["matrix"]:
        mark = {"covered": " ", "UNCOVERED": "✗", "PHANTOM": "?"}[row["status"]]
        print(f"  {mark} {row['id']:10} 上游={'有' if row['upstream'] else '无'}  下游引用 {row['refs']} 次")
    return rep


if __name__ == "__main__":
    main()
