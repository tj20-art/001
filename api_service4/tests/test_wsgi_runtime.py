import http.client
import ssl
import threading
import time
import json
from flask import Flask,request,jsonify
from api_service4.app.services.wsgi_runtime import configured_server


def test_https_connection_reuse_and_unread_error_body_are_safe():
    app=Flask(__name__)
    @app.route('/echo')
    def echo(): return jsonify(marker=request.headers.get('X-Marker'),secure=request.is_secure)
    @app.route('/early',methods=['POST'])
    def early(): return 'denied',401  # Intentionally leave the request body unread.
    with configured_server(app,host='127.0.0.1',port=0,ssl_context='adhoc',threads=2) as server:
        thread=threading.Thread(target=server.start,daemon=True)
        thread.start()
        for _ in range(100):
            if server.ready: break
            time.sleep(.02)
        assert server.ready
        port=server.socket.getsockname()[1]
        connection=http.client.HTTPSConnection('127.0.0.1',port,context=ssl._create_unverified_context(),timeout=5)
        try:
            connection.request('GET','/echo',headers={'X-Marker':'first'})
            response=connection.getresponse()
            assert response.version==11
            assert json.loads(response.read())=={'marker':'first','secure':True}
            sock=connection.sock
            connection.request('POST','/early',body=b'body that the application does not consume')
            response=connection.getresponse()
            assert response.status==401
            response.read()
            connection.request('GET','/echo',headers={'X-Marker':'second'})
            response=connection.getresponse()
            assert response.status==200
            assert json.loads(response.read())=={'marker':'second','secure':True}
            assert connection.sock is sock
        finally:
            connection.close()
        server.stop()
        thread.join(timeout=5)
        assert not thread.is_alive()
