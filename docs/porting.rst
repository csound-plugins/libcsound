.. _portability:


Portability
===========

Deprecated methods in csound 6
------------------------------

These methods do not exist in csound 7 but code can be written which supports the same
functionality

spin / spout
~~~~~~~~~~~~


**setSpinSample and addSpinSample**

.. code-block:: python

    csound = Csound()
    ...
    # Csound 6 only
    csound.addSpinSample(frame, channel, sample)

    # Portable version (csound 7 and 6)
    spin = csound.spin()
    spin[nchnls * frame + channel] = sample


**spoutSample**

.. code-block:: python

    # Csound 6
    samp = csound.spoutSample(frame, channel)

    # Portable version (csound 7 and 6)
    spout = csound.spout()
    samp = spout[nchnls * frame + channel]


**clearSpin**

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


Not supported methods in csound 7
---------------------------------

These methods exist in csound 6 but have been removed from the API in csound 7.0

* :meth:`~libcsound.api6.Csound.parseOrc`
* :meth:`~libcsound.api6.Csound.setPlayOpenCallback`
* :meth:`~libcsound.api6.Csound.setRtPlayCallback`
* :meth:`~libcsound.api6.Csound.setRecordOpenCallback`
* :meth:`~libcsound.api6.Csound.setRecordOpenCallback`
* :meth:`~libcsound.api6.Csound.compileTree`
* :meth:`~libcsound.api6.Csound.compileTreeAsync`
* :meth:`~libcsound.api6.Csound.deleteTree`
* :meth:`~libcsound.api6.Csound.performBuffer`
* :meth:`~libcsound.api6.Csound.listUtilities`
* :meth:`~libcsound.api6.Csound.utilityDescription`
* :meth:`~libcsound.api6.Csound.rand31`
* :meth:`~libcsound.api6.Csound.seedRandMT`
* :meth:`~libcsound.api6.Csound.randMT`
* :meth:`~libcsound.api6.Csound.openLibrary`
* :meth:`~libcsound.api6.Csound.closeLibrary`
* :meth:`~libcsound.api6.Csound.getLibrarySymbol`
* :meth:`~libcsound.api6.Csound.setRtCloseCallback`
* :meth:`~libcsound.api6.Csound.UDPServerStatus`
* :meth:`~libcsound.api6.Csound.UDPServerClose`
* :meth:`~libcsound.api6.Csound.UDPConsole`
* :meth:`~libcsound.api6.Csound.stopUDPConsole`
* :meth:`~libcsound.api6.Csound.inputBufferSize`
* :meth:`~libcsound.api6.Csound.outputBufferSize`
* :meth:`~libcsound.api6.Csound.inputBuffer`
* :meth:`~libcsound.api6.Csound.outputBuffer`
* :meth:`~libcsound.api6.Csound.rtRecordUserData`
* :meth:`~libcsound.api6.Csound.rtPlayUserData`
* :meth:`~libcsound.api6.Csound.setRtCloseCallback`
* :meth:`~libcsound.api6.Csound.registerSenseEventCallback`
* :meth:`~libcsound.api6.Csound.tableGet`
* :meth:`~libcsound.api6.Csound.tableSet`
* :meth:`~libcsound.api6.Csound.tableCopyOut`
* :meth:`~libcsound.api6.Csound.tableCopyOutAsync`
* :meth:`~libcsound.api6.Csound.tableCopyIn`
* :meth:`~libcsound.api6.Csound.tableCopyInAsync`
* :meth:`~libcsound.api6.Csound.isNamedGEN`
* :meth:`~libcsound.api6.Csound.namedGEN`
* :meth:`~libcsound.api6.Csound.namedGens`
* :meth:`~libcsound.api6.Csound.setYieldCallback`
