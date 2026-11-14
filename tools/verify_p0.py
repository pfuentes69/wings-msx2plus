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
from verify_world_flight import vram_image, expected_pixels, gun_flash_shape
from convert_dashboard import compose, layout, PILOT_WIDTH
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
    for number in (12,17,18,19,20):
        bank=(ROOT/f'assets_msx/dashboard/bank_{number}.bin').read_bytes()
        assert data[number*8192:number*8192+len(bank)]==bank,('dashboard bank',number)
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
                assert emulator.wait(timeout=400)==0, 'openMSX failed'
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
            # On the deck (flight byte 12: 0 deck, 2 cable arrest; 1 flying, 3 engine
            # out) or riding the elevator.
            flight=(out/f'{name}.flight').read_bytes()
            ground=stage!=1 or flight[12] in (0,2)
            # Level on the deck (rolling fast, byte 17, or held by a cable).
            deck_level=stage==1 and (flight[12]==2 or (flight[12]==0 and flight[17]!=0))
            wheel,gear,rope=(out/f'{name}.wheel').read_bytes()
            raw=(out/f'{name}.smoke').read_bytes()
            smoke=[struct.unpack_from('<HhB',raw,1+5*i) for i in range(raw[0])]
            expected=expected_pixels(scene,int(pose),int(world),int(y),int(camera),
                (ROOT/'assets_msx/mission_a'/('far.indices' if scale==8 else 'scene.indices')).read_bytes(),
                terrain['far_width'] if scale==8 else terrain['width'],scale,int(wave),pilot,int(heave),int(ship),
                projectiles,game[4],game[3],game[2],crew,ground,depth,stage!=1,flash=combat[158],
                gauges=tuple((out/f'{name}.gauges').read_bytes()),crash=(out/f'{name}.crash').read_bytes()[0],
                wheel=wheel,gear=gear,deck_level=deck_level,rope=rope,facing_left=bool(flight[11]),
                smoke=[(x & 0xFFFF,row,frame) for x,row,frame in smoke])
            for row in range(212):
                for col in range(8,256):
                    ring=col if row>=172 else (int(camera)+col)%256
                    sy=row if row>=172 else (row-int(heave))%256
                    value=vram[page*32768+sy*128+ring//2]
                    value=(value>>(0 if ring%2 else 4))&15
                    assert value==expected[row][col],(name,'composite',col,row,value,expected[row][col])
        # The HUD (ammo, lives, weapon, gauges) is part of the full-VRAM
        # comparison above for gameplay. Menus keep the dashboard too: check
        # it in every phase (the pilot window shows the last flight profile).
        gauges=tuple((out/f'{name}.gauges').read_bytes())
        assert all(g<=22 for g in gauges[:2]) and gauges[2]<=3,(name,'gauge state',gauges)
        hud=compose(ammo=game[4],weapon=game[3],lives=game[2],oil=gauges[0],fuel=gauges[1],
                    oil_lamp=bool(gauges[2]&1),fuel_lamp=bool(gauges[2]&2))
        spots=layout()
        for row in range(40):
            for col in range(8,256):
                if spots['pilot_y']<=row<spots['pilot_y']+24 and spots['pilot_x']<=col<spots['pilot_x']+PILOT_WIDTH:continue
                value=(vram[page*32768+(172+row)*128+col//2]>>(0 if col&1 else 4))&15
                assert value==hud[row*256+col],(name,'dashboard',col,172+row,value,hud[row*256+col])
        palette=(ROOT/'assets_msx/mission_a/palette.bin').read_bytes()
        # Host reconstruction verifies readable source pixels; it is not raster proof.
        preview=vram_image(vram,palette,int(camera),page,int(heave))
        preview.save(out/f'{name}-vram.png')
        shots,secondary,impacts=struct.unpack_from('<HHH',combat,152)
        snapshots[name]=dict(phase=game[0],rank=game[1],lives=game[2],weapon=game[3],stock=game[4],invert=game[5],
                            stage=stage,depth=depth,crew=crew,scale=scale,pilot=pilot,camera=int(camera),world=int(world),y=int(y),pose=int(pose),wave=int(wave),heave=int(heave),ship=int(ship),
                            shots=shots,secondary=secondary,impacts=impacts,projectiles=projectiles,flash=combat[158],
                            wheel=(out/f'{name}.wheel').read_bytes()[0],gear=(out/f'{name}.wheel').read_bytes()[1],
                            rope=(out/f'{name}.wheel').read_bytes()[2],smoke=(out/f'{name}.smoke').read_bytes()[0])
        if not args.headless:
            assert Image.open(out/f'{name}.png').size==(320,240)
    required={'lift_paused','lift_pause_wait','lift_start','lift_rise_24','lift_rise_16','lift_rise_8','lift_left_down_8','lift_left_down_16','lift_left_down_24','lift_left_inside','service_left','lift_left_return','lift_right_down_8','lift_right_down_24','lift_right_inside','service_right','lift_right_return','accelerating_roll','slow_roll','deck_0','deck_1','deck_2','approach','open_sea_right','rank','load_menu','briefing','rockets','torpedo','loadout','start','guns','aliases','short_press','paused',
              'pause_wait','inverted','resumed','no_debug','restart','ground_roll','takeoff','turn','turn_complete','compensated_turn','joystick_guns','joystick_secondary','joystick_inverted','in_game_load','in_game_save'}
    required|={f'cannon_{pitch}_{heading}' for pitch in ('climb','level','dive') for heading in ('left','right')}
    required|={'stall_held','stall_released','dive_released','dive_persistent','dive_recovered'}
    required|={'taxi_right_stop','taxi_left_stop'}
    required|={'engine_low_fuel','engine_smoke','engine_failed','engine_next_plane','game_over'}
    required|={'landed','landed_service','deck_bounce','sea_splash','sea_crash_next','engine_splash','arrest'}
    assert required<=snapshots.keys(),required-snapshots.keys()
    assert (out/'paused.combat').read_bytes()==(out/'pause_wait.combat').read_bytes(),'Pause advanced weapons'
    for key in ('world','y','pose','wave','heave','ship','crew','depth','stage'):
        assert snapshots['paused'][key]==snapshots['pause_wait'][key],('Pause advanced',key)
    assert {snapshots[f'deck_{i}']['heave'] for i in range(3)}=={0,1,2}
    # Shape ids: 0..9 pitch poses facing right (4 level), 10..39 air-turn
    # frames, 40..48 left pitch poses (16 = hc28 is level left), 51/52 tail
    # down right/left. Wheel sprites: (left ? 10 : 0) + pitch, 255 none.
    assert snapshots['start']['pose']==52 and snapshots['start']['wheel']==255
    assert snapshots['approach']['pose']==4 and snapshots['approach']['wheel']==4 and snapshots['approach']['gear']==5
    assert snapshots['accelerating_roll']['pose']==52 and snapshots['slow_roll']['pose']==52
    assert snapshots['ground_roll']['pose']==16 and snapshots['ground_roll']['wheel']==14
    sea=snapshots['open_sea_right']
    assert sea['world']>7900 and sea['camera']==sea['world']-128,('open sea',sea['world'],sea['camera'])
    assert 6609<snapshots['ground_roll']['world']<7032
    assert snapshots['takeoff']['pose'] not in (49,50,51,52) and snapshots['takeoff']['world']<6593
    assert 10<=snapshots['turn']['pose']<40
    assert snapshots['stall_held']['pose']==43 and snapshots['stall_released']['pose']==16
    assert snapshots['dive_released']['pose']==snapshots['dive_persistent']['pose'] in (44,45,46)
    assert snapshots['dive_persistent']['y']>snapshots['dive_released']['y']
    assert snapshots['dive_recovered']['pose']==16
    assert snapshots['landed']['y']==1160 and 7038<snapshots['landed']['world']<7345
    assert snapshots['arrest']['rope'] in (0,1,2,3) and snapshots['landed']['rope']==255
    assert snapshots['engine_smoke']['smoke']>=2 and snapshots['start']['smoke']==0
    for heading in ('left','right'):
        for attitude in ('climb','level','dive'):
            snapshot=snapshots[f'cannon_{attitude}_{heading}']
            expected_pose={'left':{'climb':41,'level':16,'dive':46},'right':{'climb':1,'level':4,'dive':7}}[heading][attitude]
            assert snapshot['pose']==expected_pose,(heading,attitude,'aircraft pose',snapshot['pose'])
            # The original draws a per-pose flash/tracer overlay, not travelling rounds.
            assert snapshot['flash'] in (1,2),(heading,attitude,'no cannon flash overlay')
            assert gun_flash_shape(scene,expected_pose,snapshot['flash']),(heading,attitude,'no overlay for pose')
            strikes=[p for p in snapshot['projectiles'][:2] if p['kind'] in (3,4)]
            if attitude!='dive':assert not strikes,(heading,attitude,'level/climbing fire struck the surface')
            for p in strikes:
                assert (p['x']//4<snapshot['world'])==(heading=='left'),(heading,attitude,p)
    # Turning round on the deck at rest: the captured poses walk the taxi
    # sequence in order (left rest 0 .. front 5 .. right rest 10), in place.
    taxi=scene.metadata['taxi_turn']
    for direction,step in (('right',1),('left',-1)):
        seen=[snapshots[k]['pose'] for k in sorted((k for k in snapshots if k.startswith(f'taxi_{direction}_') and k[len(f'taxi_{direction}_'):].isdigit()),
                                                    key=lambda k:int(k.rsplit('_',1)[1]))]
        assert len(seen)>=4 and all(p in taxi[1:10] for p in seen),(direction,seen)
        order=[taxi.index(p) for p in seen]
        assert all((b-a)*step>0 for a,b in zip(order,order[1:])),(direction,order)
        stop=snapshots[f'taxi_{direction}_stop']
        assert stop['world']==7032 and stop['y']==1160 and stop['pose']==(51 if direction=='right' else 52)
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
                 snapshots=snapshots,checks=['original elevator platform and hull occlusion at multiple depths','initial leftward emergence and two heading-preserving service cycles','primary/secondary elevator activation with held-confirmation consumption','real bomb expenditure then reload without a game reset','turning round on the deck at rest in both directions, in place','streamed ground-turn artwork and noncontiguous bank restoration','gear down near the carrier in either direction; original wheel overlays on every pose, sliding up and down','open sea past the map end with the camera centred on the plane','arresting rope drawn from the caught cable to the hook during the arrest','engine smoke from a damaged engine, erased by repainting terrain','full visible composite pixels including both original signalmen and deck heave','original flight model (12.5 Hz): deck roll, tail up, rolling off the bow and climbing away','original turn: height lost, regained by climbing through the turn','stall flare keeps airspeed and sinks nose up; a Down tap starts a held dive','release boot and seven-rank/load shells','context edge consumption',
                    '30/15/1 stock previews and three lives','unlimited provisional guns do not spend secondary stock',
                    'N/GRAPH alias overlap and short press buffering','PSG-boundary injection of both joystick triggers and inversion','in-game save/load shells return without state mutation','Esc-only pause freezes gameplay clocks',
                    'Ctrl-F settings and Ctrl-R restart','release profile ignores debug R/T',
                    'cannon muzzle and shot direction follow climb, level and dive attitudes in both headings','HUD digit pixels match state','bank-zero ISR and RAM palettes','bank-12 asset/mapper restoration',
                    'hidden-page immutability','zero normal input overflows'])
    (out/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(f'PASS: P0/P1 {len(snapshots)} snapshots; {args.machine}')
if __name__=='__main__':main()
