"""خادم HTTP وهمي بيحاكي S3 (path-style) و Google Drive/OAuth للاختبارات - بيخزّن في الذاكرة ويتحقق من الترويسات."""
import base64
import hashlib
import json
import threading
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from xml.sax.saxutils import escape


class Cloud:
    def __init__(self, s3_page=2):
        self.s3 = {}                # key -> bytes   (bucket "bkt")
        self.s3_times = {}
        self.gd = {}                # id -> {"name","parent","data","t"}
        self.sessions = {}
        self.tokens = set()
        self.fail_next = 0          # عدد الطلبات الجاية اللي ترجع 500
        self.s3_page = s3_page
        self.requests = []
        self.sa_public_key = None   # لو متحدد: بيتحقق من توقيع JWT
        self.refresh_ok = ("cid", "csecret", "rtok")
        self._n = 0
        cloud = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def _body(self):
                n = int(self.headers.get("Content-Length") or 0)
                return self.rfile.read(n) if n else b""

            def _send(self, code, body=b"", ctype="application/octet-stream", headers=None):
                if isinstance(body, (dict, list)):
                    body, ctype = json.dumps(body).encode(), "application/json"
                if isinstance(body, str):
                    body = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(body)

            def _handle(self):
                body = self._body()
                u = urllib.parse.urlsplit(self.path)
                q = dict(urllib.parse.parse_qsl(u.query, keep_blank_values=True))
                cloud.requests.append((self.command, u.path))
                if cloud.fail_next > 0:
                    cloud.fail_next -= 1
                    return self._send(500, "boom")
                if u.path.startswith("/bkt"):
                    return self._s3(u, q, body)
                if u.path == "/token":
                    return self._token(body)
                return self._gd(u, q, body)

            # ---- S3 ----
            def _s3(self, u, q, body):
                auth = self.headers.get("Authorization", "")
                if not auth.startswith("AWS4-HMAC-SHA256 Credential=AK/") or "Signature=" not in auth:
                    return self._send(403, "<Error>bad auth</Error>")
                if self.command == "PUT" and self.headers.get("x-amz-content-sha256") != hashlib.sha256(body).hexdigest():
                    return self._send(400, "<Error>bad payload hash</Error>")
                key = urllib.parse.unquote(u.path[len("/bkt"):].lstrip("/"))
                if self.command == "PUT":
                    cloud.s3[key] = body; cloud._n += 1; cloud.s3_times[key] = cloud._n
                    return self._send(200, b"", headers={"ETag": '"%s"' % hashlib.md5(body).hexdigest()})
                if self.command == "DELETE":
                    cloud.s3.pop(key, None)
                    return self._send(204)
                if self.command == "GET" and key:
                    return self._send(200, cloud.s3[key]) if key in cloud.s3 else self._send(404, "<Error>NoSuchKey</Error>")
                if self.command == "GET" and q.get("list-type") == "2":
                    keys = sorted(k for k in cloud.s3 if k.startswith(q.get("prefix", "")))
                    start = int(q["continuation-token"]) if q.get("continuation-token") else 0
                    page = keys[start:start + cloud.s3_page]
                    more = start + cloud.s3_page < len(keys)
                    xml = '<?xml version="1.0"?><ListBucketResult xmlns="http://s3.amazonaws.com/doc/2006-03-01/"><Name>bkt</Name>'
                    xml += f"<IsTruncated>{'true' if more else 'false'}</IsTruncated>"
                    if more:
                        xml += f"<NextContinuationToken>{start + cloud.s3_page}</NextContinuationToken>"
                    for k in page:
                        t = cloud.s3_times[k]
                        xml += f"<Contents><Key>{escape(k)}</Key><LastModified>2026-10-11T10:{t // 60 % 60:02d}:{t % 60:02d}.000Z</LastModified><Size>{len(cloud.s3[k])}</Size></Contents>"
                    return self._send(200, xml + "</ListBucketResult>", "application/xml")
                self._send(400, "<Error>?</Error>")

            # ---- Google ----
            def _token(self, body):
                f = dict(urllib.parse.parse_qsl(body.decode()))
                if f.get("grant_type") == "refresh_token":
                    if (f.get("client_id"), f.get("client_secret"), f.get("refresh_token")) != cloud.refresh_ok:
                        return self._send(400, {"error": "invalid_grant"})
                else:
                    try:
                        h, c, s = f["assertion"].split(".")
                        pad = lambda x: x + "=" * (-len(x) % 4)
                        claims = json.loads(base64.urlsafe_b64decode(pad(c)))
                        from cryptography.hazmat.primitives import hashes
                        from cryptography.hazmat.primitives.asymmetric import padding
                        cloud.sa_public_key.verify(base64.urlsafe_b64decode(pad(s)), f"{h}.{c}".encode(), padding.PKCS1v15(), hashes.SHA256())
                        assert claims["iss"] == "sa@proj.iam.gserviceaccount.com" and "drive" in claims["scope"]
                    except Exception as ex:
                        return self._send(400, {"error": "bad_jwt", "why": str(ex)})
                tok = uuid.uuid4().hex
                cloud.tokens.add(tok)
                self._send(200, {"access_token": tok, "expires_in": 3600})

            def _gd(self, u, q, body):
                if self.headers.get("Authorization", "")[7:] not in cloud.tokens:
                    return self._send(401, {"error": "unauthorized"})
                p = u.path
                if p == "/upload/drive/v3/files" and self.command == "POST":
                    meta = json.loads(body)
                    sid = uuid.uuid4().hex
                    cloud.sessions[sid] = meta
                    host = self.headers["Host"]
                    return self._send(200, b"", headers={"Location": f"http://{host}/upload-session/{sid}"})
                if p.startswith("/upload-session/") and self.command == "PUT":
                    meta = cloud.sessions.pop(p.rsplit("/", 1)[1])
                    fid = uuid.uuid4().hex
                    cloud._n += 1
                    cloud.gd[fid] = {"name": meta["name"], "parent": meta["parents"][0], "data": body, "t": cloud._n}
                    return self._send(200, {"id": fid, "name": meta["name"], "size": str(len(body)), "md5Checksum": hashlib.md5(body).hexdigest()})
                if p == "/drive/v3/files" and self.command == "GET":
                    folder = q["q"].split("'")[1]
                    files = [{"id": i, "name": f["name"], "size": str(len(f["data"])), "createdTime": f"2026-10-11T10:{f['t'] // 60 % 60:02d}:{f['t'] % 60:02d}Z"}
                             for i, f in cloud.gd.items() if f["parent"] == folder and f["name"].startswith("erp_")]
                    return self._send(200, {"files": files})
                if p.startswith("/drive/v3/files/"):
                    fid = p.rsplit("/", 1)[1]
                    if fid not in cloud.gd:
                        return self._send(404, {"error": "notfound"})
                    if self.command == "GET":
                        return self._send(200, cloud.gd[fid]["data"])
                    if self.command == "DELETE":
                        del cloud.gd[fid]
                        return self._send(204)
                self._send(404, {"error": "?"})

            do_GET = do_PUT = do_POST = do_DELETE = do_HEAD = _handle

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
