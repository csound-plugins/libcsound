.. currentmodule:: libcsound.api7


csound API, version 7
=====================

This API applies to Csound >= 7.0 and is the API exposed by ``libcsound``.


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
