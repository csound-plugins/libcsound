import libcsound
import time
import ctypes
import queue

assert libcsound.VERSION >= 7000

cs = libcsound.Csound()
cs.setOption('-odac')
cs.compileOrc(r'''

sr = 48000
0dbfs = 1
nchnls = 2

chnset 1000, "kfreq"

instr 1
  kfreq = chnget("kfreq")
  a0 oscili 0.1, kfreq
  outch 1, a0
endin

instr 2
  a0 = pinker() * linseg:a(0, 0.005, 1, 0.05, 0)
  outch 2, a0*0.5
endin
''')

q = queue.Queue()

def proc(data, q=q):
    if q.empty():
        return
    job = q.get(block=False)
    if job:
        job()


thread = cs.performanceThread()
thread.setProcessCallback(proc)
thread.play()

thread.scoreEvent(0, "i", [1, 0, 10])
thread.scoreEvent(0, "i", [2, 1, 1])
time.sleep(1)
q.put(lambda: cs.setControlChannel("kfreq", 800))

input("key...")

q.put(lambda: cs.compileOrc(r'''
instr 3
  ifreq = p4
  outch 2, oscili(0.1, ifreq)
endin
''') or thread.scoreEvent(0, "i", [3, 0, 0.1, 1500]))

time.sleep(3)
thread.stop()
