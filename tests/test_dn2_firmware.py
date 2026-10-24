# SPDX-License-Identifier: GPL-2.0-or-later
"""Compiled DN2 USB/UI checks with the Rust firmware emulator, without a device.

DN2_TEST_SYX and DN2_TEST_MAP select a built core + DigiHealth + hooks-check
candidate and its exact link manifest. DN2_BRIDGE names sysex_bridge.
DN2_TEST_OUT retains captures/replies, otherwise temporary. Missing inputs skip.
Build from this checkout and the companion Elekloader branch before running.
"""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
import digiusb as usb
from dn2_check import check


class Firmware(unittest.TestCase):
    def test_sources_and_router_abi(self):
        names=('DN2_TEST_SYX','DN2_TEST_MAP','DN2_BRIDGE')
        if any(not os.environ.get(n) for n in names): self.skipTest('missing '+', '.join(names))
        panel=Path(os.environ['DN2_BRIDGE']).with_name('panel_drive')
        if not panel.is_file(): self.skipTest('missing panel_drive beside sysex_bridge')
        manifest=json.loads(Path(os.environ['DN2_TEST_MAP']).read_text())
        entry=manifest['_map']['core_sysex']
        for source in (2,4,8,16):
            result=subprocess.run([str(panel),os.environ['DN2_TEST_SYX'],
                '--base','7e5b8a733d4ab1fdf7e5d22757f7d8eddaa3cbf71d0858874a791844c02ceb35',
                '--call-at','0x4002e464','--call-fn','0x4012194e','--call-args',str(source),
                '--capture','0x401236d2:0:1','--regs-at',f'{entry:#x},0x40121980',
                '--steps','send:'+usb.req_caps(1).hex()+',peek:0x445a2e30:7'],
                text=True,capture_output=True,check=True)
            report=json.loads(result.stdout)
            self.assertEqual(bool(report['captures']),source in (2,4))
            self.assertEqual(report['results'][-1]['hex'],'00000000000000')
            before,after=report['regs'][:2]
            self.assertEqual(before['d'],after['d'])
            self.assertEqual(before['a'][:3],after['a'][:3])
            self.assertEqual(before['a'][4:7],after['a'][4:7])
            self.assertEqual(after['a'][3],'0x40207f9e')

    def test_settings_toggle_and_disabled_input(self):
        names=('DN2_TEST_SYX','DN2_TEST_MAP','DN2_BRIDGE')
        if any(not os.environ.get(n) for n in names): self.skipTest('missing '+', '.join(names))
        panel=Path(os.environ['DN2_BRIDGE']).with_name('panel_drive')
        if not panel.is_file(): self.skipTest('missing panel_drive')
        manifest=json.loads(Path(os.environ['DN2_TEST_MAP']).read_text())
        steps=['tap:8']+['tap:14']*16+['tap:11','tap:11','tap:10','wait:200M',
            'send:'+usb.req_stats(1).hex(),'tap:14','tap:10',
            'send:'+usb.req_caps(2).hex(),'send:'+usb.req_metrics(3).hex(),
            'send:'+usb.req_frame(4).hex(),
            f"peek:{manifest['_map']['rk_off']:#x}:4",'peek:0x445a2e30:7']
        result=subprocess.run([str(panel),os.environ['DN2_TEST_SYX'],
            '--base','7e5b8a733d4ab1fdf7e5d22757f7d8eddaa3cbf71d0858874a791844c02ceb35',
            '--call-at','0x4002e464','--call-fn','0x4012194e','--call-args','2',
            '--capture','0x401236d2:0:1','--steps',','.join(steps)],
            text=True,capture_output=True,check=True)
        report=json.loads(result.stdout)
        replies=[usb.parse(bytes.fromhex(row['hex'])) for row in report['captures']]
        self.assertEqual([r['seq'] for r in replies],[1,2,3,4])
        self.assertTrue(usb.decode_stats(replies[0]['payload'])['overlay'])
        self.assertEqual((replies[1]['status'],replies[1]['payload']),(6,b''))
        self.assertEqual(usb.decode_metrics(replies[2]['payload'])['version'],1)
        self.assertEqual((replies[3]['status'],len(replies[3]['payload'])),(0,1028))
        self.assertEqual(report['results'][-2]['hex'],'01000000')
        self.assertEqual(report['results'][-1]['hex'],'00000000000000')
        if os.environ.get('DN2_TEST_OUT'):
            (Path(os.environ['DN2_TEST_OUT'])/'settings-off.json').write_text(json.dumps(report,indent=2)+'\n')

    def test_usb_and_core_events(self):
        names=('DN2_TEST_SYX','DN2_TEST_MAP','DN2_BRIDGE')
        if any(not os.environ.get(n) for n in names): self.skipTest('missing '+', '.join(names))
        with tempfile.TemporaryDirectory() as temp:
            out=Path(os.environ.get('DN2_TEST_OUT',temp));out.mkdir(parents=True,exist_ok=True)
            with (out/'emulator.stderr').open('w') as log:
                proc=subprocess.Popen([os.environ['DN2_BRIDGE'],os.environ['DN2_TEST_SYX'],
                    '--base','7e5b8a733d4ab1fdf7e5d22757f7d8eddaa3cbf71d0858874a791844c02ceb35',
                    '--call-at','0x4002e464','--call-fn','0x4012194e','--call-args','2',
                    '--capture','0x401236d2:0:1','--settle','40M'],
                    stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
                self.assertTrue(json.loads(proc.stdout.readline())['ready'])
                sent=[]
                class Port:
                    drop=None
                    def send(self,data):
                        sent.append(usb.unpack7(data[6:-1]))
                        proc.stdin.write(bytes(data).hex()+'\n');proc.stdin.flush()
                        reply=json.loads(proc.stdout.readline())
                        if reply['error']: raise RuntimeError(reply)
                        self.messages=[bytes.fromhex(x) for x in reply['replies']]
                        if self.drop==sent[-1][2]: self.messages=[];self.drop=None
                    def receive(self,seconds=1,until=None):
                        messages=self.messages;self.messages=[]
                        if until:until(messages)
                        return messages
                port=Port();diag=usb.Diag(port)
                try:
                    hello=usb.decode_hello(diag.call(usb.req_hello))
                    self.assertEqual((hello['proto'],hello['name']),(1,'digihealth 1.4'))
                    self.assertEqual(usb.decode_metrics(diag.call(usb.req_metrics))['version'],1)
                    self.assertEqual(usb.peek(diag,0x40000400,4),bytes.fromhex('400004e8'))
                    generation,pbm=usb.screen(diag)
                    self.assertGreater(generation,0);self.assertTrue(pbm.startswith(b'P1\n128 64\n'))
                    with usb.RemoteKeys(diag) as remote:
                        self.assertEqual(remote.product,3)
                        port.drop=usb.ACTION
                        before=len(sent);remote.turn(1,-1)
                        self.assertEqual(sum(row[2]==usb.ACTION for row in sent[before:]),1)
                        # Bad encoders/deltas are refused before any operation is sent.
                        for encoder,delta in ((0,1),(10,1),(1,0),(1,-31),(1,31)):
                            before=len(sent)
                            with self.assertRaises(ValueError):remote.turn(encoder,delta)
                            self.assertEqual(len(sent),before)
                        for encoder,delta in ((0,1),(10,1),(1,0),(1,31),(1,65505)):
                            with self.assertRaisesRegex(ValueError,'refused'):
                                diag.call(usb.req_action,remote.session,remote.operation+1,usb.TURN,encoder,delta)
                    manifest=json.loads(Path(os.environ['DN2_TEST_MAP']).read_text())
                    check(diag,manifest,out/'core-events')
                    # Deadline cleanup is observable separately from action acknowledgements.
                    with usb.RemoteKeys(diag) as remote:
                        remote.press('FUNC',300)
                        for _ in range(5):diag.call(usb.req_hello)
                        status=remote.status()
                        self.assertEqual((status['state'],status['owned'],status['cleanup']),('expired',0,0))
                    # All nine bounded encoder routes produce their own core events.
                    def count(name): return int.from_bytes(usb.peek(diag,manifest['_map'][name],4),'big')
                    before=count('hc_encs')
                    for encoder in range(1,10):
                        with usb.RemoteKeys(diag) as remote:
                            remote.turn(encoder,1)
                            remote.turn(encoder,-1)
                    self.assertGreaterEqual(count('hc_encs')-before,18)
                    # Each mapped press reaches the independent stock state table.
                    self.assertEqual(len(usb.MAPS[3]),54)
                    for name,(code,group,mask) in usb.MAPS[3].items():
                        with usb.RemoteKeys(diag) as remote:
                            remote.press(name)
                            self.assertTrue(usb.peek(diag,manifest['_map']['fw_key_state']+group,1)[0]&mask,name)
                            self.assertEqual(count('hc_last_code'),code,name)
                            remote.release(name)
                        self.assertEqual(usb.peek(diag,manifest['_map']['fw_key_state']+group,1)[0]&mask,0,name)
                    stats=usb.decode_stats(diag.call(usb.req_stats))
                    self.assertEqual(stats['layout'],1)
                    self.assertGreater(stats['heap_free'],0)
                    self.assertFalse(stats['fast']);self.assertNotIn('dsp',stats)
                    (out/'stats.json').write_text(json.dumps(stats,indent=2)+'\n')
                finally:
                    proc.stdin.close();proc.wait(timeout=10);proc.stdout.close()
                self.assertEqual(proc.returncode,0)
                (out/'requests.json').write_text(json.dumps([r.hex() for r in sent],indent=2)+'\n')

if __name__=='__main__': unittest.main()
