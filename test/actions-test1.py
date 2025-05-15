import sys
import os

if sys.platform.startswith('win'):
    # Add the path for github actions.
    if os.path.exists('C:/Program Files/csound'):
        os.environ['PATH'] = os.environ['PATH'] + ';C:/Program Files/csound'

import libcsound
import argparse

parser = argparse.ArgumentParser()
parser.add_argument('-o', '--outfile', default='actionstest.wav')
parser.add_argument('-d', '--dur', default=6, type=int)
args = parser.parse_args()

cs = libcsound.Csound()
print(f"Csound version: {cs.version()}")

cs.setOption(f"-o{args.outfile}")
ext = os.path.splitext(args.outfile)[1]
if ext == '.flac':
    cs.setOption("--format=flac")
elif ext == '.mp3':
    cs.setOption("--mpeg")
elif ext == '.ogg':
    cs.setOption("--format=ogg")
    cs.setOption("--format=vorbis")
else:
    assert ext == '.wav'

cs.compileOrc(r'''
0dbfs = 1
ksmps = 64
nchnls = 2

instr 1
  kchan init -1
  kchan = (kchan + metro:k(2)) % nchnls
  if changed:k(kchan) == 1 then
    println "Channel: %d", kchan + 1
  endif
  asig = pinker() * 0.2
  outch kchan + 1, asig
endin
''')

print("Duration: ", args.dur)

cs.start()
cs.scoreEvent('i', [1, 0, args.dur])
cs.scoreEvent('e', [0, args.dur+0.01])

while cs.performKsmps() == libcsound.CSOUND_SUCCESS:
    print(".", end='')
    pass
print("\nFinished...")
