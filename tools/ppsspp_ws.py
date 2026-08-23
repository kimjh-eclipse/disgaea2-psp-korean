import socket,base64,json,os,struct,sys,hashlib,time

def ws_connect(host='127.0.0.1',port=45333,path='/debugger'):
    s=socket.create_connection((host,port),timeout=10)
    key=base64.b64encode(os.urandom(16)).decode()
    req=(f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
         f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    s.sendall(req.encode())
    resp=b''
    while b'\r\n\r\n' not in resp:
        resp+=s.recv(4096)
    assert b'101' in resp.split(b'\r\n')[0], resp[:200]
    return s

def ws_send(s,obj):
    data=json.dumps(obj).encode()
    hdr=bytearray([0x81])
    L=len(data)
    if L<126: hdr.append(0x80|L)
    elif L<65536: hdr+=bytes([0x80|126])+struct.pack('>H',L)
    else: hdr+=bytes([0x80|127])+struct.pack('>Q',L)
    mask=os.urandom(4); hdr+=mask
    s.sendall(bytes(hdr)+bytes(b^mask[i%4] for i,b in enumerate(data)))

def ws_recv(s):
    def rd(n):
        b=b''
        while len(b)<n:
            c=s.recv(n-len(b))
            if not c: raise EOFError
            b+=c
        return b
    while True:
        h=rd(2)
        op=h[0]&0xf; L=h[1]&0x7f
        if L==126: L=struct.unpack('>H',rd(2))[0]
        elif L==127: L=struct.unpack('>Q',rd(8))[0]
        if h[1]&0x80:
            mask=rd(4); data=bytes(b^mask[i%4] for i,b in enumerate(rd(L)))
        else: data=rd(L)
        if op==1 or op==2:
            return json.loads(data)
        if op==8: raise EOFError('closed')
