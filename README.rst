
=========
libcsound
=========

Python bindings for Csound (fork of ``ctcsound``)

These bindings can be used with any version of csound >= 6.18. Csound 7 is explicitely supported.


Installation
------------

Csound needs to be installed in the system.


.. code::

	pip install libcsound


Quick Start
-----------

Rendering in real-time using a render thread
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

    import libcsound
    csound = libcsound.Csound()
    csound.setOption('-odac')
    csound.compileOrc(r'''

    sr = 44100   ; Modify to fit your system
    ksmps = 64
    nchnls = 2
    0dbfs = 1

    instr 1
      kchan init -1
      kchan = (kchan + metro:k(1)) % nchnls
      if changed:k(kchan) == 1 then
        println "Channel: %d", kchan + 1
      endif
      asig = pinker() * 0.2
      outch kchan + 1, asig
    endin

    ''')
    csound.start()
    thread = csound.performanceThread()
    thread.play()
    # Schedule an instance of instr 1 for 10 seconds
    thread.scoreEvent(0, "i", [1, 0, 10])
    input("Press any key to stop...\n")
    thread.stop()


Render offline
^^^^^^^^^^^^^^


.. code-block:: python

    import libcsound
    csound = libcsound.Csound()
    csound.setOption('-ooutfile.wav')
    csound.compileOrc(r'''

    sr = 44100
    ksmps = 64
    nchnls = 2
    0dbfs = 1

    instr 1
      kchan init -1
      kchan = (kchan + metro:k(1)) % nchnls
      if changed:k(kchan) == 1 then
        println "Channel: %d", kchan + 1
      endif
      asig = pinker() * 0.2
      outch kchan + 1, asig
    endin

    ''')
    csound.start()
    csound.scoreEvent("i", [1, 0, 10])
    csound.setEndMarker(10)
    # Perform until the end of the score
    while not csound.performKsmps():
        pass

Documentation
^^^^^^^^^^^^^

https://libcsound.readthedocs.io/en/latest/
