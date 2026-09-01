#!/usr/bin/env python3
"""run_chain: 三连链式任务端到端 —— v2 的招牌演示。

  PRD 原始需求 -> [fe-req-analysis] -> fe-req-*.md
                -> [fe-dev-design  ] -> fe-dev-*.md   (消费需求说明 + package.json)
                -> [fe-test-design ] -> fe-test-*.md  (消费需求说明 + 技术方案)
  每阶段: C2(trace_assert) + C3(prop_check);链路: req->dev / req->test (chain_check)

产物全部落 results/chain-<stamp>/,report.json 含全链路三层判定。
负向自检(验收用): --negative 在链跑完后把 test 产物里某个 REQ 编号改成不存在的,
                  chain-check 必须同时报 漏覆盖+幻觉编号。

用法: python scripts/run_chain.py [--negative REQ-004] [--model X]
"""
import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KIT = Path(__file__).parent.parent
sys.path.insert(0, str(KIT / "scripts"))
from trace_assert import assert_trace            # noqa: E402
from prop_check import check_props               # noqa: E402
from chain_check import check_chain              # noqa: E402
from run_task import run_claude, ALLOWED_TOOLS   # noqa: E402

SKILLS = KIT / "skills-sample" / ".claude" / "skills"


def contract_of(skill):
    return yaml.safe_load((SKILLS / skill / "tests" / "contract.yaml").read_text(encoding="utf-8"))


def stage(name, skill, prompt, setup_files, run_dir, max_turns):
    """跑一个阶段: 建工作区 -> 无头会话 -> (C2, C3)。setup_files: [(src_path, ws内名字)]"""
    ws = run_dir / "ws"
    skills_dir = ws / ".claude" / "skills"
    skills_dir.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SKILLS / skill, skills_dir / skill)
    for src, name_in_ws in setup_files:
        shutil.copy2(src, ws / name_in_ws)

    t0 = time.time()
    try:
        out, err, rc, usage = run_claude(prompt, ws, max_turns)
    except Exception as e:  # noqa: BLE001 —— 会话失败也要出结构化结果,链路不能静默断
        out, err, rc, usage = "", str(e), -1, None
    dur = round(time.time() - t0, 1)
    transcript = run_dir / "transcript.jsonl"
    transcript.write_text(out, encoding="utf-8")

    c2 = assert_trace(contract_of(skill), transcript, skill)
    c3 = check_props(contract_of(skill), ws)
    arts = c3["artifacts"]
    return {"skill": skill, "duration_s": dur, "usage": usage, "c2": c2, "c3": c3,
            "artifacts": arts, "ws": ws, "exit": rc}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--negative", default=None, help="验收负向测试: 改掉这个 REQ 编号看链路检查是否报红")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-turns", type=int, default=12)
    a = ap.parse_args()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    root = KIT / "results" / f"chain-{stamp}"
    root.mkdir(parents=True, exist_ok=True)
    fx = KIT / "tasks" / "fixtures"
    report = {"ts": stamp, "stages": [], "links": {}, "model": a.model}

    # ---- 阶段 1: 需求分析 ----
    s1 = stage("1-req", "fe-req-analysis",
               "请把这份产品需求整理成前端需求说明，材料见 prd-login.md。",
               [(fx / "prd-login.md", "prd-login.md")], root / "stage-1", a.max_turns)
    report["stages"].append(s1)
    print(f"[阶段1 fe-req-analysis] {s1['duration_s']}s 产物={s1['artifacts']}")
    print(f"    C2[{s1['c2']['verdict']}] {s1['c2']['reason']}")
    print(f"    C3[{s1['c3']['verdict']}]" + (f" {next((f['detail'] for f in s1['c3']['findings'] if f['verdict']=='FAIL'), '')}" if s1['c3']['verdict'] == "FAIL" else ""))

    req_arts = [p for p in (root / "stage-1" / "ws").glob("fe-req-*.md")]
    if not req_arts:
        print("!! 阶段1 未产出 fe-req-*.md,链路中止")
        (root / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        sys.exit(1)

    # ---- 阶段 2: 开发设计(消费阶段1产物 + package.json) ----
    s2 = stage("2-dev", "fe-dev-design",
               f"请根据前端需求说明 {req_arts[0].name} 出技术实现方案，项目技术栈以 package.json 为准。",
               [(req_arts[0], req_arts[0].name), (fx / "package.json", "package.json")],
               root / "stage-2", a.max_turns)
    report["stages"].append(s2)
    print(f"[阶段2 fe-dev-design] {s2['duration_s']}s 产物={s2['artifacts']}")
    print(f"    C2[{s2['c2']['verdict']}] {s2['c2']['reason']}")
    print(f"    C3[{s2['c3']['verdict']}]" + (f" {next((f['detail'] for f in s2['c3']['findings'] if f['verdict']=='FAIL'), '')}" if s2['c3']['verdict'] == "FAIL" else ""))

    dev_arts = [p for p in (root / "stage-2" / "ws").glob("fe-dev-*.md")]

    # ---- 阶段 3: 测试设计(消费阶段1+2产物) ----
    s3_files = [(req_arts[0], req_arts[0].name)] + [(p, p.name) for p in dev_arts]
    s3 = stage("3-test", "fe-test-design",
               f"请为登录功能做前端测试设计：需求说明见 {req_arts[0].name}"
               + (f"，技术方案见 {dev_arts[0].name}。" if dev_arts else "。"),
               s3_files, root / "stage-3", a.max_turns)
    report["stages"].append(s3)
    print(f"[阶段3 fe-test-design] {s3['duration_s']}s 产物={s3['artifacts']}")
    print(f"    C2[{s3['c2']['verdict']}] {s3['c2']['reason']}")
    print(f"    C3[{s3['c3']['verdict']}]" + (f" {next((f['detail'] for f in s3['c3']['findings'] if f['verdict']=='FAIL'), '')}" if s3['c3']['verdict'] == "FAIL" else ""))

    # ---- 链路 ----
    p1, p3 = root / "stage-1" / "ws", root / "stage-3" / "ws"
    p2 = root / "stage-2" / "ws"
    link_rt = check_chain(contract_of("fe-req-analysis"), p1, contract_of("fe-test-design"), p3, "req->test")
    report["links"]["req->test"] = link_rt
    print(f"\n[链路 req->test] [{link_rt['verdict']}] 覆盖率 {link_rt['coverage_pct']}%  {link_rt['reason']}")
    for row in link_rt["matrix"]:
        if row["status"] != "covered":
            print(f"    {row['status']:10} {row['id']}  下游引用 {row['refs']} 次")
    link_rd = check_chain(contract_of("fe-req-analysis"), p1, contract_of("fe-dev-design"), p2, "req->dev")
    report["links"]["req->dev"] = link_rd
    print(f"[链路 req->dev] [{link_rd['verdict']}] 覆盖率 {link_rd['coverage_pct']}%  {link_rd['reason']}")

    # ---- 负向验收: 改编号,链路检查必须报红 ----
    if a.negative:
        neg_ws = root / "stage-3-neg" / "ws"
        neg_ws.mkdir(parents=True)
        for art in (root / "stage-3" / "ws").glob("fe-test-*.md"):
            text = art.read_text(encoding="utf-8")
            # 编号尾部拼 9: REQ-004 -> REQ-0049,上游必然不存在 -> 幻觉编号+原编号漏覆盖双报
            (neg_ws / art.name).write_text(
                re.sub(re.escape(a.negative), a.negative + "9", text), encoding="utf-8")
        link_neg = check_chain(contract_of("fe-req-analysis"), p1, contract_of("fe-test-design"), neg_ws, "req->test(负向)")
        report["links"]["negative"] = link_neg
        caught = link_neg["verdict"] == "FAIL" and any("漏覆盖" in f for f in [link_neg["reason"]])
        print(f"\n[负向验收] 把 {a.negative} 改成不存在编号 -> 链路检查 [{'报红' if caught else '未报红!!'}]")
        print(f"    {link_neg['reason']}")

    (root / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n全链路报告: {root/'report.json'}")


if __name__ == "__main__":
    main()
