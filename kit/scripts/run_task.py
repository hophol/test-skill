#!/usr/bin/env python3
"""run_task: 端到端跑一个 golden 任务,出 C2/C3 分栏报告。

  建工作区(skill + setup 素材) -> claude -p 无头会话(转录落盘)
  -> trace_assert(C2) + prop_check(C3) -> report.json
  --runs N 时逐次独立运行,>=2 次附加幂等比对(结构签名)

用法: python scripts/run_task.py --task tasks/001-login-test-design.json [--runs 2] [--model X] [--max-turns 12]
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT / "scripts"))
from trace_assert import assert_trace          # noqa: E402
from prop_check import check_props, signature, compare  # noqa: E402

ALLOWED_TOOLS = "Read,Write,Glob,Grep,Skill"   # 文件类 + 技能加载,任务里禁其余


def run_claude(prompt, ws, max_turns, model=None, timeout=600):
    args = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
            "--max-turns", str(max_turns), "--allowedTools", ALLOWED_TOOLS]
    if model:
        args += ["--model", model]
    r = subprocess.run(subprocess.list2cmdline(args), shell=True, cwd=str(ws),
                       capture_output=True, timeout=timeout)
    out = r.stdout.decode("utf-8", errors="replace")
    usage = None
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result":
            usage = ev.get("usage")
    return out, r.stderr.decode("utf-8", errors="replace"), r.returncode, usage


def build_ws(task, skill_dir, run_dir):
    ws = run_dir / "ws"
    skills = ws / ".claude" / "skills"
    skills.mkdir(parents=True, exist_ok=True)
    shutil.copytree(skill_dir, skills / skill_dir.name)
    for src, dst in (task.get("setup", {}).get("copy") or []):
        s = (KIT / src).resolve()
        d = ws / dst
        d.mkdir(parents=True, exist_ok=True)
        shutil.copy2(s, d / s.name)
    return ws


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-turns", type=int, default=12)
    a = ap.parse_args()

    task = json.loads(Path(a.task).read_text(encoding="utf-8"))
    skill_name = task["skill"]
    skill_dir = KIT / "skills-sample" / ".claude" / "skills" / skill_name
    contract = yaml.safe_load((skill_dir / "tests" / "contract.yaml").read_text(encoding="utf-8"))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out_root = KIT / "results" / f"{task['id']}-{stamp}"
    report = {"task": task["id"], "skill": skill_name, "runs": [], "model": a.model, "ts": stamp}

    for i in range(1, a.runs + 1):
        run_dir = out_root / f"run-{i}"
        ws = build_ws(task, skill_dir, run_dir)
        t0 = time.time()
        try:
            out, err, rc, usage = run_claude(task["prompt"], ws, a.max_turns, a.model)
        except subprocess.TimeoutExpired:
            out, err, rc, usage = "", "timeout", -1, None
        dur = round(time.time() - t0, 1)
        transcript = run_dir / "transcript.jsonl"
        transcript.write_text(out, encoding="utf-8")
        (run_dir / "stderr.txt").write_text(err, encoding="utf-8", errors="replace")

        c2 = assert_trace(contract, transcript, skill_name)
        c3 = check_props(contract, ws)
        overall = "FAIL" if "FAIL" in (c2["verdict"], c3["verdict"]) else \
                  "UNKNOWN" if "UNKNOWN" in (c2["verdict"], c3["verdict"]) else "PASS"
        entry = {"run": i, "duration_s": dur, "exit": rc, "usage": usage,
                 "c2": c2, "c3": c3, "verdict": overall}
        report["runs"].append(entry)

        print(f"\n===== run {i}  {dur}s  exit={rc}  =====")
        print(f"C1 证据: skill_invoked={c2['skill_invoked']}  工具调用 {c2['n_tool_calls']} 次 {c2['tools']}"
              + ("  [证据不完整]" if c2["evidence_incomplete"] else ""))
        print(f"C2 [{c2['verdict']}] {c2['reason']}")
        for f in c2["findings"]:
            print(f"    [{f['verdict']:>4}] {f['check']}: {f['target']} {f['detail']}")
        print(f"C3 [{c3['verdict']}] 产物: {c3['artifacts']}")
        for f in c3["findings"]:
            print(f"    [{f['verdict']:>4}] {f['check']}: {f['target']} {f['detail']}")
        print(f"总判 [{overall}]")

    if a.runs >= 2:
        sigs = [signature(out_root / f"run-{i}" / "ws", contract) for i in range(1, a.runs + 1)]
        idem = compare(sigs[0], sigs[-1])
        report["idempotence"] = idem
        print(f"\n幂等 [{idem['verdict']}]")
        for d in idem["drifts"]:
            print(f"    漂移: {d}")

    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n报告与工作区: {out_root}")
    n_fail = sum(1 for r in report["runs"] if r["verdict"] == "FAIL")
    sys.exit(1 if n_fail else 0)


if __name__ == "__main__":
    main()
