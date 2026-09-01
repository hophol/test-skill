#!/usr/bin/env python3
"""run_validation: 异常 skill 验证集 runner —— v2 套件的回归测试(测试的测试)。

静态集(默认): 9 个自含异常 skill,三个 lint 全跑,预期层必须报出预期信号 —— 零会话
动态集(--dynamic): 委托 run_mutants --only <ids> —— 花会话,按需
每次改动 contract_lint / security_lint / trace_assert / prop_check 后必跑静态集

用法: python scripts/run_validation.py [--dynamic]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT / "scripts"))
from contract_lint import lint_contract          # noqa: E402
from security_lint import scan_skill             # noqa: E402

V1_LINT = Path(r"D:\work\skill-test-kit\scripts\lint_skill.py")   # v1 结构 lint(结构类异常归它)

_v1_lint_one = None
try:                                # v1 kit 不在(异机)时该工具不可用,不判 miss
    sys.path.insert(0, str(V1_LINT.parent))
    from lint_skill import lint_one as _v1_lint_one
except Exception:
    pass


def v1_lint(d: Path):
    if _v1_lint_one is None:
        return None
    errs, _warns = _v1_lint_one(d)
    return errs or []


def run_static():
    manifest = yaml.safe_load((KIT / "validation" / "manifest.yaml").read_text(encoding="utf-8"))
    rows, n_caught = [], 0
    for e in manifest["static"]:
        d = KIT / "validation" / "anomalies" / e["dir"]
        signals = {
            "contract_lint": [f"{x}" for x in lint_contract(d)[0]],
            "security_lint": [f"[{h['category']}] {h['file']}:{h['line']} {h['excerpt']}"
                              for h in scan_skill(d) if h["severity"] == "HIGH"],
            "lint_skill": v1_lint(d) or [],
        }
        want = signals.get(e["expect_tool"], [])
        hit_in_expected = any(e["expect_signal"] in s for s in want)
        elsewhere = [tool for tool, ss in signals.items()
                     if tool != e["expect_tool"] and ss and e["expect_signal"] in " ".join(ss) or
                     (tool != e["expect_tool"] and ss and any(e["expect_signal"] in x for x in ss))]
        verdict = "caught" if hit_in_expected else ("caught-elsewhere" if elsewhere else "missed")
        n_caught += hit_in_expected
        detail = next((s for s in want if e["expect_signal"] in s), "")
        rows.append((e["id"], e["class"], verdict, detail[:90]))
        print(f"[{verdict:>17}] {e['id']} ({e['class']})  {detail[:90]}")
    n = len(rows)
    print(f"\n静态集灵敏度: {n_caught}/{n} = {n_caught/n:.0%}"
          + (f"(另有 {sum(1 for r in rows if r[2]=='caught-elsewhere')} 个在非预期层报出)" if any(r[2]=='caught-elsewhere' for r in rows) else ""))
    return n_caught == n


def run_dynamic():
    manifest = yaml.safe_load((KIT / "validation" / "manifest.yaml").read_text(encoding="utf-8"))
    ids = ",".join(e["mutant"] for e in manifest["dynamic"])
    print(f"动态集委托 run_mutants --only {ids}\n")
    r = subprocess.run([sys.executable, str(KIT / "scripts" / "run_mutants.py"), "--only", ids],
                       cwd=str(KIT))
    return r.returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dynamic", action="store_true")
    a = ap.parse_args()
    ok = run_static()
    if a.dynamic:
        ok = run_dynamic() and ok
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
