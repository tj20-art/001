"""Build a separate runnable copy matching the measured baseline, never roll back the workspace."""
from pathlib import Path
import hashlib
import json
from performance.run_week89_existing import ROOT, write_json

def main():
    opt=ROOT/'performance/optimization-20261105'
    manifest=json.loads((opt/'baseline-source-manifest.json').read_text(encoding='utf-8'))
    out=opt/'baseline_source'
    out.mkdir(exist_ok=False)
    for name,value in manifest.items():
        if '/tests/' in name: continue
        source=ROOT/name
        if hashlib.sha256(source.read_bytes()).hexdigest()!=value:
            source=opt/'before'/Path(name).name
        assert hashlib.sha256(source.read_bytes()).hexdigest()==value,name
        dest=out/name
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(source.read_bytes())
    write_json(opt/'baseline-source-copy-verification.json',{'all_application_hashes_match_original_baseline':True,'source_root':str(out)})
    print(out)

if __name__=='__main__':main()
