#!/usr/bin/env python3
"""contract-lint 的自检:4 个故意注入的缺陷必须全部被抓到,3 个真实契约必须全绿。
lint 是全部下游判定的地基,地基自己得先被验证(对应 P1 验收标准第二条)。

用法: python scripts/lint_selftest.py   (在 kit/ 目录下运行)
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from contract_lint import lint_contract  # noqa: E402

KIT = Path(__file__).parent.parent
SKILLS = KIT / "skills-sample" / ".claude" / "skills"

# (名字, skill, 改动, 期望错误信息含)
CASES = [
    ("steps 漂移", "fe-test-design",
     lambda c: c.replace("steps: 5", "steps: 4"),
     "漂移"),
    ("forbidden 与 allowed-tools 矛盾", "fe-dev-design",
     lambda c: c.replace("forbidden: [Edit, Bash]", "forbidden: [Grep]"),
     "矛盾"),
    ("artifact 前缀漂移", "fe-req-analysis",
     lambda c: c.replace('artifact: "fe-req-*.md"', 'artifact: "zzz-*.md"'),
     "artifact 前缀"),
    ("must_use 引用调不动的工具", "fe-test-design",
     lambda c: c.replace("tool: Read,", "tool: ReadX,"),
     "allowed-tools 之外"),
]


def main():
    ok = True

    # 正例:3 个真实契约全绿
    for name in ("fe-req-analysis", "fe-dev-design", "fe-test-design"):
        errs, _ = lint_contract(SKILLS / name)
        status = "PASS" if not errs else "FAIL"
        ok &= not errs
        print(f"[{status}] 正例 {name}" + (f"  错误: {errs}" if errs else ""))

    # 反例:注入缺陷必须被抓
    tmp = Path(tempfile.mkdtemp(prefix="lint-selftest-"))
    try:
        for i, (label, skill, mutate, expect) in enumerate(CASES):
            d = tmp / f"case{i}"  # 每例独立子目录(同一 skill 可能复用,见 case1/case4)
            shutil.copytree(SKILLS / skill, d)
            cpath = d / "tests" / "contract.yaml"
            cpath.write_text(mutate(cpath.read_text(encoding="utf-8")), encoding="utf-8")
            errs, _ = lint_contract(d)
            hit = any(expect in e for e in errs)
            ok &= hit
            print(f"[{'PASS' if hit else 'FAIL'}] 反例 {label}" + ("" if hit else f"  未抓到(期望含「{expect}」,实际 {errs})"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n自检结果: {'全部通过' if ok else '存在失效'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
