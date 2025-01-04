import libcsound
import libcsound._util as util
import sys

sr, rtmodule = libcsound.getSystemSr(module='')

print(":::::::::: System sr: ", sr)
if not (0 < sr <= 96000):
    print("Invalid samplerate")
    sys.exit(1)
util.testCsound(module=rtmodule, sr=sr)
