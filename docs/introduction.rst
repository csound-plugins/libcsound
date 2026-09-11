
Introduction
============


Quick Start
-----------

.. note::

    *csound* should be installed before these bindings can be used. Any version 
    >= 6.18 should work. **csound 7** is explicitely supported and is the recommended
    version to use. See `installation`_.


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
    0dbfs = 1    ; amplitude scaling factor. 1.0 = full scale (csound convention)

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

    # Output to a soundfile 'outfile.flac'. Supported formats include wav, flac,
    # mp3, ogg and aiff. The format must be given explicitly via --format; it is
    # not inferred from the extension
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

.. code-block:: shell

    pip install libcsound

Csound
^^^^^^

`libcsound` does not install csound itself. To install csound, see:

See https://github.com/csound/csound/releases

**Linux / macOS**

For linux csound 7 can be installed via:

  .. code::

    curl -fsSL https://csound-plugins.github.io/getcsound.sh | bash


Environment variables
^^^^^^^^^^^^^^^^^^^^^

The csound shared library is located and loaded when ``libcsound`` is imported,
so the variables below must be set **before** importing ``libcsound``.

``LIBCSOUNDPATH``
    Absolute path to the csound shared library to load, for example
    ``/usr/local/lib/libcsound64.so`` or
    ``/Applications/Csound/CsoundLib64.framework/CsoundLib64``. It must point to
    an existing file. When set, no other search is performed, which is useful
    when csound is installed in a non-standard location or when several versions
    are present. If not set, the library is searched in the system path (via
    ``ctypes.util.find_library``, the RPATH/RUNPATH of the ``csound`` executable
    and a number of standard installation locations).

``LIBCSOUND_INSTALL``
    Controls the automatic installation of csound when it cannot be found. Set
    it to ``0`` or ``false`` to disable this behaviour. Any other value (or
    leaving it unset) allows ``libcsound`` to download and install a portable
    csound 7 release on Linux/macOS.

``OPCODE7DIR64``
    Determines the path where csound looks for plugins. It can contain multiple
    paths, separated by ``:`` on Linux/macOS or ``;`` on Windows.

``CS_USER_PLUGINDIR``
    Path to user plugins. Set it to an empty string to disable searching for
    user-installed plugins. This can be needed when using a portable version of
    csound, where user plugins might be compiled for a different version.


-------------------------

Compatibility
-------------

``libcsound`` supports both **csound 6** and **csound 7** and provides a compatibility layer
so that **the same code can be used for any version of csound**. In csound 7 some functions
have been removed; these are clearly marked in the documentation. In the csound 6 API
they are still available but marked as deprecated, with a pointer to a portable alternative so you can write
future-proof code.


.. note::
    csound 7 is the best supported version at the moment and should be preferred over csound 6.


When ``libcsound`` is imported, it queries the installed csound and loads the matching API. Each version has its own
reference page, so you can see exactly which methods changed and how to write code that is portable across
versions.

For more information, see :ref:`portability`
