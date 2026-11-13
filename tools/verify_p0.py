"""Verify release controls, P1 takeoff/turns, menu flow, HUD and state on openMSX."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import statistics
import subprocess
from PIL import Image
from convert_dashboard import DASHBOARD_DIGITS, weapon_patch
from verify_world_flight import vram_image, expected_pixels
from aircraft_scene import AircraftScene

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine',default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--output',type=Path,default=ROOT/'tools/.build/p0-ntsc')
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
    (out/'verification.json').unlink(missing_ok=True)
    rom=ROOT/'out/mission-flight/mission-flight.rom';data=rom.read_bytes()
    symbols=dict((n,int(v,16)) for n,v in re.findall(r'DEF _(\w+) (0x[0-9A-Fa-f]+)',rom.with_suffix('.noi').read_text()))
    for name in ('Scenery_Read','Scenery_ReadEnd','Controls_Store','Input_Sample','Input_JoySample','VDP_InterruptHandler','VDP_HBlankHandler'):
        assert 0x4000<=symbols[name]<0x6000,(name,'must stay in fixed bank zero')
    assert symbols['g_TopPalette']>=0xc000 and symbols['g_BottomPalette']>=0xc000
    tables=(ROOT/'assets_msx/dashboard/bank_7.bin').read_bytes()
    assert data[7*8192:7*8192+len(tables)]==tables
    bank=(ROOT/'assets_msx/dashboard/bank_12.bin').read_bytes()
    assert data[12*8192:12*8192+len(bank)]==bank
    env=dict(os.environ,WINGS_ROOT=str(ROOT),WINGS_TEST_OUT=str(out),WINGS_HEADLESS='1' if args.headless else '0',
             OPENMSX_HOME=str(out/'openmsx-home'),SDL_AUDIODRIVER='dummy')
    env.setdefault('OPENMSX_USER_DATA',str(Path.home()/'.openMSX/share'))
    settings=[]
    if args.headless:
        config=out/'headless.xml';config.write_text('<?xml version="1.0"?><!DOCTYPE settings SYSTEM "settings.dtd"><settings><settings><setting id="renderer">none</setting><setting id="save_settings_on_exit">false</setting></settings></settings>')
        settings=['-setting',str(config)]
    with (out/'openmsx.log').open('w') as log:
        with subprocess.Popen([shutil.which('openmsx'),'-control','stdio',*settings,'-machine',args.machine,'-cart',str(rom),'-romtype','ASCII8',
                        '-script',str(ROOT/'tools/p0_smoke.tcl')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.PIPE) as emulator:
            try:
                assert emulator.wait(timeout=100)==0, 'openMSX failed'
            except subprocess.TimeoutExpired:
                emulator.kill(); emulator.wait(); raise
    assert rom.read_bytes()==data,'ROM changed during verification'
    report=(out/'emulator-report.txt').read_text();assert report.rstrip().endswith('PASS'),report[-3000:]
    snapshots={}
    scene=AircraftScene()
    terrain=json.loads((ROOT/'assets_msx/mission_a/manifest.json').read_text())
    for bank in (8,9,10,14):
        payload=(ROOT/f'assets_msx/hellcat/mission_bank_{bank}.bin').read_bytes()
        assert data[bank*8192:bank*8192+len(payload)]==payload,('aircraft bank',bank)
    for_bank=(ROOT/'assets_msx/ship/bank_13.bin').read_bytes()
    assert data[13*8192:13*8192+len(for_bank)]==for_bank
    for line in report.splitlines():
        if not line.startswith('snapshot '):continue
        _,name,page,world,y,pose,wave,heave,ship,camera=line.split();page=int(page)
        game=list((out/f'{name}.game').read_bytes());combat=(out/f'{name}.combat').read_bytes()
        assert (out/f'{name}.rom').read_bytes()==data[:32768],(name,'mapper restoration')
        vram=(out/f'{name}.vram').read_bytes()
        scale,wave_view,pilot=(out/f'{name}.view').read_bytes()
        stage,depth,lift_tick=(out/f'{name}.lift').read_bytes()
        crew=(out/f'{name}.crew').read_bytes()[0]
        projectiles=[]
        if game[0]==3:
            projectiles=[dict(zip(('x','y','vx','vy','life','kind'),struct.unpack_from('<HHbbBB',combat,i*8))) for i in range(18)]
            ground=stage!=1 or name.startswith(('taxi_','lift_')) or name in {'start','accelerating_roll','slow_roll','deck_0','deck_1','deck_2','ground_roll'}
            expected=expected_pixels(scene,int(pose),int(world),int(y),int(camera),
                (ROOT/'assets_msx/mission_a'/('far.indices' if scale==8 else 'scene.indices')).read_bytes(),
                terrain['far_width'] if scale==8 else terrain['width'],True,scale,int(wave),pilot,int(heave),int(ship),
                projectiles,game[4],game[3],game[2],crew,ground,depth,stage!=1)
            for row in range(212):
                for col in range(8,256):
                    ring=col if row>=172 else (int(camera)+col)%256
                    sy=row if row>=172 else (row-int(heave))%256
                    value=vram[page*32768+sy*128+ring//2]
                    value=(value>>(0 if ring%2 else 4))&15
                    assert value==expected[row][col],(name,'composite',col,row,value,expected[row][col])
        # Match actual HUD digits to portable state, including reversed colors.
        stock=f'{game[4]:02d}'
        for digit,x in zip(stock,(22,32)):
            for row,bits in enumerate(DASHBOARD_DIGITS[digit]):
                for col,bit in enumerate(bits):
                    at=page*32768+(196+row)*128+(x+col)//2
                    value=(vram[at]>>(0 if (x+col)&1 else 4))&15
                    assert value==(12 if bit=='1' else 15),(name,'stock',row,col,value)
        for row,bits in enumerate(DASHBOARD_DIGITS[str(game[2])]):
            for col,bit in enumerate(bits):
                x=53+col;at=page*32768+(196+row)*128+x//2
                assert ((vram[at]>>(0 if x&1 else 4))&15)==(12 if bit=='1' else 15),(name,'lives')
        icon=weapon_patch(game[3])
        for row in range(7):
            for col in range(22):
                x=18+col;at=page*32768+(186+row)*128+x//2
                assert ((vram[at]>>(0 if x&1 else 4))&15)==icon[row*22+col],(name,'weapon icon')
        palette=(ROOT/'assets_msx/mission_a/palette.bin').read_bytes()
        # Host reconstruction verifies readable source pixels; it is not raster proof.
        preview=vram_image(vram,palette,int(camera),page,True,int(heave))
        preview.save(out/f'{name}-vram.png')
        shots,secondary,impacts=struct.unpack_from('<HHH',combat,152)
        snapshots[name]=dict(phase=game[0],rank=game[1],lives=game[2],weapon=game[3],stock=game[4],invert=game[5],
                            stage=stage,depth=depth,crew=crew,scale=scale,pilot=pilot,camera=int(camera),world=int(world),y=int(y),pose=int(pose),wave=int(wave),heave=int(heave),ship=int(ship),
                            shots=shots,secondary=secondary,impacts=impacts,projectiles=projectiles)
        if not args.headless:
            assert Image.open(out/f'{name}.png').size==(320,240)
    required={'lift_paused','lift_pause_wait','lift_start','lift_rise_24','lift_rise_16','lift_rise_8','lift_left_down_8','lift_left_down_16','lift_left_down_24','lift_left_inside','service_left','lift_left_return','lift_right_down_8','lift_right_down_24','lift_right_inside','service_right','lift_right_return','accelerating_roll','slow_roll','deck_0','deck_1','deck_2','approach','climb_gear_up','rank','load_menu','briefing','rockets','torpedo','loadout','start','guns','aliases','short_press','paused',
              'pause_wait','inverted','resumed','no_debug','restart','ground_roll','takeoff','turn','turn_complete','compensated_turn','joystick_guns','joystick_secondary','joystick_inverted','in_game_load','in_game_save'}
    required|={f'cannon_{pitch}_{heading}' for pitch in ('stall','level','dive') for heading in ('left','right')}
    required|={'stall_held','stall_released','dive_released','dive_persistent','dive_recovered'}
    required|={f'taxi_right_{i}' for i in range(10)}|{f'taxi_left_{i}' for i in range(10,0,-1)}
    required|={'taxi_right_stop','taxi_right_hold','taxi_left_stop','taxi_left_hold'}
    assert required<=snapshots.keys(),required-snapshots.keys()
    assert (out/'paused.combat').read_bytes()==(out/'pause_wait.combat').read_bytes(),'Pause advanced weapons'
    for key in ('world','y','pose','wave','heave','ship','crew','depth','stage'):
        assert snapshots['paused'][key]==snapshots['pause_wait'][key],('Pause advanced',key)
    assert {snapshots[f'deck_{i}']['heave'] for i in range(3)}=={0,1,2}
    assert snapshots['start']['pose']==52 and snapshots['approach']['pose']==50
    assert snapshots['accelerating_roll']['pose']==52 and snapshots['slow_roll']['pose']==52 and snapshots['ground_roll']['pose']==50
    assert snapshots['takeoff']['pose'] not in (49,50)
    assert snapshots['stall_held']['pose']==43 and snapshots['stall_released']['pose']==16
    assert snapshots['dive_released']['pose']==snapshots['dive_persistent']['pose']==45
    assert snapshots['dive_persistent']['y']>snapshots['dive_released']['y']
    assert snapshots['dive_recovered']['pose']==16
    for heading in ('left','right'):
        for attitude in ('stall','level','dive'):
            snapshot=snapshots[f'cannon_{attitude}_{heading}']
            expected_pose={'left':{'stall':43,'level':16,'dive':45},'right':{'stall':3,'level':4,'dive':6}}[heading][attitude]
            assert snapshot['pose']==expected_pose,(heading,attitude,'aircraft pose',snapshot['pose'])
            rounds=[p for p in snapshot['projectiles'] if p['kind']==1]
            assert rounds,(heading,attitude,'no live shots')
            if attitude=='level':rounds=[max(rounds,key=lambda p:p['life'])]
            for p in rounds:
                assert (p['vx']<0)==(heading=='left'),(heading,attitude,p)
                assert p['vy']<0 if attitude=='stall' else p['vy']>0 if attitude=='dive' else p['vy']==0,(heading,attitude,p)
    taxi=scene.metadata['taxi_turn']
    for i in range(10):assert snapshots[f'taxi_right_{i}']['pose']==taxi[i]
    for i in range(10,0,-1):assert snapshots[f'taxi_left_{i}']['pose']==taxi[i]
    for direction,x in (('left',6617),('right',7336)):
        for suffix in ('stop','hold'):
            assert snapshots[f'taxi_{direction}_{suffix}']['world']==x
            assert snapshots[f'taxi_{direction}_{suffix}']['y']==1160
    assert snapshots['lift_start']['depth']==31
    assert snapshots['lift_left_inside']['depth']==snapshots['lift_right_inside']['depth']==32
    assert snapshots['lift_left_return']['pose']==52 and snapshots['lift_right_return']['pose']==51
    assert snapshots['service_left']['stock']==snapshots['service_right']['stock']==30
    elevator=(ROOT/'assets_msx/elevator/bank_15.bin').read_bytes()
    assert data[15*8192:15*8192+len(elevator)]==elevator
    for key in ('world','y','stage','depth','pose','stock','crew','wave','heave','ship'):
        assert snapshots['lift_paused'][key]==snapshots['lift_pause_wait'][key],('Lift pause',key)
    cadence=[tuple(map(float,line.split()[1:])) for line in report.splitlines() if line.startswith('lift_cadence ')]
    intervals=[i for i,r in cadence]
    median=statistics.median(intervals)
    assert abs(median-(120 if args.machine=='C-BIOS_MSX2+_EU' else 100))<2,('lift cadence',median)
    lift_timing=dict(presentation_vblanks=6,samples=len(cadence),median_publication_ms=median,
        max_regular_redraw_ms=max(r for i,r in cadence),simulation_ticks_per_pixel=18,travel_ticks=576)
    summary=dict(lift_timing=lift_timing,machine=args.machine,rom_sha256=hashlib.sha256(data).hexdigest(),raster_captured=not args.headless,
                 snapshots=snapshots,checks=['original elevator platform and hull occlusion at multiple depths','initial leftward emergence and two heading-preserving service cycles','primary/secondary elevator activation with held-confirmation consumption','real bomb expenditure then reload without a game reset','bidirectional taxi with five angular steps per quarter turn','both temporary deck end stops under sustained input','streamed ground-turn artwork and noncontiguous bank restoration','gear-down deck start and inbound approach; automatic retraction','full visible composite pixels including both original signalmen and deck heave','leftward deck roll and ordinary takeoff','simulation-driven turn and altitude loss','release boot and seven-rank/load shells','context edge consumption',
                    '30/15/1 stock previews and three lives','unlimited provisional guns do not spend secondary stock',
                    'N/GRAPH alias overlap and short press buffering','PSG-boundary injection of both joystick triggers and inversion','in-game save/load shells return without state mutation','Esc-only pause freezes gameplay clocks',
                    'Ctrl-F settings and Ctrl-R restart','release profile ignores debug R/T',
                    'cannon muzzle and shot direction follow nose-up, level and dive attitudes in both headings','HUD digit pixels match state','bank-zero ISR and RAM palettes','bank-12 asset/mapper restoration',
                    'hidden-page immutability','zero normal input overflows'])
    (out/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(f'PASS: P0/P1 {len(snapshots)} snapshots; {args.machine}')
if __name__=='__main__':main()
