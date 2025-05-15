from __future__ import annotations

import sys
import numpy as np
import warnings
import ctypes as ct
import queue as _queue
from collections import deque as _deque
import threading as _threading

from .common import *
from . import _util
from . import _dll

import typing as _t


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


#
# PVSDAT window types
#
PVS_WIN_HAMMING = 0
PVS_WIN_HANN = 1
PVS_WIN_KAISER = 2
PVS_WIN_CUSTOM = 3
PVS_WIN_BLACKMAN = 4
PVS_WIN_BLACKMAN_EXACT = 5
PVS_WIN_NUTTALLC3 = 6
PVS_WIN_BHARRIS_3 = 7
PVS_WIN_BHARRIS_MIN = 8
PVS_WIN_RECT = 9

#
# PVSDAT formats
#
PVS_AMP_FREQ = 0   # phase vocoder
PVS_AMP_PHASE = 1  # polar DFT
PVS_COMPLEX = 2    # rectangular DFT
PVS_TRACKS = 3     # amp, freq, phase, ID tracks

#
# Constants used by the bus interface (csoundGetChannelPtr() etc.).
#
CSOUND_CONTROL_CHANNEL = 1
CSOUND_AUDIO_CHANNEL  = 2
CSOUND_STRING_CHANNEL = 3
CSOUND_PVS_CHANNEL = 4
CSOUND_VAR_CHANNEL = 5
CSOUND_ARRAY_CHANNEL = 6

CSOUND_CHANNEL_TYPE_MASK = 15

CSOUND_INPUT_CHANNEL = 16
CSOUND_OUTPUT_CHANNEL = 32

CSOUND_CONTROL_CHANNEL_NO_HINTS = 0
CSOUND_CONTROL_CHANNEL_INT = 1
CSOUND_CONTROL_CHANNEL_LIN = 2
CSOUND_CONTROL_CHANNEL_EXP = 3


#
# Event types
#
CS_INSTR_EVENT = 0
CS_TABLE_EVENT = 1
CS_END_EVENT = 2


# Symbols for Windat.polarity field
NOPOL = 0
NEGPOL = 1
POSPOL = 2
BIPOL = 3

# Callback functions
CHANNELFUNC = ct.CFUNCTYPE(None, CSOUND_p, ct.c_char_p, ct.c_void_p, ct.c_void_p)
MIDIINOPENFUNC = ct.CFUNCTYPE(ct.c_int32, CSOUND_p, ct.POINTER(ct.c_void_p), ct.c_char_p)
MIDIREADFUNC = ct.CFUNCTYPE(ct.c_int32, CSOUND_p, ct.c_void_p, ct.c_char_p, ct.c_int32)
MIDIINCLOSEFUNC = ct.CFUNCTYPE(ct.c_int32, CSOUND_p, ct.c_void_p)
MIDIOUTOPENFUNC = ct.CFUNCTYPE(ct.c_int32, CSOUND_p, ct.POINTER(ct.c_void_p), ct.c_char_p)
MIDIWRITEFUNC = ct.CFUNCTYPE(ct.c_int32, CSOUND_p, ct.c_void_p, ct.c_char_p, ct.c_int32)
MIDIOUTCLOSEFUNC = ct.CFUNCTYPE(ct.c_int32, CSOUND_p, ct.c_void_p)
MIDIERRORFUNC = ct.CFUNCTYPE(ct.c_char_p, ct.c_int32)
MIDIDEVLISTFUNC = ct.CFUNCTYPE(ct.c_int32, CSOUND_p, ct.POINTER(CsoundMidiDevice), ct.c_int32)
OPENSOUNDFILEFUNC = ct.CFUNCTYPE(ct.c_void_p, CSOUND_p, ct.c_char_p, ct.c_int32, ct.c_void_p)
OPENFILEFUNC = ct.CFUNCTYPE(ct.c_void_p, CSOUND_p, ct.c_char_p, ct.c_char_p)
MSGSTRFUNC = ct.CFUNCTYPE(None, CSOUND_p, ct.c_int32, ct.c_char_p)
KEYBOARDFUNC = ct.CFUNCTYPE(ct.c_int32, ct.py_object, ct.c_void_p, ct.c_uint32)
OPCODEFUNC = ct.CFUNCTYPE(ct.c_int32, CSOUND_p, ct.c_void_p)
MAKEGRAPHFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.POINTER(Windat), ct.c_char_p)
DRAWGRAPHFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.POINTER(Windat))
KILLGRAPHFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.POINTER(Windat))
EXITGRAPHFUNC = ct.CFUNCTYPE(ct.c_int32, ct.c_void_p)
CSOUNDPERFTHREAD_p = ct.c_void_p
PROCESSFUNC = ct.CFUNCTYPE(None, ct.c_void_p)
EVALCODEFUNC = ct.CFUNCTYPE(None, MYFLT)
REQUESTCALLBACKFUNC = ct.CFUNCTYPE(None, ct.c_void_p)


# class CsType
#     """
#     typedef struct cstype {
#         char* varTypeName;
#         char* varDescription;
#         int32_t argtype; // used to denote if allowed as in-arg, out-arg, or both
#         struct csvariable* (*createVariable)(void *cs, void *p, struct opds *ctx);
#         void (*copyValue)(CSOUND* csound, const struct cstype* cstype, void* dest, const
#                           void* src, struct opds *ctx);
#         void (*freeVariableMemory)(void* csound, void* varMem);
#         CONS_CELL* members;
#         int32_t userDefinedType;
#       } CS_TYPE;
#     """
#     _fields_ = [
#         ("varTypeName", ct.c_char_p),
#         ("varDescription", ct.c_char_p),
#         ("argtype", ct.c_int32),
#         ("createVariable", ct.c_void_p),
#         ("copyValue", ct.c_void_p),
#         ("freeVariableMemory", ct.c_void_p),
#         ("members", ct.c_void_p),
#         ("userDefinedType", ct.c_int32)
#     ]

# class ArrayDat(ct.Structure):
#     """
#     struct arraydat {
#       int32_t dimensions;             /* number of array dimensions */
#       int32_t *sizes;                 /* size of each dimensions */
#       int32_t arrayMemberSize;        /* size of each item */
#       const struct cstype *arrayType; /* type of array */
#       MYFLT *data;                    /* data */
#       size_t allocated;               /* size of allocated data */
#     };
#     """
#     _fields_ = [
#         ("dimensions", ct.c_int32),
#         ("sizes", ct.POINTER(ct.c_int32)),
#         ("arrayMemberSize", ct.c_int32),
#         ("arrayType", ct.POINTER(CsType)),
#         ("data", ct.POINTER(MYFLT)),
#         ("allocated", ct.c_size_t)
#     ]


def _declareAPI(libcsound, libcspt):
    # Instantiation
    libcsound.csoundInitialize.restype = ct.c_int32
    libcsound.csoundInitialize.argtypes = [ct.c_int32]
    libcsound.csoundCreate.restype = CSOUND_p
    libcsound.csoundCreate.argtypes = [ct.py_object, ct.c_char_p]
    libcsound.csoundDestroy.argtypes = [CSOUND_p]

    # Attributes
    libcsound.csoundGetVersion.restype = ct.c_int32
    libcsound.csoundGetSr.restype = MYFLT
    libcsound.csoundGetSr.argtypes = [CSOUND_p]
    libcsound.csoundGetKr.restype = MYFLT
    libcsound.csoundGetKr.argtypes = [CSOUND_p]
    libcsound.csoundGetKsmps.restype = ct.c_uint32
    libcsound.csoundGetKsmps.argtypes = [CSOUND_p]
    libcsound.csoundGetChannels.restype = ct.c_uint32
    libcsound.csoundGetChannels.argtypes = [CSOUND_p, ct.c_int32]
    libcsound.csoundGet0dBFS.restype = MYFLT
    libcsound.csoundGet0dBFS.argtypes = [CSOUND_p]
    libcsound.csoundGetA4.restype = MYFLT
    libcsound.csoundGetA4.argtypes = [CSOUND_p]
    libcsound.csoundGetCurrentTimeSamples.restype = ct.c_int64
    libcsound.csoundGetCurrentTimeSamples.argtypes = [CSOUND_p]
    libcsound.csoundGetSizeOfMYFLT.restype = ct.c_int32
    libcsound.csoundGetHostData.restype = ct.py_object
    libcsound.csoundGetHostData.argtypes = [CSOUND_p]
    libcsound.csoundSetHostData.argtypes = [CSOUND_p, ct.py_object]
    libcsound.csoundGetEnv.restype = ct.c_char_p
    libcsound.csoundGetEnv.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundSetGlobalEnv.restype = ct.c_int32
    libcsound.csoundSetGlobalEnv.argtypes = [ct.c_char_p, ct.c_char_p]
    libcsound.csoundSetOption.restype = ct.c_int32
    libcsound.csoundSetOption.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundGetParams.argtypes = [CSOUND_p, ct.POINTER(CsoundParams)]
    libcsound.csoundGetDebug.restype = ct.c_int32
    libcsound.csoundGetDebug.argtypes = [CSOUND_p]
    libcsound.csoundSetDebug.argtypes = [CSOUND_p, ct.c_int32]
    libcsound.csoundSystemSr.restype = MYFLT
    libcsound.csoundSystemSr.argtypes = [CSOUND_p, MYFLT]
    libcsound.csoundGetModule.restype = ct.c_int32
    libcsound.csoundGetModule.argtypes = [CSOUND_p, ct.c_int, ct.POINTER(ct.c_char_p), ct.POINTER(ct.c_char_p)]
    libcsound.csoundGetAudioDevList.restype = ct.c_int32
    libcsound.csoundGetAudioDevList.argtypes = [CSOUND_p, ct.c_void_p, ct.c_int32]
    libcsound.csoundGetMIDIDevList.restype = ct.c_int32
    libcsound.csoundGetMIDIDevList.argtypes = [CSOUND_p, ct.c_void_p, ct.c_int32]
    libcsound.csoundGetMessageLevel.restype = ct.c_int32
    libcsound.csoundSetMessageLevel.argtypes = [CSOUND_p, ct.c_int32]

    # Performance
    libcsound.csoundCompile.restype = ct.c_int32
    libcsound.csoundCompile.argtypes = [CSOUND_p, ct.c_int32, ct.POINTER(ct.c_char_p)]
    libcsound.csoundCompileOrc.restype = ct.c_int32
    libcsound.csoundCompileOrc.argtypes = [CSOUND_p, ct.c_char_p, ct.c_int32]
    libcsound.csoundEvalCode.restype = MYFLT
    libcsound.csoundEvalCode.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundCompileCSD.restype = ct.c_int32
    libcsound.csoundCompileCSD.argtypes = [CSOUND_p, ct.c_char_p, ct.c_int32, ct.c_int32]
    libcsound.csoundStart.restype = ct.c_int32
    libcsound.csoundStart.argtypes = [CSOUND_p]
    libcsound.csoundPerformKsmps.restype = ct.c_int32
    libcsound.csoundPerformKsmps.argtypes = [CSOUND_p]
    # libcsound.csoundPerform.restype = ct.c_int32
    # libcsound.csoundPerform.artypes = [CSOUND_p]
    libcsound.csoundRunUtility.restype = ct.c_int32
    libcsound.csoundRunUtility.argtypes = [CSOUND_p, ct.c_char_p, ct.c_int32, ct.POINTER(ct.c_char_p)]
    libcsound.csoundReset.argtypes = [CSOUND_p]

    # Realtime Audio I/O
    libcsound.csoundSetHostAudioIO.argtypes = [CSOUND_p]
    libcsound.csoundSetRTAudioModule.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundGetSpin.restype = ct.POINTER(MYFLT)
    libcsound.csoundGetSpin.argtypes = [CSOUND_p]
    libcsound.csoundGetSpout.restype = ct.POINTER(MYFLT)
    libcsound.csoundGetSpout.argtypes = [CSOUND_p]

    # Realtime MIDI I/O
    libcsound.csoundSetHostMIDIIO.argtypes = [CSOUND_p]
    libcsound.csoundSetMIDIModule.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundSetExternalMidiInOpenCallback.argtypes = [CSOUND_p, MIDIINOPENFUNC]
    libcsound.csoundSetExternalMidiReadCallback.argtypes = [CSOUND_p, MIDIREADFUNC]
    libcsound.csoundSetExternalMidiInCloseCallback.argtypes = [CSOUND_p, MIDIINCLOSEFUNC]
    libcsound.csoundSetExternalMidiOutOpenCallback.argtypes = [CSOUND_p, MIDIOUTOPENFUNC]
    libcsound.csoundSetExternalMidiWriteCallback.argtypes = [CSOUND_p, MIDIWRITEFUNC]
    libcsound.csoundSetExternalMidiOutCloseCallback.argtypes = [CSOUND_p, MIDIOUTCLOSEFUNC]
    libcsound.csoundSetExternalMidiErrorStringCallback.argtypes = [CSOUND_p, MIDIERRORFUNC]
    libcsound.csoundSetMIDIDeviceListCallback.argtypes = [CSOUND_p, MIDIDEVLISTFUNC]

    # Messages
    libcsound.csoundMessage.argtypes = [CSOUND_p, ct.c_char_p, ct.c_char_p]
    libcsound.csoundMessageS.argtypes = [CSOUND_p, ct.c_int32, ct.c_char_p, ct.c_char_p]
    libcsound.csoundSetMessageStringCallback.argtypes = [CSOUND_p, MSGSTRFUNC]
    libcsound.csoundCreateMessageBuffer.argtypes = [CSOUND_p, ct.c_int32]
    libcsound.csoundGetFirstMessage.restype = ct.c_char_p
    libcsound.csoundGetFirstMessage.argtypes = [CSOUND_p]
    libcsound.csoundGetFirstMessageAttr.restype = ct.c_int32
    libcsound.csoundGetFirstMessageAttr.argtypes = [CSOUND_p]
    libcsound.csoundPopFirstMessage.argtypes = [CSOUND_p]
    libcsound.csoundGetMessageCnt.restype = ct.c_int32
    libcsound.csoundGetMessageCnt.argtypes = [CSOUND_p]
    libcsound.csoundDestroyMessageBuffer.argtypes = [CSOUND_p]

    # Channels, Controls and Events
    libcsound.csoundGetChannelPtr.restype = ct.c_int32
    libcsound.csoundGetChannelPtr.argtypes = [CSOUND_p, ct.POINTER(ct.c_void_p), ct.c_char_p, ct.c_int32]
    libcsound.csoundGetChannelVarTypeName.restype = ct.c_char_p
    libcsound.csoundGetChannelVarTypeName.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundListChannels.restype = ct.c_int32
    libcsound.csoundListChannels.argtypes = [CSOUND_p, ct.POINTER(ct.POINTER(ControlChannelInfo))]
    libcsound.csoundDeleteChannelList.argtypes = [CSOUND_p, ct.POINTER(ControlChannelInfo)]
    libcsound.csoundSetControlChannelHints.restype = ct.c_int32
    libcsound.csoundSetControlChannelHints.argtypes = [CSOUND_p, ct.c_char_p, ControlChannelHints]
    libcsound.csoundGetControlChannelHints.restype = ct.c_int32
    libcsound.csoundGetControlChannelHints.argtypes = [CSOUND_p, ct.c_char_p, ct.POINTER(ControlChannelHints)]
    libcsound.csoundLockChannel.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundUnlockChannel.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundGetControlChannel.restype = MYFLT
    libcsound.csoundGetControlChannel.argtypes = [CSOUND_p, ct.c_char_p, ct.POINTER(ct.c_int32)]
    libcsound.csoundSetControlChannel.argtypes = [CSOUND_p, ct.c_char_p, MYFLT]
    libcsound.csoundGetAudioChannel.argtypes = [CSOUND_p, ct.c_char_p, ct.POINTER(MYFLT)]
    libcsound.csoundSetAudioChannel.argtypes = [CSOUND_p, ct.c_char_p, ct.POINTER(MYFLT)]
    libcsound.csoundGetStringChannel.argtypes = [CSOUND_p, ct.c_char_p, ct.c_char_p]
    libcsound.csoundSetStringChannel.argtypes = [CSOUND_p, ct.c_char_p, ct.c_char_p]

    libcsound.csoundInitArrayChannel.restype = ARRAYDAT_p
    libcsound.csoundInitArrayChannel.argtypes = [CSOUND_p, ct.c_char_p, ct.c_char_p, ct.c_int32, ct.POINTER(ct.c_int32)]
    libcsound.csoundArrayDataType.restype = ct.c_char_p
    libcsound.csoundArrayDataType.argtypes = [ARRAYDAT_p]
    libcsound.csoundArrayDataDimensions.restype = ct.c_int32
    libcsound.csoundArrayDataDimensions.argtypes = [ARRAYDAT_p]
    libcsound.csoundArrayDataSizes.restype = ct.POINTER(ct.c_int32)
    libcsound.csoundArrayDataSizes.argtypes = [ARRAYDAT_p]
    libcsound.csoundSetArrayData.argtypes = [ARRAYDAT_p, ct.c_void_p]
    libcsound.csoundGetArrayData.restype = ct.c_void_p
    libcsound.csoundGetArrayData.argtypes = [ARRAYDAT_p]
    libcsound.csoundGetStringData.restype = ct.c_char_p
    libcsound.csoundGetStringData.argtypes = [CSOUND_p, STRINGDAT_p]
    libcsound.csoundSetStringData.argtypes = [CSOUND_p, STRINGDAT_p, ct.c_char_p]
    libcsound.csoundInitPvsChannel.restype = PVSDAT_p
    libcsound.csoundInitPvsChannel.argtypes = [CSOUND_p, ct.c_char_p, ct.c_int32, ct.c_int32, ct.c_int32, ct.c_int32, ct.c_int32]
    libcsound.csoundPvsDataFFTSize.restype = ct.c_int32
    libcsound.csoundPvsDataFFTSize.argtypes = [PVSDAT_p]
    libcsound.csoundPvsDataOverlap.restype = ct.c_int32
    libcsound.csoundPvsDataOverlap.argtypes = [PVSDAT_p]
    libcsound.csoundPvsDataWindowSize.restype = ct.c_int32
    libcsound.csoundPvsDataWindowSize.argtypes = [PVSDAT_p]
    libcsound.csoundPvsDataFormat.restype = ct.c_int32
    libcsound.csoundPvsDataFormat.argtypes = [PVSDAT_p]
    libcsound.csoundPvsDataFramecount.restype = ct.c_uint32
    libcsound.csoundPvsDataFramecount.argtypes = [PVSDAT_p]
    libcsound.csoundGetPvsData.restype = ct.POINTER(ct.c_float)
    libcsound.csoundGetPvsData.argtypes = [PVSDAT_p]
    libcsound.csoundSetPvsData.argtypes = [PVSDAT_p, ct.POINTER(ct.c_float)]
    libcsound.csoundGetChannelDatasize.restype = ct.c_int32
    libcsound.csoundGetChannelDatasize.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundSetInputChannelCallback.argtypes = [CSOUND_p, CHANNELFUNC]
    libcsound.csoundSetOutputChannelCallback.argtypes = [CSOUND_p, CHANNELFUNC]
    libcsound.csoundEvent.argtypes = [CSOUND_p, ct.c_int32, ct.POINTER(MYFLT), ct.c_int32, ct.c_int32]
    libcsound.csoundEventString.argtypes = [CSOUND_p, ct.c_char_p, ct.c_int32]
    libcsound.csoundKeyPress.argtypes = [CSOUND_p, ct.c_char]
    libcsound.csoundRegisterKeyboardCallback.restype = ct.c_int32
    libcsound.csoundRegisterKeyboardCallback.argtypes = [CSOUND_p, KEYBOARDFUNC, ct.py_object, ct.c_uint32]
    libcsound.csoundRemoveKeyboardCallback.argtypes = [CSOUND_p, KEYBOARDFUNC]

    # Tables
    libcsound.csoundTableLength.restype = ct.c_int32
    libcsound.csoundTableLength.argtypes = [CSOUND_p, ct.c_int32]
    libcsound.csoundGetTable.restype = ct.c_int32
    libcsound.csoundGetTable.argtypes = [CSOUND_p, ct.POINTER(ct.POINTER(MYFLT)), ct.c_int32]
    libcsound.csoundGetTableArgs.restype = ct.c_int32
    libcsound.csoundGetTableArgs.argtypes = [CSOUND_p, ct.POINTER(ct.POINTER(MYFLT)), ct.c_int32]

    # Score Handling
    libcsound.csoundGetScoreTime.restype = ct.c_double
    libcsound.csoundGetScoreTime.argtypes = [CSOUND_p]
    libcsound.csoundIsScorePending.restype = ct.c_int32
    libcsound.csoundIsScorePending.argtypes = [CSOUND_p]
    libcsound.csoundSetScorePending.argtypes = [CSOUND_p, ct.c_int32]
    libcsound.csoundGetScoreOffsetSeconds.restype = MYFLT
    libcsound.csoundGetScoreOffsetSeconds.argtypes = [CSOUND_p]
    libcsound.csoundSetScoreOffsetSeconds.argtypes = [CSOUND_p, MYFLT]
    libcsound.csoundRewindScore.argtypes = [CSOUND_p]
    libcsound.csoundSleep.argtypes = [ct.c_size_t]

    # Opcodes
    libcsound.csoundLoadPlugins.restype = ct.c_int32
    libcsound.csoundLoadPlugins.argtypes = [CSOUND_p, ct.c_char_p]
    libcsound.csoundAppendOpcode.restype = ct.c_int32
    libcsound.csoundAppendOpcode.argtypes = [CSOUND_p, ct.c_char_p, ct.c_int32, ct.c_int32, ct.c_char_p, ct.c_char_p, OPCODEFUNC, OPCODEFUNC, OPCODEFUNC]

    # Table display (from graph_display.h)
    libcsound.csoundSetIsGraphable.argtypes = [CSOUND_p, ct.c_int]
    libcsound.csoundSetDrawGraphCallback.argtypes = [CSOUND_p, DRAWGRAPHFUNC]
    libcsound.csoundSetMakeGraphCallback.argtypes = [CSOUND_p, MAKEGRAPHFUNC]
    libcsound.csoundSetKillGraphCallback.argtypes = [CSOUND_p, KILLGRAPHFUNC]
    libcsound.csoundSetExitGraphCallback.argtypes = [CSOUND_p, EXITGRAPHFUNC]

    # Circular buffer functions (from circular_buffer.h)
    libcsound.csoundCreateCircularBuffer.restype = ct.c_void_p
    libcsound.csoundCreateCircularBuffer.argtypes = [CSOUND_p, ct.c_int32, ct.c_int32]
    libcsound.csoundReadCircularBuffer.restype = ct.c_int32
    libcsound.csoundReadCircularBuffer.argtypes = [CSOUND_p, ct.c_void_p, ct.c_void_p, ct.c_int32]
    libcsound.csoundPeekCircularBuffer.restype = ct.c_int32
    libcsound.csoundPeekCircularBuffer.argtypes = [CSOUND_p, ct.c_void_p, ct.c_void_p, ct.c_int32]
    libcsound.csoundWriteCircularBuffer.restype = ct.c_int32
    libcsound.csoundWriteCircularBuffer.argtypes = [CSOUND_p, ct.c_void_p, ct.c_void_p, ct.c_int32]
    libcsound.csoundFlushCircularBuffer.argtypes = [CSOUND_p, ct.c_void_p]
    libcsound.csoundDestroyCircularBuffer.argtypes = [CSOUND_p, ct.c_void_p]
    libcsound.csoundSetOpenSoundFileCallback.argtypes = [CSOUND_p, OPENSOUNDFILEFUNC]
    libcsound.csoundSetOpenFileCallback.argtypes = [CSOUND_p, OPENFILEFUNC]

    libcspt.csoundCreatePerformanceThread.restype = CSOUNDPERFTHREAD_p
    libcspt.csoundCreatePerformanceThread.argtypes = [CSOUND_p]
    libcspt.csoundDestroyPerformanceThread.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadIsRunning.restype = ct.c_int32
    libcspt.csoundPerformanceThreadIsRunning.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadGetProcessCB.restype = ct.c_void_p
    libcspt.csoundPerformanceThreadGetProcessCB.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadSetProcessCB.argtypes = [CSOUNDPERFTHREAD_p, PROCESSFUNC, ct.c_void_p]
    libcspt.csoundPerformanceThreadGetCsound.restype = CSOUND_p
    libcspt.csoundPerformanceThreadGetCsound.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadGetStatus.restype = ct.c_int32
    libcspt.csoundPerformanceThreadGetStatus.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadPlay.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadPause.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadTogglePause.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadStop.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadRecord.argtypes = [CSOUNDPERFTHREAD_p, ct.c_char_p, ct.c_int32, ct.c_int32]
    libcspt.csoundPerformanceThreadStopRecord.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadScoreEvent.argtypes = [CSOUNDPERFTHREAD_p, ct.c_int32, ct.c_char, ct.c_int32, ct.POINTER(MYFLT)]
    libcspt.csoundPerformanceThreadInputMessage.argtypes = [CSOUNDPERFTHREAD_p, ct.c_char_p]
    libcspt.csoundPerformanceThreadSetScoreOffsetSeconds.argtypes = [CSOUNDPERFTHREAD_p, ct.c_double]
    libcspt.csoundPerformanceThreadJoin.restype = ct.c_int32
    libcspt.csoundPerformanceThreadJoin.argtypes = [CSOUNDPERFTHREAD_p]
    libcspt.csoundPerformanceThreadFlushMessageQueue.argtypes = [CSOUNDPERFTHREAD_p]

    libcspt.csoundPerformanceThreadCompileOrc.restype = ct.c_void_p
    libcspt.csoundPerformanceThreadCompileOrc.argtypes = [CSOUNDPERFTHREAD_p, ct.c_char_p]

    libcspt.csoundPerformanceThreadEvalCode.restype = ct.c_void_p
    libcspt.csoundPerformanceThreadEvalCode.argtypes = [CSOUNDPERFTHREAD_p, ct.c_char_p, EVALCODEFUNC]

    libcspt.csoundPerformanceThreadRequestCallback.restype = ct.c_void_p
    libcspt.csoundPerformanceThreadRequestCallback.argtypes = [CSOUNDPERFTHREAD_p, REQUESTCALLBACKFUNC]


if not BUILDING_DOCS:
    libcsound, libcsoundpath = _dll.csoundDLL()
    libcspt = libcsound
    _declareAPI(libcsound, libcspt)


_scoreEventToTypenum = {
    'i': CS_INSTR_EVENT,
    'f': CS_TABLE_EVENT,
    'e': CS_END_EVENT}


# --------------------------------------------------------------------------------


class Csound:
    """
    This class represents an instance of a csound process

    Args:
        hostData: any data, will be accessible within certain callbacks
        opcodeDir: the folder where to load opcodes from. If not given,
            default folders are used
        pointer: if given, the result of calling libcsound.csoundCreate(...),
            uses the given csound process instead of creating a new one

    Attributes:
        cs: a pointer to a csound process

    """
    def __init__(self,
                 hostData=None,
                 opcodeDir='',
                 pointer: ct.c_void_p | None = None):
        """
        Creates an instance of Csound.

        The hostData parameter can be None, or it can be any sort of data; these
        data can be accessed from the Csound instance that is passed to callback routines.
        If not None the opcodeDir parameter sets an override for the plugin module/opcode
        directory search.
        """
        if pointer is not None:
            self.cs: CSOUND_p = pointer
            self._fromPointer = True
        else:
            opcdir = cstring(opcodeDir) if opcodeDir else ct.c_char_p()
            self.cs: CSOUND_p = libcsound.csoundCreate(ct.py_object(hostData), opcdir)
            self._fromPointer = False

        self._callbacks: dict[str, ct._FuncPointer] = {}
        """Holds any callback set"""

        self._perfthread: PerformanceThread | None = None
        """Holds the PerformanceThread attached to this csound instance, if any"""

        self._compilationStarted = False

        self._started = False

    def destroy(self):
        if self._perfthread:
            self._perfthread = None  # This should destroy the performance thread
        if self.cs is not None:
            libcsound.csoundDestroy(self.cs)
            self.cs = None  # type: ignore

    def __del__(self):
        """Destroys an instance of Csound."""
        if self._perfthread:
            self._perfthread = None  # This should destroy the performance thread

        if not self._fromPointer and self.cs is not None:
            libcsound.csoundDestroy(self.cs)
            self.cs = None  # type: ignore

    def csound(self) -> CSOUND_p:
        """
        Returns the opaque pointer to the underlying CSOUND struct.

        This pointer is needed to instantiate a PerformanceThread object.
        """
        return self.cs

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

        """
        if self._perfthread is None:
            self._perfthread = PerformanceThread(self)
        return self._perfthread

    #
    # Attributes
    #
    def version(self) -> int:
        """The version number times 1000 (6.18.0 = 6180)."""
        return libcsound.csoundGetVersion()

    def APIVersion(self) -> int:
        """
        For compatibility, csound 7 does not implement an api version at the moment

        In csound 6 there was a version for csound / libcsound and a version for
        the API, indicating that a new version of csound did not necessarily mean
        a modification of the API itself. The API version tracked changes in the API.
        With csound 7 this practice has been abandoned and the API version removed.
        This method is added for compatibility, with the version reported being the
        same as the csound version (returned by :py:meth:`version`)
        """
        return self.version()

    def sr(self) -> float:
        """Returns the number of audio sample frames per second."""
        return libcsound.csoundGetSr(self.cs)

    def kr(self) -> float:
        """Number of control samples per second."""
        return libcsound.csoundGetKr(self.cs)

    def ksmps(self) -> int:
        """Number of audio sample frames per control sample."""
        return libcsound.csoundGetKsmps(self.cs)

    def nchnls(self) -> int:
        """Number of output channels"""
        return libcsound.csoundGetChannels(self.cs, ct.c_int32(0))

    def nchnlsInput(self) -> int:
        """Number of input channels"""
        return libcsound.csoundGetChannels(self.cs, ct.c_int32(1))

    def get0dBFS(self) -> float:
        """Returns the 0dBFS level of the spin/spout buffers."""
        return libcsound.csoundGet0dBFS(self.cs)

    def A4(self) -> float:
        """Returns the A4 frequency reference."""
        return libcsound.csoundGetA4(self.cs)

    def currentTimeSamples(self) -> int:
        """Current performance time in samples."""
        return libcsound.csoundGetCurrentTimeSamples(self.cs)

    def sizeOfMYFLT(self) -> int:
        """Size of MYFLT in bytes."""
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

    def env(self, name: str) -> str | None:
        """Gets the value of environment variable name.

        Args:
            name: the environment variable

        Returns:
            the value or None if no such variable is found

        The searching order is: local environment of Csound,
        variables set with :meth:`Csound.setGlobalEnv`, and system environment variables.
        Should be called after compileCommandLine().
        Return value is None if the variable is not set.
        """
        ret = libcsound.csoundGetEnv(self.cs, cstring(name))
        if (ret):
            return pstring(ret)
        return None

    def setGlobalEnv(self, name: str, value: str | None) -> int:
        """Set the global value of environment variable name to value.

        Args:
            name: the name of the environment variable
            value: the value of the variable, or None to delete the variable

        Returns:
            0 if successfull, non-zero otherwise

        .. note::  It is not safe to call this function while any Csound instances
            are active.

        """
        return libcsound.csoundSetGlobalEnv(cstring(name), cstring(value) if value is not None else ct.c_char_p())

    def setOption(self, option: str) -> int:
        """
        Set csound option/options

        Args:
            option: a command line option passed to the csound process. Any number
                of options can be passed at once, separated by whitespace

        Returns:
            zero on success, an error code otherwise

        **Options can only be set before the csound process is started**. Multiple
        options are allowed in one string.

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
        if self._compilationStarted:
            raise RuntimeError(f"Cannot set options once code has already been compiled")
        return libcsound.csoundSetOption(self.cs, cstring(option))

    def params(self, params: CsoundParams | None = None) -> CsoundParams:
        """Current set of parameters from a CSOUND instance.

        Args:
            params: if given, the destination of the params structure. Otherwise
                a ``CsoundParams`` struct is created and returned

        Returns:
            the CsoundParams structure. If given a struct as argument,
            that same struct is returned

        .. seealso:: :meth:`Csound.setParams`

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

        Those messages are sent through the DebugMsg() internal API
        function.
        """
        return libcsound.csoundGetDebug(self.cs) != 0

    def setDebug(self, debug: bool) -> None:
        """Sets whether Csound prints debug messages.

        Args:
            debug: if True, debugging is turned on. Otherwise debug
                messages are not printed

        The debug argument must have value True or False.
        Those messages come from the DebugMsg() internal API function.
        """
        libcsound.csoundSetDebug(self.cs, ct.c_int32(debug))

    def systemSr(self, val: float = 0.) -> float:
        """If val > 0, sets the internal variable holding the system HW sr.

        Args:
            val: if given, sets the system sr to this value

        Returns:
            the stored value containing the system HW sr.
        """
        return libcsound.csoundSystemSr(self.cs, val)

    def module(self, number: int) -> tuple[str, str, int]:
        """
        Retrieves a module name and type given a number.

        Args:
            number: a number identifying the module

        Returns:
            a tuple ``(name: str, kind: str, errcode: int)``

        Name is the name of the module, kind is "audio" or "midi" and
        errcode is CSOUND_SUCCESS on success and CSOUND_ERROR if module
        number was not found

        .. rubric:: Example

        .. code-block:: python

            n = 0
            while True:
                name, kind, err = cs.module(n)
                if err == ctcsound.CSOUND_ERROR:
                    break
                print(f"Module {n}: {name} ({kind})")
                n += 1
        """
        name = ct.pointer(ct.c_char_p(cstring("dummy")))
        kind = ct.pointer(ct.c_char_p(cstring("dummy")))
        err = libcsound.csoundGetModule(self.cs, ct.c_int32(number), name, kind)
        if err == CSOUND_ERROR:
            return '', '', err
        n = pstring(ct.string_at(name.contents))
        t = pstring(ct.string_at(kind.contents))
        return n, t, err

    def modules(self) -> list[tuple[str, str]]:
        """
        Returns a list of modules

        Returns:
            a list of tuples of the form ``(name: str, type: str)``,
            where name is the name of the module and type is one of
            "audio" or "midi"

        .. seealso:: :py:meth:`module`
        """
        n = 0
        out = []
        while True:
            name, moduletype, err = self.module(n)
            if err == CSOUND_ERROR:
                break
            out.append((name, moduletype))
            n += 1
        return out

    def audioDevList(self, isOutput: bool) -> list[AudioDevice]:
        """List of available input and output audio devices.

        Args:
            isOutput: True to return output devices, False outputs
                input devices

        Returns:
            a list of audio devices

        Each item in the list is a :class:`AudioDevice` with attributes
        ``deviceName``, ``deviceId``, ``rtModule``, ``masNchnls``,
        ``isOutput``

        Must be called after an orchestra has been compiled
        to get meaningful information.
        """
        n = libcsound.csoundGetAudioDevList(self.cs, None, ct.c_int32(isOutput))
        devs = (CsoundAudioDevice * n)()
        libcsound.csoundGetAudioDevList(self.cs, ct.byref(devs), ct.c_int32(isOutput))
        lst = []
        for dev in devs:
            d = AudioDevice(deviceName=pstring(dev.device_name),
                            deviceId=pstring(dev.device_id),
                            rtModule=pstring(dev.rt_module),
                            maxNchnls=dev.max_nchnls,
                            isOutput=dev.isOutput == 1)
            lst.append(d)
        return lst

    def midiDevList(self, isOutput=False) -> list[MidiDevice]:
        """Returns a list of available input or output midi devices.

        Args:
            isOutput: True to return output devices, False outputs
                input devices

        Returns:
            a list of midi devices

        Each item in the list is a dictionnary representing a device. The
        dictionnary keys are device_name, interface_name, device_id,
        midi_module (value type string), isOutput (value type boolean).

        Must be called after an orchestra has been compiled
        to get meaningful information.
        """
        n = libcsound.csoundGetMIDIDevList(self.cs, None, ct.c_int32(isOutput))
        devs = (CsoundMidiDevice * n)()
        libcsound.csoundGetMIDIDevList(self.cs, ct.byref(devs), ct.c_int32(isOutput))
        return [MidiDevice(deviceName=pstring(dev.device_name),
                           interfaceName=pstring(dev.interface_name),
                           deviceId=pstring(dev.device_id),
                           midiModule=pstring(dev.midi_module),
                           isOutput=(dev.isOutput == 1))
                for dev in devs]

    def messageLevel(self) -> int:
        """Returns the Csound message level (from 0 to 231)."""
        return libcsound.csoundGetMessageLevel(self.cs)

    def setMessageLevel(self, messageLevel: int) -> None:
        """Sets the Csound message level (from 0 to 231).

        Args:
            messageLevel: message level, a number between 0 and 231.
                TODO: explain what this means
        """
        libcsound.csoundSetMessageLevel(self.cs, ct.c_int32(messageLevel))

    #
    # Performance
    #
    def compile(self, *args, **kws):
        warnings.warn("This method is deprecated, use compileCommandLine")
        raise DeprecationWarning("This method has been renamed to compileCommandLine")

    def compileCommandLine(self, *args):
        """
        Compiles csound command line arguments

        As directed by the supplied command-line arguments,
        but does not perform them. Returns a non-zero error code on failure.
        In this mode, the sequence of calls should be as follows::

            cs = Csound()
            cs.compileCommandLine(args)
            cs.perform()
            cs.reset()
        """
        self._compilationStarted = True
        argc, argv = csoundArgList(args)
        return libcsound.csoundCompile(self.cs, argc, argv)

    def compileOrc(self, orc: str, block=True) -> int:
        """
        Parses and compiles the given orchestra from a string.

        Args:
            orc: the code to compile
            block: if True, any global code will be evaluated in synchronous
                mode. Otherwise, this methods returns immediately but any
                global code passed to csound might not still be available

        Returns:
            0 if OK, an error code otherwise

        Also evaluating any global space code (i-time only)
        in synchronous or asynchronous (block=False) mode.

        .. rubric:: Example

        .. code-block:: python

            cs = Csound()
            cs.setOption(...)
            cs.compileOrc(r'''
            instr 1
                a1 rand 0dbfs/4
                out a1
            endin
            ''')
            cs.scoreEvent(...)
            cs.perform()

        .. seealso:: :meth:`PerformanceThread.compileOrc`
        """
        return libcsound.csoundCompileOrc(self.cs, cstring(orc), ct.c_int32(not block))

    def compileOrcAsync(self, orc: str) -> int:
        """Async version of :py:meth:`compileOrc()`.

        .. note::

            ported from csound 6 for portability. This is similar to calling
            :py:meth:`compileOrc` with ``block=False``

        Args:
            orc: the code to compile

        Returns:
            0 if OK, an error otherwise

        The code is parsed and compiled, then placed on a queue for
        asynchronous merge into the running engine, and evaluation.
        The function returns following parsing and compilation.

        .. seealso:: :meth:`PerformanceThread.compileOrc`

        """
        return self.compileOrc(orc, block=False)

    def compileOrcHeader(self,
                         sr: int | None = None,
                         nchnls=2,
                         nchnls_i: int | None = None,
                         zerodbfs=1.,
                         ksmps=64,
                         a4: int | None = None) -> None:
        """
        Compile the orchestra header (sr, ksmps, nchnls, ...)

        Only those values which are explicitly given (not None) are included

        .. note:: Values set via options are prioritized over values set in the orchestra

        Args:
            sr: the sample rate
            ksmps: samples per cycle
            nchnls: number of output channels
            nchnls_i: number of input channels
            zerodbfs: the value of 0dbfs, should be 1. for any mordern orchestra
            a4: reference frequency
        """
        lines = []
        if sr:
            lines.append(f'sr = {sr}')
        lines.append(f'ksmps = {ksmps}\nnchnls = {nchnls}\n0dbfs = {zerodbfs}')
        if nchnls_i is not None:
            lines.append(f'nchnls_i = {nchnls_i}')
        if a4 is not None:
            lines.append(f'A4 = {a4}')
        code = '\n'.join(lines)
        self.compileOrc(code)

    def evalCode(self, code: str) -> float:
        """
        Evaluate the given code (blocking), returns the value passed to the ``return`` opcode

        Args:
            code: the code to evaluate. This code is evaluated at the global space
                and is limited to init-time code

        Returns:
            the value passed to the ``return`` opcode in global space

        .. rubric:: Example

        .. code-block:: python

            code = '''
              i1 = 2 + 2
              return i1
            '''
            retval = cs.evalCode(code)

        .. note::

            Calling this method while csound is run in realtime via a performance
            thread might incur in high latency. To avoid this, call the
            :meth:`~PerformanceThread.evalCode` method on the performance
            thread
        """
        return libcsound.csoundEvalCode(self.cs, cstring(code))

    def compileCsd(self, path: str, block=True) -> int:
        """
        Compiles a Csound input file (.csd file)

        Returns a non-zero error code on failure.

        Args:
            path: the path to the .csd file
            block: if True, block until finished. Otherwise compilation
                is done asynchronously. In this case the returned value
                is meaningless

        If :py:meth:`start()` is called before this method, the ``<CsOptions>``
        element is ignored (but :py:meth:`setOption()` can be called any number of
        times), the ``<CsScore>`` element **is not pre-processed**, but dispatched as
        real-time events; and performance continues indefinitely, or until
        ended by calling stop or some other logic.

        .. note::
            this function can be called repeatedly during performance to
            replace or add new instruments and events.

        .. rubric:: Example

        .. code-block:: python

            cs = Csound()
            cs.setOption(...)
            cs.start()   # <---- start before compile, options in compiled code will be ignored
            cs.compileCsd("/path/to/my.csd")
            while cs.performKsmps() == CSOUND_SUCCESS:
                pass
            cs.reset()

        But if this method is called before start, the ``<CsOptions>``
        element is used, the ``<CsScore>`` section **is pre-processed and dispatched
        normally**, and performance terminates when the score terminates, or
        stop is called.

        .. code-block:: python

            cs = Csound()
            cs.setOption(...)
            # No start, the <CsOption> section is honoured
            cs.compileCsd("/path/to/my.csd")
            # .start is called internally before performKsmps,
            while cs.performKsmps() == CSOUND_SUCCESS:
                pass
            cs.reset()

        """
        return libcsound.csoundCompileCSD(self.cs, cstring(path), ct.c_int32(0), ct.c_int32(1-int(block)))

    def compileCsdText(self, code: str, block=True) -> int:
        """
        Compiles a Csound input file (.csd file) or a text string.

        Args:
            code: the code to compile
            block: if True, block until finished. Otherwise compilation
                is done asynchronously. In this case the returned value
                is meaningless

        Returns:
            non-zero error code on failure.

        If :py:meth:`start()` is called before this method, the ``<CsOptions>``
        element **is ignored** (but :py:meth:`setOption()` can be called any number of
        times), the ``<CsScore>`` element **is not pre-processed**, but *dispatched as
        real-time events*; and **performance continues indefinitely**, or until
        ended by calling stop or some other logic.

        .. note::

            This function can be called repeatedly during performance to
            replace or add new instruments and events.

        .. rubric:: Example

        .. code-block:: python

            >>> from libcsound import *
            >>> cs = Csound()
            >>> cs.setOption(...)
            >>> cs.start()
            >>> cs.compileCsdText(code)
            >>> while not cs.performKsmps():
            ...     pass
            >>> cs.reset()

        But if this method is called before :py:meth:`start()`, the ``<CsOptions>``
        element is used, the ``<CsScore>`` section **is pre-processed and dispatched
        normally**, and performance terminates when the score terminates, or
        stop is called.

        .. code-block:: python

            ...
            cs.compileCsdText(code)
            cs.start()
            while not cs.performKsmps():
                pass
            cs.reset()
        """
        return libcsound.csoundCompileCSD(self.cs, cstring(code), ct.c_int32(1), ct.c_int32(1-int(block)))

    def start(self):
        """
        Prepares Csound for performance.

        Returns:
            CSOUND_SUCCESS (0) if ok, an error code otherwise

        Normally called after compiling a csd file or an orc file, in which
        case score preprocessing is performed and performance terminates
        when the score terminates.

        However, **if called before compiling any csound code** (either by
        compiling a csd file or orc code), score preprocessing is not
        performed and "i" statements are dispatched as real-time events.
        In this case, any options given as part of the ``<CsOptions>``
        section are ignored: **options can only be set prior to
        starting the csound process**

        .. note::

            This method is called internally by methods like
            :py:meth:`compileCommandLine()`, :py:meth:`perform`, :py:meth:`performKsmps`,
            :py:meth:`performBuffer`, or when a performance thread is
            created for this csound instance and the thread itself is started
            via its :meth:`~PerformanceThread.play` method.

        """
        if not self._started:
            self._started = True
            return libcsound.csoundStart(self.cs)

    def stop(self) -> None:
        """
        Only here for compatibility, not exposed in csound7
        """
        if self._perfthread:
            self._perfthread.stop()
            self._perfthread.join()
            self._perfthread = None
        return

    def cleanup(self) -> None:
        """
        This is not needed in csound7, only here for compatibility
        """
        return

    def perform(self) -> int:
        """
        Handles input events and performs audio output.

        This is done until the end of score is reached (positive return value),
        an error occurs (negative return value), or performance is stopped by
        calling :py:meth:`stop()` from another thread (zero return value).

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

        .. note::

            The underlying function ``csoundPerform`` has been removed from the
            API in csound 7. This method is included here for backwards compatibility
            with csound 6 and might be removed in the future.

        """
        if not self._started:
            self.start()
        while True:
            retcode = self.performKsmps()
            if retcode != CSOUND_SUCCESS:
                break
        return 1

    def performKsmps(self) -> bool:
        """
        Handles input events, and performs audio output for one cycle

        This is done for one control sample worth (ksmps) of audio output.

        Returns:
            False during performance, True when performance is finished.

        If called until it returns True, it will perform an entire score.
        Enables external software to control the execution of Csound,
        and to synchronize performance with audio input and output.
        """
        if not self._started:
            self.start()
        return bool(libcsound.csoundPerformKsmps(self.cs))

    def runUtility(self, name: str, args: list[str]) -> int:
        """Runs utility with the specified name and command line arguments.

        Args:
            name: the utility to run
            args: a list of arguments to pass to it

        Returns:
            zero if ok, an error code otherwise

        Should be called after loading utility plugins.
        Use reset() to clean up after calling this function.
        Returns zero if the utility was run successfully.
        """
        argc, argv = csoundArgList(args)
        return libcsound.csoundRunUtility(self.cs, cstring(name), argc, argv)

    def reset(self) -> None:
        """
        Resets all internal memory and state.

        In preparation for a new performance.
        Enable external software to run successive Csound performances
        without reloading Csound.
        """
        libcsound.csoundReset(self.cs)
        self._started = False
        self._compilationStarted = False

    #
    # Realtime Audio I/O
    #
    def setHostAudioIO(self):
        """Disable all default handling of sound I/O.

        Calling this function after the creation of a Csound object
        and before the start of performance will disable all default
        handling of sound I/O by the Csound library via its audio
        backend module.
        Host application should in this case use the spin/spout
        buffers directly.
        """
        libcsound.csoundSetHostAudioIO(self.cs)

    def setHostImplementedAudioIO(self, state: bool, bufSize: int = 0):
        warnings.warn("This method is deprecated, use setHostAudioIO")
        self.setHostAudioIO()

    def setRTAudioModule(self, module: str) -> None:
        """Sets the current RT audio module.

        Args:
            module: the name of the module. Possible values depend on
                the platform.

        =========  ===========================
        Platform    Modules
        =========  ===========================
        linux       jack, pa_cb (portaudio)
        macos       au_hal (coreaudio), pa_cb, jack
        windows     pa_cb (portaudio), winmm
        =========  ===========================

        """
        libcsound.csoundSetRTAudioModule(self.cs, cstring(module))

    def spin(self) -> np.ndarray:
        """
        Returns the Csound audio input working buffer (spin) as an ndarray.

        Enables external software to write audio into Csound before
        calling perform_ksmps().
        """
        buf = libcsound.csoundGetSpin(self.cs)
        size = self.ksmps() * self.nchnlsInput()
        return _util.castarray(buf, shape=(size,))

    def spout(self) -> np.ndarray:
        """
        Returns the address of the Csound audio output working buffer (spout).

        Enables external software to read audio from Csound after
        calling perform_ksmps().
        """
        buf = libcsound.csoundGetSpout(self.cs)
        size = self.ksmps() * self.nchnls()
        return _util.castarray(buf, shape=(size,))

    def setHostMidiIO(self) -> None:
        """
        Disable all default handling of MIDI I/O.

        Call this method before the start of performance to implement
        MIDI via the callbacks below.
        """
        libcsound.csoundSetHostMIDIIO(self.cs)

    def setHostImplementedMidiIO(self, state: bool) -> None:
        """
        Called with ``state=True`` disables native midi IO

        In that case the host implements all midi input/output via callbacks

        .. note:: this method is here for compatibility with csound 6. It is a proxy
            for :meth:`Csound.setHostMidiIO`
        """
        if state:
            self.setHostMidiIO()

    def setMidiModule(self, module: str) -> None:
        """Sets the current MIDI IO module.

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

    def setExternalMidiInOpenCallback(self, function) -> None:
        """
        Sets a callback for opening real-time MIDI input.
        """
        self._callbacks['externalMidiInOpen'] = func = MIDIINOPENFUNC(function)
        libcsound.csoundSetExternalMidiInOpenCallback(self.cs, func)

    def setExternalMidiReadCallback(self, function) -> None:
        """Sets a callback for reading from real time MIDI input."""
        self._callbacks['externalMidiRead'] = func = MIDIREADFUNC(function)
        libcsound.csoundSetExternalMidiReadCallback(self.cs, func)

    def setExternalMidiInCloseCallback(self, function):
        """Sets a callback for closing real time MIDI input."""
        self._callbacks['externalMidiInClose'] = func = MIDIINCLOSEFUNC(function)
        libcsound.csoundSetExternalMidiInCloseCallback(self.cs, func)

    def setExternalMidiOutOpenCallback(self, function):
        """Sets a callback for opening real-time MIDI input."""
        self._callbacks['externalMidiOutOpen'] = func = MIDIOUTOPENFUNC(function)
        libcsound.csoundSetExternalMidiOutOpenCallback(self.cs, func)

    def setExternalMidiWriteCallback(self, function):
        """Sets a callback for reading from real time MIDI input."""
        self._callbacks['externalMidiWrite'] = func = MIDIWRITEFUNC(function)
        libcsound.csoundSetExternalMidiWriteCallback(self.cs, func)

    def setExternalMidiOutCloseCallback(self, function):
        """Sets a callback for closing real time MIDI input."""
        self._callbacks['externalMidiOutClose'] = func = MIDIOUTCLOSEFUNC(function)
        libcsound.csoundSetExternalMidiOutCloseCallback(self.cs, func)

    def setExternalMidiErrorStringCallback(self, function):
        """ Sets a callback for converting MIDI error codes to strings."""
        self._callbacks['externalMidiErrorString'] = f = MIDIERRORFUNC(function)
        libcsound.csoundSetExternalMidiErrorStringCallback(self.cs, f)

    def setMidiDeviceListCallback(self, function):
        """Sets a callback for obtaining a list of MIDI devices."""
        self._callbacks['setMidiDeviceList'] = f = MIDIDEVLISTFUNC(function)
        libcsound.csoundSetMIDIDeviceListCallback(self.cs, f)
    #
    # Csound Messages and Text
    #
    def message(self, message: str):
        """Displays an informational message.

        Args:
            message: the message to display

        """
        libcsound.csoundMessage(self.cs, cstring("%s"), cstring(message))

    def messageS(self, attr: int, message: str) -> None:
        """
        Prints message with special attributes.

        Args:
            attr: an integer attribute
            message: the message to display

        (See msg_attr.h for the list of available attributes). With attr=0,
        message_S() is identical to message().
        """
        libcsound.csoundMessageS(self.cs, ct.c_int32(attr), cstring("%s"), cstring(message))

    def setMessageStringCallback(self, attr: int, function):
        """Sets an alternative message print function.

        This function is to be called by Csound to print an
        informational message, using a less granular signature.
        This callback can be set for --realtime mode.
        This callback is cleared after reset.
        """
        self._callbacks['messageString'] = func = MSGSTRFUNC(function)
        libcsound.csoundSetMessageStringCallback(self.cs, ct.c_int32(attr), func)

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
        libcsound.csoundCreateMessageBuffer(self.cs, ct.c_int32(echo))

    def firstMessage(self) -> str:
        """
        Returns the first message from the buffer.

        .. seealso:: :py:meth:`readMessage` or :py:meth:`iterMessages` for a
            more ergonomic method to access the message buffer
        """
        s = libcsound.csoundGetFirstMessage(self.cs)
        return pstring(s)

    def firstMessageAttr(self) -> int:
        """
        Returns the attribute parameter of the first message in the buffer.

        .. seealso:: :py:meth:`readMessage` or :py:meth:`iterMessages` for a
            more ergonomic method to access the message buffer
        """
        return libcsound.csoundGetFirstMessageAttr(self.cs)

    def popFirstMessage(self) -> None:
        """
        Removes the first message from the buffer.

        .. seealso:: :py:meth:`readMessage` or :py:meth:`iterMessages` for a
            more ergonomic method to access the message buffer
        """
        libcsound.csoundPopFirstMessage(self.cs)

    def messageCnt(self) -> int:
        """Returns the number of pending messages in the buffer."""
        return libcsound.csoundGetMessageCnt(self.cs)

    def destroyMessageBuffer(self) -> None:
        """Releases all memory used by the message buffer."""
        libcsound.csoundDestroyMessageBuffer(self.cs)

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

    #
    # Channels, Controls and Events
    #
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
                CSOUND_STRING_CHANNEL: 'string',
                CSOUND_PVS_CHANNEL: 'pvs',
                CSOUND_ARRAY_CHANNEL: 'array'
            }.get(chantype)
            if kind is None:
                raise RuntimeError(f"Got invalid channel kind: {chantype}")
            return kind, mode

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
        length = 1  # default buf length for CSOUND_CONTROL_CHANNEL:
        ptr = ct.c_void_p()
        chan_type = type_ & CSOUND_CHANNEL_TYPE_MASK
        err = ''
        ret = libcsound.csoundGetChannelPtr(self.cs, ct.byref(ptr), cstring(name), type_)
        if ret == CSOUND_SUCCESS:
            if chan_type == CSOUND_STRING_CHANNEL:
                return ct.cast(ptr, STRINGDAT_p), err
            elif chan_type == CSOUND_ARRAY_CHANNEL:
                # TODO: cast to a numpy array
                return ct.cast(ptr, ARRAYDAT_p), err
            elif chan_type == CSOUND_PVS_CHANNEL:
                return ct.cast(ptr, PVSDAT_p), err
            elif chan_type == CSOUND_AUDIO_CHANNEL:
                length = libcsound.csoundGetKsmps(self.cs)
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
        elif ret == CSOUND_ARRAY_CHANNEL:
            err = 'An array channel named {} already exists'.format(name)
        elif ret == CSOUND_PVS_CHANNEL:
            err = 'A PVS channel named {} already exists'.format(name)
        else:
            err = 'Unknown error'
        return None, err

    def channelVarTypeName(self, name: str) -> str:
        """Returns the var type for a channel name.

        Args:
            name: name of the channel

        Returns:
            The channel variable type (one of 'control', 'audio',
            'string', 'pvs' or 'array') or an empty string
            if the channel does not exist

        Returns None if the channel was not found.
        Currently supported channel var types are 'control', 'audio',
        'string', 'pvs' and 'array'
        """
        ret = libcsound.csoundGetChannelVarTypeName(self.cs, cstring(name))
        if not ret:
            return ''
        return {
            'k': 'control',
            'a': 'audio',
            'S': 'string',
            'f': 'pvs',
            '[': 'array'
            }[ret]

    def allocatedChannels(self) -> list[ChannelInfo]:
        """
        Returns a list of allocated channels
        """
        chanlist, err = self.listChannels()
        if err:
            raise RuntimeError(f"Error while getting a list of channels: {err}")
        assert chanlist is not None
        n = len(chanlist)
        out = []
        for chaninfo in chanlist:
            assert isinstance(chaninfo, ControlChannelInfo)
            if chaninfo.hints:
                hints = {'min': chaninfo.hints.min,
                        'max': chaninfo.hints.max,
                        'width': chaninfo.hints.width,
                        'height': chaninfo.hints.height}
            else:
                hints = None
            kind, modeint = _util.unpackChannelType(chaninfo.type)
            out.append(ChannelInfo(name=chaninfo.name, kind=kind, mode=modeint, hints=hints))
        self.deleteChannelList(chanlist)
        return out

    def listChannels(self) -> tuple[ct.Array[ControlChannelInfo] | None, str]:
        """
        Returns a list of allocated channels and an error message.

        .. note::
            This is a low-level function, kept here for completion and compatibility
            with csound 6. To list all allocated channels in a more ergonomic way
            see :py:meth:`allocatedChannels()`

        A :class:`ControlChannelInfo` object contains the channel characteristics.
        The error message indicates if there is not enough
        memory for allocating the list or it is an empty string if there is no
        error. In the case of no channels or an error, the list is None.

        .. note::

            The caller is responsible for freeing the list returned by the
            C API with :py:meth:`deleteChannelList()`. The name pointers may become
            invalid after calling reset().

        .. seealso:: :py:meth:`allocatedChannels()`
        """
        ptr = ct.cast(ct.POINTER(ct.c_int)(), ct.POINTER(ControlChannelInfo))
        n = libcsound.csoundListChannels(self.cs, ct.byref(ptr))
        if n > 0:
            return ct.cast(ptr, ct.POINTER(ControlChannelInfo * n)).contents, ''
        if n == CSOUND_MEMORY :
            return None, 'There is not enough memory for allocating the list'
        else:
            return None, 'Unknown error'

    def deleteChannelList(self, lst: ct.Array[ControlChannelInfo]) -> None:
        """Releases a channel list previously returned by list_channels()."""
        ptr = ct.cast(lst, ct.POINTER(ControlChannelInfo))
        libcsound.csoundDeleteChannelList(self.cs, ptr)

    def setControlChannelHints(self,
                               name: str,
                               hints: ControlChannelHints | None = None,
                               behav: int = 0,
                               dflt: float = 0.01,
                               min: float = 0.,
                               max: float = 1.,
                               x: int = 0,
                               y: int = 0,
                               width: int = 0,
                               height: int = 0,
                               attributes: str | None = None) -> None:
        """
        Args:
            name: name of the channel
            hints: the hints to set. If None, a hints structure will be constructed with
                the named arguments. If given, any other settings (min, max, x, ...) will
                be ignored
            behav:

        Returns:
            CSOUND_SUCCSESS (0) if ok, CSOUND_ERROR if the channel does not exist,
            it is not a control channel or the parameters are invalid, CSOUND_MEMORY
            if could not allocate memory

        These hints have no internal function but can be used by front ends to
        construct GUIs or to constrain values. See the ControlChannelHints
        structure for details.

        """
        if hints is None:
            hints = ControlChannelHints(behav=behav, dflt=dflt, min=min, max=max, x=x, y=y, width=width, height=height, attributes=attributes)
        return libcsound.csoundSetControlChannelHints(self.cs, cstring(name), hints)

    def controlChannelHints(self, name: str) -> tuple[ControlChannelHints | None, int]:
        """
        Returns special parameters (if any) of a control channel.

        Args:
            name: name of the channel

        Returns:
            a tuple ``(hints: ControlChannelHints, errorcode: int)`` where hints is a
            ControlChannelHints struct or None if the channel does not exist.

        Those parameters have been previously set with
        :meth:`Csound.setControlChannelHints` or the ``chnparams`` opcode.

        The return values are a ControlChannelHints structure and
        CSOUND_SUCCESS if the channel exists and is a control channel,
        otherwise, None and an error code are returned.
        """
        hints = ControlChannelHints()
        ret = libcsound.csoundGetControlChannelHints(self.cs, cstring(name),
            ct.byref(hints))
        if ret != CSOUND_SUCCESS:
            hints = None
        return hints, ret

    def lockChannel(self, channel: str) -> None:
        """Locks access to the channel.

        Access to data is allowed in a threadsafe manner.
        """
        libcsound.csoundLockChannel(self.cs, cstring(channel))

    def unlockChannel(self, channel: str):
        """Unlocks access to the channel.

        It allows access to data from elsewhere.
        """
        libcsound.csoundUnlockChannel(self.cs, cstring(channel))

    def controlChannel(self, name: str) -> tuple[float, int]:
        """Retrieves the value of control channel identified by *name*.

        Args:
            name: the name of the channel

        Returns:
            a tuple (value: float, returncode: int)

        """
        err = ct.c_int32(0)
        ret = libcsound.csoundGetControlChannel(self.cs, cstring(name), ct.byref(err))
        return ret, err.value

    def setControlChannel(self, name: str, val: float) -> None:
        """Sets the value of control channel identified by name.

        Args:
            name: name of the channel
            val: new value of the channel

        .. code-block:: python

            cs = libcsound.Csound()
            ...
            # This will create the channel if it does not exist already
            cs.setControlChannel('foo', 10)

            # To modify a control channel with low latency use a performance thread
            thread = cs.performanceThread()
            thread.play()

            # At some point, change the value with a thread task. This takes effect
            # in the next cycle
            thread.requestCallback(lambda csound: csound.setControlChannel('foo', 20))

        """
        libcsound.csoundSetControlChannel(self.cs, cstring(name), MYFLT(val))

    def audioChannel(self, name: str, samples: np.ndarray | None = None) -> np.ndarray:
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
        return samples

    def setAudioChannel(self, name: str, samples: np.ndarray):
        """
        Sets the audio channel name with data from the ndarray samples.

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

    def stringChannel(self, name: str):
        """Return a string from the string channel identified by name."""
        n = libcsound.csoundGetChannelDatasize(self.cs, cstring(name))
        if n <= 0:
            return ""
        s = ct.create_string_buffer(n)
        libcsound.csoundGetStringChannel(self.cs, cstring(name),
            ct.cast(s, ct.POINTER(ct.c_char)))
        return pstring(ct.string_at(s))

    def setStringChannel(self, name: str, string: str) -> None:
        """Sets the string channel identified by name with string.

        Args:
            name: name of the channel
            string: new value of the channel
        """
        libcsound.csoundSetStringChannel(self.cs, cstring(name), cstring(string))

    def initArrayChannel(self, name: str, dtype: str, size: int | _t.Sequence[int]):
        """Create and initialise an array channel with a given array type.

        Args:
            name: name of the channel
            dtype: the data type of array, one of 'a' (audio), 'k' (control values),
                or 'S' (strings).
            size: the size of the array or the sizes of each dimension

        Returns:
            the ARRAYDAT_p for the requested channel or None on error

        .. note:: if the channel exists and has already been initialised,
            this function is a non-op.
        """
        if isinstance(size, int):
            sizes = (size, )
        else:
            sizes = size
        sz = np.array(sizes).astype(ct.c_int)
        sizeptr = sz.ctypes.data_as(ct.POINTER(ct.c_int))
        return libcsound.csoundInitArrayChannel(self.cs, cstring(name), cstring(dtype),
                                                sz.size, sizeptr)

    def arrayDataType(self, adat: ARRAYDAT_p) -> str:
        """Get the type of data the ARRAYDAT adat.

        Args:
            adata: the ARRAYDAT_p array

        Returns:
            the array datatype as a str, one of 'a' (audio), 'i' (init),
            'k' (control values) or 'S' (strings)

        """
        return pstring(libcsound.csoundArrayDataType(adat))

    def arrayDataDimensions(self, adat: ARRAYDAT_p) -> int:
        """Get the dimensions of the ARRAYDAT adat."""
        return libcsound.csoundArrayDataDimensions(adat)

    def arrayDataSizes(self, adat) -> tuple[int, ...]:
        """Get the sizes of each dimension of the ARRAYDAT adat.

        Args:
            adata: the array, a ARRAYDAT_p struct

        Returns:
            a list of sizes, where the size of the list is the number of
            dimensions of the array
        """
        sizes = libcsound.csoundArrayDataSizes(adat)
        dims = libcsound.csoundArrayDataDimensions(adat)
        return tuple(_util.castarray(sizes, shape=(dims,)))

    def setArrayData(self, adat: ARRAYDAT_p, data: np.ndarray) -> None:
        """Set the data in the ARRAYDAT adat."""
        # TODO: check data, get a void pointer to the data
        libcsound.csoundSetArrayData(adat, data)

    def arrayData(self, adat: ARRAYDAT_p) -> np.ndarray:
        """Get the data from the ARRAYDAT adat."""
        # TODO: construct a numpy array pointing to the returned data
        return libcsound.csoundGetArrayData(adat)

    # These two functions are using c void * for the data.
    # Not very useful in Python. To be refined.
    def stringData(self, sdata):
        """Get a null-terminated string from a STRINGDAT structure."""
        return pstring(libcsound.csoundGetStringData(self.cs, sdata))

    def setStringData(self, sdata, string: str):
        """Set a STRINGDAT structure with a null-terminated string."""
        libcsound.csoundSetStringData(self.cs, sdata, cstring(string))

    def initPvsChannel(self, name: str, fftsize: int, overlap: int,
                       winsize: int, wintype: int | str, format: int = 0
                       ) -> PVSDAT_p | None:
        """
        Create/initialise an Fsig channel.

        Args:
            name: name of the channel
            fftsize: FFT analysis size
            overlap: analysis overlap size in samples
            winsize: analysis window size in samples
            wintype: analysis window type. One of 'hamming', 'hann', 'kaiser',
                'blackman', 'blackman-exact', 'nuttallc3', 'bharris3',
                'bharrismin', 'rect' (see pvsdat types enumeration)
            format: analysis data format (see pvsdat format enumeration)

        Returns:
            the PVSDAT for the requested channel or None on error.

        .. note:: if the channel exists and has already been initialised,
            this function is a non-op.
        """
        if isinstance(wintype, str):
            wintypenum = PVS_WINDOWS.get(wintype)
            if wintypenum is None:
                raise ValueError(f"Window {wintype} not known. Possible windows: {PVS_WINDOWS.keys()}")
        else:
            wintypenum = wintype
        return libcsound.csoundInitPvsChannel(self.cs, cstring(name),
            fftsize, overlap, winsize, wintypenum, format)

    def pvsDataFftSize(self, pvsdat: PVSDAT_p) -> int:
        """Get the analysis FFT size used by the PVSDAT pvsdat."""
        return libcsound.csoundPvsDataFFTSize(pvsdat)

    def pvsDataOverlap(self, pvsdat: PVSDAT_p) -> int:
        """Get the analysis overlap size used by the PVSDAT pvsdat."""
        return libcsound.csoundPvsDataOverlap(pvsdat)

    def pvsDataWindowSize(self, pvsdat: PVSDAT_p) -> int:
        """Get the analysis window size used by the PVSDAT pvsdat."""
        return libcsound.csoundPvsDataWindowSize(pvsdat)

    def pvsDataFormat(self, pvsdat: PVSDAT_p) -> int:
        """Get the analysis data format used by the PVSDAT pvsdat."""
        return libcsound.csoundPvsDataFormat(pvsdat)

    def pvsDataFramecount(self, pvsdat: PVSDAT_p) -> int:
        """Get the current framecount from PVSDAT pvsdat."""
        return libcsound.csoundPvsDataFramecount(pvsdat)

    # These two functions are using c float * for the frame data.
    # Not very useful in Python. To be refined.
    def pvsData(self, pvsdat):
        """Get the analysis data frame from the PVSDAT pvsdat."""
        return libcsound.csoundGetPvsData(pvsdat)

    def setPvsData(self, pvsdat, frame):
        """Set the analysis data frame in the PVSDAT pvsdat."""
        libcsound.csoundSetPvsData(pvsdat, frame)

    def channelDatasize(self, name: str) -> int:
        """Returns the size of data stored in a channel.

        Args:
            name: name of the channel

        Returns:
            size of the data.
        """
        return libcsound.csoundGetChannelDatasize(self.cs, cstring(name))

    def setInputChannelCallback(self, function: _t.Callable) -> None:
        """Sets the function to call whenever the invalue opcode is used."""
        self._intputChannelCallback = CHANNELFUNC(function)
        libcsound.csoundSetInputChannelCallback(self.cs, self._intputChannelCallback)

    def setOutputChannelCallback(self, function: _t.Callable) -> None:
        """Sets the function to call whenever the outvalue opcode is used."""
        self._outputChannelCallback = CHANNELFUNC(function)
        libcsound.csoundSetOutputChannelCallback(self.cs, self._outputChannelCallback)

    def event(self, kind: str, pfields: _t.Sequence[float] | np.ndarray, block=True) -> None:
        """
        Send a new event.

        Args:
            kind: the kind of event, one of 'i', 'f', 'e'
            params: pfields of the event, starting with p1
            block: if True, the operation is blocking. Otherwise it is
                performed asynchronously

        .. note:: this method does not exist in csound 6. For backwards compatibility
            use :py:meth:`scoreEvent` or :py:meth:`scoreEventAsync`
        """
        # TODO: is time absolute or relative here???
        if not self._started:
            raise RuntimeError("Csound was not started yet, cannot schedule any events")

        eventtype = _scoreEventToTypenum.get(kind)
        if eventtype is None:
            raise ValueError(f"Invalid event kind, get {kind}, expected one of {_scoreEventToTypenum.keys()}")
        p = np.asarray(pfields, dtype=MYFLT)
        ptr = p.ctypes.data_as(ct.POINTER(MYFLT))
        n_fields = ct.c_int32(p.size)
        libcsound.csoundEvent(self.cs, ct.c_int32(eventtype), ptr, n_fields, ct.c_int32(not block))

    def scoreEvent(self, kind: str, pfields: _t.Sequence[float] | np.ndarray) -> int:
        """
        Send a new event

        This is an alias to event(..., block=True), here for compatibility
        with csound 6

        Args:
            kind: the kind of event, one of 'i', 'f', 'e'
            pfields: pfields of the event, starting with p1

        Returns:
            CSOUND_SUCCESS (0) if ok, an error otherwise
        """
        self.event(kind=kind, pfields=pfields, block=True)
        return CSOUND_SUCCESS

    def scoreEventAsync(self, kind: str, pfields: _t.Sequence[float] | np.ndarray) -> None:
        """
        Send a new event, async

        This is an alias to ``csound.event(..., block=True)``, here for compatibility
        with csound 6

        Args:
            kind: the kind of event, one of 'i', 'f', 'e'
            params: pfields of the event, starting with p1
        """
        return self.event(kind=kind, pfields=pfields, block=False)

    def setEndMarker(self, time: float) -> None:
        """
        Add an end event ('e') to the score

        This stops the performance at the given time

        Args:
            time: time to add the end event
        """
        self.scoreEvent("e", [0, time])

    def inputMessage(self, message: str):
        """
        Send a new event as a string, blocking

        The syntax is the same as a score line.

        Similar to :py:meth:`eventString`, here for compatibility with csound6

        Args:
            s: a score line to send

        .. seealso:: :py:meth:`inputMessageAsync`
        """
        return self.eventString(message, block=True)

    def inputMessageAsync(self, message: str) -> None:
        """
        Send a new event as a string, async

        Similar to :py:meth:`eventString` called with ``block=False``,
        here for compatibility with csound6

        Args:
            s: a score line to send

        .. seealso:: :py:meth:`inputMessage`
        """
        return self.eventString(message, block=False)

    def eventString(self, message: str, block=True):
        """Send a new event as a string.

        Args:
            message: the message to send. Multiple events separated by newlines
                are possible. Score preprocessing (carry, etc.) is applied
            block: if true, the operation is run blocking

        .. note::

            This method is new in csound 7, fusing :py:meth:`inputMessage`
            and :py:meth:`inputMessageAsync` into one method. It has been
            ported to csound 6 for forward compatibility.

        """
        libcsound.csoundEventString(self.cs, cstring(message),
            ct.c_int32(not block))

    def keyPress(self, c: int | str):
        """Sets the ASCII code of the most recent key pressed.

        This value is used by the sensekey opcode if a callback for
        returning keyboard events is not set (see
        registerKeyboardCallback()).
        """
        if isinstance(c, str):
            c = ord(c[0])
        libcsound.csoundKeyPress(self.cs, cchar(c))

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
            in csound 7. This method implements the functionality present
            in csound 6 using the `turnoff2` opcode directly
        """
        if isinstance(instr, str):
            self.compileOrc(f'''turnoff2_i "{instr}", {mode}, {int(allowRelease)}''')
        else:
            self.compileOrc(f'''turnoff2_i {instr}, {mode}, {int(allowRelease)}''')

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
            self._callbacks['keyboardEvent'] = func = KEYBOARDFUNC(function)
        else:
            self._callbacks['keyboardText'] = func = KEYBOARDFUNC(function)
        return libcsound.csoundRegisterKeyboardCallback(self.cs, func, ct.py_object(userdata), ct.c_uint(typemask))

    def removeKeyboardCallback(self, function):
        """Removes a callback previously set with register_keyboard_callback()."""
        libcsound.csoundRemoveKeyboardCallback(self.cs, KEYBOARDFUNC(function))

    def tableLength(self, table: int) -> int:
        """Returns the length of a function table.

        Args:
            table: table number

        Returns:
            the length of the table, -1 of the table does not exist

        The returned length does not include the guard point
        """
        return libcsound.csoundTableLength(self.cs, ct.c_int32(table))

    def table(self, table: int) -> np.ndarray | None:
        """Returns a pointer to function table as an ndarray.

        Args:
            table: table number

        Returns:
            a numpy array sharing the memory of the table, None if the table does not exist

        Any modification to the returned array will modify the table itself. I
        """
        ptr = ct.POINTER(MYFLT)()
        size = libcsound.csoundGetTable(self.cs, ct.byref(ptr), table)
        return _util.castarray(ptr, shape=(size,)) if size >= 0 else None

    def tableArgs(self, table: int) -> np.ndarray | None:
        """Returns a pointer to the args used to generate a function table.

        The pointer is returned as an ndarray. If the table does not exist,
        None is returned.

        .. note::

            the argument list starts with the GEN number and is followed by
            its parameters. eg. ``f 1 0 1024 10 1 0.5``  yields the list
            ``[10.0, 1.0, 0.5]``
        """
        ptr = ct.POINTER(MYFLT)()
        size = libcsound.csoundGetTableArgs(self.cs, ct.byref(ptr), table)
        if size < 0:
            return None
        return _util.castarray(ptr, shape=(size,)) if size >= 0 else None

    #
    # Score Handling
    #
    def scoreTime(self) -> float:
        """Returns the current score time.

        Returns:
            current time, in seconds

        The return value is the time in seconds since the beginning of
        performance. This can be used to schedule events at absolute times

        .. seealso:: :meth:`Csound.currentTimeSamples`
        """
        return libcsound.csoundGetScoreTime(self.cs)

    def isScorePending(self) -> bool:
        """Tells whether Csound score events are performed or not.

        Independently of real-time MIDI events (see :py:meth:`setScorePending`).
        """
        return bool(libcsound.csoundIsScorePending(self.cs))

    def setScorePending(self, pending: bool) -> None:
        """Sets whether Csound score events are performed or not.

        Real-time events will continue to be performed. Can be used by external
        software, such as a VST host, to turn off performance of score events
        (while continuing to perform real-time events), for example to mute
        a Csound score while working on other tracks of a piece, or to play
        the Csound instruments live.
        """
        libcsound.csoundSetScorePending(self.cs, ct.c_int32(pending))

    def scoreOffsetSeconds(self) -> float:
        """
        Returns the score time beginning.

        At this time score events will actually immediately be performed
        (see :meth:`Csound.setScoreOffsetSeconds`).
        """
        return libcsound.csoundGetScoreOffsetSeconds(self.cs)

    def setScoreOffsetSeconds(self, time: float) -> None:
        """Csound score events prior to the specified time are not performed.

        Args:
            time: the new time offset, in seconds

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

    def sleep(self, milliseconds: int) -> None:
        """Waits for at least the specified number of milliseconds.

        Args:
            milliseconds: the number of milliseconds to sleep

        It yields the CPU to other threads.
        """
        libcsound.csoundSleep(ct.c_uint(milliseconds))

    #
    # Opcodes
    #
    def loadPlugins(self, directory: str) -> int:
        """
        Loads all plugins from a given directory.

        Args:
            directory: the path to the plugins directory

        Generally called immediatly after csoundCreate() to make new
        opcodes/modules available for compilation and performance.
        """
        return libcsound.csoundLoadPlugins(self.cs, cstring(directory))

    def appendOpcode(self, opname: str, dsblksiz: int, flags: int,
                     outypes: str, intypes: str, initfunc: _t.Callable,
                     perffunc: _t.Callable, deinitfunc: _t.Callable = None):
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
        deinit = deinitfunc if deinitfunc else OPCODEFUNC()
        return libcsound.csoundAppendOpcode(self.cs, cstring(opname), dsblksiz,
            flags, cstring(outypes), cstring(intypes),
            OPCODEFUNC(initfunc), OPCODEFUNC(perffunc), deinit)

    #
    # Table Display
    #
    def setIsGraphable(self, isGraphable: bool ) -> bool:
        """Tells Csound whether external graphic table display is supported.

        Return the previously set value (initially False).
        """
        ret = libcsound.csoundSetIsGraphable(self.cs, ct.c_int32(isGraphable))
        return (ret != 0)

    def setMakeGraphCallback(self, function) -> None:
        """Called by external software to set Csound's MakeGraph function."""
        self._callbacks['makeGraph'] = f = MAKEGRAPHFUNC(function)
        libcsound.csoundSetMakeGraphCallback(self.cs, f)

    def setDrawGraphCallback(self, function) -> None:
        """Called by external software to set Csound's DrawGraph function."""
        self._callbacks['drawGraph'] = f = DRAWGRAPHFUNC(function)
        libcsound.csoundSetDrawGraphCallback(self.cs, f)

    def setKillGraphCallback(self, function) -> None:
        """Called by external software to set Csound's KillGraph function."""
        self._callbacks['killGraph'] = func = KILLGRAPHFUNC(function)
        libcsound.csoundSetKillGraphCallback(self.cs, func)

    def setExitGraphCallback(self, function) -> None:
        """Called by external software to set Csound's ExitGraph function."""
        self._callbacks['exitGraph'] = f = EXITGRAPHFUNC(function)
        libcsound.csoundSetExitGraphCallback(self.cs, f)

    #
    # Circular Buffer Functions
    #
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

    def readCircularBuffer(self, buffer: ct.c_void_p, out: np.ndarray, numitems: int) -> int:
        """Reads from circular buffer.

        Args:
            buffer: pointer to an existing circular buffer
            out: preallocated ndarray with at least items number of elements,
                where buffer contents will be read into
            items: number of samples to be read

        Returns:
            the actual number of items read (0 <= n <= items).
        """
        if len(out) < numitems:
            return 0
        ptr = out.ctypes.data_as(ct.c_void_p)
        return libcsound.csoundReadCircularBuffer(self.cs, buffer, ptr, numitems)

    def peekCircularBuffer(self, buffer: ct.c_void_p, out: np.ndarray, numitems: int) -> int:
        """Reads from circular buffer without removing them from the buffer.

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
        return libcsound.csoundPeekCircularBuffer(self.cs, buffer, ptr, numitems)

    def writeCircularBuffer(self, buffer: ct.c_void_p, data: np.ndarray, numitems: int) -> int:
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

    def setOpenSoundFileCallback(self, function) -> None:
        """Sets a callback for opening a sound file.

        The callback is made when a sound file is going to be opened.
        The following information is passed to the callback:

        string
            pathname of the file; either full or relative to current dir
        int
            access flags for the file.
        ptr
            sound file info of the file.

        Pass None to disable the callback.
        This callback is retained after a reset() call.
        """
        self._callbacks['openSoundFile'] = f = OPENSOUNDFILEFUNC(function)
        libcsound.csoundSetOpenSoundFileCallback(self.cs, f)

    def setOpenFileCallback(self, function) -> None:
        """Sets a callback for opening a file.

        The callback is made when a file is going to be opened.
        The following information is passed to the callback:

        string
            pathname of the file; either full or relative to current dir
        string
            access mode of the file.

        Pass None to disable the callback.
        This callback is retained after a reset() call.
        """
        self._callbacks['openFile'] = f = OPENFILEFUNC(function)
        libcsound.csoundSetOpenFileCallback(self.cs, f)

    def getOpcodes(self) -> list[OpcodeDef]:
        return _getOpcodes()

    def setOutput(self, name: str, filetype='', format='') -> None:
        """
        Sets output destination, filetype and format.

        Args:
            name: the name of the output device/filename
            type_: in the case of a filename, the type can determine the file
                type used. One of "wav", "aiff", "au", "raw", "paf", "svx", "nist",
                "voc", "ircam", "w64", "mat4", "mat5", "pvf", "xi", "htk", "sds",
                "avr", "wavex", "sd2", "flac", "caf", "wve", "ogg", "mpc2k", "rf64"
            format: only used for offline output to a filename, one of "alaw",
                "schar", "uchar", "float", "double", "long", "short", "ulaw",
                "24bit", "vorbis"

        For RT audio, use device_id from CS_AUDIODEVICE for a given audio
        device.

        .. note::
            This is placed here for compatibility with csound6. In csound7 this
            functionality is not exposed through the API and must be set via
            command-line options (see :meth:`~Csound.setOption`)
        """
        self.setOption(f'-o "{name}"')
        if filetype:
            self.setOption(f'--format={filetype}')
        if format:
            self.setOption(f'--format={format}')

    def setInput(self, name: str) -> None:
        """Sets input source.

        Args:
            name: name of the input device. Depends on the rt module used

        .. note::
            The underlying API function (``csoundSetInput``) has been removed
            from csound 7. This method implements the same functionality present
            in the csound 6 API by means of command line options (``-i``). It
            is present here for compatibility with csound 6.
            (see :meth:`~libcsound.api6.Csound.setInput`, :py:meth:`setOption()`)
        """
        self.setOption(f'-i "{name}"')

    def setMidiInput(self, name: str) -> None:
        """
        Sets MIDI input device name/number.

        Args:
            name: name of the input midi device

        .. note::
            The underlying API function (``csoundSetMidiInput``) has been removed
            from csound 7. This method implements the same functionality present
            in the csound 6 API by means of command line options (``--midi-device=...``).
            It is present here for compatibility with csound 6.
        """
        name = name if " " not in name else f'"{name}"'
        self.setOption(f'--midi-device={name}')

    def UDPServerStart(self, port: int) -> int:
        """Starts the UDP server on a supplied port number.

        Args:
            port: port number

        Returns:
            ``CSOUND_SUCCESS`` if ok, ``CSOUND_ERROR`` otherwise.

        .. note::
            Not present in csound 7. This is placed here for compatibility
            with csound 6.

        In csound 7 this functionality is not exposed through the API and must
        be set via command-line options (``--port=...``). This means that the
        UDP server can only be started before any compilation has taken place,
        since options can not be set after the csound process has been started

        .. seealso:: :py:meth:`setOption`
        """
        self.setOption(f'--port={port}')
        return CSOUND_SUCCESS


class PerformanceThread:
    """
    Runs Csound in a separate thread.

    Args:
        csound: the Csound instance managed by this thread

    .. seealso:: :meth:`Csound.performanceThread`

    The playback is paused at start time. It can be stopped
    by calling :meth:`stop`.

    .. note:: The recommended way to create a performance thread is to call the
        :meth:`~Csound.performanceThread` method

    .. code-block:: python

        from libcsound import *
        cs = Csound(...)
        ...
        perfthread = PerformanceThread(cs)
        ...

    Or simply::

        perfthread = cs.performanceThread()

    To stop the performance thread, call :meth:`stop` and then :meth:`join`::

        # When finished:
        perfthread.stop()
        perfthread.join()

    """
    def __init__(self, csound: Csound):
        if csound._perfthread is not None:
            raise RuntimeError(f"A Csound instance can only have one attached performance "
                               f"thread, but {csound} already has one: {csound._perfthread}")
        self.csound = csound
        self.cpt = libcspt.csoundCreatePerformanceThread(csound.csound())
        self._processCallback: tuple[ct._FuncPointer, _t.Any] | None = None
        self._processQueue: _queue.SimpleQueue | None = None
        self._status = 'paused'
        # Used to hold a reference to functions passed to requestCallback.
        # We only need to hold the reference until the next cycle, so the maxlen
        # is a maximum of callbacks which can be processed per cycle
        self._futureCallbacks = _deque(maxlen=1000)

    def __del__(self):
        libcspt.csoundDestroyPerformanceThread(self.cpt)

    def isRunning(self) -> bool:
        """True if the performance thread is running, False otherwise."""
        return libcspt.csoundPerformanceThreadIsRunning(self.cpt) != 0

    def processCallback(self) -> ct._FuncPointer | None:
        """Returns the process callback."""
        out = libcspt.csoundPerformanceThreadGetProcessCB(self.cpt)
        if out:
            return PROCESSFUNC(out)
        return None

    def setProcessCallback(self, function: _t.Callable[[ct.c_void_p], None], data=None) -> None:
        """Sets the process callback.

        Args:
            function: a function of the form ``(data: void) -> None``
            data: can be anything

        The callback is called with a pointer to the data passed as ``data``
        """
        if self._processQueue is not None:
            raise RuntimeError(f"Process callback already set to manage the process queue")
        self._setProcessCallback(function=function, data=data)

    def _setProcessCallback(self, function: _t.Callable[[ct.c_void_p], None], data=None):
        procfunc = PROCESSFUNC(function)
        if data is None:
            data = ct.c_void_p()
        self._processCallback = (procfunc, data)
        libcspt.csoundPerformanceThreadSetProcessCB(self.cpt, procfunc, ct.byref(data))

    def setProcessQueue(self):
        """
        Setup a queue to pprocess tasks within the performance loop

        This is useful if access to the csound API is needed during a performance
        (code compilation, table access, etc), since when a performance thread is
        active any access to the API can result in high latency.

        .. note:: this sets up the process callback.

        """
        if self._processQueue is not None:
            return
        elif self._processCallback is not None:
            raise RuntimeError(f"Process callback already set: {self._processCallback}")
        self._processQueue = _queue.SimpleQueue()
        self._setProcessCallback(self._processQueueCallback)

    def _processQueueCallback(self, data) -> None:
        assert self._processQueue is not None
        N = self._processQueue.qsize()
        if N > 0:
            for _ in range(min(10, N)):
                job = self._processQueue.get_nowait()
                job(self.csound)

    def requestCallback(self, callback: _t.Callable[[Csound], None]) -> None:
        """
        Calls the given callback within the performance loop

        Args:
            callback: function of the form ``(Csound) -> None``. Can
                access the :class:`Csound` instance through the :py:attr:`csound`
                attribute

        The main advantage of using this method instead of accessing the API
        directly via the :class:`Csound` object is that, when csound is run
        with a performance thread, any direct access to the API can result in
        extra long latency.

        .. note::

            This method was introduced in csound >= 7.0. In csound 6 a similar
            effect can be achieved by setting a process queue (see :py:meth:`setProcessQueue`)
            and calling :py:meth:`processQueueTask`

        To pass extra arguments to the callback you can use early binding (see
        the example)

        .. rubric:: Example

        .. code-block:: python

            from libcsound import *
            import queue

            csound = Csound(...)
            thread = csound.performanceThread()

            # Create an empty table of 100 elements, let csound assign a number
            thread.compileOrc('gi__tab1 ftgen 0, 0, -100, -2, 0')

            # Get a pointer to it, as an alternative to csound.table(...)
            q = queue.SimpleQueue()
            def func(csound, q=q):
                tabnum = int(csound.evalCode('return gi__tab1'))
                q.put((tabnum, pt.csound.table(tabnum)))
            thread.requestCallback(func)
            # This blocks until the callback has been called
            tabnum, tabarr = q.get()

        .. seealso:: :py:meth:`evalCode`

        """
        def _func(pt, cb=callback, cs=self.csound):
            cb(cs)
        func = REQUESTCALLBACKFUNC(_func)
        libcspt.csoundPerformanceThreadRequestCallback(self.cpt, func)
        self._futureCallbacks.append(func)

    def evalCode(self, code: str, callback: _t.Callable[[float], None] | None = None, timeout=5.) -> float:
        """
        Similar to :meth:`Csound.evalCode`, run within the context of the performance thread

        Args:
            code: the code to evaluate. It must end with a ``return`` statement,
                returning one scalar value
            callback: if given, the function is called with the generated value and
                this method runs non-blocking. Otherwise this method blocks until the
                code is evaluated and the resulting value is returned
            timeout: if the callback does not return after this amount of time (in seconds)
                a TimeoutError exeption is raised

        Returns:
            the evaluated value if callback was not given, 0. otherwise

        .. note::

            This method was introduced in csound >= 7.0.

        .. rubric:: Example

        Allocate an empty table, return the table number. This will block for at least the
        duration of one performance cycle. The same code evaluated directly by
        :meth:`Csound.evalCode` might result in a much higher latency when csound
        is run using a performance thread

        .. code-block:: python

            csound = Csound()
            csound.compileOrc(...)
            thread = csound.performanceThread()
            tabnum = thread.evalCode(r'''
            gi__tabnum ftgen 0, 0, 1024, -2, 0
            return gi__tabnum
            ''')

        .. seealso:: :py:meth:`compileOrc`, :py:meth:`requestCallback`
        """
        if callback:
            _func = EVALCODEFUNC(callback)
            self._futureCallbacks.append(_func)
            libcspt.csoundPerformanceThreadEvalCode(self.cpt, cstring(code), _func)
            return 0.
        else:
            q = _queue.SimpleQueue()
            def _func(outvalue, q=q):
                q.put(outvalue)
            callback = EVALCODEFUNC(_func)
            libcspt.csoundPerformanceThreadEvalCode(self.cpt, cstring(code), callback)
            return q.get(timeout=timeout)

    def processQueueTask(self, func: _t.Callable[[Csound], None]) -> None:
        """
        Add a task to the process queue, to be picked up by the process callback

        Args:
            func: a function of the form ``(csound: Csound) -> None``,
                which can access the csound API

        .. note::
            This method is only available if the process queue was set
            (via :py:meth:`setProcessQueue`). In csound 7 it is advisable
            to use :py:meth:`requestCallback` instead of setting a process
            queue.

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

        .. seealso:: :py:meth:`evalCode()`

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
        """
        Returns the Csound instance pointer.
        """
        return libcspt.csoundPerformanceThreadGetCsound(self.cpt)

    def status(self) -> int:
        """Returns the current status.

        Zero if still playing, positive if the end of score was reached or
        performance was stopped, and negative if an error occured.
        """
        return libcspt.csoundPerformanceThreadGetStatus(self.cpt)

    def play(self):
        """Continues performance if it was paused."""
        if not self.csound._started:
            self.csound.start()
        libcspt.csoundPerformanceThreadPlay(self.cpt)
        self._status = 'playing'

    def pause(self) -> None:
        """Pauses performance (can be continued by calling play())."""
        libcspt.csoundPerformanceThreadPause(self.cpt)
        self._status = 'paused'

    def togglePause(self) -> None:
        """Pauses or continues performance, depending on current state."""
        if self._status == 'stopped':
            raise RuntimeError("This thread is stopped")
        libcspt.csoundPerformanceThreadtogglePause(self.cpt)
        self._status = 'playing' if self._status == 'paused' else 'paused'

    def stop(self) -> None:
        """Stops performance (cannot be continued)."""
        libcspt.csoundPerformanceThreadStop(self.cpt)
        self._status = 'stopped'

    def record(self, filename: str, samplebits: int, numbufs: int):
        """Starts recording the output from Csound.

        Args:
            filename: the output soundfile
            samplebits: number of bits per sample (16, 24, 32)
            numbufs: number of buffers

        The sample rate and number of channels are taken directly from the
        running Csound instance.
        """
        libcspt.csoundPerformanceThreadRecord(self.cpt, cstring(filename), samplebits, numbufs)

    def stopRecord(self):
        """Stops recording and closes audio file."""
        libcspt.csoundPerformanceThreadStopRecord(self.cpt)

    def scoreEvent(self, abstime: bool, kind: str, pfields: _t.Sequence[float] | np.ndarray):
        """Sends a score event.

        The event has type *kind* (e.g. 'i' for a note event).

        Args:
            abstime: if True, the start time of the event is measured
                from the beginning of performance, instead of the default of
                relative to the current time
            kind: the event kind, one of 'i', 'f', 'e', ...
            pfields: a tuple, a list, or an ndarray of MYFLTs with all the pfields
        """
        p = np.array(pfields).astype(MYFLT)
        ptr = p.ctypes.data_as(ct.POINTER(MYFLT))
        numFields = p.size
        libcspt.csoundPerformanceThreadScoreEvent(self.cpt, ct.c_int32(int(abstime)), cchar(kind), numFields, ptr)

    def inputMessage(self, s: str):
        """Sends a score event as a string, similarly to line events.

        Args:
            s: the input message (a line within a score)
        """
        libcspt.csoundPerformanceThreadInputMessage(self.cpt, cstring(s))

    def compileOrc(self, code: str) -> None:
        """
        Compile the given orchestra code

        Args:
            code: the code to compile

        This method queues a compilation event within the context of this
        thread. The main difference with just calling :meth:`~Csound.compileOrc` on the
        :class:`Csound` object is that this compilation takes place within the
        performance loop, reducing latency
        """
        libcspt.csoundPerformanceThreadCompileOrc(self.cpt, cstring(code))

    def setScoreOffsetSeconds(self, time: float) -> None:
        """Sets the playback time pointer to the specified value (in seconds).

        Args:
            time: playback time in seconds
        """
        libcspt.csoundPerformanceThreadSetScoreOffsetSeconds(self.cpt, ct.c_double(time))

    def join(self) -> int:
        """Waits until the performance is finished or fails.

        Returns:
            positive if the end of score was reached or :py:meth:`stop()`
            was called, negative if an error occured.

        Releases any resources associated with the performance thread
        object.
        """
        return libcspt.csoundPerformanceThreadJoin(self.cpt)

    def flushMessageQueue(self):
        """Waits until all pending messages are actually received.

        (pause, send score event, etc.)
        """
        libcspt.csoundPerformanceThreadFlushMessageQueue(self.cpt)

    def setEndMarker(self, time: float, absolute=False) -> None:
        """
        Add an end event to the score

        This stops the performance at the given time

        Args:
            time: time to add the end event
            absolute: if True, use absolute time
        """
        self.scoreEvent(absolute, "e", [0, time])


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
    for msg, attr in csound.iterMessages():
        if msg.startswith("system sr:"):
            sr = float(msg.split(":")[1].strip())
            break
    csound.destroyMessageBuffer()
    return sr, module


def _getOpcodes() -> list[OpcodeDef]:
    cs = Csound()
    cs.createMessageBuffer(echo=False)
    cs.setOption('-z1')
    msgcnt = cs.messageCnt()
    opcodes = []
    parts = []
    _ = _util.asciistr
    for i in range(cs.messageCnt()):
        msg = cs.firstMessage()
        cs.popFirstMessage()
        msgstripped = msg.strip()
        if msgstripped:
            parts.append(msgstripped)
        if msg.endswith('\n'):
            if not parts:
                break
            name = parts[0]
            if len(parts) == 3:
                outsig = parts[1].strip()
                insig = parts[2].strip()
            else:
                continue
            if outsig == '(null)':
                outsig = ''
            if insig == '(null)':
                insig = ''
            opcodes.append(OpcodeDef(name=_(name), outtypes=_(outsig), intypes=_(insig), flags=0))
            parts.clear()
    return opcodes
