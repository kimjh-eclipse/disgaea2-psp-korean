import sys, struct
iso=open(sys.argv[1],'rb')
S=2048
def rd(lba,n=1):
    iso.seek(lba*S); return iso.read(n*S)
pvd=rd(16)
assert pvd[1:6]==b'CD001', pvd[:16]
root=pvd[156:156+34]
def parse_dir(rec):
    lba=struct.unpack('<I',rec[2:6])[0]
    size=struct.unpack('<I',rec[10:14])[0]
    return lba,size
rl,rs=parse_dir(root)
out=[]
def walk(lba,size,path):
    n=(size+S-1)//S
    data=rd(lba,n)
    i=0
    while i<size:
        L=data[i]
        if L==0:
            i=(i//S+1)*S; continue
        rec=data[i:i+L]
        flags=rec[25]
        nlen=rec[32]
        name=rec[33:33+nlen]
        elba=struct.unpack('<I',rec[2:6])[0]
        esz=struct.unpack('<I',rec[10:14])[0]
        if nlen==1 and name in (b'\x00',b'\x01'):
            pass
        else:
            nm=name.decode('latin1').split(';')[0]
            p=path+'/'+nm
            if flags&2:
                out.append((p+'/',elba,esz))
                walk(elba,esz,p)
            else:
                out.append((p,elba,esz))
        i+=L
walk(rl,rs,'')
for p,l,s in out:
    print(f"{l:>8} {s:>12} {p}")
