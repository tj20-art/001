"""Restricted ZAP scans of the local lab; redact fixture credentials in exports."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import requests

OUT = Path(__file__).resolve().parent.parent
SESSION = requests.Session()
SESSION.trust_env = False
API = "http://127.0.0.1:8099/"
KEY = "week7-local-scan"


def api(component, kind, action, **params):
    response = SESSION.get(API + f"JSON/{component}/{kind}/{action}/", params=dict(apikey=KEY, **params), timeout=30)
    response.raise_for_status()
    result = response.json()
    if "code" in result and result.get("code") != "OK":
        raise RuntimeError(result)
    return result


def redact(value):
    if isinstance(value, dict):
        return {k:redact(v) for k,v in value.items()}
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        return re.sub(r"(?i)(Authorization:\s*Bearer\s+)[^\r\n]+", r"\1<TEST_FIXTURE_TOKEN>", value)
    return value


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("phase",choices=["before","after"])
    p.add_argument("--port",type=int,required=True)
    args = p.parse_args()
    base = f"https://127.0.0.1:{args.port}"
    if args.port not in {2445,2446}:
        raise SystemExit("Only isolated test ports 2445/2446 are authorized by this script")
    meta = {"phase":args.phase, "target":base,"started_utc":datetime.now(timezone.utc).isoformat(),
            "version":api("core","view","version"), "scope":"production Flask API, isolated MySQL; no Vue/browser crawling",
            "active_scope":"public GET /api/v1/products query parameters; SQL injection and reflected XSS rules only",
            "fixture_traffic":"authenticated RBAC/CSV and security-envelope HTTP suite sent through this proxy"}
    scanners = api("ascan","view","scanners")["scanners"]
    chosen = [s for s in scanners if s["name"] in {"SQL Injection", "Cross Site Scripting (Reflected)"}]
    if len(chosen) != 2:
        raise RuntimeError("Expected SQLi and reflected-XSS release rules")
    api("ascan","action","disableAllScanners")
    for rule in chosen:
        api("ascan","action","enableScanners",ids=rule["id"])
        api("ascan","action","setScannerAttackStrength",id=rule["id"],attackStrength="LOW")
    api("ascan","action","setOptionThreadPerHost",Integer=1)
    api("ascan","action","setOptionDelayInMs",Integer=1400)
    api("ascan","action","setOptionMaxScanDurationInMins",Integer=3)
    meta["rules"] = chosen
    target = base + "/api/v1/products?name=week7&product_id=1"
    api("core","action","accessUrl",url=target,followRedirects="false")
    sid = api("ascan","action","scan",url=target,recurse="false",inScopeOnly="false",method="GET")["scan"]
    meta["scan_id"] = sid
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        status = api("ascan","view","status",scanId=sid)["status"]
        if status == "100":
            break
        print(args.phase, "active",status,flush=True)
        time.sleep(12)
    else:
        api("ascan","action","stop",scanId=sid)
        meta["external_timeout"] = True
    meta["scan_status"] = api("ascan","view","scans")
    for _ in range(15):
        if api("pscan","view","recordsToScan")["recordsToScan"] == "0":
            break
        time.sleep(2)
    alerts = api("core","view","alerts",baseurl=base,start=0,count=10000)
    messages = api("core","view","messages",baseurl=base,start=0,count=10000)
    meta["addons"] = api("autoupdate","view","installedAddons")
    meta["passive_scanners"] = api("pscan","view","scanners")
    meta["finished_utc"] = datetime.now(timezone.utc).isoformat()
    meta["message_count"] = len(messages.get("messages",[]))
    meta["remaining_passive"] = api("pscan","view","recordsToScan")
    for name, data in [("alerts",alerts),("messages",redact(messages)),("execution",meta)]:
        (OUT / "原始证据" / ("zap-"+args.phase+"-"+name+".json")).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"phase":args.phase,"messages":meta["message_count"],"alerts":len(alerts.get("alerts",[]))}),flush=True)
