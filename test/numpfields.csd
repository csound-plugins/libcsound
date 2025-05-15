<CsoundSynthesizer>
<CsOptions>
-odac 
</CsOptions>

<CsInstruments>
sr     = 44100
ksmps  = 64
nchnls = 2
0dbfs  = 1

instr 10
  ; inumpfields = p4
  ipfields[] passign 4
  printarray ipfields
  turnoff
endin

</CsInstruments>

<CsScore>

i10 0 1 10 20 30 40 50

</CsScore>
</CsoundSynthesizer>
