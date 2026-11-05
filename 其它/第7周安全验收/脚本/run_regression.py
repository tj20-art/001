"""Run existing and new tests with isolated MySQL, never the business schema."""
import json
from pathlib import Path
import subprocess
import sys
from security_lab import ROOT, OUT, start_lab

if __name__ == "__main__":
    lab = start_lab("regression",2447)
    import pytest
    result = pytest.main([str(ROOT / "api_service4/tests"), "-q", "--junitxml=" + str(OUT / "原始证据/pytest-after.xml")])
    lab["server"].shutdown()
    (OUT / "原始证据/regression-environment.json").write_text(json.dumps({"schema":lab["schema"],"python":sys.version,
        "pytest_exit_code":int(result),"production_database_modified":False},ensure_ascii=False,indent=2),encoding="utf-8")
    raise SystemExit(result)
