import json
from pathlib import Path
import xml.etree.ElementTree as E
import zipfile
import pymysql
from api_service4.config.init import get_config

def main():
    with zipfile.ZipFile(Path('D:/学习/综设3/课堂文件/安全电子商务系统III——第4-12周学生小组实施计划.docx')) as z:
        r = E.fromstring(z.read('word/document.xml'))
        paragraphs = [''.join(p.itertext()) for p in r.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p')]
        text = '\n'.join(paragraphs)
        for key in ['第8周', '第9周', '20%', '1%']:
            i = text.find(key)
            print(key, text[max(0, i-50):i+1500] if i >= 0 else 'not found')
    cfg = dict(get_config().MYSQL_CONFIG)
    with pymysql.connect(**cfg) as c:
        with c.cursor(pymysql.cursors.DictCursor) as s:
            s.execute('SELECT TABLE_NAME,TABLE_ROWS FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s', (cfg.get('database', cfg.get('db')),))
            print(json.dumps(s.fetchall(), ensure_ascii=False))
            for q in ['SELECT id,status,stock FROM products WHERE id=3', 'SHOW VARIABLES LIKE "performance_schema"', 'SELECT VERSION() version']:
                s.execute(q)
                print(s.fetchall())
    for name in ['登录性能测试', '商品查询性能测试', '下单性能测试']:
        root = E.parse(Path('D:/学习/综设3/89周-JMeter')/(name+'.jmx'))
        print(name, [(n.tag, n.get('testname'), [(p.get('name'), p.text) for p in n if p.tag in ['stringProp','boolProp']]) for n in root.findall('.//ThreadGroup')])

if __name__ == '__main__': main()
