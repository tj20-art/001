"""Run the generated JMX against an isolated in-memory HTTP fixture, not MySQL."""
from collections import Counter
from email import policy
from email.parser import BytesParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import xml.etree.ElementTree as ET

from cryptography import x509
from cryptography.x509.oid import NameOID
from api_service4.app.services.payment_crypto import generate_sm2_keypair
from api_service4.app.services.security_tunnel import open_request_envelope, encrypt_response_payload


ROOT = Path(__file__).resolve().parent.parent
JAVA = Path('D:/PyCharm Community Edition 2023.3.1/jbr/bin/java.exe')
JMETER = Path('D:/Downloads/JMeter/apache-jmeter-5.6.3/bin/ApacheJMeter.jar')
PAIR = generate_sm2_keypair()
CARTS = {}
COUNTS = Counter()
USERS = set()
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def respond(self, code, data, status=200, context=None):
        body = {'code': code, 'data': data, 'message': 'fixture'}
        if context:
            body = encrypt_response_payload(body, key=context[0], request_id=context[1])
        encoded = json.dumps(body).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        if context:
            self.send_header('X-Secure-Response', '1')
        self.send_header('Content-Length', str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        with LOCK:
            COUNTS['GET ' + self.path] += 1
            if self.path == '/api/v1/security/public-key':
                return self.respond(0, {'public_key': PAIR['public_key']})
            user = self.headers.get('Authorization', '')
            if self.path == '/api/v1/cart/items':
                return self.respond(0, {'items': CARTS.get(user, [])})
        self.respond(404, {}, 404)

    def do_POST(self):
        raw = self.rfile.read(int(self.headers.get('Content-Length', 0)))
        with LOCK:
            COUNTS['POST ' + self.path] += 1
            if self.path == '/api/v1/auth/login':
                message = BytesParser(policy=policy.default).parsebytes(
                    ('Content-Type: ' + self.headers['Content-Type'] + '\r\nMIME-Version: 1.0\r\n\r\n').encode() + raw)
                parts = {p.get_param('name', header='content-disposition'): p.get_payload(decode=True)
                         for p in message.iter_parts()}
                certificate = x509.load_pem_x509_certificate(parts['certificate'])
                username = certificate.subject.get_attributes_for_oid(NameOID.COMMON_NAME)[0].value
                assert parts['password'], 'missing password'
                USERS.add(username)
                return self.respond(0, {'access_token': 'fixture-' + username,
                                        'user_info': {'role': 'user', 'username': username}})
            if not raw.startswith(b'{'):
                raise AssertionError(f'Unexpected fixture body: path={self.path}, bytes={len(raw)}, content-type={self.headers.get("Content-Type")}')
            envelope = json.loads(raw)
            payload, key, rid = open_request_envelope(envelope, method='POST', path=self.path,
                                                      private_key=PAIR['private_key'])
            user = self.headers['Authorization']
            if self.path == '/api/v1/cart/items':
                CARTS.setdefault(user, []).append({'product_id': payload['product_id'],
                                                  'quantity': payload['quantity'], 'price_cents': 18000})
                return self.respond(0, {'items': CARTS[user]}, context=(key, rid))
            if self.path == '/api/v1/orders':
                items = CARTS.pop(user)
                order = {'id': COUNTS['POST ' + self.path], 'items': items,
                         'total_amount_cents': sum(i['quantity'] * i['price_cents'] for i in items)}
                return self.respond(0, {'order': order}, 201, (key, rid))
        self.respond(404, {}, 404)


def main():
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='jmeter-plan-check-') as folder:
            temporary = Path(folder)
            for kind, name in [('order', '下单性能测试'), ('login', '登录性能测试'),
                               ('order-timed', '下单性能测试')]:
                COUNTS.clear()
                USERS.clear()
                CARTS.clear()
                xml = ET.parse(ROOT / 'performance/plans' / (name + '.jmx'))
                defaults = xml.find(".//ConfigTestElement[@testname='HTTP Request Defaults']")
                defaults.find("stringProp[@name='HTTPSampler.protocol']").text = 'http'
                defaults.find("stringProp[@name='HTTPSampler.port']").text = str(server.server_port)
                for listener in xml.findall('.//ResultCollector'):
                    listener.set('enabled', 'false')
                plan = temporary / (kind + '.jmx')
                xml.write(plan, encoding='UTF-8', xml_declaration=True)
                jtl = temporary / (kind + '.jtl')
                timed = kind == 'order-timed'
                args = [str(JAVA), '-Xmx512m', '-jar', str(JMETER), '-n', '-t', str(plan),
                        '-Jusers=1' if timed else '-Jusers=3', '-Jramp=1',
                        '-Jloops=-1' if timed else '-Jloops=2',
                        '-Jduration=15' if timed else '-Jduration=30',
                        '-Jdelay_ms=50' if timed else '-Jdelay_ms=0',
                        '-l', str(jtl), '-j', str(temporary / (kind + '.log'))]
                process = subprocess.run(args, cwd=temporary, capture_output=True, text=True,
                                         encoding='utf-8', errors='replace', timeout=60)
                assert process.returncode == 0, process.stdout + process.stderr
                with jtl.open(encoding='utf-8-sig', newline='') as stream:
                    rows = list(csv.DictReader(stream))
                failures = [r for r in rows if r['success'].lower() != 'true']
                if failures:
                    log_lines = (temporary / (kind + '.log')).read_text(encoding='utf-8').splitlines()
                    details = []
                    for i, line in enumerate(log_lines):
                        if 'ERROR' in line:
                            details.extend(log_lines[i:i + 14])
                    raise AssertionError(json.dumps(failures, ensure_ascii=False) + '\n' + '\n'.join(details[:60]))
                assert len(USERS) == (1 if timed else 3), USERS
                if timed:
                    assert COUNTS['POST /api/v1/auth/login'] == 1, COUNTS
                    assert COUNTS['GET /api/v1/security/public-key'] == 1, COUNTS
                    assert COUNTS['POST /api/v1/orders'] >= 3, COUNTS
                    first = min(int(r['timeStamp']) for r in rows)
                    last = max(int(r['timeStamp']) + int(r['elapsed']) for r in rows)
                    assert last - first >= 2500
                    print('PASS order-timed: infinite business loop stopped by 15-second scheduler; login occurred only once')
                    continue
                if kind == 'order':
                    assert COUNTS['POST /api/v1/auth/login'] == 3, COUNTS
                    assert COUNTS['GET /api/v1/security/public-key'] == 3, COUNTS
                    assert COUNTS['GET /api/v1/cart/items'] == 3, COUNTS
                    assert COUNTS['POST /api/v1/cart/items'] == 6, COUNTS
                    assert COUNTS['POST /api/v1/orders'] == 6, COUNTS
                    assert not CARTS
                else:
                    assert COUNTS['POST /api/v1/auth/login'] == 6, COUNTS
                    assert sum(COUNTS.values()) == 6, COUNTS
                print(f'PASS {kind}: native JMeter loaded JMX; 3 distinct accounts; 2 loops; '
                      f'{len(rows)} successful HTTP samples; no real database or orders touched')
                if kind == 'login':
                    report = subprocess.run([str(JAVA), '-Xmx512m', '-jar', str(JMETER),
                                             '-g', str(jtl), '-o', str(temporary / 'report'),
                                             '-j', str(temporary / 'report.log')], cwd=temporary,
                                            capture_output=True, text=True, encoding='utf-8',
                                            errors='replace', timeout=60)
                    assert report.returncode == 0, report.stdout + report.stderr
                    assert (temporary / 'report/index.html').is_file()
                    print('PASS report: native HTML dashboard generated from saved JTL')
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    main()
