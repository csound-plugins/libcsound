import libcsound

import libcsound
cs = libcsound.Csound()
cs.setOption('-+rtaudio=jack')
cs.setOption('-odac:"Built-in Audio Analog Stereo:"')
# cs.setOption('-iadc:Built-in Audio Analog Stereo:')
cs.setOption('-iadc:Built-in Audio Analog Stereo:')

cs.setOption('-b256')
cs.setOption('-B1024')
ok = cs.compileOrc(r'''
sr=48000
ksmps=64
nchnls=2
nchnls_i=2
0dbfs = 1
A4 = 440
''')

print("Compile", ok)

cs.start()

input("------------ key...")

cs.destroy()
