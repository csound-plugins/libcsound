
Introduction
============


Quick Start
-----------

.. note::

    *csound* should be installed before these bindings can be used. Any version of csound
    after and including ``6.18`` will work with these bindings. **csound 7** is
    explicitely supported and should work without any changes. See `installation`_.


Rendering in real-time
^^^^^^^^^^^^^^^^^^^^^^

The following example shows how to make csound generate audio in real-time.

.. code-block:: python

    import libcsound

    # Create a csound process
    csound = libcsound.Csound()

    # Output to the default audio device, using the default audio backend
    csound.setOption('-odac')

    # Compile some csound code. In this case just an output test, sends
    # some pink noise to each channel, in succession.

    csound.compileOrc(r'''

    sr = 44100   ; Modify to fit your system
    ksmps = 64   ; samples per performance cycle
    nchnls = 2   ; number of output channels
    0dbfs = 1    ; amplitude scaling factor. Here for atavistic reasons

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

    # Creates a performance thread to be able to run csound without blocking
    # python's main thread.
    thread = csound.performanceThread()

    # Start the performance
    thread.play()

    # Schedule an instance of instr 1 for 10 seconds
    thread.scoreEvent(0, "i", [1, 0, 10])

    # This makes python wait for a key at the REPL, here to show that csound
    # remains active even if python is blocked doing something else.
    input("Press any key to stop...\n")

    # Stop performance
    csound.stop()


Render offline
^^^^^^^^^^^^^^

The same code can be run offline (non-realtime mode)

.. code-block:: python

    import libcsound
    csound = libcsound.Csound()

    # Send output to a soundfile 'outfile.flac'. Other formats are supported: wav
    # mp3, ogg, aiff. The corresponding --format option needs to be added, since it
    # will not be infered from the extension.
    csound.setOption('-ooutfile.flac --format=flac')

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

    # Schedule an instance of instr 1 for 10 seconds
    csound.scoreEvent("i", [1, 0, 10])

    # End rendering at 10 seconds. Without this the main
    # loop keeps rendering silence indefinitely
    csound.setEndMarker(10)

    # Perform until the end of the score
    csound.perform()


--------------------------

.. _installation:

Installation
------------

.. rubric:: 1. Install csound (if not installed already)

For macos and windows, the recomended way to install csound is via
the installers provided by csound itself (https://csound.com/download.html).
In linux the recommended way is to install csound via the package manager
(``sudo apt install csound`` for debian based distributions). In all
these cases, at the moment, this will install csound 6. Installing csound 7
is out of the scope of this introduction

.. rubric:: 2. Install libcsound

.. code-block:: shell

    pip install libcsound


-------------------------

Compatibility
-------------

``libcsound`` supports both **csound 6** and **csound 7** and provides a compatibility layer
so that **the same code can be used for any version of csound**. In csound 7 some functions
have been removed. : these are marked clearly in the documentation. Their
corresponding method has been kept in the csound 6 API with the indication that it needs to be
replaced with a compatible alternative in order to write future-proof code.

When this package is imported, the installed csound is queried and based on
its version the corresponding API is loaded. So whereas the different versions supported
might differ, for the user there are very little changes. For completeness, however,
each version has its own documentation, making it clear which methods have changed
between versions and, particularly, how to write code which is portable across multiple versions.

For more information, see :ref:`portability`
