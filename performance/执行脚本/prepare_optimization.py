"""Preserve the measured code before applying targeted performance changes."""
from pathlib import Path
import json
import shutil
from performance.run_week89_existing import ROOT, code_manifest, write_json, database_state
from api_service4.config.init import get_config

OUT=ROOT/'performance/optimization-20261105'
FILES=['gm_crypto.py','payment_crypto.py','model_2_denglu.py','model_3_product.py','model_4_cart_order.py','security_control.py','security_tunnel.py']

def main():
    baseline=ROOT/'performance/results/现有系统持续测试-20261105021111'
    before=json.loads((baseline/'business-source-before.json').read_text(encoding='utf-8'))
    assert before==code_manifest(), 'Business source differs from measured baseline; inspect first'
    OUT.mkdir(exist_ok=False)
    for name in FILES:
        target=OUT/'before'/name
        target.parent.mkdir(exist_ok=True)
        shutil.copyfile(ROOT/'api_service4/app/services'/name,target)
    write_json(OUT/'baseline-source-manifest.json',before)
    state=database_state(get_config().MYSQL_CONFIG['db'])
    old=json.loads((baseline/'original-database-before.json').read_text(encoding='utf-8'))
    write_json(OUT/'original-database-before.json',state)
    write_json(OUT/'preflight.json',{'matches_measured_source':True,'matches_measured_database_counts':state==old,'baseline':str(baseline)})
    print(OUT)

if __name__=='__main__':main()
