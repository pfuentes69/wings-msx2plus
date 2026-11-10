from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
import struct, math
src=Path('/mnt/data/wings_adf_files/Wings_of_Fury/shapes');dest=Path('/mnt/data/wings_previews');dest.mkdir(exist_ok=True)
def be16(b,o=0):return struct.unpack_from('>H',b,o)[0]
def be32(b,o=0):return struct.unpack_from('>I',b,o)[0]
def unpack_br1(data,size):
 o=bytearray();i=0
 while i<len(data) and len(o)<size:
  n=data[i];i+=1
  if n<128:
   o.extend(data[i:i+n+1]);i+=n+1
  elif n>128:
   o.extend(data[i:i+1]*(257-n));i+=1
 return o
def iff_img(p):
 b=p.read_bytes(); assert b[:4]==b'FORM' and b[8:12]==b'ILBM'
 off=12;chunks={}
 while off+8<=len(b):
  key=b[off:off+4];n=be32(b,off+4);chunks.setdefault(key,b[off+8:off+8+n]);off+=8+n+(n%2)
 bm=chunks[b'BMHD']; w,h,x,y,planes,mask,comp,pad,trans=struct.unpack_from('>HHhhBBBBH',bm);rowbytes=((w+15)//16)*2
 cmap=chunks.get(b'CMAP',b'');palette=[tuple(cmap[i:i+3]) for i in range(0,len(cmap),3)]
 if len(palette)==0:palette=[(v,v,v) for v in range(0,256,16)]
 need=h*rowbytes*(planes+(1 if mask==1 else 0)); raw=unpack_br1(chunks[b'BODY'],need) if comp==1 else chunks[b'BODY'];
 if len(raw)<need:raise ValueError(f'{p.name} {w}x{h} {planes} bpl {comp} output {len(raw)}/{need}')
 pixels=bytearray(w*h);off=0
 for yy in range(h):
  rows=[]
  for pp in range(planes+(1 if mask==1 else 0)):
   rows.append(raw[off:off+rowbytes]);off+=rowbytes
  for xx in range(w):
   pixels[yy*w+xx]=sum(((rows[pp][xx//8]>>(7-xx%8))&1)<<pp for pp in range(planes))
 im=Image.frombytes('P',(w,h),bytes(pixels));pal=[]
 for c in palette:pal+=list(c)
 pal=pal[:768]+[0]*(768-len(pal[:768]));im.putpalette(pal)
 return im.convert('RGB'),{'width':w,'height':h,'planes':planes,'compression':comp,'mask':mask,'colors':len(palette)}
images=[]
for p in sorted(src.iterdir()):
 if p.read_bytes()[:12].endswith(b'ILBM'):
  try:
   im,meta=iff_img(p);name=p.name.replace('.','_'); im.save(dest/(name+'.png'));images.append((p.name,im,meta));print(p.name,meta)
  except Exception as e:print('ERROR',p.name,str(e))
width=1100;cellw=350; cellh=255; out=Image.new('RGB',(width,math.ceil(len(images)/3)*cellh),'#ddd');draw=ImageDraw.Draw(out)
for i,(name,img,m) in enumerate(images):
 x=(i%3)*365+12;y=(i//3)*cellh+8;draw.text((x,y),name,fill='black');draw.text((x,y+16),str(m),fill='#333');scale=min((cellw-12)/img.width,205/img.height,3);img=img.resize((max(1,int(img.width*scale)),max(1,int(img.height*scale))),Image.Resampling.NEAREST);out.paste(img,(x,y+41))
out.save('/mnt/data/wings_iff_contact_sheet.png')
print('saved',len(images),'contact sheet')
