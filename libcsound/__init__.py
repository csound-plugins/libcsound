#   libcsound
#
#   fork of ctcsound.py, made to be pip installable and support any
#   version of csound 6 and csound 7
#
#   Copyright (C) 2024 Eduardo Moguillansky
#
#   Original copyright follows:
#
#   ctcsound.py:
#
#   Copyright (C) 2016 Francois Pinot
#
#   This file is part of Csound.
#
#   This code is free software; you can redistribute it
#   and/or modify it under the terms of the GNU Lesser General Public
#   License as published by the Free Software Foundation; either
#   version 2.1 of the License, or (at your option) any later version.
#
#   Csound is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Lesser General Public License for more details.
#
#   You should have received a copy of the GNU Lesser General Public
#   License along with Csound; if not, write to the Free Software
#   Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA
#   02110-1301 USA

"""Python bindings for csound.

The csound shared library is located and loaded when this package is imported,
so the environment variables below must be set *before* importing ``libcsound``.

Environment variables
---------------------

``LIBCSOUNDPATH``
    If set, the absolute path to the csound shared library to load (e.g.
    ``/usr/local/lib/libcsound64.so``). It must point to an existing file.
    When set, no other search is performed, which is useful when csound is
    installed in a non-standard location or when several versions are present.
    If not set, the library is searched in the system path (via
    ``ctypes.util.find_library``, the RPATH/RUNPATH of the ``csound``
    executable and standard installation locations).

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
"""

from . import common


if not common.BUILDING_DOCS:
    # this disables warnings about denormals
    import numpy as np
    np.finfo(np.dtype("float32"))
    np.finfo(np.dtype("float64"))

    from . import _dll
    libcsound, libcsoundPath = _dll.csoundDLL()
    VERSION = libcsound.csoundGetVersion()
    if VERSION >= 7000:
        APIVERSION = VERSION
    else:
        APIVERSION = libcsound.csoundGetAPIVersion()

    if VERSION < 7000:
        from .api6 import *
    else:
        from .api7 import *
else:
    print("------------- Building documentation -------------")
    VERSION = 0
    from . import api7
    from . import api6



#Instantiation
def csoundInitialize(signalHandler=True, atExitHandler=True) -> int:
    """
    Initializes Csound library with specific flags.

    There is generally no need to use it explicitly unless you need to
    avoid default initialization that sets signal handlers and atexit()
    callbacks.

    Within a python context, it is often necessary to call this function
    with `signalHandler=False` in order for csound not to obstruct
    python's own SIGINT (Keyboard Interrupt) handler. If called explicitely,
    it needs to be called prior to any other function within the API.

    Args:
        signalHandler: if True, add a signal handler
        atExitHandler: if True, adds a callback to destroy all instances of csound
            when exiting

    Returns:
        zero on success, positive if initialization was done already, and negative on error.

    """
    flags = 0
    if not signalHandler:
        flags |= common.CSOUNDINIT_NO_SIGNAL_HANDLER
    if not atExitHandler:
        flags |= common.CSOUNDINIT_NO_ATEXIT
    return libcsound.csoundInitialize(flags)
