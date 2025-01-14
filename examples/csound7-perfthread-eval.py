import libcsound
import time
import queue

assert libcsound.VERSION >= 7000

cs = libcsound.Csound()
cs.setOption('-odac')
cs.compileOrc(r'''

sr = 48000
ksmps = 64
0dbfs = 1
nchnls = 2

givalue = 1000

instr 1
  ifreq = p4
  a0 oscili 0.1, ifreq
  outch 1, a0
endin

''')

thread = cs.performanceThread()
thread.play()

thread.scoreEvent(False, "i", [1, 0, 100, 440])

time.sleep(0.1)

givalue = thread.evalCode("return givalue")
print(givalue)

input("key...")

thread.stop()
