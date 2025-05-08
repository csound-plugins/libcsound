import libcsound as lcs

cs = lcs.Csound()

cs.compileOrcHeader(sr=None)
cs.compile(r'''
instr 10
  ; inumpfields = p4
  ipfields[] passign 5
  printarray ipfields
  turnoff
endin
''')

cs.start()

