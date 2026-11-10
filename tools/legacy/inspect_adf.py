from pathlib import Path
import struct,os
b=Path('/mnt/data/Wings of Fury (1990)(Broderbund)[a].adf').read_bytes()
U=lambda d,o:struct.unpack_from('>I',d,o)[0]
root=880
out=Path('/mnt/data/wings_adf_files');out.mkdir(exist_ok=True)
files=[]; seen=set()
def walk(block,prefix=''):
 if block in seen:return
 seen.add(block)
 d=b[block*512:(block+1)*512]; name=d[433:433+d[432]].decode('latin1','replace');typ=U(d,508)
 if typ==2 or typ==1:
  if block!=root: prefix=prefix+name+'/'
  for off in range(24,312,4):
   child=U(d,off)
   count=0
   while child and count<100:
    walk(child,prefix)
    cd=b[child*512:(child+1)*512];child=U(cd,496);count+=1
 elif typ==0xfffffffd:
  size=U(d,324); ptr=U(d,16); data=bytearray();visited=set(); nums=[]
  while ptr and ptr not in visited and ptr<1760:
   visited.add(ptr); db=b[ptr*512:(ptr+1)*512];nums.append(ptr)
   if U(db,0)!=8:print('INVALID BLOCK',name,ptr,U(db,0));break
   data+=db[24:24+min(U(db,12),488)];ptr=U(db,16)
  if len(data)!=size: print('SIZE MISMATCH',prefix+name,size,len(data))
  loc=out/(prefix+name);loc.parent.mkdir(parents=True,exist_ok=True);loc.write_bytes(data[:size]);files.append((prefix+name,size,nums,data[:12]))
walk(root)
for n,s,bl,head in sorted(files):print(f'{s:>7} {n:45} {head.hex(" ")}')
print('TOTAL',len(files),'filebytes',sum(a[1] for a in files))
