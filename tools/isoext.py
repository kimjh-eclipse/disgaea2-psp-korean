import sys,os,struct
iso=open(r"Disgaea 2 - Dark Hero Days (USA).iso",'rb')
def ext(lba,size,out):
    iso.seek(lba*2048)
    os.makedirs(os.path.dirname(out),exist_ok=True)
    with open(out,'wb') as f:
        left=size
        while left>0:
            c=iso.read(min(1<<20,left)); f.write(c); left-=len(c)
    print(out,size)
tbl={
 'SCRIPTPACK.DAT':(164704,3451837),
 'START_US.LZS':(166400,4995259),
 'START_VM_US.LZS':(169376,454498),
 'START_VM2_US.LZS':(171056,1305734),
 'START_VM_US.DAT':(169600,2962800),
 'START_VM2_US.DAT':(168848,1071408),
 'TXPPACK.DAT':(171712,13673168),
 'EBOOT.BIN':(32,1691904),
 'BOOT.BIN':(54128+128,1691556),
 'NISGFX.DAT':(164624,34896),
 'MODULE.DAT':(106384,17008),
 'DEBUG.DAT':(106304,4624),
 'CUTINPACK.DAT':(234160,441217),
}
for k,(l,s) in tbl.items(): ext(l,s,'D2DHD_kr/ext/'+k)
# check DIS2_PSP_DATA content
iso.seek(55088*2048); import hashlib
nz=0
for i in range(0,104857600,1<<20):
    b=iso.read(1<<20)
    if any(b): nz+=1
print("DIS2_PSP_DATA nonzero MB blocks:",nz)
