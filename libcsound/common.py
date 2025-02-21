from __future__ import annotations
import ctypes as ct
import sys
from dataclasses import dataclass
import logging
from typing import Sequence


logger = logging.getLogger("libcsound")


BUILDING_DOCS = 'sphinx' in sys.modules


MYFLT = ct.c_double

#
# Opaque pointers for Csound structs
#
CSOUND_p = ct.c_void_p
STRINGDAT_p = ct.c_void_p
ARRAYDAT_p = ct.c_void_p
PVSDAT_p = ct.c_void_p

string128 = ct.c_char * 128

CAPSIZE  = 60


DEFMSGFUNC = ct.CFUNCTYPE(None, ct.c_void_p, ct.c_int, ct.c_char_p, ct.c_void_p)


#
# Compilation or performance aborted, but not as a result of an error
# (e.g. --help, or running an utility with -U).
#
CSOUND_EXITJMP_SUCCESS = 256

#
# Flags for csoundInitialize().
#
CSOUNDINIT_NO_SIGNAL_HANDLER = 1
CSOUNDINIT_NO_ATEXIT = 2

#
# Types for keyboard callbacks set in csoundRegisterKeyboardCallback()
#
CSOUND_CALLBACK_KBD_EVENT = ct.c_uint32(1)
CSOUND_CALLBACK_KBD_TEXT = ct.c_uint32(2)


class CsoundAudioDevice(ct.Structure):
    _fields_ = [("device_name", string128),
                ("device_id", string128),
                ("rt_module", string128),
                ("max_nchnls", ct.c_int32),
                ("isOutput", ct.c_int32)]


class CsoundMidiDevice(ct.Structure):
    _fields_ = [("device_name", string128),
                ("interface_name", string128),
                ("device_id", string128),
                ("midi_module", string128),
                ("isOutput", ct.c_int32)]


class CsoundRtAudioParams(ct.Structure):
    _fields_ = [("devName", ct.c_char_p),   # device name (NULL/empty: default)
                ("devNum", ct.c_int32),       # device number (0-1023), 1024: default
                ("bufSamp_SW", ct.c_uint),  # buffer fragment size (-b) in sample frames
                ("bufSamp_HW", ct.c_int32),   # total buffer size (-B) in sample frames
                ("nChannels", ct.c_int32),    # number of channels
                ("sampleFormat", ct.c_int32), # sample format (AE_SHORT etc.)
                ("sampleRate", ct.c_float)] # sample rate in Hz


class OpcodeListEntry(ct.Structure):
    _fields_ = [("opname", ct.c_char_p),
                ("outypes", ct.c_char_p),
                ("intypes", ct.c_char_p),
                ("flags", ct.c_int)]


@dataclass
class OpcodeDef:
    name: str
    outtypes: str
    intypes: str
    flags: int


@dataclass
class AudioDevice:
    deviceName: str
    deviceId: str
    rtModule: str
    maxNchnls: int
    isOutput: bool


@dataclass
class MidiDevice:
    deviceName: str
    interfaceName: str
    deviceId: str
    midiModule: str
    isOutput: bool


@dataclass
class ChannelInfo:
    name: str
    kind: str
    mode: int
    hints: dict | None

    def isoutput(self) -> bool:
        return bool(self.mode & CSOUND_OUTPUT_CHANNEL)

    def isinput(self) -> bool:
        return bool(self.mode & CSOUND_INPUT_CHANNEL)


class CsoundRandMTState(ct.Structure):
    _fields_ = [("mti", ct.c_int),
                ("mt", ct.c_uint32*624)]


# PVSDATEXT is a variation on PVSDAT used in the pvs bus interface
class PvsdatExt(ct.Structure):
    _fields_ = [("N", ct.c_int32),
                ("sliding", ct.c_int),      # Flag to indicate sliding case
                ("NB", ct.c_int32),
                ("overlap", ct.c_int32),
                ("winsize", ct.c_int32),
                ("wintype", ct.c_int),
                ("format", ct.c_int32),
                ("framecount", ct.c_uint32),
                ("frame", ct.POINTER(ct.c_float))]


# This structure holds the parameter hints for control channels
class ControlChannelHints(ct.Structure):
    _fields_ = [("behav", ct.c_int),
                ("dflt", MYFLT),
                ("min", MYFLT),
                ("max", MYFLT),
                ("x", ct.c_int),
                ("y", ct.c_int),
                ("width", ct.c_int),
                ("height", ct.c_int),
                # This member must be set explicitly to None if not used
                ("attributes", ct.c_char_p)]


class ControlChannelInfo(ct.Structure):
    _fields_ = [("name", ct.c_char_p),
                ("type", ct.c_int),
                ("hints", ControlChannelHints)]


class Windat(ct.Structure):
    _fields_ = [("windid", ct.POINTER(ct.c_uint)),    # set by makeGraph()
                ("fdata", ct.POINTER(MYFLT)),      # data passed to drawGraph()
                ("npts", ct.c_int32),              # size of above array
                ("caption", ct.c_char * CAPSIZE),  # caption string for graph
                ("waitflg", ct.c_int16 ),          # set =1 to wait for ms after Draw
                ("polarity", ct.c_int16),          # controls positioning of X axis
                ("max", MYFLT),                 # workspace .. extrema this frame
                ("min", MYFLT),
                ("absmax", MYFLT),              # workspace .. largest of above
                ("oabsmax", MYFLT),             # Y axis scaling factor
                ("danflag", ct.c_int),             # set to 1 for extra Yaxis mid span
                ("absflag", ct.c_int)]             # set to 1 to skip abs check


class NamedGen(ct.Structure):
    pass


NamedGen._fields_ = [
    ("name", ct.c_char_p),
    ("genum", ct.c_int),
    ("next", ct.POINTER(NamedGen))]


class RtClock(ct.Structure):
    _fields_ = [("starttime_real", ct.c_int64),
                ("starttime_CPU", ct.c_int64)]


# Contansts
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

PVS_WINDOWS = {
    'hamming': PVS_WIN_HAMMING,
    'hann': PVS_WIN_HANN,
    'kaiser': PVS_WIN_KAISER,
    'custom': PVS_WIN_CUSTOM,
    'blackman': PVS_WIN_BLACKMAN,
    'blackman-exact': PVS_WIN_BLACKMAN_EXACT,
    'nuttallc3': PVS_WIN_NUTTALLC3,
    'bharris3': PVS_WIN_BHARRIS_3,
    'bharrismin': PVS_WIN_BHARRIS_MIN,
    'rect': PVS_WIN_RECT
}

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

# Symbols for Windat.polarity field
NOPOL = 0
NEGPOL = 1
POSPOL = 2
BIPOL = 3


# ERROR DEFINITIONS
CSOUND_SUCCESS = 0               # Completed successfully.
CSOUND_ERROR = -1                # Unspecified failure.
CSOUND_INITIALIZATION = -2       # Failed during initialization.
CSOUND_PERFORMANCE = -3          # Failed during performance.
CSOUND_MEMORY = -4               # Failed to allocate requested memory.
CSOUND_SIGNAL = -5               # Termination requested by SIGINT or SIGTERM.



def cchar(s):
    return ct.c_char(ord(s[0]))


def cstring(s: str) -> bytes:
    return bytes(s, 'utf-8')


def pstring(s: bytes) -> str:
    return str(s, 'utf-8')


def csoundArgList(lst: Sequence[str]):
    if len(lst) == 1 and type(lst[0]) is list:
        lst = lst[0]
    argc = len(lst)
    argv = (ct.POINTER(ct.c_char_p) * argc)()
    for i in range(argc):
        v = cstring(lst[i])
        argv[i] = ct.cast(ct.pointer(ct.create_string_buffer(v)), ct.POINTER(ct.c_char_p))
    return ct.c_int(argc), ct.cast(argv, ct.POINTER(ct.c_char_p))



# Language definitions
# # list of languages
CSLANGUAGE_DEFAULT = 0
CSLANGUAGE_AFRIKAANS = 1
CSLANGUAGE_ALBANIAN = 2
CSLANGUAGE_ARABIC = 3
CSLANGUAGE_ARMENIAN = 4
CSLANGUAGE_ASSAMESE = 5
CSLANGUAGE_AZERI = 6
CSLANGUAGE_BASQUE = 7
CSLANGUAGE_BELARUSIAN = 8
CSLANGUAGE_BENGALI = 9
CSLANGUAGE_BULGARIAN = 10
CSLANGUAGE_CATALAN = 11
CSLANGUAGE_CHINESE = 12
CSLANGUAGE_CROATIAN = 13
CSLANGUAGE_CZECH = 14
CSLANGUAGE_DANISH = 15
CSLANGUAGE_DUTCH = 16
CSLANGUAGE_ENGLISH_UK = 17
CSLANGUAGE_ENGLISH_US = 18
CSLANGUAGE_ESTONIAN = 19
CSLANGUAGE_FAEROESE = 20
CSLANGUAGE_FARSI = 21
CSLANGUAGE_FINNISH = 22
CSLANGUAGE_FRENCH = 23
CSLANGUAGE_GEORGIAN = 24
CSLANGUAGE_GERMAN = 25
CSLANGUAGE_GREEK = 26
CSLANGUAGE_GUJARATI = 27
CSLANGUAGE_HEBREW = 28
CSLANGUAGE_HINDI = 29
CSLANGUAGE_HUNGARIAN = 30
CSLANGUAGE_ICELANDIC = 31
CSLANGUAGE_INDONESIAN = 32
CSLANGUAGE_ITALIAN = 33
CSLANGUAGE_JAPANESE = 34
CSLANGUAGE_KANNADA = 35
CSLANGUAGE_KASHMIRI = 36
CSLANGUAGE_KAZAK = 37
CSLANGUAGE_KONKANI = 38
CSLANGUAGE_KOREAN = 39
CSLANGUAGE_LATVIAN = 40
CSLANGUAGE_LITHUANIAN = 41
CSLANGUAGE_MACEDONIAN = 42
CSLANGUAGE_MALAY = 43
CSLANGUAGE_MALAYALAM = 44
CSLANGUAGE_MANIPURI = 45
CSLANGUAGE_MARATHI = 46
CSLANGUAGE_NEPALI = 47
CSLANGUAGE_NORWEGIAN = 48
CSLANGUAGE_ORIYA = 49
CSLANGUAGE_POLISH = 50
CSLANGUAGE_PORTUGUESE = 51
CSLANGUAGE_PUNJABI = 52
CSLANGUAGE_ROMANIAN = 53
CSLANGUAGE_RUSSIAN = 54
CSLANGUAGE_SANSKRIT = 55
CSLANGUAGE_SERBIAN = 56
CSLANGUAGE_SINDHI = 57
CSLANGUAGE_SLOVAK = 58
CSLANGUAGE_SLOVENIAN = 59
CSLANGUAGE_SPANISH = 60
CSLANGUAGE_SWAHILI = 61
CSLANGUAGE_SWEDISH = 62
CSLANGUAGE_TAMIL = 63
CSLANGUAGE_TATAR = 64
CSLANGUAGE_TELUGU = 65
CSLANGUAGE_THAI = 66
CSLANGUAGE_TURKISH = 67
CSLANGUAGE_UKRAINIAN = 68
CSLANGUAGE_URDU = 69
CSLANGUAGE_UZBEK = 70
CSLANGUAGE_VIETNAMESE = 71
CSLANGUAGE_COLUMBIAN = 72
