<CsoundSynthesizer>

<CsOptions>
-d 
-o dac 
-i adc
-m0
--use-system-sr

</CsOptions>

<CsInstruments>
; sr     = 48000
ksmps  = 64
nchnls = 2
0dbfs  = 1
nchnls_i = 2

instr 1
  pset 0, 0, 0, 0.1, 1000, 0.1, 0.2, 0.5
  idur, iamp, ifreq, irise, idec, ipan passign 3
  kenv  linen iamp, irise, idur, idec
  asig  oscili kenv, ifreq
a1, a2    pan2      asig, ipan
  outs      a1, a2
endin
</CsInstruments>

<CsScore>
i 1 0 4 0.1 1000
f 0 14400
</CsScore>
</CsoundSynthesizer>

