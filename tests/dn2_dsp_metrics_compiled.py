# SPDX-License-Identifier: GPL-2.0-or-later
"""Inject only an emulator test trampoline; execute the actual ColdFire decoder."""
import binascii
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

firmware, manifest_path, panel, output, cross = sys.argv[1:]
out = Path(output)
out.mkdir(parents=True, exist_ok=True)
root = Path(__file__).resolve().parents[1]
objects = Path(os.environ.get('DN2_TEST_OBJECTS', root/'out/digihealth.work'))
manifest = json.loads(Path(manifest_path).read_text())['_map']
symbols = {}
for line in subprocess.check_output([cross+'nm', '-n', str(objects/'sysinfo.s.o')], text=True).splitlines():
    p = line.split()
    if len(p) == 3: symbols[p[2]] = int(p[0], 16)
base = manifest['dn2_clock'] + symbols['tx'] - symbols['dn2_clock']
# The helper's unused TX buffer is large enough for this bounded test only.
source = '''typedef unsigned U;
extern void dhs_block(U,U);
extern void dhs_read(U *);
void probe(const U *input,U bytes) {
 U sr,i;
 __asm__ volatile ("move.w %%sr,%0\\n\\tmove.w #0x2700,%%sr" : "=d"(sr) : : "memory");
 for(i=0;i<bytes/8;++i) dhs_block(input[2*i],input[2*i+1]);
 dhs_read((U *)OUTPUT);
 __asm__ volatile ("move.w %0,%%sr" : : "d"(sr) : "memory");
}
'''.replace('OUTPUT', hex(base+0x300))
(out/'probe.c').write_text(source)
for cmd in ([cross+'gcc', '-mcpu=54455', '-msoft-float', '-ffreestanding', '-fno-builtin',
             '-fno-pic', '-O2', '-c', '-o', str(out/'probe.o'), str(out/'probe.c')],
            [cross+'ld', f'-Ttext={base:#x}', '-e', 'probe',
             '--defsym', f"dhs_block={manifest['dhs_block']:#x}",
             '--defsym', f"dhs_read={manifest['dhs_read']:#x}",
             '-o', str(out/'probe.elf'), str(out/'probe.o')],
            [cross+'objcopy', '-O', 'binary', str(out/'probe.elf'), str(out/'probe.bin')]):
    subprocess.run(cmd, check=True)
probe = (out/'probe.bin').read_bytes()
assert len(probe) < 0x200
payload = struct.pack('>8I',0x44485331,17,0,17000,1000,1234,1,0)
halves = struct.unpack('>16H',payload)+(binascii.crc_hqx(payload,0xffff),)
packet = [0xd6200000 | (i<<16) | half for i,half in enumerate(halves)]
crc = packet.copy(); crc[-1] ^= 1
torn = packet.copy(); torn[6] = (torn[6] & 0xffff0000) | (torn[7] & 0xffff)
gap = packet[:5]+packet[6:]
cases = [('complete',packet,3), ('missing',[0]*100,0),
         ('frozen',packet+[packet[-1]]*65,2),
         ('replayed',packet+[packet[-1]]*65+packet,2),
         ('expired-word0',packet[:1]+[packet[0]]*65+packet[1:],0),
         ('crc',crc,0), ('torn',torn,0), ('gap',gap,0)]
results = []
for name,words,flags in cases:
    data = b''.join(struct.pack('>II',word,100+i) for i,word in enumerate(words))
    steps = [f'poke:{base:#x}:{probe.hex()}', 'send:'+data.hex(), f'peek:{base+0x300:#x}:64']
    cmd = [panel, firmware, '--base','7e5b8a733d4ab1fdf7e5d22757f7d8eddaa3cbf71d0858874a791844c02ceb35',
           '--after','10M','--call-at','0x4002e464','--call-fn',f'{base:#x}','--steps',','.join(steps)]
    done = subprocess.run(cmd, text=True, capture_output=True)
    (out/(name+'.json')).write_text(done.stdout)
    (out/(name+'.stderr')).write_text(done.stderr)
    assert done.returncode == 0, (name,done.returncode,done.stderr)
    report = json.loads(done.stdout)
    decoded = struct.unpack('>16I', bytes.fromhex(report['results'][-1]['hex']))
    assert decoded[0:2] == (0x44484331,0x10040)
    assert decoded[2] == flags, (name,decoded)
    if name in ('complete','frozen','replayed'):
        assert decoded[6:12] == (17,0,17000,1000,1234,1)
        assert decoded[12] == 1
    if name in ('crc','torn'): assert decoded[13] > 0
    results.append({'case':name,'flags':flags,'accepted':decoded[12],
                    'crc_errors':decoded[13],'dropped':decoded[14]})
(out/'summary.json').write_text(json.dumps({'status':'PASS','cases':results,
    'scope':'actual compiled ColdFire decoder; synthetic words/trampoline only in emulator memory'},indent=2)+'\n')
print('PASS compiled ColdFire decoder:',len(results),'positive/negative cases')
