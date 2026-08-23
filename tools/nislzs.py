import struct,sys

def decompress(data):
    assert data[:3]==b'dat', data[:4]
    dec=struct.unpack('<I',data[4:8])[0]
    flag=data[12]
    src=16
    out=bytearray()
    while len(out)<dec and src<len(data):
        b=data[src]; src+=1
        if b==flag:
            x=data[src]; src+=1
            if x==flag:
                out.append(flag); continue
            cnt=data[src]; src+=1
            disp=x-1 if x>flag else x
            st=len(out)-disp
            for i in range(cnt): out.append(out[st+i])
        else:
            out.append(b)
    return bytes(out)

def compress(raw, flag=0xd7):
    out=bytearray(b'dat\0')
    out+=struct.pack('<I',len(raw))
    size_pos=len(out); out+=b'\0\0\0\0'
    out+=bytes([flag,0,0,0])
    n=len(raw); i=0
    body=bytearray()
    # hash chain for speed
    from collections import defaultdict
    pos3=defaultdict(list)
    MAXD=0xFE  # disp encodable up to 254 (255 maps to 254 after skip)
    while i<n:
        best_len=0; best_d=0
        if i+3<=n:
            key=raw[i:i+3]
            for p in reversed(pos3.get(bytes(key),())):
                d=i-p
                if d>MAXD: break
                l=0
                lim=min(255,d)  # game decoder requires non-overlapping copies: cnt<=disp
                while l<lim and i+l<n and raw[p+l]==raw[i+l]: l+=1
                if l>best_len:
                    best_len=l; best_d=d
                    if l>=255: break
        if best_len>=4:
            x=best_d+1 if best_d>=flag else best_d
            body+=bytes([flag,x,best_len])
            for k in range(best_len):
                if i+k+3<=n: pos3[bytes(raw[i+k:i+k+3])].append(i+k)
            i+=best_len
        else:
            b=raw[i]
            if b==flag: body+=bytes([flag,flag])
            else: body.append(b)
            if i+3<=n: pos3[bytes(raw[i:i+3])].append(i)
            i+=1
    out+=body
    struct.pack_into('<I',out,size_pos,len(body)+16)
    return bytes(out)

if __name__=='__main__':
    d=open(sys.argv[1],'rb').read()
    o=decompress(d)
    print(sys.argv[1],'->',len(o))
    if len(sys.argv)>2: open(sys.argv[2],'wb').write(o)
