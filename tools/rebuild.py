import struct,sys,os
sys.path.insert(0,os.path.dirname(__file__))
from nislzs import compress,decompress
def rebuild_start(orig_bin,overrides):
    orig=open(orig_bin,'rb').read()
    n=struct.unpack('<I',orig[:4])[0]
    ents=[]
    for i in range(n):
        o=0x10+i*0x20
        off=struct.unpack('<I',orig[o:o+4])[0]
        nm=orig[o+4:o+0x20].split(b'\0')[0].decode('latin1')
        ents.append([off,nm])
    order=sorted(range(n),key=lambda i:ents[i][0])
    prefix=orig[0x10+n*0x20:ents[order[0]][0]+0x2b0]
    files={}
    for k,i in enumerate(order):
        off,nm=ents[i]
        start=off+0x2b0
        end=(ents[order[k+1]][0]+0x2b0) if k+1<n else len(orig)
        files[nm]=orig[start:end]
    files.update(overrides)
    new=bytearray()
    new+=struct.pack('<I',n)+orig[4:0x10]+b'\x00'*(n*0x20)+prefix
    offs={}
    for k,i in enumerate(order):
        nm=ents[i][1]
        while len(new)%16: new.append(0)
        offs[nm]=len(new)-0x2b0
        new+=files[nm]
    for i in range(n):
        nm=ents[i][1]
        struct.pack_into('<I',new,0x10+i*0x20,offs[nm])
        new[0x14+i*0x20:0x30+i*0x20]=orig[0x14+i*0x20:0x30+i*0x20]
    return bytes(new)
def inject_iso(iso_path,lzs,lba=166400,slot_end_lba=168848,dir_lba=25,name=b'START_US.LZS'):
    SLOT=(slot_end_lba-lba)*2048
    assert len(lzs)<=SLOT,(len(lzs),SLOT)
    f=open(iso_path,'r+b')
    f.seek(lba*2048); f.write(lzs); f.write(b'\x00'*(SLOT-len(lzs)))
    f.seek(dir_lba*2048); d=bytearray(f.read(2048))
    p=d.find(name); rec=p-33
    struct.pack_into('<I',d,rec+10,len(lzs)); struct.pack_into('>I',d,rec+14,len(lzs))
    f.seek(dir_lba*2048); f.write(d); f.close()
