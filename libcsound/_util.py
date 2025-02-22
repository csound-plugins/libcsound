from __future__ import annotations
import warnings
import signal
import ctypes
import numpy as np
import sys

from .common import (MYFLT,
                     CSOUND_CONTROL_CHANNEL,
                     CSOUND_AUDIO_CHANNEL,
                     CSOUND_ARRAY_CHANNEL,
                     CSOUND_PVS_CHANNEL,
                     CSOUND_OUTPUT_CHANNEL,
                     CSOUND_INPUT_CHANNEL,
                     CSOUND_CHANNEL_TYPE_MASK,
                     CSOUND_STRING_CHANNEL)


def asciistr(s) -> str:
    if isinstance(s, str):
        return s
    elif isinstance(s, bytes):
        return s.decode('ascii')
    else:
        raise TypeError(f"Expected a bytes or str instance, got {s}")


def packChannelType(kind: str, output: bool, input: bool) -> int:
    chantype = {'control': CSOUND_CONTROL_CHANNEL,
                'audio': CSOUND_AUDIO_CHANNEL,
                'str': CSOUND_STRING_CHANNEL,
                'string': CSOUND_STRING_CHANNEL,
                'array': CSOUND_ARRAY_CHANNEL,
                'pvs': CSOUND_PVS_CHANNEL}[kind]
    chanmode = CSOUND_OUTPUT_CHANNEL * int(output) + CSOUND_INPUT_CHANNEL * int(input)
    return chantype + chanmode


def unpackChannelType(chantype: int) -> tuple[str, int]:
    """
    Returns:
        a tuple (type: str, mode: int)
        Where type is one of 'control', 'audio', 'string', 'array' or 'pvs', mode
        is CSOUND_OUTPUT_CHANNEL, CSOUND_INPUT_CHANNEL or
        CSOUND_OUTPUT_CHANNEL + CSOUND_INPUT_CHANNEL
    """
    typecode = chantype & CSOUND_CHANNEL_TYPE_MASK
    typename = {
        CSOUND_CONTROL_CHANNEL: 'control',
        CSOUND_AUDIO_CHANNEL: 'audio',
        CSOUND_STRING_CHANNEL: 'string',
        CSOUND_ARRAY_CHANNEL: 'array',
        CSOUND_PVS_CHANNEL: 'pvs'
    }.get(typecode)
    if typename is None:
        raise ValueError(f"Invalid channel type: {chantype}")
    modecode = chantype - typecode
    return typename, modecode


_sigintHandler = None


def setupSigint(handler=lambda: sys.exit(0)):
    """
    Set a SIGINT handler

    This can be used in context with csound to avoid the situation where
    ctrl-c is hit during a performance and is handled by csound, making
    it exit without notifying the underlying python process. This results
    often in an unrecoverable situation

    Args:
        handler: a function taking to args and returning nothing. It will be called
            whenever SIGINT (ctrl-c) is signaled

    .. note:: to restore the previous sigint handler, call :func:`restoreSigint`
    """
    global _sigintHandler
    _sigintHandler = signal.getsignal(signal.SIGINT)
    def _handler(signal, frame):
        handler()
    signal.signal(signal.SIGINT, _handler)


def restoreSigint() -> None:
    """
    Restores the SIGINT handler previously replaced via :func:`setupSigint`
    """
    global _sigintHandler
    if _sigintHandler is not None:
        signal.signal(signal.SIGINT, _sigintHandler)


def defaultRealtimeModule() -> str:
    """
    Determines the default realtime module for the current architecture
    """
    if sys.platform == 'linux':
        return 'jack'
    elif sys.platform == 'darwin':
        return 'auhal'
    return 'pa_cb'


def realtimeModulesForPlatform(platform='') -> set[str]:
    if not platform:
        platform = sys.platform
    if platform == 'linux':
        return {'portaudio', 'jack', 'pulse', 'alsa'}
    elif platform == 'darwin':
        return {'portaudio', 'auhal', 'jack'}
    elif platform == 'windows':
        return {'portaudio', 'winmme'}
    else:
        return set()


def testCsound(module: str = '',
               sr: float = 0.,
               outdev='',
               nchnls=2,
               dur=10.,
               signal='pinker() * 0.2'
               ) -> None:
    """
    Test csound

    Args:
        module: the realtime audio module ('jack', 'auhal', 'portaudio', etc.). A default
            is used if not given
        sr: the samplerate to use. Leave unset to use the system sr or the default sr according
            to the module used
        outdev: the output device (unset to use default)
        nchnls: number of output channels
        signal: which signal to use. Any valid sound-generating csound code
    """
    if not module:
        module = defaultRealtimeModule()
    from . import Csound
    csound = Csound()
    if outdev:
        csound.setOption(f'-o{outdev}')
    elif module == 'jack':
        csound.setOption('-odac:_')
    else:
        csound.setOption('-odac')

    csound.setOption(f'-+rtaudio={module}')
    if sr <= 0:
        csound.setOption('--use-system-sr')
    else:
        csound.setOption(f'--sample-rate={sr}')
    csound.compileOrc(fr"""
    0dbfs = 1
    ksmps = 64
    nchnls = {nchnls}

    instr 1
      kchan init -1
      kchan = (kchan + metro:k(1)) % nchnls
      if changed:k(kchan) == 1 then
        println "Channel: %d", kchan + 1
      endif
      asig = {signal}
      outch kchan + 1, asig
    endin
    """)
    csound.start()
    pt = csound.performanceThread()
    pt.play()
    pt.scoreEvent(False, "i", [1, 0, dur])
    setupSigint(lambda: (pt.stop()))
    input(">>> Press any key to stop <<< \n")
    restoreSigint()
    pt.stop()
    csound.stop()


def castarray(ptr: ctypes._Pointer | ctypes.c_void_p, shape: tuple[int, ...]) -> np.ndarray:
    """
    Cast a ctypes pointer to an array
    """
    arrtype = np.ctypeslib.ndpointer(dtype=MYFLT, ndim=len(shape), shape=shape, flags='C_CONTIGUOUS')
    return ctypes.cast(ptr, arrtype).contents


def deprecated(func):
    """
    Decorator used to mark functions as deprecated

    It will result in a warning being emitted
    when the function is used."""
    import functools
    @functools.wraps(func)
    def newfunc(*args, **kwargs):
        warnings.simplefilter('always', DeprecationWarning)  # turn off filter
        warnings.warn("Call to deprecated function {}.".format(func.__name__),
                      category=DeprecationWarning,
                      stacklevel=2)
        warnings.simplefilter('default', DeprecationWarning)  # reset filter
        return func(*args, **kwargs)
    return newfunc


def splitCommandLine(args: str) -> list[str]:
    import re
    return re.findall(r"(?:\".*?\"|\S)+", args)


def waveplot(samples: np.ndarray, samplerate: int):
    def sec2str(seconds):
        s = seconds % 60
        sfrac = str(round((s - int(s)), 3)).split(".")[1]
        return f"{int(seconds//60)}:{int(s):>02}.{sfrac}"
    import matplotlib.pyplot as plt
    import matplotlib.ticker
    numch = 1 if len(samples.shape) == 1 else samples.shape[1]
    fig = plt.figure(figsize=(24, 4))
    formatter = matplotlib.ticker.FuncFormatter(lambda idx, x:sec2str(idx/samplerate))
    axes = ax1 = fig.add_subplot(numch, 1, 1)
    for i in range(numch):
        if i > 0:
            axes = fig.add_subplot(numch, 1, i + 1, sharex=ax1, sharey=ax1)
        if i < numch - 1:
            plt.setp(axes.get_xticklabels(), visible=False)
        chan = samples[:, i] if len(samples.shape) > 1 else samples
        axes.plot(chan, linewidth=1)
        axes.xaxis.set_major_formatter(formatter)
    ax1.set_xlim(0, samples.shape[0])
    fig.tight_layout()
    return fig
