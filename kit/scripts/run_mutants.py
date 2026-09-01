#!/usr/bin/env python3
"""mutant-runner (M9 变异测试): 故意弄坏 skill,套件必须报警 —— 测的是测试套件自身的灵敏度。

流程(每变异体):
  1. 拷贝 skill 目录,按 find/replace 打补丁(find 串找不到 = 变异体失效,记错误)
  2. 先跑 L0: contract_lint —— 静态哨兵抓住的不花会话
  3. L0 没抓住的按 mode 跑动态:
     task  = 跑 golden 任务 001,C2/C3 任一 FAIL 即抓住(注:C3 的治理性 FAIL 见 --strict)
     probe = 裸探针验证触发(v1 L1 领地),skill 未被调用 = 抓住
  4. 漏抓定性: 语义等价挽救(模型自己补正) or 真盲区,人工看转录裁决

基线说明: fe-test-design 的 C3 在未变异时就有「孤儿用例」治理性 FAIL(编号范围缺口,
用户已裁决维持严格)。为让灵敏度实验可判,--strict 默认关: 治理性 FAIL 不算抓住变异,
只有「相对基线新增的 FAIL」才算。基线 = 变异前先跑一次同任务。

用法: python scripts/run_mutants.py [--only M1,M2] [--task tasks/001-login-test-design.json]
"""
import argparse
import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT / "scripts"))
from contract_lint import lint_contract        # noqa: E402
from trace_assert import assert_trace          # noqa: E402
from prop_check import check_props             # noqa: E402
from run_task import run_claude                # noqa: E402

SKILLS = KIT / "skills-sample" / ".claude" / "skills"
PROBE_PROMPT = ("帮我把这份登录功能的前端需求做成前端测试设计：单元测试清单、组件测试要点、"
                "E2E 场景、验收核对表都要。材料在 fe-req-login.md 和 fe-dev-login.md。")


def apply_mutant(mut, dst):
    """拷贝 skill 到 dst 并打补丁;返回 (ok, 说明)"""
    shutil.copytree(SKILLS / mut["skill"], dst)
    sk = dst / "SKILL.md"
    text = sk.read_text(encoding="utf-8")
    if mut["find"] not in text:
        return False, f"find 串在 SKILL.md 中不存在(变异体失效): {mut['find'][:40]}"
    sk.write_text(text.replace(mut["find"], mut["replace"]), encoding="utf-8")
    return True, ""


def run_golden(skill_dir, skill_name, task, max_turns=12):
    """跑一次 golden 任务,返回 (c2, c3, transcript_path)。工作区一次性。"""
    run_dir = Path(tempfile.mkdtemp(prefix="mutant-run-"))
    ws = run_dir / "ws"
    skills = ws / ".claude" / "skills"
    skills.mkdir(parents=True)
    shutil.copytree(skill_dir, skills / skill_name)
    for src, _ in (task.get("setup", {}).get("copy") or []):
        s = (KIT / src).resolve()
        shutil.copy2(s, ws / s.name)
    out, err, rc, usage = run_claude(task["prompt"], ws, max_turns)
    t = run_dir / "transcript.jsonl"
    t.write_text(out, encoding="utf-8")
    contract = yaml.safe_load((skill_dir / "tests" / "contract.yaml").read_text(encoding="utf-8"))
    c2 = assert_trace(contract, t, skill_name)
    c3 = check_props(contract, ws)
    return c2, c3, t.parent, usage


def new_fails(mut_c2, mut_c3, base):
    """相对基线新增的 FAIL(治理性已知 FAIL 不算抓住)"""
    base_keys = {(f["check"], f["target"], f["verdict"]) for f in base["c2"]["findings"] + base["c3"]["findings"]}
    new = [f for f in mut_c2["findings"] + mut_c3["findings"]
           if f["verdict"] == "FAIL" and (f["check"], f["target"], f["verdict"]) not in base_keys]
    verdict_fail = "FAIL" in (mut_c2["verdict"], mut_c3["verdict"]) and \
                   "FAIL" not in (base["c2"]["verdict"], base["c3"]["verdict"])
    return new, verdict_fail


def run_probe(skill_dir, skill_name, fixtures, max_turns=10):
    ws_dir = Path(tempfile.mkdtemp(prefix="mutant-probe-"))
    ws = ws_dir / "ws"
    skills = ws / ".claude" / "skills"
    skills.mkdir(parents=True)
    shutil.copytree(skill_dir, skills / skill_name)
    for f in fixtures:
        shutil.copy2(KIT / "tasks" / "fixtures" / f, ws / f)
    out, err, rc, usage = run_claude(PROBE_PROMPT, ws, max_turns)
    t = ws_dir / "transcript.jsonl"
    t.write_text(out, encoding="utf-8")
    contract = yaml.safe_load((skill_dir / "tests" / "contract.yaml").read_text(encoding="utf-8"))
    c2 = assert_trace(contract, t, skill_name)
    return c2["skill_invoked"], t.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="只跑指定变异体,逗号分隔 id")
    ap.add_argument("--task", default="tasks/001-login-test-design.json")
    a = ap.parse_args()

    mutants = json.loads((KIT / "mutants" / "mutants.json").read_text(encoding="utf-8"))
    if a.only:
        keep = {x.strip() for x in a.only.split(",")}
        mutants = [m for m in mutants if m["id"] in keep]
    task = json.loads((KIT / a.task).read_text(encoding="utf-8"))

    # 变异<->任务自动配对(2026-09-01 教训:M11 曾用 fe-test-design 的任务跑 fe-dev-design 变异,信号被错配污染):
    # 优先选 skill 与变异体一致的 golden 任务,没有才回退 --task
    def task_for(mut):
        for tf in sorted((KIT / "tasks").glob("*.json")):
            t = json.loads(tf.read_text(encoding="utf-8"))
            if t.get("skill") == mut["skill"]:
                return t
        return task

    # 基线: 未变异跑一次,记录已知 FAIL(治理性)
    print("== 基线运行(未变异) ==")
    baselines = {}   # 按 task id 缓存基线 —— 变异体用 task_for 配对任务,基线必须同任务才可比(差分前提)

    def baseline_for(t):
        if t["id"] not in baselines:
            b_c2, b_c3, b_dir, _u = run_golden(SKILLS / t["skill"], t["skill"], t)
            baselines[t["id"]] = {"c2": b_c2, "c3": b_c3}
            print(f"基线[{t['id']}]: C2[{b_c2['verdict']}] C3[{b_c3['verdict']}] "
                  f"已知FAIL={sum(1 for f in b_c2['findings']+b_c3['findings'] if f['verdict']=='FAIL')}  工作区 {b_dir}")
        return baselines[t["id"]]

    base = baseline_for(task)

    results = []
    n_caught = 0
    for m in mutants:
        tmp = Path(tempfile.mkdtemp(prefix="mutant-"))
        skill_dir = tmp / m["skill"]
        ok, why = apply_mutant(m, skill_dir)
        if not ok:
            results.append({**m, "caught": False, "by": "ERROR", "detail": why})
            print(f"[ERROR] {m['id']}: {why}")
            continue
        # L0 静态
        errs, _ = lint_contract(skill_dir)
        if errs:
            results.append({**m, "caught": True, "by": "L0.contract-lint", "detail": errs[0]})
            n_caught += 1
            print(f"[抓住] {m['id']}  <- L0.contract-lint: {errs[0]}")
            continue
        # 动态
        if m["mode"] == "probe":
            invoked, pdir = run_probe(skill_dir, m["skill"], ["fe-req-login.md", "fe-dev-login.md"])
            caught = not invoked
            results.append({**m, "caught": caught, "by": "L1.probe",
                            "detail": f"skill_invoked={invoked} 工作区 {pdir}"})
            n_caught += caught
            print(f"[{'抓住' if caught else '漏抓'}] {m['id']}  <- L1.probe: invoked={invoked}")
        else:
            mt = task_for(m)
            c2, c3, rdir, usage = run_golden(skill_dir, m["skill"], mt)
            new, verdict_flip = new_fails(c2, c3, baseline_for(mt))
            caught = bool(new) or verdict_flip
            by = ",".join(sorted({f["check"] for f in new})) or ("verdict翻转" if verdict_flip else "")
            results.append({**m, "caught": caught, "by": by or "未抓住",
                            "detail": f"C2[{c2['verdict']}] C3[{c3['verdict']}] 新增FAIL={[f['check'] for f in new]} 工作区 {rdir}"})
            n_caught += caught
            print(f"[{'抓住' if caught else '漏抓'}] {m['id']}  C2[{c2['verdict']}] C3[{c3['verdict']}] 新增: {by or '无'}")

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = KIT / "results" / f"mutants-{stamp}.json"
    summary = {"baseline": {tid: {"c2": b["c2"]["verdict"], "c3": b["c3"]["verdict"]}
                            for tid, b in baselines.items()},
               "n": len(mutants), "caught": n_caught,
               "sensitivity": round(n_caught / len(mutants), 2) if mutants else 0,
               "results": results}
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n灵敏度: {n_caught}/{len(mutants)} = {summary['sensitivity']:.0%}   报告: {out}")


if __name__ == "__main__":
    main()
