"""Run real SAST and dependency scanners; retain output and exit status."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from datetime import datetime, timezone

HERE = Path(__file__).resolve().parent
OUT = HERE.parent
ROOT = OUT.parents[1]


def run(name, command, cwd=ROOT, timeout=300):
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    started = datetime.now(timezone.utc).isoformat()
    try:
        result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, timeout=timeout)
        code = result.returncode
        stdout, stderr = result.stdout, result.stderr
    except subprocess.TimeoutExpired as exc:
        code, stdout, stderr = 124, exc.stdout or b"", (exc.stderr or b"") + b"\nTIMEOUT"
    target = OUT / "原始证据" / name
    target.with_suffix(".stdout.txt").write_bytes(stdout)
    target.with_suffix(".stderr.txt").write_bytes(stderr)
    meta = {"command": [str(x) for x in command], "cwd": str(cwd), "started_utc": started,
            "finished_utc": datetime.now(timezone.utc).isoformat(), "exit_code": code}
    target.with_suffix(".execution.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(name, "exit", code, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["before", "after"])
    parser.add_argument("--only", choices=["all", "npm"], default="all")
    args = parser.parse_args()
    py = OUT / ".tools/scan-env/Scripts/python.exe"
    if args.only == "all":
        run("bandit-" + args.phase, [str(py), "-m", "bandit", "-r", "api_service4/app", "api_service4/run.py", "mock_bank",
            "-f", "json", "-o", str(OUT / ("原始证据/bandit-" + args.phase + ".json"))])
        run("pip-audit-" + args.phase, [str(py), "-m", "pip_audit", "-r", "requirements.txt", "--no-deps", "--disable-pip",
            "-f", "json", "-o", str(OUT / ("原始证据/pip-audit-" + args.phase + ".json")), "--progress-spinner", "off"], timeout=240)
    run("npm-audit-" + args.phase, ["D:/C/nodejs/npm.cmd", "audit", "--json", "--package-lock-only", "--registry=https://registry.npmjs.org"], ROOT / "api-service4-frontend", timeout=240)
