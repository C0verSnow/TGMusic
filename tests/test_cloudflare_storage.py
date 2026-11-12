import hashlib
import json
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path('src').resolve()))
from cloudflare_storage import D1, R2
from models import StorageError
from support import SQLiteD1


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.objects = {}
        sqlite = SQLiteD1()
        parent = self
        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                request = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                try:
                    rows = sqlite.query(request['sql'], request.get('params', []))
                    result = {'success':True, 'result':[{'success':True,'results':rows}]}
                except Exception:
                    result = {'success':False, 'errors':[{'message':'SQL failed'}]}
                self.respond(200,json.dumps(result).encode())
            def do_PUT(self):
                previous=parent.objects.get(self.path)
                if (self.headers.get('If-None-Match') == '*' and previous) or (
                    self.headers.get('If-Match') and (not previous or self.headers['If-Match'] != previous[1])):
                    self.respond(412,b'<Error><Code>PreconditionFailed</Code></Error>')
                    return
                data=self.rfile.read(int(self.headers['Content-Length']))
                etag='"'+hashlib.md5(data).hexdigest()+'"'
                metadata={key.lower():value for key,value in self.headers.items() if key.lower().startswith('x-amz-meta-')}
                parent.objects[self.path]=(data,etag,metadata)
                self.respond(200,b'',{'ETag':etag})
            def do_GET(self):
                value=parent.objects.get(self.path)
                if value is None:
                    self.respond(404,b'<Error><Code>NoSuchKey</Code></Error>')
                else:
                    self.respond(200,value[0],{'ETag':value[1],**value[2]})
            def respond(self,status,body,headers=None):
                self.send_response(status)
                self.send_header('Content-Length',str(len(body)))
                for key,value in (headers or {}).items(): self.send_header(key,value)
                self.end_headers()
                self.wfile.write(body)
            def log_message(self,*args):
                pass
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True)
        self.thread.start()
        self.endpoint=f'http://127.0.0.1:{self.server.server_port}'

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def test_actual_s3_client_preserves_newer_version_and_checks_metadata(self):
        config=SimpleNamespace(r2_bucket='bucket',r2_endpoint=self.endpoint,
            r2_access_key_id='fake-access',r2_secret_access_key='fake-secret')
        r2=R2(config)
        self.assertIsNone(r2.get('absent',optional=True))
        with self.assertRaises(StorageError): r2.get('absent')
        old=r2.put('profile',b'old',create=True,metadata={'schema':'1'})
        new=r2.versioned_put('profile',b'new',old,{'schema':'1'})
        self.assertNotEqual(old,new)
        self.assertEqual(r2.get('profile')[0],b'new')
        self.assertEqual(r2.get('profile')[2],{'schema':'1'})
        with self.assertRaises(StorageError): r2.versioned_put('profile',b'stale',old,{'schema':'1'})
        self.assertEqual(r2.get('profile')[0],b'new')
        self.assertTrue(any('.versions/' in key for key in self.objects))

    def test_actual_d1_http_adapter_and_sql_error(self):
        config=SimpleNamespace(cloudflare_account_id='account',cloudflare_d1_database_id='db',cloudflare_api_token='fake')
        d1=D1(config)
        d1.url=self.endpoint+'/query'
        self.assertEqual(d1.query('SELECT installation_id FROM installation WHERE id=?',[1]),[{'installation_id':'test-install'}])
        with self.assertRaises(StorageError): d1.query('SELECT * FROM nonexistent_table')
