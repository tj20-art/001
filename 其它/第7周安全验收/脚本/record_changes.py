"""Create a local evidence repository from saved baseline and actual fixed files.

This does not rewrite or commit the user's existing frontend repository.
"""
import hashlib
import json
from pathlib import Path
import subprocess

OUT = Path(__file__).resolve().parent.parent
ROOT = OUT.parents[1]
RECORDS = OUT / "修复记录"
REPO = RECORDS / "证据仓库"
GIT = "D:/Git/Git/cmd/git.exe"


def git(*args):
    result = subprocess.run([GIT, "-c", "user.name=Codex security verification", "-c", "user.email=codex@local.invalid", *args],
        cwd=REPO, capture_output=True, check=True)
    return result.stdout.decode("utf-8",errors="replace")


def copy_source(src, target):
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(src.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    if REPO.exists():
        raise SystemExit("Evidence repository already exists; preserve its history rather than reinitializing it.")
    REPO.mkdir()
    baseline = RECORDS / "修复前源码"
    files = [f.relative_to(baseline) for f in baseline.rglob("*") if f.is_file()]
    for relative in files:
        copy_source(baseline/relative, REPO/relative)
    git("init", "-b", "codex/week7-security")
    git("config", "core.autocrlf", "false")
    git("add", ".")
    git("commit", "-m", "Record actual workspace baseline before week 7 security fixes")
    before = git("rev-parse", "HEAD").strip()
    files.append(Path("api_service4/tests/test_week7_security.py"))
    for relative in files:
        copy_source(ROOT/relative,REPO/relative)
        copy_source(ROOT/relative,RECORDS/"修复后源码"/relative)
    git("add", ".")
    git("commit", "-m", "Fix throttle identity, CSV formulas and server error disclosure; harden defaults and dependencies")
    after = git("rev-parse", "HEAD").strip()
    (RECORDS/"修复补丁.patch").write_text(git("diff", "--binary", before, after),encoding="utf-8",newline="\n")
    git("bundle", "create", str(RECORDS/"week7-fixes.bundle"), "--all")
    meta = {"repository":str(REPO),"branch":"codex/week7-security","baseline_commit":before,"fix_commit":after,
        "author":"Codex security verification <codex@local.invalid>",
        "note":"New local evidence repository. Baseline is the saved user workspace, not recovered historical group Git history. Text snapshots normalize line endings to LF. No push performed.",
        "actual_fixed_files":[{"path":str(f),"sha256":hashlib.sha256((ROOT/f).read_bytes()).hexdigest()} for f in files]}
    (RECORDS/"提交记录.json").write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"baseline":before,"fix":after,"files":len(files)}),flush=True)
