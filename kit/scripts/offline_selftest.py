#!/usr/bin/env python3
"""trace_assert / prop_check 的离线自检:伪造转录与产物,零 token 验证判定器本身。
三条路径都要走对: PASS / FAIL / UNKNOWN(没做 vs 没证据的纪律就内嵌在这些用例里)。

用法: python scripts/offline_selftest.py
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

import yaml

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).parent))
from trace_assert import assert_trace   # noqa: E402
from prop_check import check_props, signature, compare  # noqa: E402

KIT = Path(__file__).parent.parent
CONTRACT = yaml.safe_load(
    (KIT / "skills-sample/.claude/skills/fe-test-design/tests/contract.yaml").read_text(encoding="utf-8"))

GOOD_ART = """# 登录功能测试设计

## 单元测试清单
- REQ-001 手机号校验函数:合法/非法/空 三类输入

### U-1 倒计时 hook ｜ REQ-004

| 输入 | 期望 |
|---|---|
| 60 | 递减到 0 停止 |
| 0 | 立即停止 |

## 组件测试要点

### C-1 LoginPage
- REQ-002 提交中按钮 disabled 且有 loading
- REQ-009 防重锁:进行中只发一次

## E2E 场景

| 编号 | 场景 | 关联 |
|---|---|---|
| E2E-01 | 主流程 | REQ-003 |
| E2E-02 | 验证码 | REQ-004/005 |

## 验收核对表

| REQ | 通过标准 |
|---|---|
| REQ-001 | 红字提示 |
| REQ-007 | 锁定时间提示 |
"""   # 覆盖三种真实形态:组标题挂REQ(表格随块覆盖)/无REQ组的逐条/表格行独立单元(表头豁免)

BAD_ART = """# 登录功能测试设计

## 单元测试清单
- REQ-001 手机号校验函数
- 倒计时 hook 递减

## 组件测试要点

### C-2 LoginTabs
- 渲染两个页签
- 点击切换正常

## 验收核对表

| REQ | 通过标准 |
|---|---|
| REQ-007 | 锁定提示 |
"""   # 缺 E2E 章节;无REQ组下 3 条裸单元;验收表 OK


def ev(block):
    return json.dumps({"type": "assistant", "message": {"content": [block]}}, ensure_ascii=False)


def tu(name, **inp):
    return {"type": "tool_use", "name": name, "input": inp}


def write_transcript(path, calls, with_result=True):
    lines = [ev(c) for c in calls]
    if with_result:
        lines.append(json.dumps({"type": "result"}))
    path.write_text("\n".join(lines), encoding="utf-8")


def main():
    tmp = Path(tempfile.mkdtemp(prefix="offline-selftest-"))
    ok = True

    def check(label, cond, detail=""):
        nonlocal ok
        ok &= bool(cond)
        print(f"[{'PASS' if cond else 'FAIL'}] {label}" + (f"  {detail}" if not cond else ""))

    try:
        happy = [
            tu("Skill", skill="fe-test-design"),
            tu("Read", file_path=r"D:\ws\fe-req-login.md"),
            tu("Glob", pattern="*.md"),
            tu("Read", file_path=r"D:\ws\fe-dev-login.md"),
            tu("Write", file_path=r"D:\ws\fe-test-login.md"),
        ]
        t = tmp / "happy.jsonl"; write_transcript(t, happy)
        c2 = assert_trace(CONTRACT, t, "fe-test-design")
        check("C2 正例 PASS", c2["verdict"] == "PASS", c2["reason"])
        check("C2 正例 skill_invoked", c2["skill_invoked"] is True)

        no_skill = happy[1:]
        t = tmp / "noskill.jsonl"; write_transcript(t, no_skill)
        c2 = assert_trace(CONTRACT, t, "fe-test-design")
        check("C2 未触发 -> UNKNOWN(不定罪)", c2["verdict"] == "UNKNOWN", c2["reason"])

        bad = [tu("Skill", skill="fe-test-design"), tu("Read", file_path=r"D:\ws\fe-req-login.md"),
               tu("Edit", file_path=r"D:\ws\fe-req-login.md")]
        t = tmp / "bad.jsonl"; write_transcript(t, bad)
        c2 = assert_trace(CONTRACT, t, "fe-test-design")
        check("C2 反例 FAIL(forbidden+缺Write)", c2["verdict"] == "FAIL" and
              any(f["check"] == "forbidden" and f["verdict"] == "FAIL" for f in c2["findings"]), c2["reason"])
        check("C2 ordered 缺工具时 SKIP(不重复定罪)",
              any(f["verdict"] == "SKIP" for f in c2["findings"]))

        t = tmp / "cut.jsonl"; write_transcript(t, happy, with_result=False)
        c2 = assert_trace(CONTRACT, t, "fe-test-design")
        check("C2 截断 -> UNKNOWN(没证据≠没做)", c2["verdict"] == "UNKNOWN", c2["reason"])

        t = tmp / "empty.jsonl"; t.write_text("", encoding="utf-8")
        c2 = assert_trace(CONTRACT, t, "fe-test-design")
        check("C2 空转录 -> UNKNOWN(基础设施,非C1)",
              c2["verdict"] == "UNKNOWN" and "基础设施" in c2["reason"], c2["reason"])

        t = tmp / "api429.jsonl"
        t.write_text(ev({"type": "text", "text": "API Error: Request rejected (429) · 已达到 5 小时的使用上限"}) + "\n",
                     encoding="utf-8")
        c2 = assert_trace(CONTRACT, t, "fe-test-design")
        check("C2 API错误 -> UNKNOWN(基础设施,非C1)",
              c2["verdict"] == "UNKNOWN" and "基础设施" in c2["reason"], c2["reason"])

        wsA, wsB = tmp / "wsA", tmp / "wsB"
        wsA.mkdir(); wsB.mkdir()
        (wsA / "fe-test-login.md").write_text(GOOD_ART, encoding="utf-8")
        (wsB / "fe-test-login.md").write_text(BAD_ART, encoding="utf-8")
        c3 = check_props(CONTRACT, wsA)
        check("C3 正例 PASS", c3["verdict"] == "PASS", json.dumps(c3["findings"], ensure_ascii=False))
        bad_detail = next((f["detail"] for f in c3["findings"] if f["check"] == "invariant"), "")
        check("C3 正例: 组标题REQ覆盖表格行(表头豁免)", "L7" not in bad_detail.replace("L", " L").split() and c3["verdict"] == "PASS",
              bad_detail)
        c3 = check_props(CONTRACT, wsB)
        check("C3 反例抓缺章节", any(f["check"] == "sections" and f["verdict"] == "FAIL" for f in c3["findings"]))
        inv = next((f for f in c3["findings"] if f["check"] == "invariant"), {})
        check("C3 反例抓无编号单元(含组下条目+独立条目)",
              inv.get("verdict") == "FAIL" and "未挂编号" in inv.get("detail", ""),
              json.dumps(inv, ensure_ascii=False))

        wsA2 = tmp / "wsA2"; wsA2.mkdir()
        (wsA2 / "fe-test-login.md").write_text(
            GOOD_ART.replace("登录功能测试设计", "登录 功能 的测试设计").replace("60s 递减到 0 停止", "六十秒递减直至归零"),
            encoding="utf-8")
        idem = compare(signature(wsA, CONTRACT), signature(wsA2, CONTRACT))
        check("幂等: 措辞变化不算漂移", idem["verdict"] == "PASS", str(idem["drifts"]))
        idem = compare(signature(wsA, CONTRACT), signature(wsB, CONTRACT))
        check("幂等: 缺章节/无编号要报漂移", idem["verdict"] == "WARN" and idem["drifts"], str(idem["drifts"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\n离线自检: {'全部通过' if ok else '存在失效'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
