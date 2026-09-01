#!/usr/bin/env python3
"""run_fault_matrix: 测试的测试 —— 故障注入矩阵(变异测试思想落到被测代码)。

问题: 测试域 skill 生成的测试代码,「形态对」(框架惯用法断言全绿)不等于「真的管用」。
做法: 把已生成的测试产物放在真实执行环境里,跑 正品 + 各故障注入变体:
  正品上必须全绿(否则测试本身是坏的 —— 假红)
  每个变体上至少挂一个(该 bug 被抓住 —— 击杀);全绿 = bug 存活(测试集盲区)
产出击杀矩阵 = 该测试集的有效性得分。全程零 claude 会话,只有本地执行。

用法: python scripts/run_fault_matrix.py --test <生成的测试文件> --module discount \
        --pair clean=tasks/fixtures/discount.ts \
        --pair BUG-1满减不叠加=faults/discount-bug1.ts ...
(默认跑 009 的 vitest 矩阵)
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KIT = Path(__file__).parent.parent
ENV = KIT / "exec-env"


def run_variant(test_file: Path, module_src: Path, module_name: str, tag: str, runner: str = "vitest"):
    stage = ENV / "fault-run" / tag
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copy2(module_src, stage / f"{module_name}{module_src.suffix}")
    shutil.copy2(test_file, stage / test_file.name)
    if runner == "jest":   # jest 的 rootDir 必须落在本 stage(外部 config 会报 Can't find a root directory)
        (stage / "jest.config.cjs").write_text(
            f"module.exports = {{\n"
            f"  rootDir: '.',\n"
            f"  testEnvironment: 'jsdom',\n"
            f"  transform: {{ '^.+\\\\.[jt]sx?$': ['babel-jest', {{ configFile: {str(ENV / 'babel.config.cjs')!r} }}] }},\n"
            f"  testMatch: ['**/*.test.jsx'],\n"
            f"}};\n", encoding="utf-8")
    cmd = (["npx", "vitest", "run", test_file.name, "--reporter", "verbose"] if runner == "vitest"
           else ["npx", "jest", "--runInBand", test_file.name])
    r = subprocess.run(
        subprocess.list2cmdline(cmd),
        shell=True, cwd=str(stage), capture_output=True, timeout=240,
        env=dict(__import__("os").environ, CI="1"))   # 完整环境:精简 env 缺 SystemRoot 会让 node 原生崩溃(实测)
    out = r.stdout.decode("utf-8", errors="replace") + r.stderr.decode("utf-8", errors="replace")
    m = re.search(r"Tests?\s+(\d+)\s+failed", out)
    n_failed = int(m.group(1)) if m else None
    return {"exit": r.returncode, "failed_tests": n_failed, "tail": "\n".join(out.splitlines()[-6:])}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test", default="results/009-vitest-unit-20260901-192405/run-1/ws/discount.test.ts")
    ap.add_argument("--module", default="discount")
    ap.add_argument("--pair", action="append", nargs="+")
    ap.add_argument("--runner", default="vitest", choices=["vitest", "jest"])
    a = ap.parse_args()
    test_file = (KIT / a.test)
    pairs = []
    for p in (a.pair or []):
        for item in (p if isinstance(p, list) else [p]):   # 平铺:nargs='+' 会把多个值并成一个列表
            label, path = item.split("=", 1)
            pairs.append((label, KIT / path))
    if not pairs:   # 默认 009 矩阵
        pairs = [("clean", KIT / "tasks/fixtures/discount.ts"),
                 ("BUG-1 满减不叠加", KIT / "faults/discount-bug1.ts"),
                 ("BUG-2 VIP折扣反了", KIT / "faults/discount-bug2.ts"),
                 ("BUG-3 非法入参放行", KIT / "faults/discount-bug3.ts")]

    rows, clean_green = [], None
    for label, src in pairs:
        t0 = time.time()
        r = run_variant(test_file, src, a.module, re.sub(r"[^\w-]+", "_", label), runner=a.runner)
        dur = round(time.time() - t0, 1)
        rows.append({"label": label, **r, "duration_s": dur})
        if label == "clean":
            clean_green = r["exit"] == 0

    print(f"被评测试集: {a.test}")
    for r in rows:
        if r["label"] == "clean":
            note = "正品全绿 ✓" if r["exit"] == 0 else "正品就有失败 —— 测试集假红/环境问题!"
        else:
            note = "击杀 ✓" if r["exit"] != 0 else "存活 ✗(测试集盲区)"
        print(f"  [{r['label']:<14}] exit={r['exit']} failed={r['failed_tests']} {r['duration_s']}s  {note}")
        if r["label"] == "clean" and r["exit"] != 0:
            print("    ", r["tail"].replace("\n", "\n     "))

    bugs = [r for r in rows if r["label"] != "clean"]
    killed = [r for r in bugs if r["exit"] != 0]
    score = {"test": a.test, "clean_green": clean_green,
             "n_bugs": len(bugs), "killed": [r["label"] for r in killed],
             "survived": [r["label"] for r in bugs if r["exit"] == 0],
             "kill_rate": round(len(killed) / len(bugs), 2) if bugs else None}
    out = KIT / "results" / f"fault-matrix-{time.strftime('%Y%m%d-%H%M%S')}.json"
    out.write_text(json.dumps({"score": score, "rows": rows}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n击杀率: {len(killed)}/{len(bugs)}"
          + ("" if clean_green else "  [警告:正品未全绿,击杀率不可信]")
          + f"   报告: {out}")
    sys.exit(0 if clean_green and len(killed) == len(bugs) else 1)


if __name__ == "__main__":
    main()
