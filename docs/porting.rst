.. _portability:


Portability
===========

Deprecated methods in csound 6
------------------------------

These methods do not exist in csound 7 but code can be written which supports the same
functionality


setSpinSample and addSpinSample
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

.. code-block:: python

    csound = Csound()
    ...
    # Csound 6 only
    csound.addSpinSample(frame, channel, sample)

    # Portable version (csound 7 and 6)
    spin = csound.spin()
    spin[nchnls * frame + channel] = sample


spoutSample
~~~~~~~~~~~

.. code-block:: python

    # Csound 6
    samp = csound.spoutSample(frame, channel)

    # Portable version (csound 7 and 6)
    spout = csound.spout()
    samp = spout[nchnls * frame + channel]


clearSpin
~~~~~~~~~

.. code-block:: python

    # Csound 6
    csound.clearSpin()

    # Portable version
    spin = csound.spin()
    spin[:] = 0


queryGlobalVariable
~~~~~~~~~~~~~~~~~~~

In general, for data exchange with csound it is recommended to use channels
or tables.

.. code-block:: python

    # Csound 6
    ptr = csound.queryGlobalVariable('gkcounter')
    if ptr is not None:
        # do something with ptr...

    # Portable version
    value = csound.evalCode('return gkcounter')

    # Or better, using the performanceThread with process queue
    thread = csound.performanceThread(withProcessQueue=True)
    ...
    value = thread.evalCode('return gkcounter')


------------------------------------------


Not supported methods in csound 6
---------------------------------

These methods exist in csound 6 but have been removed from the API in csound 7

* ``setPlayOpenCallback``
* ``setRtPlayCallback``
* ``setRecordOpenCallback``
* ``setRtRecordCallback``
* ``setRtCloseCallback``
* ``listUtilities``
* ``utilityDescription``
* ``rand31``
* ``seedRandMT``
* ``randMT``
* ``openLibrary``
* ``closeLibrary``
* ``getLibrarySymbol``
