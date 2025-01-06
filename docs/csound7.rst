.. currentmodule:: libcsound.api7


Csound API, version 7
=====================

This API is valid for versions of csound >= 7.0. The correct API is imported
automatically based in the version of csound installed in the system and both
APIs (for csound 6 and csound 7) are for the most part compatible. With time
it is expected that csound 7 will slowly drift away.

.. note::
    At the moment there is no official release of csound 7,
    so this API is kept in
    sync with the develop branch of csound and is tested against it.

In general it can be said that the API has been reduced for csound 7. Some
methods which existed to set specific options, for example, have been
discontinued, but the same functionality is still available through command-line
options.


.. autosummary::
    Csound
    PerformanceThread


----------------------------


.. autoclass:: libcsound.api7.Csound
    :members:
    :autosummary:

.. autoclass:: libcsound.api7.PerformanceThread
    :members:
    :autosummary:
