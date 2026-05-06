import libcsound
import sys

print(f"Csound version: {libcsound.libcsound.csoundGetVersion()}")

cs = libcsound.Csound()
print(cs)

