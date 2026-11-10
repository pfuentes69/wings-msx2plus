from pathlib import Path
import struct,json
folder=Path('/mnt/data/wings_adf_files/Wings_of_Fury/shapes');out=Path('/mnt/data/wings_unpacked_shapes');out.mkdir(exist_ok=True)
results=[]
for f in sorted(folder.glob('*.shp')):
 b=f.read_bytes()
 if b[:4]==b'Rpck':
  target=struct.unpack_from('>I',b,4)[0];buf=bytearray();i=8
  while i<len(b) and len(buf)<target:
   ctrl=b[i];i+=1
   if ctrl>=128: count=256-ctrl;buf.extend(b[i:i+count]);i+=count
   elif ctrl>0:buf.extend(b[i:i+1]*(ctrl+1));i+=1
   else:buf.extend(b[i:i+1]);i+=1
  if len(buf)!=target: print('ERROR',f.name,len(buf),target);continue
  data=bytes(buf)
 else:data=b
 (out/(f.name+'.unpacked')).write_bytes(data)
 count=None
 if data[:4]==b'PPkc' and len(data)>=6:
  count=struct.unpack_from('>H',data,4)[0]
  if 6+8*count <=len(data):
   names=[data[6+i*4:10+i*4].decode('latin1','replace') for i in range(count)]
   offsets=[struct.unpack_from('>I',data,6+4*count+i*4)[0] for i in range(count)]
   root=out/f.stem;root.mkdir(exist_ok=True)
   base=6+8*count
   for j,(name,offset) in enumerate(zip(names,offsets)):
    end=offsets[j+1] if j+1<count else len(data)-base
    (root/(f'{j:03d}_{name}.bin')).write_bytes(data[base+offset:base+end])
   print(f.name,'count',count,'names',names[:8], 'last',names[-3:])
 results.append((f.name,len(b),len(data),count))
print('\nsummary')
for x in results:print(x)
