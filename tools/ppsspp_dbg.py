import socket,base64,json,os,struct,sys,time
sys.path.insert(0,os.path.dirname(__file__))
from ppsspp_ws import ws_connect,ws_send

class Dbg:
    def __init__(self,port=4543):
        self.s=ws_connect(port=port)
        self.n=0
    def _rd(self,n):
        b=b''
        while len(b)<n:
            c=self.s.recv(n-len(b))
            if not c: raise EOFError
            b+=c
        return b
    def recv_msg(self,timeout=30):
        self.s.settimeout(timeout)
        parts=[]
        while True:
            h=self._rd(2); fin=h[0]&0x80; op=h[0]&0xf; L=h[1]&0x7f
            if L==126: L=struct.unpack('>H',self._rd(2))[0]
            elif L==127: L=struct.unpack('>Q',self._rd(8))[0]
            data=self._rd(L)
            if op==8: raise EOFError
            if op in (9,10): continue
            parts.append(data)
            if fin:
                try: return json.loads(b''.join(parts))
                except Exception: return {}
    def req(self,obj,timeout=30):
        self.n+=1; t=f"t{self.n}"
        obj['ticket']=t
        ws_send(self.s,obj)
        while True:
            m=self.recv_msg(timeout)
            if m.get('ticket')==t: return m
    def wait_event(self,name,timeout=60):
        end=time.time()+timeout
        while time.time()<end:
            m=self.recv_msg(timeout)
            if m.get('event')==name: return m
    def read(self,addr,size):
        m=self.req({"event":"memory.read","address":addr,"size":size})
        return base64.b64decode(m['base64'])
    def write(self,addr,data):
        return self.req({"event":"memory.write","address":addr,"base64":base64.b64encode(data).decode()})
