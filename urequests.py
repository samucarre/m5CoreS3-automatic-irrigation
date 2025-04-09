import usocket

class Response:
    def __init__(self, sock):
        self._sock = sock
        self._cached = None

    def close(self):
        if self._sock:
            self._sock.close()
            self._sock = None

    @property
    def content(self):
        if self._cached is None:
            self._cached = self._sock.read()
            self._sock.close()
            self._sock = None
        return self._cached

    @property
    def text(self):
        return str(self.content, 'utf-8')

    def json(self):
        import ujson
        return ujson.loads(self.content)

def request(method, url, data=None, json=None, headers={}, stream=None, files=None):
    try:
        proto, dummy, host, path = url.split('/', 3)
    except ValueError:
        proto, dummy, host = url.split('/', 2)
        path = ''

    if proto == 'http:':
        port = 80
    else:
        raise ValueError('Unsupported protocol: ' + proto)

    if ':' in host:
        host, port = host.split(':', 1)
        port = int(port)

    addr = usocket.getaddrinfo(host, port)[0][-1]
    s = usocket.socket()
    s.connect(addr)
    s.send(bytes('%s /%s HTTP/1.0\r\n' % (method, path), 'utf8'))
    s.send(bytes('Host: %s\r\n' % host, 'utf8'))
    for k in headers:
        s.send(bytes('%s: %s\r\n' % (k, headers[k]), 'utf8'))

    if json is not None:
        import ujson
        data = ujson.dumps(json)
        s.send(b'Content-Type: application/json\r\n')

    if data:
        s.send(bytes('Content-Length: %d\r\n' % len(data), 'utf8'))
        s.send(b'\r\n')
        s.send(data)
    else:
        s.send(b'\r\n')

    l = s.readline()
    protover, status, msg = l.split(None, 2)
    while True:
        l = s.readline()
        if not l or l == b'\r\n':
            break
    return Response(s)

def get(url, **kwargs):
    return request("GET", url, **kwargs)

def post(url, **kwargs):
    return request("POST", url, **kwargs)

def put(url, **kwargs):
    return request("PUT", url, **kwargs)

def delete(url, **kwargs):
    return request("DELETE", url, **kwargs)