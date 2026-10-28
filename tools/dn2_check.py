# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise core-dn2's six UI events with the hooks-check + DigiHealth build.

python tools/dn2_check.py LINK-MANIFEST.json OUTPUT-DIRECTORY
The manifest must be from this exact installed candidate. This changes the
active UI/parameters and arms hooks-check's TEMPO consumption until reboot.
No firmware, link maps or device captures belong in Git.
"""
import json
from pathlib import Path
import sys
import time
from digiusb import RemoteKeys, peek, screen


def check(diag, manifest, output):
    output=Path(output)
    output.mkdir(parents=True,exist_ok=True)
    symbols=manifest['_map']
    required=('hc_ticks','hc_keys','hc_encs','hc_selects','hc_pselects','hc_taken','hc_order_bad','hc_armed')
    if any(name not in symbols or not 0x47f00000 <= symbols[name] < 0x47f40000 for name in required):
        raise ValueError('requires the exact DN2 hooks-check link manifest')
    evidence=[]

    def value(name):
        return int.from_bytes(peek(diag,symbols[name],4),'big')

    def capture(name):
        generation,data=screen(diag)
        (output/(name+'.pbm')).write_bytes(data)
        evidence.append(dict(screen=name,frame=generation))
        return data

    def keys(sequence):
        with RemoteKeys(diag) as remote:
            if remote.product != 3: raise ValueError('requires Digitone II OS 1.12')
            for name in sequence.split(','): remote.tap(name,30)

    def main(): keys('NO,NO,NO')
    def settings_bottom():
        main();keys('SETTINGS,'+','.join(['DOWN']*16))
    def personalize_bottom():
        settings_bottom();keys('UP,UP,UP,UP,YES,'+','.join(['DOWN']*24))

    def require(condition,message):
        if not condition: raise AssertionError(message)
        evidence.append(dict(check=message,passed=True))
        (output/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')

    require(value('hc_armed')==0,'diagnostic starts unarmed')
    before=value('hc_ticks');capture('main');require(value('hc_ticks')>before,'ev_tick advances and ev_draw publishes frames')
    before=value('hc_keys');keys('1');require(value('hc_keys')-before==2,'TRIG 1 press/release pass through ev_key')
    before=value('hc_encs')
    with RemoteKeys(diag) as remote: remote.turn(1,2)
    # Completion is driver acceptance; wait/read for the independently counted UI event.
    deadline=time.monotonic()+3
    while value('hc_encs')==before and time.monotonic()<deadline: time.sleep(.02)
    require(value('hc_encs')>before,'encoder turn reaches ev_enc');capture('encoder')
    main();normal=capture('before-tempo');keys('TEMPO');tempo=capture('tempo-pass-through')
    # Ignore the diagnostic bars and the stock title bar; compare the lower 44 rows.
    def body(data): return data.splitlines()[22:]
    require(body(normal)!=body(tempo),'pass-through TEMPO opens a different stock page')
    keys('NO')
    before=value('hc_selects');settings_bottom();capture('settings-row');keys('YES')
    require(value('hc_selects')==before+1,'SETTINGS select callback runs')
    settings_bottom();capture('settings-reopened');keys('YES')
    require(value('hc_selects')==before+2,'SETTINGS callback survives reopening')
    before=value('hc_pselects');personalize_bottom();capture('personalize-row');keys('YES')
    require(value('hc_pselects')==before+1 and value('hc_armed')==1,'PERSONALIZE callback arms consumption')
    personalize_bottom();capture('personalize-reopened');keys('YES')
    require(value('hc_pselects')==before+2,'PERSONALIZE callback survives reopening')
    main();before=value('hc_taken');ordinary=value('hc_keys');normal=capture('before-consumed-tempo')
    keys('TEMPO');consumed=capture('consumed-tempo')
    require(body(normal)==body(consumed),'consumed TEMPO leaves the stock page unchanged')
    require(value('hc_taken')==before+2 and value('hc_keys')==ordinary,'consumed TEMPO press/release stop before the later key subscriber')
    require(value('hc_order_bad')==0,'key subscribers run in declared order')
    evidence.append(dict(final_ui='main; TEMPO consumed until reboot',limits='Review captured menus and stock parameter changes; acknowledgements alone do not prove them.'))
    (output/'result.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return evidence


def main():
    from digiusb import Diag
    if len(sys.argv)!=3: raise SystemExit(__doc__)
    if sys.platform=='win32': from winmidi import Port
    else: from midimido import Port
    port=Port()
    try: check(Diag(port),json.loads(Path(sys.argv[1]).read_text()),sys.argv[2])
    finally: port.close()
    print('core event checks passed; review the saved screen captures')

if __name__=='__main__': main()
