"""Publish only the inspected report; preserve all original measured evidence."""
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import zipfile
from pypdf import PdfReader
from performance.build_overall_report import ROOT,OUT,SOURCE,PAIR,RETEST,NAME,audit,sha,read

def main():
    pair,retest,runs,sources=audit()
    pdf=ROOT/'performance/reports/overall-qa/report.pdf'
    pages=PdfReader(pdf).pages
    assert len(pages)==6 and all(len(p.extract_text())>300 for p in pages)
    assert '46 passed' in (PAIR/'regression-tests.txt').read_text(encoding='utf-8')
    assert '46 passed' in (RETEST/'regression-tests.txt').read_text(encoding='utf-8')
    expected_connect={('before','query'):4,('after','query'):0,('before','order'):18,('after','order'):0,('before','login'):5,('after','login'):0}
    expected_commits={('before','query'):13506,('after','query'):36,('before','order'):37464,('after','order'):29854,('before','login'):11728,('after','login'):12956}
    for (stage,key),value in expected_connect.items():
        folder=PAIR/stage/key
        with (folder/'measurement.jtl').open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
        values=sorted(int(r['Connect']) for r in rows)
        assert values[math.ceil(len(values)*.95)-1]==value
        commits=sum(r['COUNT_STAR'] for r in read(folder/'sql-digest.json') if r['sql_normalized'].strip().upper()=='COMMIT')
        assert commits==expected_commits[stage,key],(stage,key,commits)
    with (ROOT/'performance/data/users-local.csv').open(encoding='utf-8-sig',newline='') as f:password=next(csv.reader(f))[1].encode()
    for p in OUT.rglob('*'):
        if not p.is_file():continue
        if p.suffix=='.docx':
            with zipfile.ZipFile(p) as z:assert all(password not in z.read(n) for n in z.namelist())
        else:assert password not in p.read_bytes()
    evidence=read(OUT/'总报告核验.json')
    evidence.update({'word_pages':6,'visual_qa_all_pages_passed':True,'render_engine':'Microsoft Word native export plus bundled Poppler PNG','word_sha256':sha(OUT/(NAME+'.docx')),'sql_and_connect_table_verified':True,'password_in_report':False})
    (OUT/'总报告核验.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest={p.name:sha(p) for p in OUT.iterdir() if p.is_file() and p.name!='sha256-manifest.json'}
    (OUT/'sha256-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    target=SOURCE/OUT.name
    assert target.parent.resolve()==SOURCE.resolve() and not target.exists()
    shutil.copytree(OUT,target)
    assert all(sha(target/p.name)==sha(p) for p in OUT.iterdir() if p.is_file())
    print(json.dumps({'directory':str(target),'word_pages':6,'verified_files':len(list(target.iterdir())),'formal_samples':30661,'source_evidence_preserved':True},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
