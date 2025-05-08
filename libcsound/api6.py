from __future__ import annotations

import sys
import os
import numpy as np
import warnings
import ctypes as ct
import queue as _queue
import threading as _threading

from .common import *
from . import _util

import typing as _t


def _deprecated(s: str, level=2):
    warnings.warn(s, DeprecationWarning, stacklevel=level)


def _notPresentInCsound7(s=''):
    if s:
        msg = f'Not present in csound 7: {s}'
    else:
        msg = 'Not present in csound 7.'
    _deprecated(msg, level=3)


class CsoundParams(ct.Structure):
    _fields_ = [("debug_mode", ct.c_int32),         # debug mode, 0 or 1
                ("buffer_frames", ct.c_int32),      # number of frames in in/out buffers
                ("hardware_buffer_frames", ct.c_int32), # ibid. hardware
                ("displays", ct.c_int32),           # graph displays, 0 or 1
                ("ascii_graphs", ct.c_int32),       # use ASCII graphs, 0 or 1
                ("postscript_graphs", ct.c_int32),  # use postscript graphs, 0 or 1
                ("message_level", ct.c_int32),      # message printout control
                ("tempo", ct.c_int32),              # tempo ("sets Beatmode)
                ("ring_bell", ct.c_int32),          # bell, 0 or 1
                ("use_cscore", ct.c_int32),         # use cscore for processing
                ("terminate_on_midi", ct.c_int32),  # terminate performance at the end
                                                    #   of midifile, 0 or 1
                ("heartbeat", ct.c_int32),          # print heart beat, 0 or 1
                ("defer_gen01_load", ct.c_int32),   # defer GEN01 load, 0 or 1
                ("midi_key", ct.c_int32),           # pfield to map midi key no
                ("midi_key_cps", ct.c_int32),       # pfield to map midi key no as cps
                ("midi_key_oct", ct.c_int32),       # pfield to map midi key no as oct
                ("midi_key_pch", ct.c_int32),       # pfield to map midi key no as pch
                ("midi_velocity", ct.c_int32),      # pfield to map midi velocity
                ("midi_velocity_amp", ct.c_int32),  # pfield to map midi velocity as amplitude
                ("no_default_paths", ct.c_int32),   # disable relative paths from files, 0 or 1
                ("number_of_threads", ct.c_int32),  # number of threads for multicore performance
                ("syntax_check_only", ct.c_int32),  # do not compile, only check syntax
                ("csd_line_counts", ct.c_int32),    # csd line error reporting
                ("compute_weights", ct.c_int32),    # deprecated, kept for backwards comp.
                ("realtime_mode", ct.c_int32),      # use realtime priority mode, 0 or 1
                ("sample_accurate", ct.c_int32),    # use sample-level score event accuracy
                ("sample_rate_override", MYFLT),    # overriding sample rate
                ("control_rate_override", MYFLT),   # overriding control rate
                ("nchnls_override", ct.c_int32),    # overriding number of out channels
                ("nchnls_i_override", ct.c_int32),  # overriding number of in channels
                ("e0dbfs_override", MYFLT),         # overriding 0dbfs
                ("daemon", ct.c_int32),             # daemon mode
                ("ksmps_override", ct.c_int32),     # ksmps override
                ("FFT_library", ct.c_int32)]        # fft_lib


# Callback functions
FILEOPENFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.c_char_p, ct.c_int, ct.c_int, ct.c_int)
PLAYOPENFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.POINTER(CsoundRtAudioParams))
RTPLAYFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.POINTER(MYFLT), ct.c_int)
RECORDOPENFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.POINTER(CsoundRtAudioParams))
RTRECORDFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.POINTER(MYFLT), ct.c_int)
RTCLOSEFUNC = ct.CFUNCTYPE(None, ct.c_void_p)
AUDIODEVLISTFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.POINTER(CsoundAudioDevice), ct.c_int)
MIDIINOPENFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.POINTER(ct.c_void_p), ct.c_char_p)
MIDIREADFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_char_p, ct.c_int)
MIDIINCLOSEFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.c_void_p)
MIDIOUTOPENFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.POINTER(ct.c_void_p), ct.c_char_p)
MIDIWRITEFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.c_void_p, ct.c_char_p, ct.c_int)
MIDIOUTCLOSEFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.c_void_p)
MIDIERRORFUNC = ct.CFUNCTYPE(ct.c_char_p, ct.c_int)
MIDIDEVLISTFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.POINTER(CsoundMidiDevice), ct.c_int)
CSCOREFUNC = ct.CFUNCTYPE(None, ct.c_void_p)
DEFMSGFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_void_p)
CHANNELFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.c_char_p, ct.c_void_p, ct.c_void_p)
SENSEFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.py_object)
KEYBOARDFUNC = ct.CFUNCTYPE(ct.c_int, ct.py_object, ct.c_void_p, ct.c_uint)
MAKEGRAPHFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.POINTER(Windat), ct.c_char_p)
DRAWGRAPHFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.POINTER(Windat))
KILLGRAPHFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.POINTER(Windat))
EXITGRAPHFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p)
OPCODEFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p, ct.c_void_p)
YIELDFUNC = ct.CFUNCTYPE(ct.c_int, ct.c_void_p)
THREADFUNC = ct.CFUNCTYPE(ct.POINTER(ct.c_uint), ct.py_object)
PROCESSFUNC = ct.CFUNCTYPE(None, ct.c_void_p)


def _declareAPI(libcsound, libcspt):

    libcsound.csoundSetOpcodedir.argtypes = [ct.c_char_p]
    libcsound.csoundCreate.restype = ct.c_void_p
    libcsound.csoundCreate.argtypes = [ct.py_object]
    libcsound.csoundLoadPlugins.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundDestroy.argtypes = [ct.c_void_p]

    libcsound.csoundParseOrc.restype = ct.c_void_p
    libcsound.csoundParseOrc.argtypes = [ct.c_void_p, ct.c_char_p]

    libcsound.csoundCompileTree.argtypes = [ct.c_void_p, ct.c_void_p]
    libcsound.csoundCompileTreeAsync.argtypes = [ct.c_void_p, ct.c_void_p]
    libcsound.csoundDeleteTree.argtypes = [ct.c_void_p, ct.c_void_p]
    libcsound.csoundCompileOrc.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundCompileOrcAsync.argtypes = [ct.c_void_p, ct.c_char_p]

    libcsound.csoundEvalCode.restype = MYFLT
    libcsound.csoundEvalCode.argtypes = [ct.c_void_p, ct.c_char_p]

    libcsound.csoundCompileArgs.argtypes = [ct.c_void_p, ct.c_int, ct.POINTER(ct.c_char_p)]
    libcsound.csoundStart.argtypes = [ct.c_void_p]
    libcsound.csoundCompile.argtypes = [ct.c_void_p, ct.c_int, ct.POINTER(ct.c_char_p)]
    libcsound.csoundCompileCsd.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundCompileCsdText.argtypes = [ct.c_void_p, ct.c_char_p]

    libcsound.csoundPerform.argtypes = [ct.c_void_p]
    libcsound.csoundPerformKsmps.argtypes = [ct.c_void_p]
    libcsound.csoundPerformBuffer.argtypes = [ct.c_void_p]
    libcsound.csoundStop.argtypes = [ct.c_void_p]
    libcsound.csoundCleanup.argtypes = [ct.c_void_p]
    libcsound.csoundReset.argtypes = [ct.c_void_p]

    libcsound.csoundUDPServerStart.argtypes = [ct.c_void_p, ct.c_uint]
    libcsound.csoundUDPServerStatus.argtypes = [ct.c_void_p]
    libcsound.csoundUDPServerClose.argtypes = [ct.c_void_p]
    libcsound.csoundUDPConsole.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_uint, ct.c_uint]
    libcsound.csoundStopUDPConsole.argtypes = [ct.c_void_p]

    libcsound.csoundGetSr.restype = MYFLT
    libcsound.csoundGetSr.argtypes = [ct.c_void_p]
    libcsound.csoundGetKr.restype = MYFLT
    libcsound.csoundGetKr.argtypes = [ct.c_void_p]
    libcsound.csoundGetKsmps.restype = ct.c_uint32
    libcsound.csoundGetKsmps.argtypes = [ct.c_void_p]
    libcsound.csoundGetNchnls.restype = ct.c_uint32
    libcsound.csoundGetNchnls.argtypes = [ct.c_void_p]
    libcsound.csoundGetNchnlsInput.restype = ct.c_uint32
    libcsound.csoundGetNchnlsInput.argtypes = [ct.c_void_p]
    libcsound.csoundGet0dBFS.restype = MYFLT
    libcsound.csoundGet0dBFS.argtypes = [ct.c_void_p]
    libcsound.csoundGetA4.restype = MYFLT
    libcsound.csoundGetA4.argtypes = [ct.c_void_p]
    libcsound.csoundGetCurrentTimeSamples.restype = ct.c_int64
    libcsound.csoundGetCurrentTimeSamples.argtypes = [ct.c_void_p]
    libcsound.csoundGetHostData.restype = ct.py_object
    libcsound.csoundGetHostData.argtypes = [ct.c_void_p]
    libcsound.csoundSetHostData.argtypes = [ct.c_void_p, ct.py_object]
    libcsound.csoundSetOption.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundSetParams.argtypes = [ct.c_void_p, ct.POINTER(CsoundParams)]
    libcsound.csoundGetParams.argtypes = [ct.c_void_p, ct.POINTER(CsoundParams)]
    libcsound.csoundGetDebug.argtypes = [ct.c_void_p]
    libcsound.csoundSetDebug.argtypes = [ct.c_void_p, ct.c_int]
    libcsound.csoundSystemSr.restype = MYFLT
    libcsound.csoundSystemSr.argtypes = [ct.c_void_p, MYFLT]

    libcsound.csoundGetOutputName.restype = ct.c_char_p
    libcsound.csoundGetOutputName.argtypes = [ct.c_void_p]
    libcsound.csoundGetInputName.restype = ct.c_char_p
    libcsound.csoundGetInputName.argtypes = [ct.c_void_p]
    libcsound.csoundSetOutput.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p, ct.c_char_p]
    libcsound.csoundGetOutputFormat.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p]
    libcsound.csoundSetInput.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundSetMIDIInput.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundSetMIDIFileInput.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundSetMIDIOutput.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundSetMIDIFileOutput.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundSetFileOpenCallback.argtypes = [ct.c_void_p, FILEOPENFUNC]

    libcsound.csoundSetRTAudioModule.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundGetModule.argtypes = [ct.c_void_p, ct.c_int, ct.POINTER(ct.c_char_p), ct.POINTER(ct.c_char_p)]
    libcsound.csoundGetInputBufferSize.restype = ct.c_long
    libcsound.csoundGetInputBufferSize.argtypes = [ct.c_void_p]
    libcsound.csoundGetOutputBufferSize.restype = ct.c_long
    libcsound.csoundGetOutputBufferSize.argtypes = [ct.c_void_p]
    libcsound.csoundGetInputBuffer.restype = ct.POINTER(MYFLT)
    libcsound.csoundGetInputBuffer.argtypes = [ct.c_void_p]
    libcsound.csoundGetOutputBuffer.restype = ct.POINTER(MYFLT)
    libcsound.csoundGetOutputBuffer.argtypes = [ct.c_void_p]
    libcsound.csoundGetSpin.restype = ct.POINTER(MYFLT)
    libcsound.csoundGetSpin.argtypes = [ct.c_void_p]
    libcsound.csoundClearSpin.argtypes = [ct.c_void_p]
    libcsound.csoundAddSpinSample.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, MYFLT]
    libcsound.csoundSetSpinSample.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, MYFLT]
    libcsound.csoundGetSpout.restype = ct.POINTER(MYFLT)
    libcsound.csoundGetSpout.argtypes = [ct.c_void_p]
    libcsound.csoundGetSpoutSample.restype = MYFLT
    libcsound.csoundGetSpoutSample.argtypes = [ct.c_void_p, ct.c_int, ct.c_int]
    libcsound.csoundGetRtRecordUserData.restype = ct.POINTER(ct.c_void_p)
    libcsound.csoundGetRtRecordUserData.argtypes = [ct.c_void_p]
    libcsound.csoundGetRtPlayUserData.restype = ct.POINTER(ct.c_void_p)
    libcsound.csoundGetRtPlayUserData.argtypes = [ct.c_void_p]
    libcsound.csoundSetHostImplementedAudioIO.argtypes = [ct.c_void_p, ct.c_int, ct.c_int]
    libcsound.csoundGetAudioDevList.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int]

    libcsound.csoundSetPlayopenCallback.argtypes = [ct.c_void_p, PLAYOPENFUNC]
    libcsound.csoundSetRtplayCallback.argtypes = [ct.c_void_p, RTPLAYFUNC]
    libcsound.csoundSetRecopenCallback.argtypes = [ct.c_void_p, RECORDOPENFUNC]
    libcsound.csoundSetRtrecordCallback.argtypes = [ct.c_void_p, RTRECORDFUNC]
    libcsound.csoundSetRtcloseCallback.argtypes = [ct.c_void_p, RTCLOSEFUNC]
    libcsound.csoundSetAudioDeviceListCallback.argtypes = [ct.c_void_p, AUDIODEVLISTFUNC]

    libcsound.csoundSetMIDIModule.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundSetHostImplementedMIDIIO.argtypes = [ct.c_void_p, ct.c_int]
    libcsound.csoundGetMIDIDevList.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_int]
    libcsound.csoundSetExternalMidiInOpenCallback.argtypes = [ct.c_void_p, MIDIINOPENFUNC]
    libcsound.csoundSetExternalMidiReadCallback.argtypes = [ct.c_void_p, MIDIREADFUNC]
    libcsound.csoundSetExternalMidiInCloseCallback.argtypes = [ct.c_void_p, MIDIINCLOSEFUNC]
    libcsound.csoundSetExternalMidiOutOpenCallback.argtypes = [ct.c_void_p, MIDIOUTOPENFUNC]
    libcsound.csoundSetExternalMidiWriteCallback.argtypes = [ct.c_void_p, MIDIWRITEFUNC]
    libcsound.csoundSetExternalMidiOutCloseCallback.argtypes = [ct.c_void_p, MIDIOUTCLOSEFUNC]
    libcsound.csoundSetExternalMidiErrorStringCallback.argtypes = [ct.c_void_p, MIDIERRORFUNC]
    libcsound.csoundSetMIDIDeviceListCallback.argtypes = [ct.c_void_p, MIDIDEVLISTFUNC]

    libcsound.csoundReadScore.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundReadScoreAsync.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundGetScoreTime.restype = ct.c_double
    libcsound.csoundGetScoreTime.argtypes = [ct.c_void_p]
    libcsound.csoundIsScorePending.argtypes = [ct.c_void_p]
    libcsound.csoundSetScorePending.argtypes = [ct.c_void_p, ct.c_int]
    libcsound.csoundGetScoreOffsetSeconds.restype = MYFLT
    libcsound.csoundGetScoreOffsetSeconds.argtypes = [ct.c_void_p]
    libcsound.csoundSetScoreOffsetSeconds.argtypes = [ct.c_void_p, MYFLT]
    libcsound.csoundRewindScore.argtypes = [ct.c_void_p]
    libcsound.csoundSetCscoreCallback.argtypes = [ct.c_void_p, CSCOREFUNC]

    libcsound.csoundMessage.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p]
    libcsound.csoundMessageS.argtypes = [ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_char_p]
    libcsound.csoundSetDefaultMessageCallback.argtypes = [DEFMSGFUNC]
    libcsound.csoundGetMessageLevel.argtypes = [ct.c_void_p]
    libcsound.csoundSetMessageLevel.argtypes = [ct.c_void_p, ct.c_int]
    libcsound.csoundCreateMessageBuffer.argtypes = [ct.c_void_p, ct.c_int]
    libcsound.csoundGetFirstMessage.restype = ct.c_char_p
    libcsound.csoundGetFirstMessage.argtypes = [ct.c_void_p]
    libcsound.csoundGetFirstMessageAttr.argtypes = [ct.c_void_p]
    libcsound.csoundPopFirstMessage.argtypes = [ct.c_void_p]
    libcsound.csoundGetMessageCnt.argtypes = [ct.c_void_p]
    libcsound.csoundDestroyMessageBuffer.argtypes = [ct.c_void_p]

    libcsound.csoundGetChannelPtr.argtypes = [ct.c_void_p, ct.POINTER(ct.POINTER(MYFLT)), ct.c_char_p, ct.c_int]
    libcsound.csoundListChannels.argtypes = [ct.c_void_p, ct.POINTER(ct.POINTER(ControlChannelInfo))]
    libcsound.csoundDeleteChannelList.argtypes = [ct.c_void_p, ct.POINTER(ControlChannelInfo)]
    libcsound.csoundSetControlChannelHints.argtypes = [ct.c_void_p, ct.c_char_p, ControlChannelHints]
    libcsound.csoundGetControlChannelHints.argtypes = [ct.c_void_p, ct.c_char_p, ct.POINTER(ControlChannelHints)]
    libcsound.csoundGetChannelLock.restype = ct.POINTER(ct.c_int)
    libcsound.csoundGetChannelLock.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundGetControlChannel.restype = MYFLT
    libcsound.csoundGetControlChannel.argtypes = [ct.c_void_p, ct.c_char_p, ct.POINTER(ct.c_int)]
    libcsound.csoundSetControlChannel.argtypes = [ct.c_void_p, ct.c_char_p, MYFLT]
    libcsound.csoundGetAudioChannel.argtypes = [ct.c_void_p, ct.c_char_p, ct.POINTER(ct.c_int)]
    libcsound.csoundSetAudioChannel.argtypes = [ct.c_void_p, ct.c_char_p, ct.POINTER(ct.c_int)]
    libcsound.csoundGetStringChannel.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p]
    libcsound.csoundSetStringChannel.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_char_p]
    libcsound.csoundGetChannelDatasize.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundSetInputChannelCallback.argtypes = [ct.c_void_p, CHANNELFUNC]
    libcsound.csoundSetOutputChannelCallback.argtypes = [ct.c_void_p, CHANNELFUNC]
    libcsound.csoundSetPvsChannel.argtypes = [ct.c_void_p, ct.POINTER(PvsdatExt), ct.c_char_p]
    libcsound.csoundGetPvsChannel.argtypes = [ct.c_void_p, ct.POINTER(PvsdatExt), ct.c_char_p]
    libcsound.csoundScoreEvent.argtypes = [ct.c_void_p, ct.c_char, ct.POINTER(MYFLT), ct.c_long]
    libcsound.csoundScoreEventAsync.argtypes = [ct.c_void_p, ct.c_char, ct.POINTER(MYFLT), ct.c_long]
    libcsound.csoundScoreEventAbsolute.argtypes = [ct.c_void_p, ct.c_char, ct.POINTER(MYFLT), ct.c_long, ct.c_double]
    libcsound.csoundScoreEventAbsoluteAsync.argtypes = [ct.c_void_p, ct.c_char, ct.POINTER(MYFLT), ct.c_long, ct.c_double]
    libcsound.csoundInputMessage.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundInputMessageAsync.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundKillInstance.argtypes = [ct.c_void_p, MYFLT, ct.c_char_p, ct.c_int, ct.c_int]
    libcsound.csoundRegisterSenseEventCallback.argtypes = [ct.c_void_p, SENSEFUNC, ct.py_object]
    libcsound.csoundKeyPress.argtypes = [ct.c_void_p, ct.c_char]
    libcsound.csoundRegisterKeyboardCallback.argtypes = [ct.c_void_p, KEYBOARDFUNC, ct.py_object, ct.c_uint]
    libcsound.csoundRemoveKeyboardCallback.argtypes = [ct.c_void_p, KEYBOARDFUNC]

    libcsound.csoundTableLength.argtypes = [ct.c_void_p, ct.c_int]
    libcsound.csoundTableGet.restype = MYFLT
    libcsound.csoundTableGet.argtypes = [ct.c_void_p, ct.c_int, ct.c_int]
    libcsound.csoundTableSet.argtypes = [ct.c_void_p, ct.c_int, ct.c_int, MYFLT]
    libcsound.csoundTableCopyOut.argtypes = [ct.c_void_p, ct.c_int, ct.POINTER(MYFLT)]
    libcsound.csoundTableCopyOutAsync.argtypes = [ct.c_void_p, ct.c_int, ct.POINTER(MYFLT)]
    libcsound.csoundTableCopyIn.argtypes = [ct.c_void_p, ct.c_int, ct.POINTER(MYFLT)]
    libcsound.csoundTableCopyInAsync.argtypes = [ct.c_void_p, ct.c_int, ct.POINTER(MYFLT)]
    libcsound.csoundGetTable.argtypes = [ct.c_void_p, ct.POINTER(ct.POINTER(MYFLT)), ct.c_int]
    libcsound.csoundGetTableArgs.argtypes = [ct.c_void_p, ct.POINTER(ct.POINTER(MYFLT)), ct.c_int]
    libcsound.csoundIsNamedGEN.argtypes = [ct.c_void_p, ct.c_int]
    libcsound.csoundGetNamedGEN.argtypes = [ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_int]

    libcsound.csoundSetIsGraphable.argtypes = [ct.c_void_p, ct.c_int]
    libcsound.csoundSetMakeGraphCallback.argtypes = [ct.c_void_p, MAKEGRAPHFUNC]
    libcsound.csoundSetDrawGraphCallback.argtypes = [ct.c_void_p, DRAWGRAPHFUNC]
    libcsound.csoundSetKillGraphCallback.argtypes = [ct.c_void_p, KILLGRAPHFUNC]
    libcsound.csoundSetExitGraphCallback.argtypes = [ct.c_void_p, EXITGRAPHFUNC]

    libcsound.csoundGetNamedGens.restype = ct.c_void_p
    libcsound.csoundGetNamedGens.argtypes = [ct.c_void_p]
    libcsound.csoundNewOpcodeList.argtypes = [ct.c_void_p, ct.POINTER(ct.POINTER(OpcodeListEntry))]
    libcsound.csoundDisposeOpcodeList.argtypes = [ct.c_void_p, ct.POINTER(OpcodeListEntry)]
    libcsound.csoundAppendOpcode.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int, ct.c_int, ct.c_int,
                                            ct.c_char_p, ct.c_char_p, OPCODEFUNC, OPCODEFUNC, OPCODEFUNC]

    libcsound.csoundSetYieldCallback.argtypes = [ct.c_void_p, YIELDFUNC]
    libcsound.csoundCreateThread.restype = ct.c_void_p
    libcsound.csoundCreateThread.argtypes = [THREADFUNC, ct.py_object]
    libcsound.csoundCreateThread2.restype = ct.c_void_p
    libcsound.csoundCreateThread2.argtypes = [THREADFUNC, ct.c_uint, ct.py_object]
    libcsound.csoundGetCurrentThreadId.restype = ct.c_void_p
    libcsound.csoundJoinThread.restype = ct.POINTER(ct.c_uint)
    libcsound.csoundJoinThread.argtypes = [ct.c_void_p]
    libcsound.csoundCreateThreadLock.restype = ct.c_void_p
    libcsound.csoundWaitThreadLock.argtypes = [ct.c_void_p, ct.c_uint]
    libcsound.csoundWaitThreadLockNoTimeout.argtypes = [ct.c_void_p]
    libcsound.csoundNotifyThreadLock.argtypes = [ct.c_void_p]
    libcsound.csoundDestroyThreadLock.argtypes = [ct.c_void_p]
    libcsound.csoundCreateMutex.restype = ct.c_void_p
    libcsound.csoundCreateMutex.argtypes = [ct.c_int]
    libcsound.csoundLockMutex.argtypes = [ct.c_void_p]
    libcsound.csoundLockMutexNoWait.argtypes = [ct.c_void_p]
    libcsound.csoundUnlockMutex.argtypes = [ct.c_void_p]
    libcsound.csoundDestroyMutex.argtypes = [ct.c_void_p]
    libcsound.csoundCreateBarrier.restype = ct.c_void_p
    libcsound.csoundCreateBarrier.argtypes = [ct.c_uint]
    libcsound.csoundDestroyBarrier.argtypes = [ct.c_void_p]
    libcsound.csoundWaitBarrier.argtypes = [ct.c_void_p]
    libcsound.csoundSleep.argtypes = [ct.c_uint]
    libcsound.csoundSpinLockInit.argtypes = [ct.POINTER(ct.c_int32)]
    libcsound.csoundSpinLock.argtypes = [ct.POINTER(ct.c_int32)]
    libcsound.csoundSpinTryLock.argtypes = [ct.POINTER(ct.c_int32)]
    libcsound.csoundSpinUnLock.argtypes = [ct.POINTER(ct.c_int32)]

    libcsound.csoundRunCommand.restype = ct.c_long
    libcsound.csoundRunCommand.argtypes = [ct.POINTER(ct.c_char_p), ct.c_int]
    libcsound.csoundInitTimerStruct.argtypes = [ct.POINTER(RtClock)]
    libcsound.csoundGetRealTime.restype = ct.c_double
    libcsound.csoundGetRealTime.argtypes = [ct.POINTER(RtClock)]
    libcsound.csoundGetCPUTime.restype = ct.c_double
    libcsound.csoundGetCPUTime.argtypes = [ct.POINTER(RtClock)]
    libcsound.csoundGetRandomSeedFromTime.restype = ct.c_uint32
    libcsound.csoundGetEnv.restype = ct.c_char_p
    libcsound.csoundGetEnv.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundSetGlobalEnv.argtypes = [ct.c_char_p, ct.c_char_p]
    libcsound.csoundCreateGlobalVariable.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_uint]
    libcsound.csoundQueryGlobalVariable.restype = ct.c_void_p
    libcsound.csoundQueryGlobalVariable.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundQueryGlobalVariableNoCheck.restype = ct.c_void_p
    libcsound.csoundQueryGlobalVariableNoCheck.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundDestroyGlobalVariable.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundRunUtility.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int, ct.POINTER(ct.c_char_p)]
    libcsound.csoundListUtilities.restype = ct.POINTER(ct.c_char_p)
    libcsound.csoundListUtilities.argtypes = [ct.c_void_p]
    libcsound.csoundDeleteUtilityList.argtypes = [ct.c_void_p, ct.POINTER(ct.c_char_p)]
    libcsound.csoundGetUtilityDescription.restype = ct.c_char_p
    libcsound.csoundGetUtilityDescription.argtypes = [ct.c_void_p, ct.c_char_p]
    libcsound.csoundRand31.argtypes = [ct.POINTER(ct.c_int)]
    libcsound.csoundSeedRandMT.argtypes = [ct.POINTER(CsoundRandMTState), ct.POINTER(ct.c_uint32), ct.c_uint32]
    libcsound.csoundRandMT.restype = ct.c_uint32
    libcsound.csoundRandMT.argtypes = [ct.POINTER(CsoundRandMTState)]
    libcsound.csoundCreateCircularBuffer.restype = ct.c_void_p
    libcsound.csoundCreateCircularBuffer.argtypes = [ct.c_void_p, ct.c_int, ct.c_int]
    libcsound.csoundReadCircularBuffer.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_int]
    libcsound.csoundPeekCircularBuffer.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_int]
    libcsound.csoundWriteCircularBuffer.argtypes = [ct.c_void_p, ct.c_void_p, ct.c_void_p, ct.c_int]
    libcsound.csoundFlushCircularBuffer.argtypes = [ct.c_void_p, ct.c_void_p]
    libcsound.csoundDestroyCircularBuffer.argtypes = [ct.c_void_p, ct.c_void_p]
    libcsound.csoundOpenLibrary.argtypes = [ct.POINTER(ct.c_void_p), ct.c_char_p]
    libcsound.csoundCloseLibrary.argtypes = [ct.c_void_p]
    libcsound.csoundGetLibrarySymbol.restype = ct.c_void_p
    libcsound.csoundGetLibrarySymbol.argtypes = [ct.c_void_p, ct.c_char_p]

    # Performance thread

    libcspt.NewCsoundPT.restype = ct.c_void_p
    libcspt.NewCsoundPT.argtypes = [ct.c_void_p]
    libcspt.DeleteCsoundPT.argtypes = [ct.c_void_p]
    libcspt.CsoundPTisRunning.argtypes = [ct.c_void_p]
    libcspt.CsoundPTgetProcessCB.restype = ct.c_void_p
    libcspt.CsoundPTgetProcessCB.argtypes = [ct.c_void_p]
    libcspt.CsoundPTsetProcessCB.argtypes = [ct.c_void_p, PROCESSFUNC, ct.c_void_p]
    libcspt.CsoundPTgetCsound.restype = ct.c_void_p
    libcspt.CsoundPTgetCsound.argtypes = [ct.c_void_p]
    libcspt.CsoundPTgetStatus.argtypes = [ct.c_void_p]
    libcspt.CsoundPTplay.argtypes = [ct.c_void_p]
    libcspt.CsoundPTpause.argtypes = [ct.c_void_p]
    libcspt.CsoundPTtogglePause.argtypes = [ct.c_void_p]
    libcspt.CsoundPTstop.argtypes = [ct.c_void_p]
    libcspt.CsoundPTrecord.argtypes = [ct.c_void_p, ct.c_char_p, ct.c_int, ct.c_int]
    libcspt.CsoundPTstopRecord.argtypes = [ct.c_void_p]
    libcspt.CsoundPTscoreEvent.argtypes = [ct.c_void_p, ct.c_int, ct.c_char, ct.c_int, ct.POINTER(MYFLT)]
    libcspt.CsoundPTinputMessage.argtypes = [ct.c_void_p, ct.c_char_p]
    libcspt.CsoundPTsetScoreOffsetSeconds.argtypes = [ct.c_void_p, ct.c_double]
    libcspt.CsoundPTjoin.argtypes = [ct.c_void_p]
    libcspt.CsoundPTflushMessageQueue.argtypes = [ct.c_void_p]


# Constants

# message types (only one can be specified)
CSOUNDMSG_DEFAULT = 0x0000       # standard message
CSOUNDMSG_ERROR = 0x1000         # error message (initerror, perferror, etc.)
CSOUNDMSG_ORCH = 0x2000          # orchestra opcodes (e.g. printks)
CSOUNDMSG_REALTIME = 0x3000      # for progress display and heartbeat characters
CSOUNDMSG_WARNING = 0x4000       # warning messages
CSOUNDMSG_STDOUT = 0x5000

# format attributes (colors etc.), use the bitwise OR of any of these:
CSOUNDMSG_FG_BLACK = 0x0100
CSOUNDMSG_FG_RED = 0x0101
CSOUNDMSG_FG_GREEN = 0x0102
CSOUNDMSG_FG_YELLOW = 0x0103
CSOUNDMSG_FG_BLUE = 0x0104
CSOUNDMSG_FG_MAGENTA = 0x0105
CSOUNDMSG_FG_CYAN = 0x0106
CSOUNDMSG_FG_WHITE = 0x0107

CSOUNDMSG_FG_BOLD = 0x0008
CSOUNDMSG_FG_UNDERLINE = 0x0080

CSOUNDMSG_BG_BLACK = 0x0200
CSOUNDMSG_BG_RED = 0x0210
CSOUNDMSG_BG_GREEN = 0x0220
CSOUNDMSG_BG_ORANGE = 0x0230
CSOUNDMSG_BG_BLUE = 0x0240
CSOUNDMSG_BG_MAGENTA = 0x0250
CSOUNDMSG_BG_CYAN = 0x0260
CSOUNDMSG_BG_GREY = 0x0270

CSOUNDMSG_TYPE_MASK = 0x7000
CSOUNDMSG_FG_COLOR_MASK = 0x0107
CSOUNDMSG_FG_ATTR_MASK = 0x0088
CSOUNDMSG_BG_COLOR_MASK = 0x0270


# Constants used by the bus interface (csoundGetChannelPtr() etc.).
CSOUND_CONTROL_CHANNEL = 1
CSOUND_AUDIO_CHANNEL  = 2
CSOUND_STRING_CHANNEL = 3
CSOUND_PVS_CHANNEL = 4
CSOUND_VAR_CHANNEL = 5


if not BUILDING_DOCS:
    from . import _dll
    import ctypes.util
    libcsound, libcsoundpath = _dll.csoundDLL()
    if sys.platform.startswith('linux'):
        libcspt = ct.CDLL("libcsnd6.so")
    elif sys.platform.startswith('win'):
        libcspt = ct.CDLL(ctypes.util.find_library("csnd6"))
    elif sys.platform.startswith('darwin'):
        libcspt = ct.CDLL(ctypes.util.find_library('csnd6.6.0'))
    else:
        raise ImportError(f"Platform '{sys.platform}' unknown")

    _declareAPI(libcsound, libcspt)


class Csound:
    """
    Creates an instance of Csound.

    Args:
        hostData: any data, will be accessible within certain callbacks
        opcodeDir: the folder where to load opcodes from. If not given,
            default folders are used
        pointer: if given, the result of calling ``libcsound.csoundCreate``,
            uses the given csound process instead of creating a new one

    """

    def __init__(self,
                 hostData=None,
                 opcodeDir='',
                 pointer: ct.c_void_p | None = None):
        """
        Creates an instance of Csound.

        The hostData parameter can be None, or it can be any sort of data; these
        data can be accessed from the Csound instance that is passed to callback routines.
        If given, opcodeDir sets the directory where csound searches for plugins
        """

        if pointer:
            self.cs = pointer
            self._fromPointer = True
        else:
            if opcodeDir and os.path.exists(opcodeDir):
                libcsound.csoundSetOpcodedir(cstring(opcodeDir))
            self.cs = libcsound.csoundCreate(ct.py_object(hostData))
            self._fromPointer = False
        self._channelLocks: dict[str, ct.c_int32] = {}
        self._perfthread: PerformanceThread | None = None
        self._callbacks: dict[str, ct._FuncPointer] = {}
        self._started = False

    def performanceThread(self) -> PerformanceThread:
        """
        Creates a performance thread attached to this csound instance

        Returns:
            the created performance thread object

        .. seealso:: :meth:`Csound.performanceThread`

        Since there can be only one performance thread for each instance,
        calling this method repeatedly always returns the same thread as
        long as the thread has not been joint

        The playback is paused at start time. It can be stopped
        by calling :meth:`stop`.

        .. rubric:: Example

        .. code-block:: python

            from libcsound import *
            cs = Csound(...)
            ...
            perfthread = cs.performanceThread()

        To stop the performance thread, call :meth:`stop` and then :meth:`join`::

            # When finished:
            perfthread.stop()
            perfthread.join()

        Calling the :meth:`~Csound.stop` method on the csound instance will also
        stop its attached thread, if created

        """
        if self._perfthread is None:
            self._perfthread = PerformanceThread(self)
        return self._perfthread

    def loadPlugins(self, directory: str) -> int:
        """
        Loads all plugins from a given directory.

        Args:
            directory: the path to the plugins directory

        """
        return libcsound.csoundLoadPlugins(self.cs, cstring(directory))

    def __del__(self):
        """Destroys an instance of Csound."""
        if not self._fromPointer and libcsound:
            libcsound.csoundDestroy(self.cs)

    def destroy(self):
        if self._perfthread:
            self._perfthread = None  # This should destroy the performance thread
        if self.cs is not None:
            libcsound.csoundDestroy(self.cs)
            self.cs = None

    def csound(self) -> ct.c_void_p:
        """
        Returns the opaque pointer to the running Csound instance.

        Raises RuntimeError if the internal pointer is None. This might
        happen if this method is being called after the csound instance
        has been deleted
        """
        if self.cs is None:
            raise RuntimeError("The internal pointer is None")
        return self.cs

    def version(self) -> int:
        """
        Returns the version number x 1000 (6.18.0 = 6180).

        Returns:
            an int representing the version
        """
        return libcsound.csoundGetVersion()

    def APIVersion(self) -> int:
        """Returns the API version number x 100 (1.00 = 100)."""
        return libcsound.csoundGetAPIVersion()

    #Performance
    def parseOrc(self, orc: str) -> ct.c_void_p:
        """
        Parses the given orchestra from string into a TREE.

        This can be called during performance to parse new code.

        Args:
            orc: the orchestra code to parse

        Returns:
            a void pointer representing a TREE structure

        .. note:: this method and the underlying functionality are not
            present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundParseOrc(self.cs, cstring(orc))

    def compileTree(self, tree: ct.c_void_p) -> None:
        """
        Compiles the given TREE node into structs for Csound to use.

        This can be called during performance to compile a new TREE.

        Args:
            tree: a void pointer representing a tree structure, as returned
                from :meth:`Csound.parseOrc`

        .. note:: this method and the underlying functionality are not
            present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundCompileTree(self.cs, tree)

    def compileTreeAsync(self, tree: ct.c_void_p) -> int:
        """
        Asynchronous version of :meth:`compileTree`.

        Args:
            tree: the tree to compile

        Returns:
            CSOUND_SUCCESS (0) if ok, an error code otherwise

        .. note:: this method and the underlying functionality are not
            present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundCompileTreeAsync(self.cs, tree)

    def deleteTree(self, tree: ct.c_void_p) -> None:
        """
        Frees the resources associated with the TREE *tree*.

        Args:
            tree: the tree to delete

        This function should be called whenever the TREE was
        created with :py:meth:`parseOrc()` and memory can be deallocated.

        .. note:: this method and the underlying functionality are not
            present in csound 7

        """
        _notPresentInCsound7()
        libcsound.csoundDeleteTree(self.cs, tree)

    def compileOrcHeader(self,
                         sr: int | None,
                         nchnls=2,
                         nchnls_i: int | None = None,
                         zerodbfs=1.,
                         ksmps=64,
                         a4=440):
        """
        Compile the orchestra header (sr, ksmps, nchnls, ...)

        Args:
            sr: the sample rate. Only included if given
            ksmps: samples per cycle
            nchnls: number of output channels
            nchnls_i: number of input channels
            zerodbfs: the value of 0dbfs, should be 1. for any mordern orchestra
            a4: reference frequency

        """
        lines = [f'ksmps = {ksmps}\nchnls = {nchnls}\n0dbfs = {zerodbfs}\nA4 = {a4}']
        if sr is not None:
            lines.append(f'sr = {sr}')
        if nchnls_i is not None:
            lines.append(f'nchnls_i = {nchnls_i}')
        code = '\n'.join(lines)
        self.compileOrc(code)

    def compileOrc(self, orc: str, block=True) -> int:
        """
        Compiles the given orchestra code

        .. note:: backported from csound 7

        Args:
            orc: the code to compile
            block: if True, any global code will be evaluated in synchronous
                mode. Otherwise, this methods returns immediately but any
                global code passed to csound might not still be available

        Returns:
            0 if OK, an error code otherwise

        .. rubric:: Example

        .. code-block:: python

            cs = Csound()
            cs.setOption(...)
            cs.compileOrc(r'''
            instr 1
                a1 rand 0dbfs/4
                out a1
            endin
            cs.scoreEvent(...)
            cs.perform()

            ''')

        """
        if block:
            return libcsound.csoundCompileOrc(self.cs, cstring(orc))
        else:
            return self.compileOrcAsync(orc)

    def compileOrcAsync(self, orc: str) -> int:
        """
        Async version of :py:meth:`compileOrc()`.

        The code is parsed and compiled, then placed on a queue for
        asynchronous merge into the running engine, and evaluation.
        The function returns following parsing and compilation.

        Args:
            orc: the orchestra code to compile

        Returns:
            CSOUND_SUCCESS (0) if ok, an error code otherwise

        """
        return libcsound.csoundCompileOrcAsync(self.cs, cstring(orc))

    def evalCode(self, code: str) -> float:
        """
        Parses and compiles an orchestra given on an string, synchronously.

        Args:
            code: the code to evaluate. This code is evaluated at the global space
                and is limited to init-time code

        Returns:
            the value passed to the ``return`` opcode in global space

        .. rubric:: Example

        .. code-block:: python

            code = r'''
              i1 = 2 + 2
              return i1
            '''
            retval = cs.evalCode(code)

        .. note::

            Calling this method while csound is run in realtime via a performance
            thread might incur in high latency.

        """
        return libcsound.csoundEvalCode(self.cs, cstring(code))

    def compileArgs(self, *args: str):
        """
        Compiles *args*.

        Reads arguments, parses and compiles an orchestra,
        reads, processes and loads a score.

        Args:
            args: the arguments to compile, as passed to a csound executable
        """
        argc, argv = csoundArgList(args)
        return libcsound.csoundCompileArgs(self.cs, argc, argv)

    def start(self) -> int:
        """
        Prepares Csound for performance.

        Returns:
            CSOUND_SUCCESS (0) if ok, an error code otherwise

        Normally called after compiling a csd file or an orc file, in which
        case score preprocessing is performed and performance terminates
        when the score terminates.

        However, if called before compiling a csd file or an orc file,
        score preprocessing is not performed and "i" statements are dispatched
        as real-time events. In this case, any options given as part of
        a ``<CsOptions>`` tag are ignored (options can only be set prior to
        starting the csound process).

        .. note::

            This method is called internally by methods like
            :py:meth:`compileCommandLine()`, :py:meth:`perform`, :py:meth:`performKsmps`,
            :py:meth:`performBuffer`, or when a performance thread is
            created for this csound instance and the thread itself is started
            via its :meth:`~PerformanceThread.play` method.

        """
        if self._started:
            return CSOUND_SUCCESS
        else:
            self._started = True
            return libcsound.csoundStart(self.cs)

    def compile(self, *args, **kws):
        warnings.warn("This method is deprecated, use compileCommandLine")
        raise DeprecationWarning("This method has been renamed to compileCommandLine")

    def compileCommandLine(self, *args) -> int:
        """
        Compiles Csound input files (such as an orchestra and score).

        Args:
            args: any command line arg passed to csound

        Returns:
            0 on success, an error code on failure

        Compiles any csd or orc files as directed by the supplied
        command-line arguments, but does not perform them. Returns
        a non-zero error code on failure.
        This function cannot be called during performance, and before a
        repeated call, :py:meth:`reset()` needs to be called.

        .. rubric:: Example
        .. code-block:: python

            cs.compileCommandLine(args)
            while cs.performBuffer() == 0:
                pass
            cs.cleanup()
            cs.reset()

        Calls :py:meth:`start()` internally.
        """
        argc, argv = csoundArgList(args)
        return libcsound.csoundCompile(self.cs, argc, argv)

    def compileCsd(self, path: str, block=True) -> int:
        """Compiles a Csound input file (.csd file).

        Args:
            path: the path to the csd file
            block: dummy argument, this functions is always blocking in
                csound6

        Returns:
            CSOUND_SUCCESS (0) if ok, an error code otherwise

        The input file includes command-line arguments, but does not
        perform the file. Returns a non-zero error code on failure.

        .. rubric:: Example

        .. code-block:: python

            cs.compileCsd(csdfile)
            while cs.performBuffer() == 0:
                pass
            cs.cleanup()
            cs.reset()

        .. note::

            This function can be called during performance to
            replace or add new instruments and events.
            On a first call and if called before :py:meth:`start()`, this function
            behaves similarly to :py:meth:`compileCommandLine()`.

        """
        return libcsound.csoundCompileCsd(self.cs, cstring(path))

    def compileCsdText(self, code: str, block=True) -> int:
        """Compiles a Csound input file contained in a string of text.

        Args:
            code: the code to compile
            block: dummy argument, this functions is always blocking in
                csound6

        Returns:
            0 if ok, a non-zero code on failure

        The string of text includes command-line arguments, orchestra, score,
        etc., but it is not performed. Returns a non-zero error code on failure.

        If start is called before this method, the ``<CsOptions>``
        element is ignored (but setOption can be called any number of
        times), the ``<CsScore>`` element is not pre-processed, but dispatched as
        real-time events; and performance continues indefinitely, or until
        ended by calling stop or some other logic.

        .. rubric:: Example
        .. code-block:: python

            >>> from libcsound import *
            >>> cs = Csound()
            >>> cs.setOption(...)
            >>> cs.start()
            >>> cs.compileCsdText(code)
            >>> while cs.performBuffer() == 0:
            ...     pass
            >>> cs.reset()

        .. note::

            This function can be called repeatedly during performance to
            replace or add new instruments and events.
        """
        return libcsound.csoundCompileCsdText(self.cs, cstring(code))

    def perform(self) -> int:
        """
        Handles input events and performs audio output.

        Returns:
            0 if stopped, 1 if end of score is reached, negative on error

        Note that some form of compilation needs to happen before
        (:py:meth:`compileCommandLine()`, :py:meth:`compileOrc()`,
        etc.). Also any event scheduling (:py:meth:`readScore()`,
        :py:meth:`scoreEvent()`, etc.) needs to be done prior to calling
        this method.

        In the case of zero return value, :py:meth:`perform()` can be called
        again to continue the stopped performance. Otherwise, :py:meth:`reset()`
        should be called to clean up after the finished or failed performance.
        """
        if not self._started:
            self.start()
        return libcsound.csoundPerform(self.cs)

    def performKsmps(self) -> bool:
        """
        Handles input events, and performs audio output for one cycle

        Returns:
            True if performance is finished, False otherwise

        This is done for one control sample worth (ksmps).

        Note that some form of compilation needs to happen before
        (:py:meth:`compileCommandLine()`, :py:meth:`compileOrc()`,
        etc.). Also any event scheduling (:py:meth:`readScore()`,
        :py:meth:`scoreEvent()`, etc.) needs to be done prior to calling
        this method.

        Returns :code:`False` during performance, and :code:`True` when
        performance is finished. If called until it returns :code:`True`,
        it will perform an entire score.

        Enables external software to control the execution of Csound,
        and to synchronize performance with audio input and output.
        """
        if not self._started:
            self.start()
        return bool(libcsound.csoundPerformKsmps(self.cs))

    def performBuffer(self) -> bool:
        """Performs Csound, sensing real-time and score events.

        Processing one buffer's worth (-b frames) of interleaved audio.

        Returns:
            True if performance is finished, False otherwise

        Note that :py:meth:`compileCommandLine()` must be called first, then call
        :py:meth:`outputBuffer()` and :py:meth:`inputBuffer(`) to get ndarrays
        pointing to Csound's I/O buffers.

        Returns :code:`False` during performance, and :code:`true` when
        performance is finished.

        .. note::

            This method is not present in csound 7. Use :py:meth:`performKsmps()`
            for forward compatibility
        """
        _notPresentInCsound7()
        if not self._started:
            self.start()
        return bool(libcsound.csoundPerformBuffer(self.cs))

    def stop(self) -> None:
        """
        Stops a :py:meth:`perform()` running in another thread.

        Note that it is not guaranteed that :py:meth:`perform()` has already
        stopped when this function returns.
        """
        libcsound.csoundStop(self.cs)

    def cleanup(self) -> None:
        """
        Prints information and closes audio and MIDI devices.

        .. note:: after calling cleanup(), the operation of the perform
            function is undefined.

        """
        return libcsound.csoundCleanup(self.cs)

    def reset(self) -> None:
        """
        Resets all internal memory and state.

        In preparation for a new performance.
        Enable external software to run successive Csound performances
        without reloading Csound. Implies :py:meth:`cleanup()`, unless already
        called.
        """
        libcsound.csoundReset(self.cs)

    #UDP server
    def UDPServerStart(self, port: int) -> int:
        """Starts the UDP server on a supplied port number.

        Args:
            port: port number

        Returns:
            ``CSOUND_SUCCESS`` if ok, ``CSOUND_ERROR`` otherwise.

        .. note::

            This method is not present in csound 7. To start csound
            with a UDP server listening for commands use the command
            line options (``--port=<udpport>``)
        """
        _notPresentInCsound7()
        return libcsound.csoundUDPServerStart(self.cs, ct.c_uint(port))

    def UDPServerStatus(self) -> int:
        """Returns the port number on which the server is running.

        Returns:
            CSOUND_SUCCESS if running, CSOUND_ERROR otherwise

        .. note:: This method is not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundUDPServerStatus(self.cs)

    def UDPServerClose(self) -> int:
        """Closes the UDP server.

        Returns:
            CSOUND_SUCCESS on success, CSOUND_ERROR otherwise.

        .. note:: This method is not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundUDPServerClose(self.cs)

    def UDPConsole(self, addr: str, port: int, mirror: bool) -> int:
        """Turns on the transmission of console messages to UDP on addr:port.

        Args:
            addr: the udp address, as a string
            port: the port number
            mirror: if True, messages will continue to be sent to the usual
                destination (see :py:meth:`setMessageCallback()`) as well as to UDP.

        Returns:
            CSOUND_SUCCESS if ok, CSOUND_ERROR otherwise

        .. note:: This method is not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundUDPConsole(self.cs, cstring(addr), ct.c_uint(port), ct.c_uint(int(mirror)))

    def stopUDPConsole(self) -> None:
        """
        Stops transmitting console messages via UDP.

        .. note:: This method is not present in csound 7

        """
        _notPresentInCsound7()
        libcsound.csoundStopUDPConsole(self.cs)

    #Attributes
    def sr(self) -> float:
        """Returns the number of audio sample frames per second."""
        return libcsound.csoundGetSr(self.cs)

    def kr(self) -> float:
        """Returns the number of control samples per second."""
        return libcsound.csoundGetKr(self.cs)

    def ksmps(self) -> int:
        """Returns the number of audio sample frames per control sample."""
        return libcsound.csoundGetKsmps(self.cs)

    def nchnls(self) -> int:
        """Returns the number of audio output channels.

        Set through the ``nchnls`` header variable in the csd file.
        """
        return libcsound.csoundGetNchnls(self.cs)

    def nchnlsInput(self) -> int:
        """Returns the number of audio input channels.

        Set through the :code:`nchnls_i` header variable in the csd file. If
        this variable is not set, the value is taken from :code:`nchnls`.
        """
        return libcsound.csoundGetNchnlsInput(self.cs)

    def get0dBFS(self) -> float:
        """Returns the 0dBFS level of the spin/spout buffers."""
        return libcsound.csoundGet0dBFS(self.cs)

    def A4(self) -> float:
        """Returns the A4 frequency reference."""
        return libcsound.csoundGetA4(self.cs)

    def currentTimeSamples(self) -> int:
        """Returns the current performance time in samples."""
        return libcsound.csoundGetCurrentTimeSamples(self.cs)

    def sizeOfMYFLT(self) -> int:
        """Returns the size of MYFLT in bytes."""
        return libcsound.csoundGetSizeOfMYFLT()

    def hostData(self) -> ct.c_void_p:
        """Returns host data."""
        return libcsound.csoundGetHostData(self.cs)

    def setHostData(self, data) -> None:
        """
        Sets host data.

        Args:
            data: can be any data
        """
        libcsound.csoundSetHostData(self.cs, ct.py_object(data))

    def setOption(self, option: str) -> int:
        """
        Set csound option/options

        Args:
            option: a command line option passed to the csound process. Any number
                of options can be passed at once, separated by whitespace

        Returns:
            CSOUND_SUCCESS on success.

        This needs to be called before any code is compiled.
        Multiple options are allowed in one string.
        Returns zero on success.

        .. rubric:: Options

        ``--output= (-o)``
            Output device or filename. ``-odac`` for realtime
            audio using the default device. When using jack,
            ``-odac:<portpattern>``, for example
            ``-odac:"Built-in Audio Analog Stereo"`` will connect
            to all ports matching the given pattern

        ``--input= (-i)``
            Input device or filename. Similar to ``-o``
        ``-+rtaudio=<module>``
            Real-time audio module, used with ``-odac...``, possible
            values are ``portaudio``, ``auhal`` (coreaudio, only in macos),
            ``alsa`` (linux only), ``jack``, ``pulse`` (pulseaudio, linux)
        ``-+rtmidi=``
            Real time MIDI module
        ``--nodisplays (-d)``
            Supress all displays
        ``--format=<fmt>``
            Soundfile format, one of ``wav, aiff, w64, flac, caf, ogg, mpeg``
        ``--format=<fmt>``
            Sample format, one of ``alaw, ulaw, float, double, short, long, 24bit, vorbis``
        ``--midi-device=<dev>``
            Read MIDI from the given device
        ``--realtime``
            Realtime priority mode
        ``--sample-accurate``
            Use sample-accurate timing of score events
        ``--nosound``
            No sound onto disk or device
        ``--messagelevel=N (-m)``
            Console message level, sum of: 1=note amps, 2=out-of-range msg,
            4=warnings, 0/32/64/96=note amp format (raw,dB,colors),
            128=print benchmark information. Use ``-m0`` to disable note messages
        ``--use-system-sr``
            Use the system samplerate for realtime audio. Not all audio backends
            define a system sr. Backends which do define system sr: ``jack``,
            ``auhal``, ``pulse``
        ``--get-system-sr``
            Print system sr and exit, requires realtime audio output
            (e.g. -odac) to be defined first)
        ``--port=N``
            Listen to UDP port N for orchestra code (implies ``--daemon``)
        ``--limiter[=num]``
            Include clipping in audio output

        See ``csound --help`` for a complete list of options

        """
        parts = _util.splitCommandLine(option)
        out = 0
        for part in parts:
            if '"' in part:
                part = part.replace('"', '')
            out |= libcsound.csoundSetOption(self.cs, cstring(part))
        return out

    def setParams(self, params: CsoundParams) -> None:
        """Configures Csound with a given set of parameters.

        Args:
            params: an instance of CsoundParams

        .. note::

            This method is NOT compatible with csound 7. In csound 7
            it does not exist. All parameters can be set via command line
            arguments

        These parameters are defined in the CsoundParams structure.
        They are the part of the OPARMS struct that are configurable through
        command line flags.
        The CsoundParams structure can be obtained using :py:meth:`params()`.
        These options should only be changed before performance has started.
        """
        _deprecated("In csound 7 this method does not exist. All parameters "
                    "must be set via command line arguments")
        libcsound.csoundSetParams(self.cs, ct.byref(params))

    def params(self, params: CsoundParams | None = None) -> CsoundParams:
        """Gets the current set of parameters from a CSOUND instance.

        Args:
            params: if given, the passed instance is filled with the
                corresponding information, otherwise a new struct is
                created

        These parameters are in a CsoundParams structure. See
        :py:meth:`setParams()`::

            p = CsoundParams()
            cs.params(p)

        """
        if params is None:
            params = CsoundParams()
        libcsound.csoundGetParams(self.cs, ct.byref(params))
        return params

    def debug(self) -> bool:
        """Returns whether Csound is set to print debug messages.

        Those messages are sent through the :code:`DebugMsg()` internal API
        function.
        """
        return libcsound.csoundGetDebug(self.cs) != 0

    def setDebug(self, debug: bool) -> None:
        """Sets whether Csound prints debug messages.

        Args:
            debug: if True, debugging is turned on. Otherwise debug
                messages are not printed

        The debug argument must have value :code:`True` or :code:`False`.
        Those messages come from the :code:`DebugMsg()` internal API function.
        """
        libcsound.csoundSetDebug(self.cs, ct.c_int(debug))

    def systemSr(self, val: int = 0) -> float:
        """If val > 0, sets the internal variable holding the system HW sr.

        Args:
            val: if given, sets the system sr to this value

        Returns:
            the stored value containing the system HW sr."""
        return libcsound.csoundSystemSr(self.cs, float(val))

    def outputName(self) -> str:
        """
        Returns the audio output name (-o)

        .. note:: This method is incompatible with csound 7

        """
        _notPresentInCsound7()
        s = libcsound.csoundGetOutputName(self.cs)
        return pstring(s)

    def inputName(self) -> str:
        """
        Returns the audio input name (-i)

        .. note:: this method is incompatible with csound 7

        """
        _deprecated("This method does not exist in csound 7")
        s = libcsound.csoundGetInputName(self.cs)
        return pstring(s)

    def setOutput(self, name: str, filetype='', format='') -> None:
        """
        Sets output destination, type and format.

        Args:
            name: the name of the output device/filename
            filetype: in the case of a filename, the type can determine the file
                type used. One of "wav", "aiff", "au", "raw", "paf", "svx", "nist",
                "voc", "ircam", "w64", "mat4", "mat5", "pvf", "xi", "htk", "sds",
                "avr", "wavex", "sd2", "flac", "caf", "wve", "ogg", "mpc2k", "rf64"
            format: only used for offline output to a filename, one of "alaw",
                "schar", "uchar", "float", "double", "long", "short", "ulaw",
                "24bit", "vorbis"

        For RT audio, use device_id from CS_AUDIODEVICE for a given audio
        device.

        .. note::

            The API function which is used by this method (``csoundSetOutput``)
            does not exist in csound 7. The method itself has been implemented
            in csound 7 using command-line options (``--format=...``) and can be
            safely used for future compatibility

        """
        n = cstring(name)
        t = cstring(filetype)
        f = cstring(format)
        libcsound.csoundSetOutput(self.cs, n, t, f)

    def outputFormat(self) -> tuple[str, str]:
        """Gets output type and format.

        Returns:
            a tuple (type: str, format: str)

        .. note:: not compatible with csound 7

        """
        _deprecated("This method does not exist in csound 7")
        type_ = ct.create_string_buffer(6)
        format = ct.create_string_buffer(8)
        libcsound.csoundGetOutputFormat(self.cs, type_, format)
        return pstring(ct.string_at(type_)), pstring(ct.string_at(format))

    def setInput(self, name: str) -> None:
        """Sets input source.

        Args:
            name: name of the input device. Depends on the rt module used

        .. note::

            The API function which is used by this method (``csoundSetInput``)
            does not exist in csound 7. The method itself has been implemented
            in csound 7 using command-line options (``-i`` option) and can be
            safely used for future compatibility

        """
        libcsound.csoundSetInput(self.cs, cstring(name))

    def setMidiInput(self, name: str) -> None:
        """Sets Midi input device name/number.

        Args:
            name: name of the input midi device

        .. note::

            The API function which is used by this method (``csoundSetMIDIInput``)
            does not exist in csound 7. The method itself has been implemented
            in csound 7 using command-line options (``-i`` option) and can be
            safely used for future compatibility (see :meth:`libcsound.api7.Csound.setMidiInput')
        """
        libcsound.csoundSetMIDIInput(self.cs, cstring(name))

    def setMidiFileInput(self, name: str) -> None:
        """
        Sets Midi file input name.

        Args:
            name: the path to the Midi file used as input
        """
        _deprecated("This method does not exist in csound 7. For compatibility, use "
                    "command-line options instead")
        libcsound.csoundSetMIDIFileInput(self.cs, cstring(name))

    def setMidiOutput(self, name: str) -> None:
        """Sets Midi output device name/number.

        Args:
            name: Midi device to use as output
        """
        _deprecated("This method does not exist in csound 7. For compatibility, use "
                    "command-line options instead")
        libcsound.csoundSetMIDIOutput(self.cs, cstring(name))

    def setMidiFileOutput(self, name: str) -> None:
        """Sets Midi file output name.

        Args:
            name: name of a Midi file to output to.
        """
        _deprecated("This method does not exist in csound 7. For compatibility, use "
                    "command-line options instead")
        libcsound.csoundSetMIDIFileOutput(self.cs, cstring(name))

    def setFileOpenCallback(self, function: _t.Callable[[bytes, int, int, int], None]) -> None:
        """Sets a callback for receiving notices whenever Csound opens a file.

        Args:
            function: the callback

        The callback is made after the file is successfully opened.
        The following information is passed to the callback:

        bytes
            pathname of the file; either full or relative to current dir
        int
            a file type code from the enumeration CSOUND_FILETYPES
        int
            1 if Csound is writing the file, 0 if reading
        int
            1 if a temporary file that Csound will delete; 0 if not

        Pass NULL to disable the callback.
        This callback is retained after a :py:meth:`reset()` call.
        """
        self._callbacks['fileOpen'] = _ = FILEOPENFUNC(function)
        libcsound.csoundSetFileOpenCallback(self.cs, _)

    #Realtime Audio I/O
    def setRTAudioModule(self, module: str) -> None:
        """
        Sets the current RT audio module.

        Args:
            module: the name of the module.

        =========  ===========================
        Platform    Modules
        =========  ===========================
        linux       jack, pa_cb (portaudio)
        macos       au_hal (coreaudio), pa_cb, jack
        windows     pa_cb (portaudio), winmm
        =========  ===========================
        """
        libcsound.csoundSetRTAudioModule(self.cs, cstring(module))

    def modules(self) -> list[tuple[str, str]]:
        """
        Returns a list of modules

        Returns:
            a list of tuples of the form (name: str, type: str),
            where name is the name of the module and type is one of
            "audio" or "midi"

        .. seealso:: :meth:`Csound.module`
        """
        n = 0
        out = []
        while True:
            name, type_, err = self.module(n)
            if err == CSOUND_ERROR:
                break
            out.append((name, type_))
            n += 1
        return out

    def module(self, number: int) -> tuple[str, str, int]:
        """Retrieves a module name and type given a number.

        Args:
            number: the module number

        Returns:
            a tuple (name: str, type: str, errormsg: int), where name is
            the name of the module, type is one of "audio" or "midi" and
            errormsg is 0 if OK, CSOUND_ERROR if there is no module for
            the given number

        .. code::

            n = 0
            while True:
                name, type_, err = cs.module(n)
                if err == ctcsound.CSOUND_ERROR:
                    break
                print("Module %d:%s (%s)\\n" % (n, name, type_))
                n = n + 1

        .. seealso:: :meth:`Csound.modules`
        """
        name = ct.pointer(ct.c_char_p(cstring("dummy")))
        type_ = ct.pointer(ct.c_char_p(cstring("dummy")))
        err = libcsound.csoundGetModule(self.cs, number, name, type_)
        if err == CSOUND_ERROR:
            return '', '', err
        n = pstring(ct.string_at(name.contents))
        t = pstring(ct.string_at(type_.contents))
        return n, t, err

    def inputBufferSize(self) -> int:
        """Returns the number of samples in Csound's input buffer.

        .. note:: Not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundGetInputBufferSize(self.cs)

    def outputBufferSize(self) -> int:
        """Returns the number of samples in Csound's output buffer.

        .. note:: Not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundGetOutputBufferSize(self.cs)

    def inputBuffer(self) -> np.ndarray:
        """Returns the Csound audio input buffer as an ndarray.

        Enables external software to write audio into Csound before
        calling :py:meth:`performBuffer()`.

        .. note:: Not present in csound 7. Use :meth:`~Csound.spin`

        """
        _notPresentInCsound7()
        buf = libcsound.csoundGetInputBuffer(self.cs)
        size = libcsound.csoundGetInputBufferSize(self.cs)
        return _util.castarray(buf, shape=(size,))

    def outputBuffer(self) -> np.ndarray:
        """Returns the Csound audio output buffer as an ndarray.

        Returns:
            a numpy array representing the csound audio output buffer

        Enables external software to read audio from Csound after
        calling :py:meth:`performBuffer()`.

        .. note:: Not present in csound 7. Use :meth:`~Csound.spout` instead
        """
        _notPresentInCsound7()
        buf = libcsound.csoundGetOutputBuffer(self.cs)
        size = libcsound.csoundGetOutputBufferSize(self.cs)
        return _util.castarray(buf, shape=(size,))

    def spin(self) -> np.ndarray:
        """Returns the Csound audio input working buffer (spin) as an ndarray.

        Enables external software to write audio into Csound before
        calling :py:meth:`performKsmps()`.
        """
        buf = libcsound.csoundGetSpin(self.cs)
        size = self.ksmps() * self.nchnlsInput()
        return _util.castarray(buf, shape=(size,))

    def clearSpin(self) -> None:
        """Clears the input buffer (spin).

        .. note:: Not present in csound 7

        """
        _notPresentInCsound7()
        libcsound.csoundClearSpin(self.cs)

    def addSpinSample(self, frame: int, channel: int, sample: float) -> None:
        """Adds the indicated sample into the audio input working buffer (spin).

        This only ever makes sense before calling :py:meth:`performKsmps()`.
        The frame and channel must be in bounds relative to :py:meth:`ksmps()`
        and :py:meth:`nchnlsInput()`.

        .. note:: The spin buffer needs to be cleared at every k-cycle by calling
            :py:meth:`clearSpin()`.

        Args:
            frame: frame number
            channel: channel number
            sample: sample value

        .. note:: Not present in csound 7
        """
        _notPresentInCsound7()
        libcsound.csoundAddSpinSample(self.cs, frame, channel, sample)

    def setSpinSample(self, frame: int, channel: int, sample: float):
        """Sets the audio input working buffer (spin) to the indicated sample.

        This only ever makes sense before calling :py:meth:`performKsmps()`.
        The frame and channel must be in bounds relative to :py:meth:`ksmps()`
        and :py:meth:`nchnlsInput()`.

        Args:
            frame: frame number
            channel: channel number
            sample: sample value

        .. note:: Not present in csound 7
        """
        _notPresentInCsound7()
        libcsound.csoundSetSpinSample(self.cs, frame, channel, sample)

    def spout(self) -> np.ndarray:
        """Returns the address of the Csound audio output working buffer (spout).

        Enables external software to read audio from Csound after
        calling :py:meth:`performKsmps`.
        """
        buf = libcsound.csoundGetSpout(self.cs)
        size = self.ksmps() * self.nchnls()
        return _util.castarray(buf, shape=(size,))

    def spoutSample(self, frame: int, channel: int) -> float:
        """Returns one sample from the Csound audio output working buf (spout).

        Only ever makes sense after calling :py:meth:`performKsmps()`. The
        *frame* and *channel* must be in bounds relative to :py:meth:`ksmps()`
        and :py:meth:`nchnls()`.

        .. note:: Not present in csound 7. Use :meth:`~Csound.spout`
        """
        _notPresentInCsound7()
        return libcsound.csoundGetSpoutSample(self.cs, frame, channel)

    def rtRecordUserData(self) -> ct.c_void_p:
        """Returns pointer to user data pointer for real time audio input.

        .. note:: Not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundGetRtRecordUserData(self.cs)

    def rtPlayUserData(self) -> ct.c_void_p:
        """Returns pointer to user data pointer for real time audio output.

        .. note:: Not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundGetRtPlayUserData(self.cs)

    def setHostImplementedAudioIO(self, state: bool, bufSize: int = 0):
        """Sets user handling of sound I/O.

        Args:
            state: if True, will disable all default handling of sound IO
            bufSize: buffer size

        Calling this function with a :code:`True` *state* value between creation
        of the Csound object and the start of performance will disable all
        default handling of sound I/O by the Csound library, allowing the host
        application to use the spin/spout/input/output buffers directly.

        For applications using spin/spout, *bufSize* should be set to 0.
        If *bufSize* is greater than zero, the buffer size (-b) will be
        set to the integer multiple of :py:meth:`ksmps()` that is nearest to the
        value specified.

        .. note:: This method changed its name in csound 7 to ``setHostAudioIO``
        """
        libcsound.csoundSetHostImplementedAudioIO(self.cs, ct.c_int(int(state)), bufSize)

    def audioDevList(self, isOutput: bool) -> list[AudioDevice]:
        """Returns a list of available input or output audio devices.

        Args:
            isOutput: True for listing output devices, False for input

        Returns:
            a list of :class:`AudioDevice`

        Each item in the list is a dictionnary representing a device. The
        dictionnary keys are *deviceName*, *deviceId*, *rtModule* (value
        type string), *maxNchnls* (value type int), and *isOutput* (value
        type boolean).

        Must be called after an orchestra has been compiled
        to get meaningful information.
        """
        n = libcsound.csoundGetAudioDevList(self.cs, None, ct.c_int(isOutput))
        devs = (CsoundAudioDevice * n)()
        libcsound.csoundGetAudioDevList(self.cs, ct.byref(devs), ct.c_int(isOutput))
        lst = []
        for dev in devs:
            d = AudioDevice(deviceName=pstring(dev.device_name),
                            deviceId=pstring(dev.device_id),
                            rtModule=pstring(dev.rt_module),
                            maxNchnls=dev.max_nchnls,
                            isOutput=dev.isOutput == 1)
            lst.append(d)
        return lst

    def setPlayOpenCallback(self, function: _t.Callable) -> None:
        """Sets a callback for opening real-time audio playback.

        Args:
            function: a function of the form ``(void, CsoundRtAudioParams*) -> int``

        .. note:: not implemented in csound 7
        """
        _notPresentInCsound7()
        self.playOpenCbRef = PLAYOPENFUNC(function)
        libcsound.csoundSetPlayopenCallback(self.cs, self.playOpenCbRef)

    def setRtPlayCallback(self, function: _t.Callable) -> None:
        """Sets a callback for performing real-time audio playback.

        .. note:: not implemented in csound 7
        """
        _notPresentInCsound7()
        self.rtPlayCbRef = RTPLAYFUNC(function)
        libcsound.csoundSetRtplayCallback(self.cs, self.rtPlayCbRef)

    def setRecordOpenCallback(self, function: _t.Callable) -> None:
        """Sets a callback for opening real-time audio recording.

        .. note:: not implemented in csound 7
        """
        _notPresentInCsound7()
        self._callbacks['recordOpen'] = f = RECORDOPENFUNC(function)
        libcsound.csoundSetRecopenCallback(self.cs, f)

    def setRtRecordCallback(self, function: _t.Callable) -> None:
        """Sets a callback for performing real-time audio recording.

        .. note:: not implemented in csound 7
        """
        _notPresentInCsound7()
        self._callbacks['rtRecord'] = f = RTRECORDFUNC(function)
        libcsound.csoundSetRtrecordCallback(self.cs, f)

    def setRtCloseCallback(self, function):
        """Sets a callback for closing real-time audio playback and recording.

        .. note:: not implemented in csound 7
        """
        _notPresentInCsound7()
        self._callbacks['rtClose'] = f = RTCLOSEFUNC(function)
        libcsound.csoundSetRtcloseCallback(self.cs, f)

    def setAudioDevListCallback(self, function):
        """Sets a callback for obtaining a list of audio devices.

        This should be set by rtaudio modules and should not be set by hosts.
        (See :py:meth:`audioDevList()`).
        """
        self.audioDevListCbRef = AUDIODEVLISTFUNC(function)
        libcsound.csoundSetAudioDeviceListCallback(self.cs, self.audioDevListCbRef)

    #Realtime Midi I/O
    def setMidiModule(self, module: str) -> None:
        """
        Sets the current Midi IO module.

        Args:
            module: the name of the module. Possible modules depend on the platform
                and which modules have been compiled

        =========  ============================================
        Platform   MIDI Modules
        =========  ============================================
        linux      ``portmidi`` (default), ``alsa``, ``jack``
                   ``alsaraw``, ``alsaseq``, ``virtual``
        macos      ``portmidi`` (default), ``cmidi`` (coremidi)
        windows    ``portmidi`` (default), ``winmme``
        android    MIDI is not supported
        =========  ============================================

        """
        libcsound.csoundSetMIDIModule(self.cs, cstring(module))

    def setHostImplementedMidiIO(self, state: bool) -> None:
        """Called with *state* :code:`True` if the host is implementing via callbacks."""
        libcsound.csoundSetHostImplementedMIDIIO(self.cs, ct.c_int(state))

    def midiDevList(self, isOutput: bool) -> list[MidiDevice]:
        """
        Returns a list of available input or output midi devices.

        Args:
            isOutput: if True, list output devices. Otherwise, list
                input devices

        Each item in the list is :class:`MidiDevice`, with attributes
        `deviceName` (str), `interfaceName` (str), `deviceId` (str),
        `midiModule` (str), and `isOutput` (bool).

        Must be called after an orchestra has been compiled
        to get meaningful information.
        """
        n = libcsound.csoundGetMIDIDevList(self.cs, None, ct.c_int(isOutput))
        devs = (CsoundMidiDevice * n)()
        libcsound.csoundGetMIDIDevList(self.cs, ct.byref(devs), ct.c_int(isOutput))
        return [MidiDevice(deviceName=pstring(dev.device_name),
                           interfaceName=pstring(dev.interface_name),
                           deviceId=pstring(dev.device_id),
                           midiModule=pstring(dev.midi_module),
                           isOutput=(dev.isOutput == 1))
                for dev in devs]

    def setExternalMidiInOpenCallback(self, function) -> None:
        """Sets a callback for opening real-time Midi input."""
        self._callbacks['extMidiInOpen'] = f = MIDIINOPENFUNC(function)
        libcsound.csoundSetExternalMIDIInOpenCallback(self.cs, f)

    def setExternalMidiReadCallback(self, function) -> None:
        """Sets a callback for reading from real time Midi input."""
        self._callbacks['extMidiRead'] = f = MIDIREADFUNC(function)
        libcsound.csoundSetExternalMIDIReadCallback(self.cs, f)

    def setExternalMidiInCloseCallback(self, function) -> None:
        """Sets a callback for closing real time Midi input."""
        self._callbacks['extMidiInClose'] = f = MIDIINCLOSEFUNC(function)
        libcsound.csoundSetExternalMIDIInCloseCallback(self.cs, f)

    def setExternalMidiOutOpenCallback(self, function) -> None:
        """Sets a callback for opening real-time Midi input."""
        self._callbacks['extMidiOutOpen'] = f = MIDIOUTOPENFUNC(function)
        libcsound.csoundSetExternalMIDIOutOpenCallback(self.cs, f)

    def setExternalMidiWriteCallback(self, function) -> None:
        """Sets a callback for reading from real time Midi input."""
        self._callbacks['extMidiWrite'] = f = MIDIWRITEFUNC(function)
        libcsound.csoundSetExternalMIDIWriteCallback(self.cs, f)

    def setExternalMidiOutCloseCallback(self, function) -> None:
        """Sets a callback for closing real time Midi input."""
        self._callbacks['extMidiOutClose'] = f = MIDIOUTCLOSEFUNC(function)
        libcsound.csoundSetExternalMIDIOutCloseCallback(self.cs, f)

    def setExternalMidiErrorStringCallback(self, function):
        """ Sets a callback for converting Midi error codes to strings."""
        self.extMidiErrStrCbRef = MIDIERRORFUNC(function)
        libcsound.csoundSetExternalMIDIErrorStringCallback(self.cs, self.extMidiErrStrCbRef)

    def setMidiDevListCallback(self, function):
        """Sets a callback for obtaining a list of Midi devices.

        This should be set by IO plugins and should not be set by hosts.
        (See :py:meth:`midiDevList()`).
        """
        self.midiDevListCbRef = MIDIDEVLISTFUNC(function)
        libcsound.csoundSetMIDIDeviceListCallback(self.cs, self.midiDevListCbRef)

    #Score Handling
    def readScore(self, sco: str) -> int:
        """Reads, preprocesses, and loads a score from a string

        It can be called repeatedly, with the new score events
        being added to the currently scheduled ones.

        Args:
            sco: the score text to read

        Returns:
            CSOUND_SUCCESS on success, CSOUND_ERROR otherwise
        """
        return libcsound.csoundReadScore(self.cs, cstring(sco))

    def readScoreAsync(self, sco: str) -> None:
        """Asynchronous version of :py:meth:`readScore()`."""
        libcsound.csoundReadScoreAsync(self.cs, cstring(sco))

    def scoreTime(self) -> float:
        """Returns the current score time.

        The return value is the time in seconds since the beginning of
        performance.
        """
        return libcsound.csoundGetScoreTime(self.cs)

    def isScorePending(self) -> bool:
        """Tells whether Csound score events are performed or not.

        Independently of real-time Midi events (see :py:meth:`setScorePending()`).
        """
        return libcsound.csoundIsScorePending(self.cs) != 0

    def setScorePending(self, pending: bool) -> None:
        """Sets whether Csound score events are performed or not.

        Real-time events will continue to be performed. Can be used by external
        software, such as a VST host, to turn off performance of score events
        (while continuing to perform real-time events), for example to mute
        a Csound score while working on other tracks of a piece, or to play
        the Csound instruments live.
        """
        libcsound.csoundSetScorePending(self.cs, ct.c_int(pending))

    def scoreOffsetSeconds(self) -> float:
        """Returns the score time beginning midway through a Csound score.

        At this time score events will actually immediately be performed
        (see :py:meth:`setScoreOffsetSeconds()`).
        """
        return libcsound.csoundGetScoreOffsetSeconds(self.cs)

    def setScoreOffsetSeconds(self, time: float) -> None:
        """Csound score events prior to the specified time are not performed.

        Performance begins immediately at the specified time (real-time events
        will continue to be performed as they are received). Can be used by
        external software, such as a VST host, to begin score performance
        midway through a Csound score, for example to repeat a loop in a
        sequencer, or to synchronize other events with the Csound score.
        """
        libcsound.csoundSetScoreOffsetSeconds(self.cs, MYFLT(time))

    def rewindScore(self) -> None:
        """Rewinds a compiled Csound score.

        It is rewinded to the time specified with :py:meth:`setScoreOffsetSeconds()`.
        """
        libcsound.csoundRewindScore(self.cs)

    def setCscoreCallback(self, function):
        """Sets an external callback for Cscore processing.

        Pass :code:`None` to reset to the internal :code:`cscore()` function
        (which does nothing). This callback is retained after a
        :py:meth:`reset()` call.
        """
        self.cscoreCbRef = CSCOREFUNC(function)
        libcsound.csoundSetCscoreCallback(self.cs, self.cscoreCbRef)

    #def scoreSort(self, inFile, outFile):

    #def scoreExtract(self, inFile, outFile, extractFile)

    #Messages and Text
    def message(self, fmt: str, *args):
        """Displays an informational message.

        This is a workaround because :program:`ctypes` does not support
        variadic functions.
        The arguments are formatted in a string, using the python way, either
        old style or new style, and then this formatted string is passed to
        the Csound display message system.
        """
        if fmt[0] == '{':
            s = fmt.format(*args)
        else:
            s = fmt % args
        libcsound.csoundMessage(self.cs, cstring("%s"), cstring(s))

    def messageS(self, attr: int, fmt: str, *args) -> None:
        """Prints message with special attributes.

        (See msg_attr for the list of available attributes). With attr=0,
        messageS() is identical to :py:meth:`message()`.
        This is a workaround because :program:`ctypes` does not support
        variadic functions.
        The arguments are formatted in a string, using the python way, either
        old style or new style, and then this formatted string is passed to
        the csound display message system.
        """
        if fmt[0] == '{':
            s = fmt.format(*args)
        else:
            s = fmt % args
        libcsound.csoundMessageS(self.cs, attr, cstring("%s"), cstring(s))

    #def setMessageCallback():

    #def setMessageStringCallback()

    def messageLevel(self) -> int:
        """Returns the Csound message level (from 0 to 231)."""
        return libcsound.csoundGetMessageLevel(self.cs)

    def setMessageLevel(self, messageLevel: int) -> None:
        """Sets the Csound message level (from 0 to 231)."""
        libcsound.csoundSetMessageLevel(self.cs, messageLevel)

    def createMessageBuffer(self, echo=False) -> None:
        """
        Creates a buffer for storing messages printed by Csound.

        Should be called after creating a Csound instance.
        The buffer can be freed by calling :py:meth:`destroyMessageBuffer()`
        before deleting the Csound instance. You will generally want to call
        :py:meth:`cleanup()` to make sure the last messages are flushed to
        the message buffer before destroying Csound.

        Args:
            echo: if True, messages are also printed to stdout or stderr,
                depending on the type of the message, in addition to being
                stored in the buffer.

        Using the message buffer ties up the internal message callback, so
        :py:meth:`setMessageCallback()` should not be called after creating the
        message buffer.
        """
        libcsound.csoundCreateMessageBuffer(self.cs,  ct.c_int(echo))

    def firstMessage(self) -> str:
        """
        Returns the first message from the buffer.

        To keep reading the user needs to call :meth:`Csound.popFirstMessage`

        Returns:
            the first message in the buffer, or an empty string if there are
            no messages

        .. seealso:: :meth:`~Csound.readMessage`
        """
        s = libcsound.csoundGetFirstMessage(self.cs)
        return pstring(s)

    def firstMessageAttr(self) -> int:
        """Returns the attribute parameter of the first message in the buffer."""
        return libcsound.csoundGetFirstMessageAttr(self.cs)

    def readMessage(self) -> tuple[str, int]:
        """
        Reads a message from the message buffer and removes it from it

        Returns:
            a tuple ``(message: str, attribute: int)``. If there are no more
            messages, the message is an empty string and attribute is 0
        """
        cnt = self.messageCnt()
        if cnt <= 0:
            return '', 0
        msg = self.firstMessage()
        attr = self.firstMessageAttr()
        self.popFirstMessage()
        return msg, attr

    def iterMessages(self) -> _t.Iterator[tuple[str, int]]:
        """
        Iterate over the messages in the message buffer

        This operation empties the message buffer

        Returns:
            an iterator of tuples ``(message: str, attribute: int)``
        """
        for i in range(self.messageCnt()):
            msg = self.firstMessage()
            attr = self.firstMessageAttr()
            yield msg, attr
            self.popFirstMessage()

    def popFirstMessage(self) -> None:
        """Removes the first message from the buffer."""
        libcsound.csoundPopFirstMessage(self.cs)

    def messageCnt(self) -> int:
        """Returns the number of pending messages in the buffer."""
        return libcsound.csoundGetMessageCnt(self.cs)

    def destroyMessageBuffer(self) -> None:
        """Releases all memory used by the message buffer."""
        libcsound.csoundDestroyMessageBuffer(self.cs)

    #Channels, Control and Events
    def channelInfo(self, name: str) -> tuple[str, int]:
        """
        Query info about a channel

        Args:
            name: the name of the channel

        Returns:
            a tuple ``(kind: str, mode: int)``.

        If the channel does not exist kind will be an empty string and
        mode will be 0. Kind is one of 'control', 'audio', 'string',
        'pvs' or 'array'. Mode is 1 for input, 2 for output, 3 for input+output
        """
        ptr = ct.c_void_p()
        ret = libcsound.csoundGetChannelPtr(self.cs, ct.byref(ptr), cstring(name), 0)
        assert ret != 0
        if ret == CSOUND_ERROR:
            return ('', 0)
        else:
            chantype = ret & CSOUND_CHANNEL_TYPE_MASK
            mode = ret - chantype
            kind = {
                CSOUND_CONTROL_CHANNEL: 'control',
                CSOUND_AUDIO_CHANNEL: 'audio',
                CSOUND_STRING_CHANNEL: 'string'
            }.get(chantype)
            if kind is None:
                raise RuntimeError(f"Got invalid channel kind: {chantype}")
            return kind, mode

    def channelPtr(self, name: str, kind: str, mode='r'
                   ) -> tuple[np.ndarray | ct.c_char_p | ct.c_void_p | None, str]:
        """
        Returns a pointer to the specified channel and an error message.

        Args:
            name: the name of the channel
            kind: one of 'control', 'audio', 'string'
            mode: one of 'r' (read=input), 'w' (write=output), 'rw' (both read and write).
                The mode is determined from the perspective of the csound process, so a
                channel declared as input ('r') will read information from the host,
                a channel declared as output ('w') will write information to the host.

        Returns:
            a tuple (pointer, errormsg)

        ==============  ====================
        Channel Kind    Returned Pointer
        ==============  ====================
        control         numpy array, float64, size 1
        audio           numpy array, float64, size ``ksmps``
        string          ctypes.c_char_p
        pvs             ctypes.c_void_p
        array           numpy array, float64 (arbitrary shape)
        ==============  ====================

        The error message is either an empty string or a string describing the error.

        The channel is created first if it does not exist yet.

        If the channel already exists, it must match the data type
        (control, audio, or string). The mode bits are
        OR'd with the new value, meaning that **a channel declared in csound
        as input can be made to be input+output if called with 'rw' as mode**.

        .. note::

            Operations on the pointer are not thread-safe by default. The host is
            required to take care of thread-safety by retrieving the channel lock
            with :py:meth:`channelLock()` and using :py:meth:`spinLock()` and
            :py:meth:`spinUnlock()` to protect access to the pointer.

            Optionally, use the methods :py:meth:`setControlChannel`,
            :py:meth:`controlChannel`, :py:meth:`setAudioChannel`, etc., which
            are threadsafe by default

        See Top/threadsafe.c in the Csound library sources for
        examples.
        """
        output = 'w' in mode
        input = 'r' in mode
        chantype = _util.packChannelType(kind=kind, output=output, input=input)
        return self._channelPtr(name, chantype)

    def _channelPtr(self, name: str, type_: int) -> tuple[np.ndarray | ct.c_char_p | ct.c_void_p | None, str]:
        """Get a pointer to the specified channel and an error message.

        The channel is created first if it does not exist yet.
        type_ must be the bitwise OR of exactly one of the following values,

        CSOUND_CONTROL_CHANNEL
            control data (one MYFLT value) - (MYFLT **) pp
        CSOUND_AUDIO_CHANNEL
            audio data (ksmps() MYFLT values) - (MYFLT **) pp
        CSOUND_STRING_CHANNEL
            string data as a STRINGDAT structure - (STRINGDAT **) pp
            (see string_data() and set_string_data())
        CSOUND_ARRAY_CHANNEL
            array data as an ARRAYDAT structure - (ARRAYDAT **) pp
            (see array_data(), set_array_data(), and init_array_channel())
        CSOUND_PVS_CHANNEL
            pvs data as a PVSDATEXT structure - (PVSDATEXT **) pp
            (see pvs_data(), set_pvs_data(), and init_pvs_channel())
        and at least one of these:

        CSOUND_INPUT_CHANNEL
        CSOUND_OUTPUT_CHANNEL

        If the channel is a control or an audio channel, the pointer is
        translated to an ndarray of MYFLT. If the channel is a string channel,
        the pointer is casted to ct.c_char_p. The error message is either
        an empty string or a string describing the error that occured.

        If the channel already exists, it must match the data type
        (control, string, audio, pvs or array), however, the input/output bits
        are OR'd with the new value. Note that audio and string channels
        can only be created after calling compileCommandLine(), because the
        storage size is not known until then.

        Return value is zero on success, or a negative error code,

        CSOUND_MEMORY
            there is not enough memory for allocating the channel
        CSOUND_ERROR
            the specified name or type is invalid

        or, if a channel with the same name but incompatible type
        already exists, the type of the existing channel. In the case
        of any non-zero return value, the pointer is set to None.
        Note: to find out the type of a channel without actually
        creating or changing it, set type_ to zero, so that the return
        value will be either the type of the channel, or CSOUND_ERROR
        if it does not exist.

        Operations on the pointer are not thread-safe by default. The host is
        required to take care of threadsafety by using lock_channel() and
        unlock_channel() to protect access to the pointer.

        See Top/threadsafe.c in the Csound library sources for
        examples. Optionally, use the channel get/set functions
        provided below, which are threadsafe by default.
        """
        # ptr = ct.c_void_p()
        ptr = ct.POINTER(MYFLT)()
        chantype = type_ & CSOUND_CHANNEL_TYPE_MASK
        if chantype not in (CSOUND_STRING_CHANNEL, CSOUND_AUDIO_CHANNEL, CSOUND_CONTROL_CHANNEL):
            raise ValueError(f"Invalid channel type: {type_}")
        err = ''
        ret = libcsound.csoundGetChannelPtr(self.cs, ct.byref(ptr), cstring(name), type_)
        if ret == CSOUND_SUCCESS:
            if chantype == CSOUND_STRING_CHANNEL:
                return ct.cast(ptr, STRINGDAT_p), err

            if chantype == CSOUND_AUDIO_CHANNEL:
                length = libcsound.csoundGetKsmps(self.cs)
            else:
                assert chantype == CSOUND_CONTROL_CHANNEL
                length = 1
            return _util.castarray(ptr, shape=(length,)), err

        if ret == CSOUND_MEMORY:
            err = 'Not enough memory for allocating channel'
        elif ret == CSOUND_ERROR:
            err = 'The specified channel name or type is not valid'
        elif ret == CSOUND_CONTROL_CHANNEL:
            err = 'A control channel named {} already exists'.format(name)
        elif ret == CSOUND_AUDIO_CHANNEL:
            err = 'An audio channel named {} already exists'.format(name)
        elif ret == CSOUND_STRING_CHANNEL:
            err = 'A string channel named {} already exists'.format(name)
        else:
            err = 'Unknown error'
        return None, err

    def allocatedChannels(self) -> list[ChannelInfo]:
        # TODO: create a Dataclass to hold the channel info instead of
        # an ad-hoc dict
        chanlist, err = self.listChannels()
        if err:
            raise RuntimeError(f"Error while getting a list of channels: {err}")
        assert chanlist is not None
        n = len(chanlist)
        out = []
        for chaninfo in chanlist:
            assert isinstance(chaninfo, ControlChannelInfo)
            kind, mode = _util.unpackChannelType(chaninfo.type)
            hints = {'min': chaninfo.hints.min,
                     'max': chaninfo.hints.max,
                     'width': chaninfo.hints.width,
                     'height': chaninfo.hints.height}
            out.append(ChannelInfo(name=chaninfo.name, kind=chaninfo.type, mode=mode, hints=hints))
            # out.append({'name': chaninfo.name, 'type': chaninfo.type, 'hints': hints})
        self.deleteChannelList(chanlist)
        return out

    def listChannels(self):
        """Returns a pointer and an error message.

        The pointer points to a list of ControlChannelInfo objects for allocated
        channels. A ControlChannelInfo object contains the channel
        characteristics. The error message indicates if there is not enough
        memory for allocating the list or it is an empty string if there is no
        error. In the case of no channels or an error, the pointer is
        :code:`None`.

        Notes: the caller is responsible for freeing the list returned by the
        C API with :py:meth:`deleteChannelList()`. The name pointers may become
        invalid after calling :py:meth:`reset()`.
        """
        cInfos = None
        err = ''
        ptr = ct.cast(ct.POINTER(ct.c_int)(), ct.POINTER(ControlChannelInfo))
        n = libcsound.csoundListChannels(self.cs, ct.byref(ptr))
        if n == CSOUND_MEMORY :
            err = 'There is not enough memory for allocating the list'
        if n > 0:
            cInfos = ct.cast(ptr, ct.POINTER(ControlChannelInfo * n)).contents
        return cInfos, err

    def deleteChannelList(self, lst):
        """Releases a channel list previously returned by :py:meth:`listChannels()`."""
        ptr = ct.cast(lst, ct.POINTER(ControlChannelInfo))
        libcsound.csoundDeleteChannelList(self.cs, ptr)

    def setControlChannelHints(self, name: str, hints: ControlChannelHints) -> int:
        """
        Sets parameters hints for a control channel.

        Args:
            name: name of the channel
            hints: the hints to set

        Returns:
            CSOUND_SUCCSESS (0) if ok, CSOUND_ERROR if the channel does not exist,
            it is not a control channel or the parameters are invalid, CSOUND_MEMORY
            if could not allocate memory

        These hints have no internal function but can be used by front ends to
        construct GUIs or to constrain values. See the ControlChannelHints
        structure for details.
        """
        return libcsound.csoundSetControlChannelHints(self.cs, cstring(name), hints)

    def controlChannelHints(self, name: str) -> tuple[ControlChannelHints | None, int]:
        """Returns special parameters (if any) of a control channel.

        Those parameters have been previously set with
        :py:meth:`setControlChannelHints()` or the :code:`chnparams` opcode.

        The return values are a ControlChannelHints structure and
        CSOUND_SUCCESS if the channel exists and is a control channel,
        otherwise, :code:`None` and an error code are returned.
        """
        hints = ControlChannelHints()
        ret = libcsound.csoundGetControlChannelHints(self.cs, cstring(name), ct.byref(hints))
        if ret != CSOUND_SUCCESS:
            hints = None
        return hints, ret

    def lockChannel(self, name: str) -> None:
        lock = self.channelLock(name)
        if not lock:
            raise ValueError(f"Channel {name} not found")
        self._channelLocks[name] = lock
        self.spinLock(lock)

    def channelExists(self, name: str):
        kind, mode = self.channelInfo(name)
        return len(kind) > 0

    def unlockChannel(self, name: str):
        lock = self._channelLocks.get(name)
        if not lock:
            if not self.channelExists(name):
                raise ValueError(f"Channel {name} does not exist")
            else:
                raise ValueError(f"Channel {name} was not locked")
        self.spinUnlock(lock)

    def channelLock(self, name: str):
        """Recovers a pointer to a lock for the specified channel called *name*.

        The returned lock can be locked/unlocked  with the :py:meth:`spinLock()`
        and :py:meth:`spinUnLock()` functions.
        Returns the address of the lock or NULL if the channel does not exist.
        """
        return libcsound.csoundGetChannelLock(self.cs, cstring(name))

    def controlChannel(self, name: str) -> tuple[float, int]:
        """Retrieves the value of control channel identified by *name*.

        Args:
            name: the name of the channel

        Returns:
            a tuple (value: float, returncode: int)

        """
        err = ct.c_int(0)
        ret = libcsound.csoundGetControlChannel(self.cs, cstring(name), ct.byref(err))
        return ret, err.value

    def setControlChannel(self, name: str, val: float) -> None:
        """Sets the value of control channel identified by *name*.

        Args:
            name: name of the channel
            val: the new value of the channel
        """
        libcsound.csoundSetControlChannel(self.cs, cstring(name), MYFLT(val))

    def audioChannel(self, name: str, samples: np.ndarray) -> None:
        """
        Copies the audio channel identified by *name* into ndarray samples.

        Args:
            name: the name of the channel
            samples: an array of float64 to hold the audio samples. It should
                be a 1D array at least ``ksmps`` in size. If not given a new
                array is created

        Returns:
            the np.ndarray holding the samples. If an array was passed as argument
            the same array is returned

        .. seealso:: :py:meth:`setAudioChannel`
        """
        if samples is None:
            samples = np.zeros((self.ksmps(),), dtype=float)
        else:
            if len(samples.shape) > 1:
                raise ValueError(f"Only 1-dimensional arrays supported, got {samples}")
            if len(samples) < self.ksmps():
                raise ValueError(f"The given array is too small (ksmps: {self.ksmps()}, "
                                f"size of the given array: {len(samples)}")
        ptr = samples.ctypes.data_as(ct.POINTER(MYFLT))
        libcsound.csoundGetAudioChannel(self.cs, cstring(name), ptr)

    def setAudioChannel(self, name: str, samples: np.ndarray) -> None:
        """Sets the audio channel *name* with data from the ndarray *samples*.

        Args:
            name: the name of the channel
            samples: an array of float64 to hold the audio samples. It should
                be a 1D array at least ``ksmps`` in size

        .. seealso:: :py:meth:`audioChannel`
        """
        if len(samples.shape) > 1:
            raise ValueError(f"Only 1-dimensional arrays supported, got {samples}")
        if len(samples) < self.ksmps():
            raise ValueError(f"The given array is too small (ksmps: {self.ksmps()}, "
                             f"size of the given array: {len(samples)}")
        ptr = samples.ctypes.data_as(ct.POINTER(MYFLT))
        libcsound.csoundSetAudioChannel(self.cs, cstring(name), ptr)

    def stringChannel(self, name: str) -> str:
        """Get a string from the given channel

        Args:
            name: the name of the channel. It must be already created
                and be of string type

        Returns:
            the string value of the channel
        """
        cname = cstring(name)
        n = libcsound.csoundGetChannelDatasize(self.cs, cname)
        if n <= 0:
            return ""
        s = ct.create_string_buffer(n)
        libcsound.csoundGetStringChannel(self.cs, cname, ct.cast(s, ct.POINTER(ct.c_char)))
        return pstring(ct.string_at(s))

    def setStringChannel(self, name: str, string: str) -> None:
        """Sets the string channel identified by *name* with *string*."""
        libcsound.csoundSetStringChannel(self.cs, cstring(name), cstring(string))

    def channelDatasize(self, name: str) -> int:
        """Returns the size of data stored in a channel.

        Args:
            name: the name of the channel

        For string channels this might change if the channel space gets
        reallocated. Since string variables use dynamic memory allocation in
        Csound6, this function can be called to get the space required for
        :py:meth:`stringChannel()`.
        """
        return libcsound.csoundGetChannelDatasize(self.cs, cstring(name))

    def setInputChannelCallback(self, function) -> None:
        """Sets the function to call whenever the :code:`invalue` opcode is used."""
        self.inputChannelCbRef = CHANNELFUNC(function)
        libcsound.csoundSetInputChannelCallback(self.cs, self.inputChannelCbRef)

    def setOutputChannelCallback(self, function):
        """Sets the function to call whenever the :code:`outvalue` opcode is used."""
        self.outputChannelCbRef = CHANNELFUNC(function)
        libcsound.csoundSetOutputChannelCallback(self.cs, self.outputChannelCbRef)

    def setPvsChannel(self, fin: PvsdatExt, name: str) -> int:
        """Sends a PvsdatExt *fin* to the :code:`pvsin` opcode (f-rate) for channel *name*.

        Args:
            fin: the pvs data
            name: name of the channel

        Returns:
            zero on success, CSOUND_ERROR if the index is invalid or
            fsig framesizes are incompatible.or CSOUND_MEMORY if there
            is not enough memory to extend the bus.
        """
        return libcsound.csoundSetPvsChannel(self.cs, ct.byref(fin), cstring(name))

    def pvsChannel(self, fout: PvsdatExt, name: str) -> int:
        """Receives a PvsdatExt *fout* from the :code:`pvsout` opcode (f-rate) at channel *name*.

        Returns:
            zero on success, CSOUND_ERROR if the index is invalid or
            if fsig framesizes are incompatible; CSOUND_MEMORY if there is
            not enough memory to extend the bus.
        """
        return libcsound.csoundGetPvsChannel(self.cs, ct.byref(fout), cstring(name))

    def scoreEvent(self,
                   kind: str,
                   pfields: tuple[float, ...] | list[float] | np.ndarray
                   ) -> int:
        """Sends a new score event (blocking)

        Args:
            kind: score event type ('a', 'i', 'q', 'f', or 'e').
            pfields: a tuple, a list, or an ndarray of MYFLTs with all the
                pfields for this event, starting with p1

        Returns:
            0 on success, an error code on failure
        """
        p = np.asarray(pfields, dtype=MYFLT)
        ptr = p.ctypes.data_as(ct.POINTER(MYFLT))
        numfields = ct.c_long(p.size)
        return libcsound.csoundScoreEvent(self.cs, cchar(kind), ptr, numfields)

    def scoreEventAsync(self,
                        kind: str,
                        pfields: tuple[float, ...] | list[float] | np.ndarray) -> None:
        """Asynchronous version of :py:meth:`scoreEvent()`.

        Args:
            kind: score event type ('a', 'i', 'q', 'f', or 'e').
            pfields: a tuple, a list, or an ndarray of MYFLTs with all the
                pfields for this event, starting with p1

        """
        p = np.asarray(pfields, dtype=MYFLT)
        ptr = p.ctypes.data_as(ct.POINTER(MYFLT))
        numfields = ct.c_long(p.size)
        libcsound.csoundScoreEventAsync(self.cs, cchar(kind), ptr, numfields)

    def scoreEventAbsolute(self,
                           kind: str,
                           pfields: tuple[float, ...] | list[float] | np.ndarray,
                           timeOffset: float = 0.) -> int:
        """Like :py:meth:`scoreEvent()`, this function inserts a score event.

        Args:
            kind: score event type ('a', 'i', 'q', 'f', or 'e').
            pfields: a tuple, a list, or an ndarray of MYFLTs with all the
                pfields for this event, starting with p1
            timeOffset: the time offset to use as reference

        Returns:
            0 on success, an error code otherwise

        The event is inserted at absolute time with respect to the start of
        performance, or from an offset set with timeOffset.

        .. note:: This method is not present in csound 7. Use
        """
        _notPresentInCsound7()
        p = np.asarray(pfields, dtype=MYFLT)
        ptr = p.ctypes.data_as(ct.POINTER(MYFLT))
        numFields = ct.c_long(p.size)
        return libcsound.csoundScoreEventAbsolute(self.cs, cchar(kind), ptr, numFields, ct.c_double(timeOffset))

    def scoreEventAbsoluteAsync(self, type_: str, pfields, timeOffset: float = 0.) -> None:
        """
        Asynchronous version of :py:meth:`scoreEventAbsolute()`.

        Args:
            kind: score event type ('a', 'i', 'q', 'f', or 'e').
            pfields: a tuple, a list, or an ndarray of MYFLTs with all the
                pfields for this event, starting with p1
            timeOffset: the time offset to use as reference
        """
        p = np.asarray(pfields, dtype=MYFLT)
        ptr = p.ctypes.data_as(ct.POINTER(MYFLT))
        numFields = ct.c_long(p.size)
        libcsound.csoundScoreEventAbsoluteAsync(self.cs, cchar(type_), ptr, numFields, ct.c_double(timeOffset))

    def setEndMarker(self, time: float) -> None:
        """
        Add an end event to the score

        This stops the performance at the given time

        Args:
            time: time to add the end event

        .. rubric:: Example

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
            # Without the end marker this would render for ever
            while not csound.performKsmps():
                pass
        """
        self.scoreEvent("e", [0, time])

    def eventString(self, message: str, block=True) -> None:
        """Send a new event as a string.

        Args:
            message: the message to send. Multiple events separated by newlines
                are possible. Score preprocessing (carry, etc.) is applied
            block: if true, the operation is run blocking

        .. note::

            This method does not exist natively in csound 6, it just calls
            either :py:meth:`inputMessage` or :py:meth:`inputMessageAsync`
            respectively, depending on the value of the `block` param. It
            exists natively in csound 7 and was backported to csound 6 for
            forward compatibility

        """
        if block:
            self.inputMessage(message)
        else:
            self.inputMessageAsync(message)

    def inputMessage(self, message: str) -> None:
        """
        Send a new event as a string, blocking

        The syntax is the same as a score line

        .. note:: use :py:meth:`eventString()` for compatibility with csound 7

        .. seealso:: :py:meth:`inputMessageAsync`
        """
        libcsound.csoundInputMessage(self.cs, cstring(message))

    def inputMessageAsync(self, message: str) -> None:
        """
        Asynchronous version of :py:meth:`inputMessage()`

        .. seealso:: :py:meth:`inputMessage`
        """
        libcsound.csoundInputMessageAsync(self.cs, cstring(message))

    def killInstance(self, instr: float | int | str, mode: int, allowRelease=True):
        """
        Kills off one or more running instances of an instrument.

        Args:
            instr: the instrument number or the name
            mode: which instance/instances to kill (see below)
            allowRelease: the killed instances are allowed to stay alive
                to perform the release part of an amplitude envelope

        ======= ===================
        Mode    Meaning
        ======= ===================
        0       killall instances
        1       oldest only
        2       newest only
        4       turnoff notes with exactly matching fractional instr number
        8       turnoff notes with indefinite duration (p3 < 0)
        ======= ===================

        Modes can be combined. For example 1+4 will kill the oldest event with
        exactly matching fractional instr. A mode of 2+8 will kill the newest
        event of indefinite duration matching the given instr

        .. note::

            The underlying function in the csound API has been removed
            in csound 7. This method can still be used both in csound 6 and
            csound 7, but in the latter it is implemented in csound code
        """
        if isinstance(instr, str):
            instrnum, instrname = 0, cstring(instr)
        else:
            instrnum, instrname = instr, cstring('')
        return libcsound.csoundKillInstance(self.cs, MYFLT(instrnum), instrname, mode, ct.c_int(int(allowRelease)))

    def registerSenseEventCallback(self, function, userData):
        """Registers a function to be called by :code:`sensevents()`.

        This function will be called once in every control period. Any number
        of functions may be registered, and will be called in the order of
        registration.

        The callback function takes two arguments: the Csound instance
        pointer, and the *userData* pointer as passed to this function.

        This facility can be used to ensure a function is called synchronously
        before every csound control buffer processing. It is important
        to make sure no blocking operations are performed in the callback.
        The callbacks are cleared on :py:meth:`cleanup()`.

        Returns zero on success.

        .. note:: this method has been removed in csound 7
        """
        _notPresentInCsound7()
        self.senseEventCbRef = SENSEFUNC(function)
        return libcsound.csoundRegisterSenseEventCallback(self.cs, self.senseEventCbRef, ct.py_object(userData))

    def keyPress(self, c: int | str) -> None:
        """Sets the ASCII code of the most recent key pressed.

        This value is used by the :code:`sensekey` opcode if a callback for
        returning keyboard events is not set (see
        :py:meth:`registerKeyboardCallback()`).
        """
        if isinstance(c, str):
            c = ord(c[0])
        libcsound.csoundKeyPress(self.cs, cchar(c))

    def registerKeyboardCallback(self, function, userdata, typemask):
        """Registers general purpose callback functions for keyboard events.

        Args:
            function: the callback
            userData: data passed to the callback
            typemask: the callback type, one of CSOUND_CALLBACK_KBD_EVENT or
                CSOUND_CALLBACK_KBD_TEXT

        These callbacks are called on every control period by the sensekey
        opcode.

        The callback is preserved on :py:meth:`reset()`, and multiple
        callbacks may be set and will be called in reverse order of
        registration. If the same function is set again, it is only moved
        in the list of callbacks so that it will be called first, and the
        user data and type mask parameters are updated. *type_* can be the
        bitwise OR of callback types for which the function should be called,
        or zero for all types.

        Returns zero on success, ``CSOUND_ERROR`` if the specified function
        pointer or type mask is invalid, and ``CSOUND_MEMORY`` if there is not
        enough memory.

        The callback function takes the following arguments:

        * **userData**: the "user data" pointer, as specified when setting the callback

        * **p**: data pointer, depending on the callback type

        * **typemask**: callback type, can be one of the following (more may be added in
          future versions of Csound)

          * ``CSOUND_CALLBACK_KBD_EVENT``

          * ``CSOUND_CALLBACK_KBD_TEXT``: called by the :code:`sensekey` opcode
            to fetch key codes. The data pointer is a pointer to a single
            value of type `int`, for returning the key code, which can be in
            the range 1 to 65535, or 0 if there is no keyboard event.

            For ``CSOUND_CALLBACK_KBD_EVENT``, both key press and release
            events should be returned (with 65536 (0x10000) added to the
            key code in the latter case) as unshifted ASCII codes.
            CSOUND_CALLBACK_KBD_TEXT expects key press events only as the
            actual text that is typed.

        The return value should be zero on success, negative on error, and
        positive if the callback was ignored (for example because the type is
        not known).
        """
        if typemask == CSOUND_CALLBACK_KBD_EVENT:
            self.keyboardCbEventRef = KEYBOARDFUNC(function)
        else:
            self.keyboardCbTextRef = KEYBOARDFUNC(function)
        return libcsound.csoundRegisterKeyboardCallback(self.cs, KEYBOARDFUNC(function), ct.py_object(userdata), ct.c_uint(typemask))

    def removeKeyboardCallback(self, function):
        """Removes a callback previously set with :py:meth:`registerKeyboardCallback()`."""
        libcsound.csoundRemoveKeyboardCallback(self.cs, KEYBOARDFUNC(function))

    #Tables
    def tableLength(self, table: int) -> int:
        """Returns the length of a function table.

        Args:
            table: table number

        Returns:
            the length of the table, -1 of the table does not exist

        The returned length does not include the guard point
        """
        return libcsound.csoundTableLength(self.cs, table)

    def tableGet(self, table: int, index: int) -> float:
        """Returns the value of a slot in a function table.

        Args:
            table: table number
            index: index within the table

        Returns:
            the value of the table at the given index

        The *table* number and *index* are assumed to be valid.

        .. note:: This method is not present in csound 7. Use :py:meth:`table()`
            directly
        """
        _notPresentInCsound7()
        return libcsound.csoundTableGet(self.cs, table, index)

    def tableSet(self, table: int, index: int, value: float) -> None:
        """Sets the value of a slot in a function table.

        The *table* number and *index* are assumed to be valid.

        .. note:: This method is not present in csound 7. Use :py:meth:`table()`
            directly

        """
        _notPresentInCsound7()
        libcsound.csoundTableSet(self.cs, table, index, MYFLT(value))

    def tableCopyOut(self, table: int, dest: np.ndarray) -> None:
        """Copies the contents of a function table into a supplied ndarray *dest*.

        Args:
            table: table number
            dest: where to put the contents of the table (needs to have enough space)

        .. note:: not present in csound 7. Use :py:meth:`table()` instead
        """
        _notPresentInCsound7()
        ptr = dest.ctypes.data_as(ct.POINTER(MYFLT))
        libcsound.csoundTableCopyOut(self.cs, table, ptr)

    def tableCopyOutAsync(self, table: int, dest: np.ndarray):
        """
        Asynchronous version of :py:meth:`tableCopyOut()`.

        .. note:: not present in csound 7. Use :py:meth:`table()` instead
        """
        _notPresentInCsound7()
        ptr = dest.ctypes.data_as(ct.POINTER(MYFLT))
        libcsound.csoundTableCopyOutAsync(self.cs, table, ptr)

    def tableCopyIn(self, table: int, src: np.ndarray):
        """Copies the contents of an ndarray *src* into a given function *table*.

        The *table* number is assumed to be valid, and the table needs to
        have sufficient space to receive all the array contents.

        .. note:: not present in csound 7. Use :py:meth:`table()` instead

        """
        _notPresentInCsound7()
        ptr = src.ctypes.data_as(ct.POINTER(MYFLT))
        libcsound.csoundTableCopyIn(self.cs, table, ptr)

    def tableCopyInAsync(self, table: int, src: np.ndarray):
        """Asynchronous version of :py:meth:`tableCopyIn()`.

        .. note:: not present in csound 7. Use :py:meth:`table()` instead
        """
        _notPresentInCsound7()
        ptr = src.ctypes.data_as(ct.POINTER(MYFLT))
        libcsound.csoundTableCopyInAsync(self.cs, table, ptr)

    def table(self, table: int) -> np.ndarray | None:
        """Returns a pointer to function as an ndarray.

        Returns:
            a numpy array pointing to the actual data, or None if the
            table does not exist. The ndarray does not include the
            guard point.
        """
        ptr = ct.POINTER(MYFLT)()
        size = libcsound.csoundGetTable(self.cs, ct.byref(ptr), table)
        if size < 0:
            return None
        return _util.castarray(ptr, shape=(size,))

    def tableArgs(self, table: int) -> np.ndarray | None:
        """Returns a pointer to the args used to generate a function table.

        The pointer is returned as an ndarray. If the table does not exist,
        :code:`None` is returned.

        .. note::

            The argument list starts with the GEN number and is followed by
            its parameters. eg. ``f 1 0 1024 10 1 0.5``  yields the list
            ``{10.0, 1.0, 0.5}``
        """
        ptr = ct.POINTER(MYFLT)()
        size = libcsound.csoundGetTableArgs(self.cs, ct.byref(ptr), table)
        if size < 0:
            return None
        return _util.castarray(ptr, shape=(size,))

    def isNamedGEN(self, num: int ) -> int:
        """Checks if a given GEN number *num* is a named GEN.

        Returns:
            the length of the gen's name, or 0 if the gen does not exist

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundIsNamedGEN(self.cs, num)

    def namedGEN(self, num: int, nameLen: int) -> str:
        """Gets the GEN name from a GEN number, if this is a named GEN.

        The final parameter is the max len of the string.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        s = ct.create_string_buffer(nameLen)
        libcsound.csoundGetNamedGEN(self.cs, num, s, nameLen)
        return pstring(ct.string_at(s, nameLen))

    #Function Table Display
    def setIsGraphable(self, isGraphable: bool) -> bool:
        """Tells Csound whether external graphic table display is supported.

        Return the previously set value (initially False).
        """
        ret = libcsound.csoundSetIsGraphable(self.cs, ct.c_int(int(isGraphable)))
        return (ret != 0)

    def setMakeGraphCallback(self, function):
        """Called by external software to set Csound's MakeGraph function."""
        self._callbacks['makeGraph'] = _ = MAKEGRAPHFUNC(function)
        libcsound.csoundSetMakeGraphCallback(self.cs, _)

    def setDrawGraphCallback(self, function):
        """Called by external software to set Csound's DrawGraph function."""
        self._callbacks['drawGraph'] = _ = DRAWGRAPHFUNC(function)
        libcsound.csoundSetDrawGraphCallback(self.cs, _)

    def setKillGraphCallback(self, function):
        """Called by external software to set Csound's KillGraph function."""
        self._callbacks['killGraph'] = _ = KILLGRAPHFUNC(function)
        libcsound.csoundSetKillGraphCallback(self.cs, _)

    def setExitGraphCallback(self, function):
        """Called by external software to set Csound's ExitGraph function."""
        self._callbacks['exitGraph'] = _ = EXITGRAPHFUNC(function)
        libcsound.csoundSetExitGraphCallback(self.cs, _)

    #Opcodes
    def namedGens(self) -> list[tuple[str, int]]:
        """Finds the list of named gens

        Returns:
            a list of tuples of the form ``(name: str, num: int)``

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        lst = []
        ptr = libcsound.csoundGetNamedGens(self.cs)
        ptr = ct.cast(ptr, ct.POINTER(NamedGen))
        while (ptr):
            ng = ptr.contents
            lst.append((pstring(ng.name), int(ng.genum)))
            ptr = ng.next
        return lst

    def getOpcodes(self) -> list[OpcodeDef]:
        """
        Get a list of all defined opcodes

        This can be used instead of :meth:`Csound.newOpcodeList` and
        :meth:`Csound.disposeOpcodeList`

        Returns:
            a list of OpcodeDef, a dataclass with attributes ``name``: ``str``,
            ``outtypes``: ``str``, ``intypes``: ``str``, ``flags``: ``int``
        """
        opcodes, numopcodes = self.newOpcodeList()
        if opcodes is None:
            return []
        out = []
        _ = _util.asciistr
        for n in range(numopcodes):
            opc = opcodes[n]
            opcodedef = OpcodeDef(name=_(opc.opname), outtypes=_(opc.outypes), intypes=_(opc.intypes), flags=int(opc.flags))
            out.append(opcodedef)
        self.disposeOpcodeList(opcodes)
        return out

    def newOpcodeList(self) -> tuple[ct.Array[OpcodeListEntry] | None, int]:
        """Gets an alphabetically sorted list of all opcodes.

        Returns:
            a tuple (entries: array[OpcodeListEntry], numentries: int)

        Should be called after externals are loaded by :py:meth:`compileCommandLine()`.
        Returns a pointer to the list of OpcodeListEntry structures and the
        number of opcodes, or a negative error code on  failure.
        Make sure to call :py:meth:`disposeOpcodeList()` when done with the
        list.
        """
        ptr = ct.cast(ct.POINTER(ct.c_int)(), ct.POINTER(OpcodeListEntry))
        n = libcsound.csoundNewOpcodeList(self.cs, ct.byref(ptr))
        if n <= 0:
            return None, 0
        return ct.cast(ptr, ct.POINTER(OpcodeListEntry * n)).contents, n

    def disposeOpcodeList(self, lst):
        """Releases an opcode list."""
        ptr = ct.cast(lst, ct.POINTER(OpcodeListEntry))
        libcsound.csoundDisposeOpcodeList(self.cs, ptr)

    def appendOpcode(self, opname, dsblksiz, flags, thread, outypes, intypes, iopfunc, kopfunc, aopfunc):
        """
        Appends an opcode implemented by external software.

        This opcode is added to Csound's internal opcode list.

        The opcode list is extended by one slot, and the parameters are copied
        into the new slot.

        Args:
            opname: opcode name
            dsblksiz: ``sizeof`` the structure used for the opcode.
            flags: flags passed, normally 0
            outtypes: a string defining the output types of the opcode
            intypes: string defining input types
            initfunc: func called at init, with the form (CSOUND *, void *),
                where the second pointer is a pointer to a struct used for the opcode
            perffunc: func called at perf time, with the same form as the initfunc
            deinitfunc: func called at deinit, same form as initfunc

        Returns:
            zero on success
        """
        return libcsound.csoundAppendOpcode(self.cs, cstring(opname), dsblksiz, flags, thread,
                                            cstring(outypes), cstring(intypes),
                                            OPCODEFUNC(iopfunc),
                                            OPCODEFUNC(kopfunc),
                                            OPCODEFUNC(aopfunc))

    #Threading and Concurrency
    def setYieldCallback(self, function):
        """
        Called by external software to set a yield function.

        This callback is used for checking system events, yielding cpu time
        for coopertative multitasking, etc.

        This function is optional. It is often used as a way to 'turn off'
        Csound, allowing it to exit gracefully. In addition, some operations
        like utility analysis routines are not reentrant and you should use
        this function to do any kind of updating during the operation.

        Returns an 'OK to continue' boolean.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        self.yieldCbRef = YIELDFUNC(function)
        libcsound.csoundSetYieldCallback(self.cs, self.yieldCbRef)

    def createThread(self, function, userdata):
        """Creates and starts a new thread of execution.

        Returns an opaque pointer that represents the thread on success,
        or :code:`None` for failure.
        The *userdata* pointer is passed to the thread routine.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        ret = libcsound.csoundCreateThread(THREADFUNC(function), ct.py_object(userdata))
        if (ret):
            return ret
        return None

    def createThread2(self, function, stack, userdata):
        """Creates and starts a new thread of execution with a user-defined stack size.

        Returns an opaque pointer that represents the thread on success,
        or :code:`None` for failure.
        The *userdata* pointer is passed to the thread routine.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        ret = libcsound.csoundCreateThread2(THREADFUNC(function),
                ct.c_uint(stack), ct.py_object(userdata))
        if (ret):
            return ret
        return None

    def currentThreadId(self) -> int | None:
        """Returns the ID of the currently executing thread, or :code:`None`
        for failure.

        NOTE: The return value can be used as a pointer
        to a thread object, but it should not be compared
        as a pointer. The pointed to values should be compared,
        and the user must free the pointer after use.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        ret = libcsound.csoundGetCurrentThreadId()
        if (ret):
            return ret
        return None

    def joinThread(self, thread):
        """Waits until the indicated thread's routine has finished.

        Returns the value returned by the thread routine.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundJoinThread(thread)

    def createThreadLock(self) -> ct.c_void_p | None:
        """Creates and returns a monitor object, or :code:`None` if not successful.

        The object is initially in signaled (notified) state.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        ret = libcsound.csoundCreateThreadLock()
        if (ret):
            return ret
        return None

    def waitThreadLock(self, lock: ct.c_void_p, milliseconds: int) -> int:
        """Waits on the indicated monitor object for the indicated period.

        The function returns either when the monitor object is notified,
        or when the period has elapsed, whichever is sooner; in the first case,
        zero is returned.

        If *milliseconds* is zero and the object is not notified, the function
        will return immediately with a non-zero status.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundWaitThreadLock(lock, ct.c_uint(milliseconds))

    def waitThreadLockNoTimeout(self, lock: ct.c_void_p) -> None:
        """Waits on the indicated monitor object until it is notified.

        This function is similar to :py:meth:`waitThreadLock()` with an infinite
        wait time, but may be more efficient.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        libcsound.csoundWaitThreadLockNoTimeout(lock)

    def notifyThreadLock(self, lock: ct.c_void_p) -> None:
        """Notifies the indicated monitor object.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        libcsound.csoundNotifyThreadLock(lock)

    def destroyThreadLock(self, lock: ct.c_void_p):
        """Destroys the indicated monitor object.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        libcsound.csoundDestroyThreadLock(lock)

    def createMutex(self, isRecursive: bool) -> ct.c_void_p | None:
        """Creates and returns a mutex object, or :code:`None` if not successful.

        Mutexes can be faster than the more general purpose monitor objects
        returned by :py:meth:`createThreadLock()` on some platforms, and can
        also be recursive, but the result of unlocking a mutex that is owned by
        another thread or is not locked is undefined.

        If *isRecursive'* id :code:`True`, the mutex can be re-locked multiple
        times by the same thread, requiring an equal number of unlock calls;
        otherwise, attempting to re-lock the mutex results in undefined
        behavior.

        Note: the handles returned by :py:meth:`createThreadLock()` and
        :py:meth:`createMutex()` are not compatible.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundCreateMutex(ct.c_int(isRecursive)) or None

    def lockMutex(self, mutex: ct.c_void_p) -> None:
        """Acquires the indicated mutex object.

        Args:
            mutex: the mutex, as returned by :meth:`~Csound.createMutex`

        If it is already in use by another thread, the function waits until
        the mutex is released by the other thread.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        libcsound.csoundLockMutex(mutex)

    def lockMutexNoWait(self, mutex: ct.c_void_p) -> int:
        """Acquire the indicated mutex object.

        Args:
            mutex: the mutex, as returned by :meth:`~Csound.createMutex`

        Returns zero, unless it is already in use by another thread, in which
        case a non-zero value is returned immediately, rather than waiting
        until the mutex becomes available.

        .. note:: this function may be unimplemented on Windows.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundLockMutexNoWait(mutex)

    def unlockMutex(self, mutex: ct.c_void_p) -> None:
        """Releases the indicated mutex object.

        Args:
            mutex: the mutex, as returned by :meth:`~Csound.createMutex`

        The mutex should be owned by the current thread, otherwise the
        operation of this function is undefined. A recursive mutex needs
        to be unlocked as many times as it was locked previously.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        libcsound.csoundUnlockMutex(mutex)

    def destroyMutex(self, mutex: ct.c_void_p):
        """Destroys the indicated mutex object.

        Args:
            mutex: the mutex, as returned by :meth:`~Csound.createMutex`

        Destroying a mutex that is currently owned by a thread results
        in undefined behavior.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        libcsound.csoundDestroyMutex(mutex)

    def createBarrier(self, maxthreads: int) -> ct.c_void_p | None:
        """Creates a Thread Barrier.

        Args:
            maxthreads: should be equal to the number of child threads
                using the barrier plus one for the master thread.

        Returns:
            the barrier as an opaque pointer, or None if failed

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundCreateBarrier(ct.c_uint(maxthreads)) or None

    def destroyBarrier(self, barrier: ct.c_void_p) -> int:
        """Destroys a Thread Barrier.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundDestroyBarrier(barrier)

    def waitBarrier(self, barrier: ct.c_void_p):
        """Waits on the thread barrier.

        Args:
            barrier: the barrier, as returned by :meth:`Csound.createBarrier`

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundWaitBarrier(barrier)

    #def createCondVar(self):
    #def condWait(self, condVar, mutex):
    #def condSignal(self, condVar):
    #def destroyCondVar(self, condVar):

    def sleep(self, milliseconds: int) -> None:
        """Waits for at least the specified number of *milliseconds*.

        Args:
            milliseconds: time to sleep, in milliseconds

        It yields the CPU to other threads.
        """
        libcsound.csoundSleep(ct.c_uint(milliseconds))

    def spinLockInit(self, spinlock: ct.c_int32 | None) -> ct.c_int32:
        """Inits the spinlock.

        Args:
            spinlock: if given, initializes the given spinlock. Otherwise
                a new spinlock is created

        Returns:
            the initialized spinlock

        If the spinlock is not locked, locks it and returns;
        if is is locked, waits until it is unlocked, then locks it and returns.
        Uses atomic compare and swap operations that are safe across processors
        and safe for out of order operations,
        and which are more efficient than operating system locks.

        Use spinlocks to protect access to shared data, especially in functions
        that do little more than read or write such data, for example::

            lock = ctypes.ct.c_int32(0)
            cs.spinLockInit(lock)
            def write(cs, frames, signal):
                cs.spinLock(lock)
                for frame in range(frames) :
                    global_buffer[frame] += signal[frame];
                cs.spinUnlock(lock)

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        if spinlock is None:
            spinlock = ct.c_int32(0)
        ret = libcsound.csoundSpinLockInit(ct.byref(spinlock))
        if ret != CSOUND_SUCCESS:
            raise RuntimeError(f"Could not init spinlock, got {ret}")
        return spinlock

    def spinLock(self, spinlock: ct.c_int32) -> None:
        """Locks the spinlock.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        libcsound.csoundSpinLock(ct.byref(spinlock))

    def spinTryLock(self,spinlock: ct.c_int32) -> int:
        """Tries the spinlock.

        returns CSOUND_SUCCESS if lock could be acquired,
        CSOUND_ERROR, otherwise.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundSpinLock(ct.byref(spinlock))

    def spinUnlock(self, spinlock: ct.c_int32) -> None:
        """Unlocks the spinlock.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        libcsound.csoundSpinUnLock(ct.byref(spinlock))

    #Miscellaneous Functions
    def runCommand(self, args, noWait: bool):
        """Runs an external command with the arguments specified in list *args*.

        args[0] is the name of the program to execute (if not a full path
        file name, it is searched in the directories defined by the PATH
        environment variable).

        If *noWait* is :code:`False`, the function waits until the external
        program finishes, otherwise it returns immediately. In the first case,
        a non-negative return value is the exit status of the command (0 to
        255), otherwise it is the PID of the newly created process.
        On error, a negative value is returned.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        n = len(args)
        argv = (ct.POINTER(ct.c_char_p) * (n+1))()
        for i in range(n):
            v = cstring(args[i])
            argv[i] = ct.cast(ct.pointer(ct.create_string_buffer(v)), ct.POINTER(ct.c_char_p))
        argv[n] = None
        return libcsound.csoundRunCommand(ct.cast(argv, ct.POINTER(ct.c_char_p)), ct.c_int(noWait))

    def initTimerStruct(self, timerStruct):
        """Initializes a timer structure.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        libcsound.csoundInitTimerStruct(ct.byref(timerStruct))

    def realTime(self, timerStruct: RtClock) -> int:
        """Returns the elapsed real time (in seconds).

        The time is measured since the specified timer structure was initialised.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundGetRealTime(ct.byref(timerStruct))

    def CPUTime(self, timerStruct: RtClock) -> int:
        """Returns the elapsed CPU time (in seconds).

        The time is measured since the specified timer structure was initialised.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundGetCPUTime(ct.byref(timerStruct))

    def randomSeedFromTime(self) -> int:
        """Returns a 32-bit unsigned integer to be used as seed from current time.

        .. note:: not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundGetRandomSeedFromTime()

    def setLanguage(self, langcode: int):
        """Sets language to *langcode*.

        *langcode* can be for example CSLANGUAGE_ENGLISH_UK or
        CSLANGUAGE_FRENCH or many others, (see n_getstr.h for the list of
        languages). This affects all Csound instances running in the address
        space of the current process. The special language code
        CSLANGUAGE_DEFAULT can be used to disable translation of messages and
        free all memory allocated by a previous call to setLanguage().
        setLanguage() loads all files for the selected language
        from the directory specified by the CSSTRNGS environment
        variable.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        libcsound.csoundSetLanguage(langcode)

    def env(self, name: str, withCsoundInstance=True) -> str | None:
        """
        Gets the value of environment variable *name*.

        Args:
            name: the name of the variable
            withCsoundInstance: if True, the local environment of the
                current instance is taken into account. Should be called
                after :py:meth:`compileCommandLine()`

        Returns:
            the value of the variable, or None if it is not set

        The searching order is:

        1. Local environment of Csound (if *withCsoundInstance* is :code:`True`)
        2. Variables set with :py:meth:`setGlobalEnv()`,
        3. System environment variables.

        """
        if withCsoundInstance:
            ret = libcsound.csoundGetEnv(self.cs, cstring(name))
        else:
            ret = libcsound.csoundGetEnv(None, cstring(name))
        if (ret):
            return pstring(ret)
        return None

    def setGlobalEnv(self, name: str, value: str | None):
        """Sets the global value of environment variable *name* to *value*.

        Args:
            name: variable name
            value: variable value. The key: value pair is deleted if the
                value is ``None``

        Returns:
            zero on success, an error code otherwise

        .. note:: It is not safe to call this function while any Csound instances are active.

        """
        cstr = cstring(value) if value is not None else ct.c_char_p()
        return libcsound.csoundSetGlobalEnv(cstring(name), cstr)

    def createGlobalVariable(self, name: str, nbytes: int):
        """
        Allocates *nbytes* bytes of memory.

        This memory can be accessed later by calling
        :py:meth`queryGlobalVariable()` with the specified name; the space is
        cleared to zero.

        Returns CSOUND_SUCCESS on success, CSOUND_ERROR in case of invalid
        parameters (zero *nbytes*, invalid or already used *name*), or
        CSOUND_MEMORY if there is not enough memory.

        .. note:: not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundCreateGlobalVariable(self.cs, cstring(name), ct.c_uint(nbytes))

    def queryGlobalVariable(self, name: str) -> ct.c_void_p | None:
        """Gets pointer to space allocated with the name *name*.

        Returns:
            an opaque pointer, or `None` if the variable is undefined

        .. note:: Not implemented in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundQueryGlobalVariable(self.cs, cstring(name)) or None

    def queryGlobalVariableNoCheck(self, name: str) -> ct.c_void_p:
        """This function is the similar to :py:meth`queryGlobalVariable()`.

        Except the variable is assumed to exist and no error checking is done.
        Faster, but may crash or return an invalid pointer if *name* is
        not defined.

        .. note:: Not implemented in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundQueryGlobalVariableNoCheck(self.cs, cstring(name))

    def destroyGlobalVariable(self, name: str):
        """Frees memory allocated for *name* and remove *name* from the database.

        Return value is CSOUND_SUCCESS on success, or CSOUND_ERROR if the *name*
        is not defined.

        .. note:: Not implemented in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundDestroyGlobalVariable(self.cs, cstring(name))

    def runUtility(self, name, args):
        """Runs utility with the specified *name* and command line arguments.

        Should be called after loading utility plugins.
        Use :py:meth`reset()` to clean up after calling this function.
        Returns zero if the utility was run successfully.
        """
        argc, argv = csoundArgList(args)
        return libcsound.csoundRunUtility(self.cs, cstring(name), argc, argv)

    def listUtilities(self) -> list[str]:
        """Returns a list of registered utility names.

        The return value may be :code:`None` in case of an error.

        .. note:: Not present in csound 7
        """
        _notPresentInCsound7()
        lst = []
        ptr = libcsound.csoundListUtilities(self.cs)
        if ptr:
            i = 0
            while ptr[i]:
                lst.append(pstring(ptr[i]))
                i += 1
            libcsound.csoundDeleteUtilityList(self.cs, ptr)
        return lst

    def utilityDescription(self, name: str) -> str:
        """
        Gets utility description.

        Returns an empty string if the utility was not found, or it has no
        description, or an error occured.

        .. note:: Not present in csound 7

        """
        _notPresentInCsound7()
        ptr = libcsound.csoundGetUtilityDescription(self.cs, cstring(name))
        return pstring(ptr) if ptr else ''

    def rand31(self, seed: int) -> float:
        """
        Simple linear congruential random number generator

        ::

            seed = seed * 742938285 % 2147483647

        The initial value of *seed* must be in the range 1 to 2147483646.
        Returns the next number from the pseudo-random sequence, in the range
        1 to 2147483646.

        .. note:: Not present in csound 7

        """
        _notPresentInCsound7()
        n = ct.c_int(seed)
        return libcsound.csoundRand31(ct.byref(n))

    def seedRandMT(self, initKey: int | _t.Sequence[int]) -> CsoundRandMTState:
        """Initializes Mersenne Twister (MT19937) random number generator.

        Args:
            initKey: can be a single int, a list of int Those int values are
                converted to unsigned 32 bit values and used for seeding.

        Returns:
            a CsoundRandMTState stuct to be used by :py:meth`csoundRandMT()`.

        .. note:: Not present in csound 7

        """
        _notPresentInCsound7()
        state = CsoundRandMTState()
        if type(initKey) == int:
            if initKey < 0:
                initKey = -initKey
            libcsound.csoundSeedRandMT(ct.byref(state), None, ct.c_uint32(initKey))
        elif isinstance(initKey, (list, tuple, np.ndarray)):
            n = len(initKey)
            lst = (ct.c_uint32 * n)()
            for i in range(n):
                k = initKey[i]
                if k < 0 :
                    k = -k
                lst[i] = ct.c_uint32(k)
            p = ct.pointer(lst)
            p = ct.cast(p, ct.POINTER(ct.c_uint32))
            libcsound.csoundSeedRandMT(ct.byref(state), p, ct.c_uint32(len(lst)))
        else:
            raise TypeError(f"Expected an int or a sequence of ints, got {initKey}")
        return state

    def randMT(self, state: CsoundRandMTState) -> float:
        """Returns next random number from MT19937 generator.

        Args:
            state: a CsoundRandMTState as returned by :meth:`~Csound.seedRandMT`

        The PRNG must be initialized first by calling :py:meth`seedRandMT()`.

        .. note:: Not present in csound 7

        """
        _notPresentInCsound7()
        return libcsound.csoundRandMT(ct.byref(state))

    def createCircularBuffer(self, numelem: int, elemsize: int = 0) -> ct.c_void_p:
        """Creates a circular buffer with *numelem* number of elements.

        Args:
            numelem: number of elements in the buffer
            elemsize: size of each element, in bytes. Defaults to the size of MYFLT

        Returns:
            the circular buffer, as an opaque pointer

        The element's size is set from *elemsize*. It should be used like::

            >>> cs = Csound()
            >>> ...
            >>> circularbuf = cs.createCircularBuffer(1024, cs.sizeOfMYFLT())
        """
        if elemsize == 0:
            elemsize = self.sizeOfMYFLT()
        return libcsound.csoundCreateCircularBuffer(self.cs, numelem, elemsize)

    def readCircularBuffer(self, buffer: ct.c_void_p, out: np.ndarray, numitems: int):
        """Reads from circular buffer.

        Args:
            buffer: pointer to an existing circular buffer
            out: preallocated ndarray with at least items number of elements,
                where buffer contents will be read into
            numitems: number of samples to be read

        Returns:
            The actual number of items read (0 <= n <= items).
        """
        if len(out) < numitems:
            return 0
        ptr = out.ctypes.data_as(ct.c_void_p)
        return libcsound.csoundReadCircularBuffer(self.cs, buffer, ptr, numitems)

    def peekCircularBuffer(self, circularBuffer: ct.c_void_p, out: np.ndarray, numitems: int) -> int:
        """Reads from circular buffer without removing them from the buffer.

        Args:
            buffer: pointer to an existing circular buffer
            data: ndarray with at least items number of elements to be written
                into circular buffer
            numitems: number of samples to write

        Returns:
            The actual number of items written (0 <= n <= items).

        """
        if len(out) < numitems:
            return 0
        ptr = out.ctypes.data_as(ct.c_void_p)
        return libcsound.csoundPeekCircularBuffer(self.cs, circularBuffer, ptr, numitems)

    def writeCircularBuffer(self, buffer: ct.c_void_p, data: np.ndarray, numitems: int):
        """Writes to circular buffer.

        Args:
            buffer: pointer to an existing circular buffer
            data: ndarray with at least items number of elements to be written
                into circular buffer
            numitems: number of samples to write

        Returns:
            The actual number of items written (0 <= n <= items).
        """
        if len(data) < numitems:
            return 0
        ptr = data.ctypes.data_as(ct.c_void_p)
        return libcsound.csoundWriteCircularBuffer(self.cs, buffer, ptr, numitems)

    def flushCircularBuffer(self, buffer: ct.c_void_p) -> None:
        """Empties circular buffer of any remaining data.

        This function should only be used if there is no reader actively
        getting data from the buffer.

        Args:
            buffer: pointer to an existing circular buffer
        """
        libcsound.csoundFlushCircularBuffer(self.cs, buffer)

    def destroyCircularBuffer(self, buffer: ct.c_void_p) -> None:
        """Frees circular buffer."""
        libcsound.csoundDestroyCircularBuffer(self.cs, buffer)

    def openLibrary(self, libraryPath: str) -> tuple[int, ct.c_void_p]:
        """Platform-independent function to load a shared library.

        Args:
            libraryPath: the path to the library

        Returns:
            a tuple (retcode: int, library: void)

        .. note:: Not present in csound 7

        """
        _notPresentInCsound7()
        ptr = ct.POINTER(ct.c_int)()
        library = ct.cast(ptr, ct.c_void_p)
        ret = libcsound.csoundOpenLibrary(ct.byref(library), cstring(libraryPath))
        return ret, library

    def closeLibrary(self, library: ct.c_void_p) -> int:
        """Platform-independent function to unload a shared library.

        .. note:: Not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundCloseLibrary(library)

    def getLibrarySymbol(self, library: ct.c_void_p, symbolName: str):
        """Platform-independent function to get a symbol address in a shared library.

        .. note:: Not present in csound 7
        """
        _notPresentInCsound7()
        return libcsound.csoundGetLibrarySymbol(library, cstring(symbolName))


class PerformanceThread:
    """Performs a score in a separate thread until the end of score is reached.

    The playback (which is paused by default) is stopped by calling
    :py:meth:`stop()`, or if an error occurs.
    The constructor takes a Csound instance as argument. Once the playback is
    stopped for one of the above mentioned reasons, the performance thread calls
    :meth:`Csound.cleanup <libcsound.api6.Csound.cleanup>` and returns.

    Args:
        csound: the Csound object (not the bare pointer)

    .. rubric:: Example

    .. code-block:: python

        from libcsound import *
        cs = Csound(...)
        ...
        perfthread = PerformanceThread(cs)


    From the user perspective the recommended way to create a performance thread
    is to call the :meth:`~Csound.performanceThread` method::

        perfthread = cs.performanceThread()

    """
    def __init__(self, csound: Csound):
        self.csound = csound
        """The Csound instance corresponding to this PerformanceThread"""

        csp = csound.csound()
        self.cpt = libcspt.NewCsoundPT(csp)
        """The opaque pointer to the actual CsoundPerformanceThread"""

        self._callbacks: dict[str, ct._FuncPointer] = {}
        self._processQueue: _queue.SimpleQueue | None = None
        self._processCallback: tuple[ct._FuncPointer, _t.Any] | None = None

    def __del__(self):
        libcspt.DeleteCsoundPT(self.cpt)

    def isRunning(self) -> bool:
        """Returns True if the performance thread is running, False otherwise."""
        return libcspt.CsoundPTisRunning(self.cpt) != 0

    def processCallback(self) -> ct._FuncPointer:
        """Returns the process callback."""
        return PROCESSFUNC(libcspt.CsoundPTgetProcessCB(self.cpt))

    def setProcessCallback(self, function: _t.Callable[[ct.c_void_p], None], data=None
                           ) -> None:
        """
        Sets the process callback.

        Args:
            function: a function of the form ``(data: void) -> None``
            data: can be anything

        The callback is called with a pointer to the data passed as ``data``
        """
        if self._processQueue is not None:
            raise RuntimeError(f"Process callback already set to manage the process queue")
        self._setProcessCallback(function=function, data=data)

    def _setProcessCallback(self, function: _t.Callable[[ct.c_void_p], None], data=None):
        """Sets the process callback.

        Args:
            function: a function of the form ``(csound: void) -> None``
            data: data passed to the function

        """
        if data is None:
            data = ct.c_void_p()
        procfunc = PROCESSFUNC(function)
        self._processCallback = (procfunc, data)
        libcspt.CsoundPTsetProcessCB(self.cpt, procfunc, ct.byref(data))

    def setProcessQueue(self) -> None:
        """
        Setup a queue to process tasks within the performance loop

        .. note::

            This sets up the process callback.
        """
        if self._processQueue is not None:
            return
        elif self._processCallback is not None:
            raise RuntimeError(f"Process callback already set")
        self._processQueue = _queue.SimpleQueue()
        self._setProcessCallback(self._processQueueCallback)

    def _processQueueCallback(self, data) -> None:
        assert self._processQueue is not None
        N = self._processQueue.qsize()
        if N > 0:
            for _ in range(min(10, N)):
                job = self._processQueue.get_nowait()
                job(self.csound)

    def processQueueTask(self, func: _t.Callable[[Csound], None]) -> None:
        """
        Add a task to the process queue, to be picked up by the process callback

        Args:
            func: a function of the form ``(csound: Csound) -> None``,
                which can access the csound API

        .. note::
            This method is only available if the process queue was set
            (via :py:meth:`setProcessQueue`).

        .. rubric:: Example

        Allocate a table in csound and return the assigned table number and a numpy
        array pointing to the table data

        .. code-block:: python

            import queue
            cs = Csound()
            cs.compileOrc(...)
            thread = cs.performanceThread()
            thread.setProcessQueue()

            sndfile = "/path/to/sndfile.wav"
            q = queue.SimpleQueue()

            def mytask(cs, q=q):
                tabnum = cs.evalCode(fr'''
                gi__tabnum ftgen 0, 0, -1, "{sndfile}", 0, 0, 0
                return gi__tabnum''')
                tabpointer = csound.table(tabnum)
                q.put((tabnum, tabpointer))

            thread.processQueueTask(mytask)
            tabnum, tabpointer = q.get(block=True)

        .. seealso:: :py:meth:`compile()`, :py:meth:`evalCode()`

        """
        if self._processQueue is None:
            raise RuntimeError("This action needs the process queue, start it via "
                               "the setProcessQueue method")
        assert self._processQueue is not None
        self._processQueue.put_nowait(func)

    def flushProcessQueue(self, timeout: float | None = None) -> None:
        """
        Wait until all process queue tasks have been acted upon

        Args:
            timeout: if given, a max. amount of time to wait

        .. note::
            This method is only available if the process queue was set (see
            :py:meth:`setProcessQueue`)
        """
        if self._processQueue is None or self._processQueue.qsize() == 0:
            return
        event = _threading.Event()
        self.processQueueTask(lambda cs, e=event: e.set())
        event.wait(timeout=timeout)


    def csoundPtr(self) -> ct.c_void_p:
        """Returns the Csound instance pointer."""
        return libcspt.CsoundPTgetCsound(self.cpt)

    def status(self) -> int:
        """Returns the current status.

        Returns:
            Zero if still playing, positive if the end of score was reached or
            performance was stopped, and negative if an error occured.
        """
        return libcspt.CsoundPTgetStatus(self.cpt)

    def play(self) -> None:
        """Continues performance if it was paused."""
        if not self.csound._started:
            self.csound.start()
        libcspt.CsoundPTplay(self.cpt)

    def pause(self) -> None:
        """Pauses performance (can be continued by calling :py:meth:`play()`)."""
        libcspt.CsoundPTpause(self.cpt)

    def togglePause(self) -> None:
        """Pauses or continues performance, depending on current state."""
        libcspt.CsoundPTtogglePause(self.cpt)

    def stop(self) -> None:
        """Stops performance (cannot be continued)."""
        libcspt.CsoundPTstop(self.cpt)

    def record(self, filename: str, samplebits: int, numbufs: int):
        """Starts recording the output from Csound.

         Args:
             filename: the output soundfile. Format is always WAVE
             samplebits: number of bits per sample (16, 24, 32)
             numbufs: number of buffers

        The sample rate and number of channels are taken directly from the
        running Csound instance.
        """
        libcspt.CsoundPTrecord(self.cpt, cstring(filename), samplebits, numbufs)

    def stopRecord(self) -> None:
        """Stops recording and closes audio file."""
        libcspt.CsoundPTstopRecord(self.cpt)

    def scoreEvent(self, abstime: int, kind: str, pfields: _t.Sequence[float] | np.ndarray) -> None:
        """
        Sends a score event.

        Args:
            abstime: if True, the start time of the event is measured from
                the beginning of performance, instead of relative to the current time
            kind: the kind of event, one of 'i', 'f', 'e'
            pfields: pfields of the event, starting with p1

        """
        p = np.array(pfields).astype(MYFLT)
        ptr = p.ctypes.data_as(ct.POINTER(MYFLT))
        numfields = p.size
        libcspt.CsoundPTscoreEvent(self.cpt, ct.c_int(int(abstime)), cchar(kind), numfields, ptr)

    def inputMessage(self, s: str) -> None:
        """
        Sends a score event as a string

        Args:
            s: a string representing a line within a score (following the score syntax)

        """
        libcspt.CsoundPTinputMessage(self.cpt, cstring(s))

    def setScoreOffsetSeconds(self, time: float) -> None:
        """Sets the playback time pointer to the specified value (in seconds).

        Args:
            time: playback time in seconds
        """
        libcspt.CsoundPTsetScoreOffsetSeconds(self.cpt, ct.c_double(time))

    def join(self) -> int:
        """Waits until the performance is finished or fails.

        Returns:
            a positive value if the end of score was reached or :py:meth:`stop()`
            was called, and a negative value if an error occured.

        Releases any resources associated with the performance thread
        object.
        """
        return libcspt.CsoundPTjoin(self.cpt)

    def flushMessageQueue(self) -> None:
        """Waits until all pending messages are actually received.

        (pause, send score event, etc.)
        """
        libcspt.CsoundPTflushMessageQueue(self.cpt)

    def setEndMarker(self, time: float, absolute=False) -> None:
        """
        Add an end event to the score

        This stops the performance at the given time

        Args:
            time: time to add the end event
            absolute: if True, use absolute time.
        """
        self.scoreEvent(int(absolute), "e", [0, time])


def getSystemSr(module: str = '') -> tuple[float, str]:
    """
    Get the system samplerate reported by csound

    Not all modules report a system samplerate. Modules
    which do report it are 'jack' and 'auhal' (coreaudio). Portaudio
    will normally report a default samplerate of 44100, but this may
    vary for each platform. T obtain a list of available modules see
    :meth:`Csound.modules`

    Args:
        module: the module to use, or a default for each platform

    Returns:
        a tuple (samplerate: float, module: str), where samplerate
        is the reported samplerate and module is the module used
        (which is only of interest if no module was given)

    ==============   =============  ================
    Module            Platforms      Has System sr
    ==============   =============  ================
    ``portaudio``    linux, macos,   no
                     windows
    ``jack``         linux, macos    yes
    ``alsa``         linux           no
    ``pulseaudio``   linux           yes
    ``auhal``        macos           yes
    (coreaudio)
    ``winmme``       windows         no
    ==============   =============  ================

    """
    if not module:
        module = _util.defaultRealtimeModule()
    else:
        modules = _util.realtimeModulesForPlatform()
        if module not in modules:
            raise ValueError(f"Module {module} not known for this platform")
    csound = Csound()
    csound.createMessageBuffer(echo=False)
    csound.setOption(f'-+rtaudio={module}')
    csound.setOption(f'-odac')
    csound.setOption('--get-system-sr')
    sr = 0.
    csound.cleanup()
    for msg, attr in csound.iterMessages():
        if msg.startswith("system sr:"):
            sr = float(msg.split(":")[1].strip())
            break
    csound.destroyMessageBuffer()
    return sr, module
