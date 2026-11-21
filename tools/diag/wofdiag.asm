; Wings of Fury MSX2+ - hardware/loader diagnostic ROM (ASCII8)
; Build: python3 tools/build_diag.py  (docs/diag-rom.md)
;
; A 512 KiB (or 256 KiB) ASCII8 ROM laid out like the game: code in bank 0
; at 4000h, every 8 KiB bank tagged in its last 4 bytes ('W', n, ~n, '8').
; It prints each step's name before doing it, so the last line on screen
; tells where a freeze happened. Text mode through the BIOS only.
	.module	wofdiag

CHPUT	= 0x00A2
INITXT	= 0x006C
ENASLT	= 0x0024
RDSLT	= 0x000C
MSXVER	= 0x002D
LINL40	= 0xF3AE
FORCLR	= 0xF3E9
BAKCLR	= 0xF3EA
BDRCLR	= 0xF3EB
BOTTOM	= 0xFC48
HIMEM	= 0xFC4A
EXPTBL	= 0xFCC1
SLTTBL	= 0xFCC5
HKEYI	= 0xFD9A
HTIMI	= 0xFD9F
JIFFY	= 0xFC9E

; Locals, on the stack (IX): no fixed RAM is touched before the IM2 step.
F_IDS	= 0	; 4: the bank seen in windows 0..3 (FF: no tag)
F_ROMSLOT = 4
F_P3SLOT = 5
F_A8	= 6
F_W	= 7	; window under test
F_V	= 8	; bank written
F_M	= 9	; method 0=LD (nn),A 1=LD (HL),A 2=MegaRAM-style
F_CNT	= 10
F_BAD	= 11
F_SPL	= 12
F_SPH	= 13
F_EXP	= 14	; 4: expected ids
F_FM	= 18
F_TMP	= 19
F_BOOT	= 20	; 4: ids at boot
F_P	= 24
F_S	= 25
FRAME	= 32

	.area	CODE (ABS)
	.org	0x4000
	.db	0x41, 0x42
	.dw	init, 0, 0, 0, 0, 0, 0
nbanks:	.db	64		; patched by tools/build_diag.py
	.ascii	"WOFDIAG1"

init:
	di
	ld	hl, #0
	add	hl, sp
	ex	de, hl			; DE = SP at entry
	ld	hl, #-FRAME
	add	hl, sp
	ld	sp, hl
	push	hl
	pop	ix
	ld	F_SPL(ix), e
	ld	F_SPH(ix), d

	; Slot of page 1 (this ROM), the way the game's startup finds it.
	in	a, (0xA8)
	ld	F_A8(ix), a
	rrca
	rrca
	and	#3
	ld	c, a
	ld	hl, #EXPTBL
	add	a, l
	ld	l, a
	ld	a, (hl)
	and	#0x80
	or	c
	ld	c, a
	inc	hl
	inc	hl
	inc	hl
	inc	hl
	ld	a, (hl)
	and	#0x0C
	or	c
	ld	F_ROMSLOT(ix), a

	; Slot of page 3 (the RAM the game uses).
	ld	a, F_A8(ix)
	rlca
	rlca
	and	#3
	ld	c, a
	ld	hl, #EXPTBL
	add	a, l
	ld	l, a
	ld	a, (hl)
	and	#0x80
	or	c
	ld	c, a
	inc	hl
	inc	hl
	inc	hl
	inc	hl
	ld	a, (hl)
	rrca
	rrca
	rrca
	rrca
	and	#0x0C
	or	c
	ld	F_P3SLOT(ix), a

	; Page 2 = this ROM, as the game does; then the banks as found.
	ld	a, F_ROMSLOT(ix)
	ld	h, #0x80
	call	ENASLT
	call	read_ids
	ld	a, F_IDS+0(ix)
	ld	F_BOOT+0(ix), a
	ld	a, F_IDS+1(ix)
	ld	F_BOOT+1(ix), a
	ld	a, F_IDS+2(ix)
	ld	F_BOOT+2(ix), a
	ld	a, F_IDS+3(ix)
	ld	F_BOOT+3(ix), a

	ld	a, #40
	ld	(LINL40), a
	ld	a, #15
	ld	(FORCLR), a
	ld	a, #4
	ld	(BAKCLR), a
	ld	(BDRCLR), a
	call	INITXT

step1:
	; --- line 1: version, VDP
	call	prt
	.asciz	"WOF DIAG 2 BANKS "
	ld	a, (nbanks)
	call	pdec
	call	prt
	.asciz	" MSXVER "
	ld	a, (MSXVER)
	call	phex
	call	prt
	.asciz	" VDP "
	di
	ld	a, #1
	out	(0x99), a
	ld	a, #0x8F
	out	(0x99), a
	in	a, (0x99)
	ld	b, a
	xor	a
	out	(0x99), a
	ld	a, #0x8F
	out	(0x99), a
	ld	a, b
	rrca
	and	#0x1F
	call	phex
	call	nl

step2:
	; --- line 2: slots
	call	prt
	.asciz	"ROM SLOT "
	ld	a, F_ROMSLOT(ix)
	call	phex
	call	prt
	.asciz	" P3 SLOT "
	ld	a, F_P3SLOT(ix)
	call	phex
	call	prt
	.asciz	" A8 "
	ld	a, F_A8(ix)
	call	phex
	call	nl

step3:
	; --- line 3: memory
	call	prt
	.asciz	"HIMEM "
	ld	hl, (HIMEM)
	call	phex16
	call	prt
	.asciz	" BOTTOM "
	ld	hl, (BOTTOM)
	call	phex16
	call	prt
	.asciz	" SP "
	ld	l, F_SPL(ix)
	ld	h, F_SPH(ix)
	call	phex16
	call	nl

step4:
	; --- line 4: memory mapper ports
	call	prt
	.asciz	"MAPPER"
	ld	c, #0xFC
1$:	call	sp1
	in	a, (c)
	call	phex
	inc	c
	jr	nz, 1$
	call	prt
	.asciz	" TIMI "
	ld	a, (HTIMI)
	call	phex
	call	prt
	.asciz	" KEYI "
	ld	a, (HKEYI)
	call	phex
	call	nl

step6:
	; --- line 6: banks at boot
	call	prt
	.asciz	"BOOT BANKS  "
	ld	a, F_BOOT+0(ix)
	ld	F_IDS+0(ix), a
	ld	a, F_BOOT+1(ix)
	ld	F_IDS+1(ix), a
	ld	a, F_BOOT+2(ix)
	ld	F_IDS+2(ix), a
	ld	a, F_BOOT+3(ix)
	ld	F_IDS+3(ix), a
	call	pids
	call	nl

step7:
	; --- the switching tests (windows 1..3; code runs in window 0)
	call	prt
	.asciz	"BASE 1 2 3  "
	call	base
	ld	b, #0
	ld	c, #0
	ld	a, #0		; method 0 with window 0 = 'expect the base'
	call	expect
	call	result

	call	prt
	.asciz	"A W1 15     "
	ld	b, #0
	ld	c, #1
	ld	a, #0x15
	call	dotest
	call	prt
	.asciz	"A W2 2A     "
	ld	b, #0
	ld	c, #2
	ld	a, #0x2A
	call	dotest
	call	prt
	.asciz	"A W3 3F     "
	ld	b, #0
	ld	c, #3
	ld	a, #0x3F
	call	dotest

	call	prt
	.asciz	"B W1 15     "
	ld	b, #1
	ld	c, #1
	ld	a, #0x15
	call	dotest
	call	prt
	.asciz	"B W2 2A     "
	ld	b, #1
	ld	c, #2
	ld	a, #0x2A
	call	dotest
	call	prt
	.asciz	"B W3 3F     "
	ld	b, #1
	ld	c, #3
	ld	a, #0x3F
	call	dotest

	call	prt
	.asciz	"C 8000 2A   "
	ld	b, #2
	ld	c, #2
	ld	a, #0x2A
	call	dotest
	call	prt
	.asciz	"C A000 3F   "
	ld	b, #2
	ld	c, #3
	ld	a, #0x3F
	call	dotest

step8:
	; --- every bank in each window (method A)
	call	prt
	.asciz	"SCAN"
	ld	c, #1
scan_w:	ld	F_W(ix), c
	call	prt
	.asciz	" W"
	ld	a, F_W(ix)
	add	a, #'0'
	call	CHPUT
	call	sp1
	xor	a
	ld	F_CNT(ix), a
	ld	F_BAD(ix), #0xFF
	ld	F_V(ix), a
scan_b:	ld	a, F_V(ix)
	ld	c, F_W(ix)
	call	selA
	call	read_ids
	call	id_w
	cp	F_V(ix)
	jr	nz, 1$
	inc	F_CNT(ix)
	jr	2$
1$:	ld	a, F_BAD(ix)
	inc	a
	jr	nz, 2$
	ld	a, F_V(ix)
	ld	F_BAD(ix), a
2$:	inc	F_V(ix)
	ld	a, (nbanks)
	cp	F_V(ix)
	jr	nz, scan_b
	call	base
	ld	a, F_CNT(ix)
	call	pdec
	ld	a, F_BAD(ix)
	inc	a
	jr	z, 3$
	ld	a, #'@'
	call	CHPUT
	ld	a, F_BAD(ix)
	call	phex
3$:	ld	c, F_W(ix)
	inc	c
	ld	a, c
	cp	#4
	jr	nz, scan_w
	call	nl

step9:
	; --- the cost of a switch: 32 switches of window 3, timed in frames
	; (0 on a real mapper; a loader that copies 8 KiB per switch takes ~2)
	call	prt
	.asciz	"SPEED 32 SWITCHES: FRAMES "
	ei
	halt
	ld	hl, (JIFFY)
	push	hl
	ld	b, #32
1$:	push	bc
	ld	a, b
	and	#0x1F
	add	a, #0x20
	ld	c, #3
	call	selA
	pop	bc
	djnz	1$
	ld	hl, (JIFFY)
	pop	de
	or	a
	sbc	hl, de
	call	base
	ld	a, h
	or	a
	ld	a, l
	jr	z, 2$
	ld	a, #255
2$:	call	pdec
	call	nl

step10:
	; --- MSX-MUSIC ("OPLL" at 401Ch of some slot)
	call	prt
	.asciz	"FM "
	ld	F_FM(ix), #0xFF
	ld	F_P(ix), #0
fm_p:	ld	a, F_P(ix)
	ld	hl, #EXPTBL
	add	a, l
	ld	l, a
	ld	a, (hl)
	and	#0x80
	or	F_P(ix)
	ld	F_TMP(ix), a	; base slot id
	ld	F_S(ix), #0
fm_s:	ld	a, F_S(ix)
	rlca
	rlca
	or	F_TMP(ix)
	ld	e, a
	call	chkfm
	jr	nz, 1$
	ld	F_FM(ix), e
	jr	fm_done
1$:	bit	7, F_TMP(ix)
	jr	z, 2$
	inc	F_S(ix)
	ld	a, F_S(ix)
	cp	#4
	jr	nz, fm_s
2$:	inc	F_P(ix)
	ld	a, F_P(ix)
	cp	#4
	jr	nz, fm_p
fm_done:
	ei
	ld	a, F_FM(ix)
	inc	a
	jr	nz, 3$
	call	prt
	.asciz	"NONE"
	jr	4$
3$:	call	prt
	.asciz	"SLOT "
	ld	a, F_FM(ix)
	call	phex
4$:	call	nl

step11:
	; --- the game's interrupt setup: IM2 table at C000h, ISR at C1C1h
	call	prt
	.asciz	"IM2 AT C000: INTS "
	di
	ld	hl, #0xC000
	ld	(hl), #0xC1
	ld	de, #0xC001
	ld	bc, #256
	ldir
	ld	hl, #isr2
	ld	de, #0xC1C1
	ld	bc, #isr2_end-isr2
	ldir
	xor	a
	ld	(0xC1F0), a
	ld	a, #0xC0
	ld	i, a
	im	2
	ei
	call	wait1s
	di
	im	1
	ld	a, (0xC1F0)
	ei
	call	pdec
	call	nl
	call	prt
	.asciz	"IM2 A W3 3F "
	ld	b, #0
	ld	c, #3
	ld	a, #0x3F
	call	dotest

step12:
	; --- the game's variables fill C000h..EFB4h: fill that RAM with HALT
	; (76h) and let the BIOS interrupt run its hooks for a second. Anything
	; resident there (a loader's helper) freezes here or shows as changed.
	call	prt
	.asciz	"RAM C000-"
	ld	l, F_SPL(ix)
	ld	h, F_SPH(ix)
	ld	de, #-0x100
	add	hl, de
	ld	a, h
	cp	#0xF0
	jr	c, 1$
	ld	hl, #0xF000
1$:	ld	a, h
	cp	#0xC4
	jr	nc, 2$
	call	prt
	.asciz	" SKIP (SP LOW)"
	jp	ram_done
2$:	push	hl
	dec	hl
	call	phex16
	call	prt
	.asciz	" FILL.. "
	pop	hl
	push	hl
	ld	de, #0xC000
	or	a
	sbc	hl, de
	ld	b, h
	ld	c, l
	dec	bc
	di
	ld	hl, #0xC000
	ld	(hl), #0x76
	ld	de, #0xC001
	ldir
	ei
	call	wait1s
	pop	de			; DE = end
	ld	hl, #0xC000
	ld	bc, #0
3$:	ld	a, (hl)
	cp	#0x76
	jr	z, 4$
	inc	bc
4$:	inc	hl
	ld	a, h
	cp	d
	jr	nz, 3$
	ld	a, l
	cp	e
	jr	nz, 3$
	call	prt
	.asciz	"CHG "
	ld	h, b
	ld	l, c
	call	phex16
ram_done:
	call	nl
	call	prt
	.asciz	"RAM A W3 3F "
	ld	b, #0
	ld	c, #3
	ld	a, #0x3F
	call	dotest

patchdump:
	call	prt
	.asciz	"P68"
	ld	hl, #pA1
	call	p3bytes
	call	prt
	.asciz	" P70"
	ld	hl, #pA2
	call	p3bytes
	call	prt
	.asciz	" P78"
	ld	hl, #pA3
	call	p3bytes
	call	nl
	; the first call/jump target among them, 10 bytes from there
	ld	hl, #pA3
	call	target
	jr	z, 1$
	ld	hl, #pA1
	call	target
	jr	z, 1$
	call	prt
	.asciz	"NO CALL/JP"
	jr	3$
1$:	push	de
	ex	de, hl
	call	phex16
	ld	a, #':'
	call	CHPUT
	pop	hl
	ld	b, #10
2$:	call	sp1
	ld	a, (hl)
	call	phex
	inc	hl
	djnz	2$
3$:	call	nl
	call	prt
	.asciz	"DONE - PLEASE SEND A PHOTO"
	di
9$:	jr	9$

;------------------------------------------------------------------------------
; dotest: B = method, C = window, A = bank. Prints ids and the verdict.
dotest:
	ld	F_M(ix), b
	ld	F_W(ix), c
	ld	F_V(ix), a
	call	expect
	ld	a, F_M(ix)
	ld	c, F_W(ix)
	or	a
	jr	nz, 1$
	ld	a, F_V(ix)
	call	selA
	jr	3$
1$:	dec	a
	jr	nz, 2$
	ld	a, F_V(ix)
	call	selB
	jr	3$
2$:	ld	a, F_V(ix)
	call	selC
3$:	call	result
	jp	base

; expect: expected = 00 01 02 03, window C = A (not for method 2 or C=0).
expect:
	ld	F_EXP+0(ix), #0
	ld	F_EXP+1(ix), #1
	ld	F_EXP+2(ix), #2
	ld	F_EXP+3(ix), #3
	ld	e, a
	ld	a, b
	cp	#2
	ret	z
	ld	a, c
	or	a
	ret	z
	push	ix
	pop	hl
	ld	a, #F_EXP
	add	a, c
	ld	c, a
	ld	b, #0
	add	hl, bc
	ld	(hl), e
	ret

; result: read the windows, print them and ok/BAD against the expectation.
result:
	call	read_ids
	call	pids
	ld	a, F_IDS+0(ix)
	cp	F_EXP+0(ix)
	jr	nz, 1$
	ld	a, F_IDS+1(ix)
	cp	F_EXP+1(ix)
	jr	nz, 1$
	ld	a, F_IDS+2(ix)
	cp	F_EXP+2(ix)
	jr	nz, 1$
	ld	a, F_IDS+3(ix)
	cp	F_EXP+3(ix)
	jr	nz, 1$
	call	prt
	.asciz	" ok"
	jp	nl
1$:	call	prt
	.asciz	" BAD"
	jp	nl

; base: windows 1..3 = banks 1, 2, 3 (canonical ASCII8 writes).
base:
	ld	a, #1
	ld	(0x6800), a
	inc	a
	ld	(0x7000), a
	inc	a
	ld	(0x7800), a
	ret

; selA: bank A into window C with LD (nnnn),A (the form loaders patch).
; pA1..pA3 are read back by the PATCH line: what the loader put there.
selA:
	dec	c
	jr	nz, selA_2
pA1:	ld	(0x6800), a
	ret
selA_2:	dec	c
	jr	nz, selA_3
pA2:	ld	(0x7000), a
	ret
selA_3:
pA3:	ld	(0x7800), a
	ret

; selB: the same through LD (HL),A (the game's Scenery_Read/Terrain_InitPage).
selB:
	ld	hl, #0x6800
	dec	c
	jr	z, 1$
	ld	hl, #0x7000
	dec	c
	jr	z, 1$
	ld	hl, #0x7800
1$:	ld	(hl), a
	ret

; selC: a write to the window itself (8000h/A000h): switches on MegaRAM,
; does nothing on a real ASCII8 mapper.
selC:
	ld	hl, #0x8000
	dec	c
	dec	c
	jr	z, 1$
	ld	hl, #0xA000
1$:	ld	(hl), a
	ret

; read_ids: the tag in each window's last 4 bytes -> IDS[0..3] (FF if none).
read_ids:
	push	ix
	pop	hl
	ld	de, #0x5FFC
	ld	b, #4
1$:	push	de
	ld	a, (de)
	cp	#'W'
	jr	nz, 2$
	inc	de
	ld	a, (de)
	ld	c, a
	inc	de
	ld	a, (de)
	cpl
	cp	c
	jr	nz, 2$
	inc	de
	ld	a, (de)
	cp	#'8'
	jr	nz, 2$
	ld	a, c
	jr	3$
2$:	ld	a, #0xFF
3$:	ld	(hl), a
	inc	hl
	pop	de
	ld	a, d
	add	a, #0x20
	ld	d, a
	djnz	1$
	ret

; id_w: A = IDS[F_W]
id_w:
	push	ix
	pop	hl
	ld	e, F_W(ix)
	ld	d, #0
	add	hl, de
	ld	a, (hl)
	ret

; pids: the four ids, "--" for none.
pids:
	push	ix
	pop	hl
	ld	b, #4
1$:	ld	a, (hl)
	inc	a
	jr	nz, 2$
	call	prt
	.asciz	"--"
	jr	3$
2$:	dec	a
	call	phex
3$:	call	sp1
	inc	hl
	djnz	1$
	ret

; chkfm: Z if slot E has "OPLL" at 401Ch.
chkfm:
	ld	hl, #0x401C
	ld	bc, #opll
1$:	push	bc
	push	de
	push	hl
	ld	a, e
	call	RDSLT
	pop	hl
	pop	de
	pop	bc
	ld	d, a
	ld	a, (bc)
	cp	d
	ret	nz
	inc	hl
	inc	bc
	ld	a, l
	cp	#0x20
	jr	nz, 1$
	ret
opll:	.ascii	"OPLL"

; wait1s: about one second on a 3.58 MHz Z80 (2 x 65536 x 26 T).
wait1s:
	ld	d, #2
	ld	bc, #0
1$:	dec	bc
	ld	a, b
	or	c
	jr	nz, 1$
	dec	d
	jr	nz, 1$
	ret

; The IM2 test's interrupt routine (copied to C1C1h).
isr2:	push	af
	in	a, (0x99)
	ld	a, (0xC1F0)
	inc	a
	ld	(0xC1F0), a
	pop	af
	ei
	reti
isr2_end:

; target: Z and DE = HL = address if HL points at CALL nn / JP nn.
target:
	ld	a, (hl)
	cp	#0xCD
	jr	z, 1$
	cp	#0xC3
	ret	nz
1$:	inc	hl
	ld	e, (hl)
	inc	hl
	ld	d, (hl)
	ex	de, hl
	ld	d, h
	ld	e, l
	xor	a
	ret

; p3bytes: " xx xx xx" from HL
p3bytes:
	ld	b, #3
1$:	call	sp1
	ld	a, (hl)
	call	phex
	inc	hl
	djnz	1$
	ret

; prt: print the zero-terminated string that follows the call.
prt:	ex	(sp), hl
1$:	ld	a, (hl)
	inc	hl
	or	a
	jr	z, 2$
	call	CHPUT
	jr	1$
2$:	ex	(sp), hl
	ret

phex16:	ld	a, h
	call	phex
	ld	a, l
phex:	push	af
	rrca
	rrca
	rrca
	rrca
	call	1$
	pop	af
1$:	and	#0x0F
	add	a, #0x90
	daa
	adc	a, #0x40
	daa
	jp	CHPUT

; pdec: A as three decimal digits.
pdec:	push	bc
	ld	b, #100
	call	1$
	ld	b, #10
	call	1$
	add	a, #'0'
	call	CHPUT
	pop	bc
	ret
1$:	ld	c, #'0'-1
2$:	inc	c
	sub	b
	jr	nc, 2$
	add	a, b
	push	af
	ld	a, c
	call	CHPUT
	pop	af
	ret

sp1:	ld	a, #' '
	jp	CHPUT
nl:	ld	a, #13
	call	CHPUT
	ld	a, #10
	jp	CHPUT
code_end:
