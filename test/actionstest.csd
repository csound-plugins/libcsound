<CsoundSynthesizer>
<CsOptions>
-odac 

</CsOptions>

<CsInstruments>
0dbfs = 1
ksmps = 64
nchnls = 2

instr 1
  kchan init -1
  kchan = (kchan + metro:k(1)) % nchnls
  if changed:k(kchan) == 1 then
    println "Channel: %d", kchan + 1
  endif
  asig = pinker() * 0.2
  outch kchan + 1, asig
endin

schedule 1, 0, 5
event_i "e", 5.01

</CsInstruments>

<CsScore>

</CsScore>
</CsoundSynthesizer>
