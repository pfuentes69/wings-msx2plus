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
from verify_world_flight import vram_image, expected_pixels, gun_flash_shape, island_background, vram_row
from convert_dashboard import compose, layout, PILOT_WIDTH
from aircraft_scene import AircraftScene

ROOT=Path(__file__).resolve().parents[1]

def ticker_rows(island):
    """The message ticker's text as 12 rows of pixels (src/msx/message.c):
    the island's message with its bonus; the mission's last island appends
    "Good work ..." over the final full stop. Odd glyphs get a blank column."""
    from convert_font import glyphs, strings
    height, first, last, font = glyphs()
    msgs = strings()
    text = msgs['g_MessageCleared'].replace(b'%ld', str(struct.unpack_from('<H', island, 312)[0]).encode())
    if island[314]: text = text[:-1] + msgs['g_MessageMission']
    rows = [[] for _ in range(height)]
    for c in text:
        width, bits = font[c if first <= c <= last else first]
        for r in range(height): rows[r] += bits[r] + [0] * (width & 1)
    return text, rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--machine',default='Panasonic_FS-A1WX-512K')
    parser.add_argument('--headless',action='store_true')
    parser.add_argument('--no-fm',action='store_true',help='turn the MSX-MUSIC driver off: PSG-only sound')
    parser.add_argument('--record',type=Path,help="save the run's sound to this WAV file")
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
    env=dict(os.environ,WINGS_ROOT=str(ROOT),WINGS_TEST_OUT=str(out),WINGS_HEADLESS='1' if args.headless else '0',WINGS_NO_FM='1' if args.no_fm else '0',WINGS_RECORD=str(args.record.resolve()) if args.record else '',
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
    from convert_hellcat import aircraft_bank
    for bank in (aircraft_bank(s) for s in range((json.loads((ROOT/'assets_msx/hellcat/manifest.json').read_text())['animation']['pixel_bytes']+8191)//8192)):
        payload=(ROOT/f'assets_msx/hellcat/mission_bank_{bank}.bin').read_bytes()
        assert data[bank*8192:bank*8192+len(payload)]==payload,('aircraft bank',bank)
    for_bank=(ROOT/'assets_msx/ship/bank_13.bin').read_bytes()
    assert data[13*8192:13*8192+len(for_bank)]==for_bank
    for line in report.splitlines():
        if not line.startswith('snapshot '):continue
        _,name,page,world,y,pose,wave,heave,ship,camera=line.split();page=int(page)
        game=list((out/f'{name}.game').read_bytes());combat=(out/f'{name}.combat').read_bytes()
        assert (out/f'{name}.rom').read_bytes()==data[:32768],(name,'mapper restoration')
        # Colour 0 (the sky) is set once at boot and never by the ISR.
        terrain_palette=(ROOT/'assets_msx/mission_a/palette.bin').read_bytes()
        assert (out/f'{name}.palette').read_bytes()[:2]==terrain_palette[:2],(name,'sky colour 0',(out/f'{name}.palette').read_bytes()[:2])
        vram=(out/f'{name}.vram').read_bytes()
        # Tile cache: every loaded slot holds its strip's 8 tiles (ROM banks
        # from 32, 256 bytes a strip), as 64 rows of 4 bytes at rows 180..
        # of VRAM page 2 or 3.
        for slot,strip in enumerate((out/f'{name}.slots').read_bytes()):
            if strip==255: continue
            want=data[(32*8192)+strip*256:(32*8192)+strip*256+256]
            got=b''.join(vram[0x10000+((slot>>5)*256+180+row)*128+(slot&31)*4:][:4] for row in range(64))
            assert got==want,(name,'tile slot',slot,'strip',strip,[r for r in range(64) if got[r*4:r*4+4]!=want[r*4:r*4+4]][:8])
        fine=struct.unpack('b',(out/f'{name}.fine').read_bytes())[0]   # -1..7
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
            band,ticker=struct.unpack('<BH',(out/f'{name}.band').read_bytes())
            if band: _,text_rows=ticker_rows((out/f'{name}.island').read_bytes())
            raw=(out/f'{name}.smoke').read_bytes()
            smoke=[struct.unpack_from('<HhB',raw,1+5*i) for i in range(raw[0])]
            expected=expected_pixels(scene,int(pose),int(world),int(y),int(camera),
                island_background((ROOT/'assets_msx/mission_a'/('far.indices' if scale==8 else 'scene.indices')).read_bytes(),
                                  scale,(out/f'{name}.island').read_bytes()),
                terrain['far_width'] if scale==8 else terrain['width'],scale,int(wave),pilot,int(heave),int(ship),
                projectiles,game[4],game[3],game[2],crew,ground,depth,stage!=1,flash=combat[158],
                gauges=tuple((out/f'{name}.gauges').read_bytes()),crash=(out/f'{name}.crash').read_bytes()[0],
                wheel=wheel,gear=gear,deck_level=deck_level,rope=rope,facing_left=bool(flight[11]),
                smoke=[(x & 0xFFFF,row,frame) for x,row,frame in smoke],
                score=struct.unpack('<I',(out/f'{name}.score').read_bytes())[0],fine=fine,band=band)
            for row in range(212):
                for col in range(8,256):
                    if row<band:
                        # The ticker: text pixel ticker at the right edge.
                        ring=(ticker+1+col)%256;sy=row;p=ticker-255+col
                        want=11 if 1<=row<=12 and 0<=p<len(text_rows[0]) and text_rows[row-1][p] else 0
                    else:
                        ring=col if row>=172 else (int(camera)+col)%256
                        sy=row if row>=172 else vram_row(row,fine,int(heave))
                        want=expected[row][col]
                    value=vram[page*32768+sy*128+ring//2]
                    value=(value>>(0 if ring%2 else 4))&15
                    assert value==want,(name,'composite',col,row,value,want,band)
        # The HUD (ammo, lives, weapon, gauges) is part of the full-VRAM
        # comparison above for gameplay. Menus keep the dashboard too: check
        # it in every phase (the pilot window shows the last flight profile).
        # The PSG driver (src/msx/sound.c): port A stays input for the
        # joysticks, port B output; no engine or guns outside a sortie.
        psg=(out/f'{name}.psg').read_bytes()
        assert psg[7]&0xc0==0x80,(name,'PSG mixer port bits',hex(psg[7]))
        if game[0]!=3: assert psg[8]==0 and psg[9]==0,(name,'sound outside a sortie',list(psg[8:11]))
        # MSX-MUSIC: both test machines have it, so the driver runs unless
        # turned off; the engine then plays there (silent outside a sortie)
        # and the PSG's engine channel stays quiet.
        fm=(out/f'{name}.fm').read_bytes()
        assert fm[0]==(0 if args.no_fm else 1),(name,'FM driver',fm[0])
        if fm[0]:
            assert psg[8]==0,(name,'PSG engine with FM',psg[8])
            if game[0]!=3: assert fm[1+0x30]&15==15 and fm[1+0x31]&15==15,(name,'FM engine outside a sortie',fm[1+0x30:1+0x32].hex())
        gauges=tuple((out/f'{name}.gauges').read_bytes())
        assert all(g<=22 for g in gauges[:2]) and gauges[2]<=3,(name,'gauge state',gauges)
        score=struct.unpack('<I',(out/f'{name}.score').read_bytes())[0]
        hud=compose(ammo=game[4],weapon=game[3],lives=game[2],oil=gauges[0],fuel=gauges[1],
                    oil_lamp=bool(gauges[2]&1),fuel_lamp=bool(gauges[2]&2),score=min(score,999999))
        spots=layout()
        for row in range(40):
            for col in range(8,256):
                if spots['pilot_y']<=row<spots['pilot_y']+24 and spots['pilot_x']<=col<spots['pilot_x']+PILOT_WIDTH:continue
                value=(vram[page*32768+(172+row)*128+col//2]>>(0 if col&1 else 4))&15
                assert value==hud[row*256+col],(name,'dashboard',col,172+row,value,hud[row*256+col])
        palette=(ROOT/'assets_msx/mission_a/palette.bin').read_bytes()
        # Host reconstruction verifies readable source pixels; it is not raster proof.
        preview=vram_image(vram,palette,int(camera),page,int(heave),fine)
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
    required|={'island_bombed','pan_high','pan_mid'}
    required|={'deck_smoke_live','deck_smoke_cleared'}
    required|={'island_soldiers','island_cleared'}
    # P4: back on the carrier with the mission complete, the next mission.
    required|={'return_arrest','return_landed','mission_briefing','mission_two'}
    assert snapshots['mission_briefing']['phase']==1 and snapshots['mission_two']['phase']==3,('next mission',snapshots['mission_briefing']['phase'],snapshots['mission_two']['phase'])
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
    assert sea['world']>7900 and sea['camera']==sea['world']-128+40,('open sea, camera 40 ahead',sea['world'],sea['camera'])
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
    assert struct.unpack('<I',(out/'engine_smoke.score').read_bytes())[0]==20160
    # Close-view pan steps over the carrier can run 1-3 VBlanks long (the
    # block move covers the tower); they are counted apart from missed frames.
    tolerated=[l for l in report.splitlines() if l.startswith('tolerated_miss ')]
    print(f'tolerated misses (island bomb burst): {len(tolerated)}', *tolerated)
    overruns=int(next(l.split()[1] for l in report.splitlines() if l.startswith('pan_overruns ')))
    assert overruns<=16,('pan step overruns',overruns)
    print(f'pan step overruns: {overruns}')
    # P3: the bombed hut at 2392 is wrecked (the one at 2712 and the dugouts
    # may be too): 150 a hut, 200 a manned dugout.
    island=(out/'island_bombed.island').read_bytes()
    score=struct.unpack('<I',(out/'island_bombed.score').read_bytes())[0]
    assert island[3]==1 and island[0]==0 and island[1]==5,('wrecked hut',list(island[:8]))
    assert score==150*sum(island[8*i+3] for i in range(2))+200*sum(island[64+8*i]==0 for i in range(2)),('island score',score)
    assert snapshots['island_bombed']['smoke']>=1
    # Soldiers (frames 23..42 of the smoke path): a walker, the dying and a corpse.
    raw=(out/'island_soldiers.smoke').read_bytes()
    drawn={raw[1+5*i+4] for i in range(raw[0])}
    assert drawn&set(range(23,28)) and drawn&set(range(28,32)) and 40 in drawn,('soldier frames',sorted(drawn))   # dying 28..30, or his corpse 31
    # The flag (0x3b52) waves over the island until it is cleared (0x3f5e):
    # then the bonus (450 for island A, the only one: the mission is
    # complete) and the ticker at the top with the executable's messages.
    assert drawn&{43,44,45},('flag cloth',sorted(drawn))
    before=(out/'island_soldiers.island').read_bytes();cleared=(out/'island_cleared.island').read_bytes()
    raw=(out/'island_cleared.smoke').read_bytes()
    assert not {raw[1+5*i+4] for i in range(raw[0])}&{43,44,45},'flag cloth after the clear'
    assert cleared[309]==1 and cleared[310]==0 and cleared[311]==0 and struct.unpack_from('<H',cleared,312)[0]==450 and cleared[314]==1,('island cleared',cleared[302:315].hex())
    gained=struct.unpack('<I',(out/'island_cleared.score').read_bytes())[0]-struct.unpack('<I',(out/'island_soldiers.score').read_bytes())[0]
    assert gained>=450+25,('clear bonus',gained)
    band,ticker=struct.unpack('<BH',(out/'island_cleared.band').read_bytes())
    text,_=ticker_rows(cleared)
    assert band>=15 and ticker>=300 and text.startswith(b'All enemy forces on island have been destroyed . . . Bonus 450 points . . Good work !'),(band,ticker,text)
    print(f'ticker: {text.decode()!r}, band {band}, at pixel {ticker}')
    # Smoke over the signalmen and the elevator is drawn, then fully erased.
    assert snapshots['deck_smoke_live']['smoke']>=4 and snapshots['deck_smoke_cleared']['smoke']==0
    # Dugout guns (0x4f5c): the run passes the right dugout at low altitude.
    assert struct.unpack_from('<H',island,160)[0]>=1,('ground-fire hits',island[136:162].hex())
    # The close-view pan, with the carrier in view and a bomb falling.
    for name,low,high in (('pan_high',45,55),('pan_mid',14,32)):
        snapshot=snapshots[name]
        assert snapshot['scale']==1 and low<=1200-snapshot['y']-131<=high,(name,snapshot['y'])
        assert snapshot['camera']+256>6592 and snapshot['camera']<7368,(name,'carrier not in view',snapshot['camera'])
    assert any(p['kind'] in (2,3,4) for p in snapshots['pan_mid']['projectiles'][2:]),'no bomb in the panned view'
    # Sound: the engine drones in flight (tone period 2.24 x the original's
    # Paula period, 335..~1100), the cannon rattles on channel B (noise),
    # the lift's motor grinds there (tone 1200 and noise), and the run hears
    # bomb bursts, splashes, the lift's clang and the cable's screech.
    for name in [k for k in snapshots if k.startswith('cannon_')]:
        psg=(out/f'{name}.psg').read_bytes()
        fm=(out/f'{name}.fm').read_bytes()
        if fm[0]:
            # Two channels a few % apart, block 2, keyed on; fnum 131,700 / P.
            for ch in (0,1):
                fnum=fm[1+0x10+ch]|(fm[1+0x20+ch]&1)<<8
                assert fm[1+0x20+ch]&0x1e==0x14 and 120<=fnum<=470 and fm[1+0x30+ch]>>4==0 and fm[1+0x30+ch]&15<=8,(name,'FM engine',ch,fm[1+0x10:1+0x12].hex(),fm[1+0x20:1+0x22].hex(),fm[1+0x30:1+0x32].hex())
            assert fm[1+0x0e]&0x20,(name,'FM rhythm mode',hex(fm[1+0x0e]))
        else:
            tone=psg[0]|(psg[1]&15)<<8
            assert psg[8]>=6 and 700<=tone<=2600 and not psg[7]&1,(name,'engine',psg[8],tone,hex(psg[7]))
        assert not psg[7]&0x10,(name,'cannon rattle',hex(psg[7]))
    for name in ('lift_rise_24','lift_rise_16','lift_left_down_8','lift_left_down_16','lift_right_down_8'):
        psg=(out/f'{name}.psg').read_bytes()
        assert not psg[7]&0x12 and psg[2]|psg[3]<<8==1200,(name,'lift grind',hex(psg[7]),list(psg[2:4]))
    heard={int(l.split()[1]) for l in report.splitlines() if l.startswith('sound ')}
    print('effects heard:',sorted(heard))
    assert {2,3,4,5}<=heard,('effects heard',sorted(heard))
    for heading in ('left','right'):
        for attitude in ('climb','level','dive'):
            snapshot=snapshots[f'cannon_{attitude}_{heading}']
            expected_pose={'left':{'climb':(41,),'level':(16,),'dive':(45,46,47)},'right':{'climb':(1,),'level':(4,),'dive':(6,7,8)}}[heading][attitude]
            assert snapshot['pose'] in expected_pose,(heading,attitude,'aircraft pose',snapshot['pose'])
            # The original draws a per-pose flash/tracer overlay, not travelling rounds.
            assert snapshot['flash'] in (1,2),(heading,attitude,'no cannon flash overlay')
            assert gun_flash_shape(scene,snapshot['pose'],snapshot['flash']),(heading,attitude,'no overlay for pose')
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
                 snapshots=snapshots,checks=['original elevator platform and hull occlusion at multiple depths','initial leftward emergence and two heading-preserving service cycles','primary/secondary elevator activation with held-confirmation consumption','real bomb expenditure then reload without a game reset','turning round on the deck at rest in both directions, in place','streamed ground-turn artwork and noncontiguous bank restoration','gear down near the carrier in either direction; original wheel overlays on every pose, sliding up and down','open sea past the map end with the camera leading the plane by 40 px','arresting rope drawn from the caught cable to the hook during the arrest','engine smoke from a damaged engine, erased by repainting terrain','six-digit score field drawn from the glyphs','full visible composite pixels including both original signalmen and deck heave','original flight model (12.5 Hz): deck roll, tail up, rolling off the bow and climbing away','original turn: height lost, regained by climbing through the turn','stall flare keeps airspeed and sinks nose up; a Down tap starts a held dive','release boot and seven-rank/load shells','context edge consumption',
                    '30/15/1 stock previews and three lives','unlimited provisional guns do not spend secondary stock',
                    'N/GRAPH alias overlap and short press buffering','PSG-boundary injection of both joystick triggers and inversion','in-game save/load shells return without state mutation','Esc-only pause freezes gameplay clocks',
                    'Ctrl-F settings and Ctrl-R restart','release profile ignores debug R/T',
                    'cannon muzzle and shot direction follow climb, level and dive attitudes in both headings','HUD digit pixels match state','bank-zero ISR and RAM palettes','bank-12 asset/mapper restoration',
                    'hidden-page immutability','zero normal input overflows'])
    (out/'verification.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(f'PASS: P0/P1 {len(snapshots)} snapshots; {args.machine}')
if __name__=='__main__':main()
