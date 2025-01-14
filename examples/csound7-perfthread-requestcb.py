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


gi_tab1 ftfill 1, 10, 2, 20, 3, 30

instr 1
  ifreq = p4
  a0 oscili 0.1, ifreq
  outch 1, a0
  if metro:k(5) == 1 then
    ftprint gi_tab1, -1
  endif
endin

''')

thread = cs.performanceThread()
thread.play()

thread.scoreEvent(False, "i", [1, 0, 100, 440])

    
time.sleep(0.5)


thread.requestCallback(lambda pt: pt.csound.compileOrc(r'''
instr 2
  ifreq = p4
  outch 2, (oscili(0.1, ifreq) + oscili(0.1, ifreq+12)) * linsegr:a(0, 0.05, 1, 0.05, 0)
endin
'''))

thread.scoreEvent(False, "i", [2, 0, 100, 500])

q = queue.SimpleQueue()
def func(pt, q=q):
    tabnum = int(pt.csound.evalCode("return gi_tab1"))
    tabptr = pt.csound.table(tabnum)
    q.put(tabptr)

input("key...")

thread.requestCallback(func)
tabptr = q.get()
tabptr[0] = 0.5
    
input("key...")


thread.stop()
