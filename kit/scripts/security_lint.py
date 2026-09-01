#!/usr/bin/env python3
"""security-lint: skill 安检扫描器 —— 把入池人肉审计的 grep 模式工具化(2026-09-01 入池流程的固化)。

扫描对象: SKILL.md + 所有文本文件(scripts/、references/、templates/;二进制跳过)
模式五类,两级严重度:
  HIGH(退出码 1): 破坏 / 凭证读取 / 数据外传 / 凭证+网络 / 管道执行下载 / 持久化
  WARN:            普通网络下载 / 提权 / 环境变量访问(单独出现,可能是正常配置读取)
判定原则: 模式是"红旗信号"不是"定罪证据"——HIGH 命中必须人工复核上下文后再决定入池与否
(本套件用它拦截异常 skill 验证集里的 A07-A09,也用于以后每个外部 skill 的第一道安检)。

用法: python scripts/security_lint.py <skillDir> [skillDir ...]
"""
import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

TEXT_EXT = {".md", ".py", ".sh", ".bash", ".js", ".ts", ".jsx", ".tsx", ".json", ".yaml", ".yml",
            ".csv", ".txt", ".html", ".css", ".ps1", ".rb", ".java", ".toml", ".cfg", ".ini"}

# (severity, 类别, 正则) —— 顺序即优先级,HIGH 命中的行不再报 WARN
PATTERNS = [
    ("HIGH", "破坏",       r"rm\s+-rf\s+[~/]|del\s+/[sq]\s+[Cc]:|format\s+[Cc]:|shutil\.rmtree\(\s*['\"]~|Remove-Item\s+-Recurse\s+C:\\"),
    ("HIGH", "凭证读取",   r"~/]?\.ssh|id_rsa|id_ed25519|\.aws[/\\]credentials|\.netrc|\.kube/config|\.docker/config"),
    ("HIGH", "凭证外传",   r"(printenv|os\.environ|process\.env)[^\n]{0,150}(curl[^\n]{0,100}(--data|-d\s|--upload|-F\b)|wget[^\n]{0,100}--post)|(curl|wget)[^\n]{0,150}(printenv|os\.environ|process\.env)"),
    ("HIGH", "数据外传",   r"curl(?=.{0,250}https?://)(?=.{0,250}(--data|--upload|-F\b|-T\b|--form|-d\s))|wget(?=.{0,250}https?://)(?=.{0,250}--post)"),
    ("HIGH", "管道执行下载", r"(curl|wget)[^\n]{0,150}\|\s*(ba)?sh|iex\s*\(|Invoke-Expression|eval\(atob|eval\(decode|base64\s+-d[^\n]{0,60}\|\s*(ba)?sh"),
    ("HIGH", "持久化",     r"crontab\s+-e|schtasks\s+/create|reg\s+add[^\n]{0,80}(Run|Startup)|Start-Process[^\n]{0,60}-WindowStyle Hidden|>>\s*~/\.(bashrc|zshrc|profile)"),
    ("WARN", "凭证关键词", r"keychain|credentials\.json"),   # 裸关键词无路径/动词语境,数据文件常见,降级
    ("WARN", "网络下载",   r"(curl|wget)\s+[^\n]{0,100}https?://"),
    ("WARN", "提权",       r"\bsudo\s|chmod\s+777"),
    ("WARN", "环境变量访问", r"\bprintenv\b|os\.environ\b|process\.env\b"),
]


def scan_file(path: Path):
    hits = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return hits
    for i, line in enumerate(text.splitlines(), 1):
        line_hit = None
        for sev, cat, rx in PATTERNS:
            if re.search(rx, line):
                line_hit = {"severity": sev, "category": cat, "file": str(path), "line": i,
                            "excerpt": line.strip()[:120]}
                break   # 一行只报最高级
        if line_hit:
            hits.append(line_hit)
    return hits


def scan_skill(d: Path):
    hits = []
    for p in sorted(d.rglob("*")):
        if p.is_file() and (p.suffix.lower() in TEXT_EXT or p.name.upper() == "SKILL.MD"):
            hits += scan_file(p)
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+")
    a = ap.parse_args()
    n_high = 0
    for d in a.dirs:
        hits = scan_skill(Path(d))
        highs = [h for h in hits if h["severity"] == "HIGH"]
        warns = [h for h in hits if h["severity"] == "WARN"]
        n_high += len(highs)
        print(f"[{'FAIL' if highs else 'PASS'}] {Path(d).name}  HIGH={len(highs)} WARN={len(warns)}")
        for h in highs:
            print(f"    HIGH [{h['category']}] {Path(h['file']).name}:{h['line']}  {h['excerpt']}")
        for h in warns[:5]:
            print(f"    WARN [{h['category']}] {Path(h['file']).name}:{h['line']}  {h['excerpt']}")
        if len(warns) > 5:
            print(f"    ...另 {len(warns)-5} 条 WARN")
    print(f"\n结果: {n_high} 个 HIGH(须人工复核)")
    sys.exit(1 if n_high else 0)


if __name__ == "__main__":
    main()
