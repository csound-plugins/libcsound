.. currentmodule:: libcsound.api7


csound API, version 7
=====================

This API applies to csound >= 7.0. The correct API is imported automatically based on the installed csound
version. The csound 6 and csound 7 APIs are currently compatible for the most part, but they are expected to
diverge as csound 7 evolves.


.. note::
    This API is kept in sync with the develop branch of csound and is tested against it.

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
