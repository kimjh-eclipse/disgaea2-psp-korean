import struct
def swizzle(data,rowbytes,h):
    out=bytearray(len(data)); i=0
    for by in range(h//8):
        for bx in range(rowbytes//16):
            for y in range(8):
                src=(by*8+y)*rowbytes+bx*16
                out[i:i+16]=data[src:src+16]; i+=16
    return bytes(out)
def unswizzle(data,rowbytes,h):
    out=bytearray(len(data)); i=0
    for by in range(h//8):
        for bx in range(rowbytes//16):
            for y in range(8):
                dst=(by*8+y)*rowbytes+bx*16
                out[dst:dst+16]=data[i:i+16]; i+=16
    return bytes(out)
def decode(d):
    w,h,ncol16,z,cs,pb,sw,mip=struct.unpack('<HHHHHHHH',d[:16])
    ncol=16*pb
    pal=[tuple(d[0x10+i*4:0x10+i*4+4]) for i in range(ncol)]
    pxoff=0x10+ncol*4
    px=unswizzle(d[pxoff:pxoff+w*h//2],w//2,h)
    # 4bpp indices
    idx=bytearray(w*h)
    for i,b in enumerate(px):
        idx[i*2]=b&0xf; idx[i*2+1]=b>>4
    return dict(w=w,h=h,pal=pal,idx=idx,hdr=d[:16])
def encode(w,h,pal,idx,hdr_extra=(16,0,16,1,1,1)):
    ncol=len(pal)
    hdr=struct.pack('<HHHHHHHH',w,h,hdr_extra[0],hdr_extra[1],hdr_extra[2],hdr_extra[3],hdr_extra[4],hdr_extra[5])
    p=b''.join(bytes(c) for c in pal)
    px=bytearray(w*h//2)
    for i in range(0,w*h,2):
        px[i//2]=(idx[i]&0xf)|((idx[i+1]&0xf)<<4)
    return hdr+p+swizzle(bytes(px),w//2,h)
