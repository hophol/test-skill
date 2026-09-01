#!/usr/bin/env python3
"""judge (M7 残差裁判·对抗证伪式): 只盖确定性层盖不住的开放性维度。

纪律(继承 v1 裁判纪律,但形态是证伪不是打分):
  - 逐项二值 pass/fail,禁整体打分
  - 每项必须给证据(pass 给依据,fail 给产物原文引用)
  - 裸会话,只给 Read:裁判不加载任何 skill,不产生副作用
  - 只挂在锚点任务上,面积必须小于确定性层(跑完要统计占比)

用法:
  python scripts/judge.py --ws <任务工作区> --skill <skillDir> --rubric tasks/rubric-001.json
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
KIT = Path(__file__).parent.parent

PROMPT_TMPL = """你是严格的测试评审,任务是【证伪】:下面每个检查项,只要找到一处不满足就判 fail。
被评审产物: {artifact}
参考材料: {refs}
产出该产物的技能规范(SKILL.md):
---
{skill_md}
---

检查项:
{rubric}

先读上述文件再判定。verdict 只能是 pass 或 fail;每项都要给一句证据(fail 给产物原文引用)。
最后只输出一个 JSON 对象,不要任何其他文字:
{{"results": [{{"id": {first_id}, "verdict": "pass|fail", "evidence": "一句话依据"}}, ...]}}
"""


def extract_json(text):
    """取最后一个 {...} 并解析;裁判爱写 markdown 表,兜底从表里抽 verdict(实测教训)"""
    for m in reversed(list(re.finditer(r"\{[\s\S]*\}", text))):
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
    rows = []
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 3 and any(re.search(r"(?i)\b(pass|fail)\b", c) for c in cells):
            verdict = next((c for c in cells if re.fullmatch(r"(?i)\*{0,2}(pass|fail)\*{0,2}", c.replace("**", "") ) or re.search(r"(?i)^\*{0,2}(pass|fail)\*{0,2}$", c)), None)
            v = re.sub(r"[*_ ]", "", verdict or "").upper()
            if v in ("PASS", "FAIL"):
                rows.append({"verdict": v.lower(),
                             "evidence": next((c for c in cells if len(c) > 8 and c != verdict), "")})
    return {"results": rows} if rows else None


def run_judge(ws, skill_dir, rubric_path, model=None, timeout=240):
    rubric = json.loads(Path(rubric_path).read_text(encoding="utf-8"))
    items = rubric["items"]
    artifact = rubric["artifact_glob"]

    # 裁判工作区:被评工作区副本 + SKILL.md(只读参考),裸会话不加载 skill
    jdir = Path(tempfile.mkdtemp(prefix="judge-"))
    jws = jdir / "ws"
    shutil.copytree(ws, jws)
    shutil.copy2(Path(skill_dir) / "SKILL.md", jws / "_judge_skill.md")
    arts = sorted(p for p in jws.glob(artifact) if p.is_file())
    refs = ", ".join(sorted(p.name for p in jws.glob("*.md") if p.name != "_judge_skill.md"
                            and not p.name.startswith(arts[0].name if arts else "@@")))
    if not arts:
        return {"verdict": "ERROR", "reason": "工作区未找到被评审产物"}

    rubric_text = "\n".join(f"{i+1}. {it['item']}" for i, it in enumerate(items))
    prompt = PROMPT_TMPL.format(artifact=arts[0].name, refs=refs or "(无)",
                                skill_md=(Path(skill_dir) / "SKILL.md").read_text(encoding="utf-8"),
                                rubric=rubric_text, first_id=items[0].get("id", 1))
    args = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
            "--max-turns", "14", "--allowedTools", "Read"]
    if model:
        args += ["--model", model]
    r = subprocess.run(subprocess.list2cmdline(args), shell=True, cwd=str(jws),
                       capture_output=True, timeout=timeout)
    out = r.stdout.decode("utf-8", errors="replace")
    final_text = ""
    for line in out.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") == "result" and ev.get("result"):
            final_text = ev["result"]
    (jdir / "transcript.jsonl").write_text(out, encoding="utf-8")

    parsed = extract_json(final_text)
    if not parsed or "results" not in parsed:
        return {"verdict": "ERROR", "reason": "裁判输出不可解析", "raw": final_text[:400], "dir": str(jdir)}
    by_id = {x.get("id"): x for x in parsed["results"]}
    results = []
    n_fail = 0
    for it in items:
        r0 = by_id.get(it.get("id"), {})
        v = r0.get("verdict", "?")
        n_fail += (v == "fail")
        results.append({"id": it.get("id"), "item": it["item"], "verdict": v,
                        "evidence": r0.get("evidence", "")})
    return {"layer": "C3-judge", "verdict": "FAIL" if n_fail else "PASS",
            "n_items": len(items), "n_fail": n_fail, "results": results,
            "n_judge_calls": 1, "dir": str(jdir)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", required=True)
    ap.add_argument("--skill", required=True)
    ap.add_argument("--rubric", required=True)
    ap.add_argument("--model", default=None)
    a = ap.parse_args()
    rep = run_judge(a.ws, a.skill, a.rubric, a.model)
    print(f"{rep.get('layer', 'judge')} [{rep['verdict']}]  {rep.get('n_fail', '?')}/{rep.get('n_items', '?')} 项 fail")
    for r in rep.get("results", []):
        print(f"  [{r['verdict']:>4}] {r['id']}: {r['item']}")
        print(f"         证据: {r['evidence'][:120]}")
    if rep["verdict"] == "ERROR":
        print(f"  原因: {rep.get('reason')} {rep.get('raw', '')[:200]}")
    return rep


if __name__ == "__main__":
    main()
