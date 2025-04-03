"""Enumerated types for abstraction of commonly used values."""

from enum import Enum, IntEnum


NBNTN_MAX_MSG_SIZE = 1200


class ChipsetManufacturer(IntEnum):
    """Supported chipset manufacturers."""
    UNKNOWN = 0
    MEDIATEK = 1
    SONYALTAIR = 2
    QUALCOMM = 3


class Chipset(IntEnum):
    """Supported chipsets."""
    UNKNOWN = 0
    MT6825 = 1   # Mediatek
    MDM9205S = 2   # Qualcomm
    ALT1250 = 3   # Sony/Altair
    QCX212S = 4   # Qualcomm


class ModuleManufacturer(IntEnum):
    """Supported module manufacturers."""
    UNKNOWN = 0
    QUECTEL = 1
    MURATA = 2
    SEMTECH = 3
    COMPAL = 4
    TELIT = 5
    UBLOX = 6
    NORDIC = 7


class ModuleModel(IntEnum):
    "Supported modules"
    UNKNOWN = 0
    CC660D = 1   # Quectel CC660D-LS
    TYPE1SC = 2   # Murata Type 1SC
    BG95S5 = 3   # Quectel BG95-S5
    HL781X = 4   # Semtech HL781x
    BG770ASN = 5   # Quectel BG770A-SN
    RMMT1 = 6   # Compal RMM-T1
    ME910G1 = 7   # Telit ME910G1
    SARAS528NM10 = 8   # uBlox SARA-S528NM10
    NRF9151 = 9   # Nordic Semiconductor nRF9151


class PdpType(IntEnum):
    """PDP type enumerations for +CGDCONT"""
    IP = 0
    IPV6 = 1
    IPV4V6 = 2
    NON_IP = 3


class RegistrationState(IntEnum):
    """State enumerations for +CEREG"""
    NONE = 0
    HOME = 1
    SEARCHING = 2
    DENIED = 3
    UNKNOWN = 4
    ROAMING = 5


class NtnOpMode(IntEnum):
    """Normalized enumeration for mobility class"""
    MOBILE = 0
    FIXED = 1


class GnssFixType(IntEnum):
    INVALID = 0
    GNSS = 1
    DGNSS = 2


class RrcState(IntEnum):
    IDLE = 0
    CONNECTED = 1
    UNKNOWN = 2


class RadioAccessTechnology(IntEnum):
    UNKNOWN = -1
    GPRS = 0
    CATM = 1
    NBIOT = 2
    BIS = 3
    NBNTN = 4


class TransportType(IntEnum):
    """Supported transport types for NB-NTN network."""
    NIDD = 0
    UDP = 1
    # SMS = 2


class UrcType(IntEnum):
    """Types of URC used to determine parameters passed to handling function."""
    UNKNOWN = -1
    SIB31 = 0   # System Information Broadcast 31 for satellite ephemeris
    GNSS_REQ = 1   # GNSS input required for RACH
    IGNSS_FIX = 2   # Integrated GNSS fix obtained (if supported)
    RACH = 3   # Random Access Channel attach attempt
    RRC_STATE = 4   # Radio Resource Control connect or disconnect
    REGISTRATION = 5   # Registration event (success or fail)
    NIDD_MO_SENT = 6
    NIDD_MO_FAIL = 7
    NIDD_MT_RCVD = 8
    UDP_SOCKET_OPENED = 9
    UDP_SOCKET_CLOSED = 10
    UDP_MO_SENT = 11   # UDP mobile-originated message transmitted
    UDP_MO_FAIL = 12   # UDP mobile-originated message failed (if supported)
    UDP_MT_RCVD = 13   # UDP mobile-originated message confirmed by RRC
    NTP_SYNC = 14
    PSM_ENTER = 15
    PSM_EXIT = 16
    DEEP_SLEEP_ENTER = 17
    DEEP_SLEEP_EXIT = 18
    MODEM_REBOOT = 19


class TauMultiplier(IntEnum):
    M_10 = 0
    H_1 = 1
    H_10 = 2
    S_2 = 3
    S_30 = 4
    M_1 = 5
    H_320 = 6
    DEACTIVATED = 7


class ActMultiplier(IntEnum):
    S_2 = 0
    M_1 = 1
    M_6 = 2
    DEACTIVATED = 7


class EdrxCycle(IntEnum):
    S_5 = 0   # 5.12 seconds
    S_10 = 1   # 10.24 seconds
    S_20 = 2   # 20.48 seconds
    S_40 = 3   # 40.96 seconds
    S_60 = 4   # 61.44 seconds
    S_80 = 5   # 81.92 seconds
    S_100 = 6   # 102.4 seconds
    S_120 = 7   # 122.88 seconds
    S_140 = 8   # 143.36 seconds
    S_160 = 9   # 163.84 seconds
    S_325 = 10   # 327.68 seconds
    S_655 = 11   # 655.36 seconds
    S_1310 = 12   # 1310.72 seconds
    S_2620 = 13   # 2621.44 seconds
    S_5240 = 14   # 5242.88 seconds
    S_10485 = 15   # 10485.76 seconds


class EdrxPtw(IntEnum):
    S_2 = 0   # 2.56 seconds
    S_5 = 1   # 5.12 seconds
    S_7 = 2   # 7.68 seconds
    S_10 = 3   # 10.24 seconds
    S_12 = 4   # 12.8 seconds
    S_15 = 5   # 15.36 seconds
    S_17 = 6   # 17.92 seconds
    S_20 = 7   # 20.48 seconds
    S_23 = 8   # 23.04 seconds
    S_25 = 9   # 25.6 seconds
    S_28 = 10   # 28.16 seconds
    S_30 = 11   # 30.72 seconds
    S_33 = 12   # 33.28 seconds
    S_35 = 13   # 35.84 seconds
    S_38 = 14   # 38.4 seconds
    S_40 = 15   # 40.96 seconds


class SignalLevel(Enum):
    """Qualitative index of SINR."""
    BARS_0 = -10
    BARS_1 = -7
    BARS_2 = -4
    BARS_3 = 0
    BARS_4 = 4
    BARS_5 = 7
    INVALID = 15


class SignalQuality(IntEnum):
    """Qualitative metric of signal quality."""
    NONE = 0
    WEAK = 1
    LOW = 2
    MID = 3
    GOOD = 4
    STRONG = 5
    WARNING = 6


class EmmRejectionCause(IntEnum):
    """EPS Mobility Management rejection causes by the network.
    
    Defined in TS 24.008 Annext G
    """
    UNKNOWN = -1   # not in spec
    IMSI_NOT_IN_VLR = 4
    # UE identification
    IMSI_NOT_IN_HSS = 2
    ILLEGAL_UE = 3
    ILLEGAL_ME = 6
    UE_IDENTITY_INDETERMINATE = 9
    IMPLICITLY_DETACHED = 10
    # subscription related
    IMEI_NOT_ACCEPTED = 5
    EPS_SERVICES_NOT_ALLOWED = 7
    EPS_NON_EPS_SERVICES_NOT_ALLOWED = 8
    PLMN_NOT_ALLOWED = 11
    AC_NOT_ALLOWED = 12
    ROAMING_NOT_ALLOWED_IN_TA = 13
    EPS_NOT_ALLOWED_THIS_PLMN = 14
    NO_SUITABLE_CELLS_IN_TA = 15
    NOT_AUTHORIZED_FOR_THIS_CSG = 25
    REDIRECT_TO_5GCN_REQUIRED = 31
    REQUESTED_SERVICE_NOT_AVAILABLE_THIS_PLMN = 35
    NO_EPS_BEARER_CONTEXT_ACTIVATED = 40
    # PLMN-specific and congestion/auth
    MSC_TEMP_UNREACHABLE = 16
    NETWORK_FAILURE = 17
    CS_DOMAIN_UNAVAILABLE = 18
    ESM_FAILURE = 19
    MAC_FAILURE = 20
    SYNC_FAILURE = 21
    CONGESTION = 22
    UE_SECURITY_CAPABILITY_MISMATCH = 23
    SECURITY_MODE_REJECTED = 24
    NON_EPS_AUTH_UNACCEPTABLE = 26
    CS_TEMP_UNAVAILABLE = 39
    SEVERE_NETWORK_FAILURE = 42
    # EPS session management
    OPERATOR_BARRING = 8
    INSUFFICIENT_RESOURCES = 26
    MISSING_OR_UNKNOWN_APN = 27
    UNKNOWN_PDN_TYPE = 28
    USER_AUTH_FAILED = 29
    REJECTED_BY_PDN_GW = 30
    SERVICE_OPTION_NOT_SUPPORTED = 32
    SERVICE_NOT_SUBSCRIBED = 33
    SERVICE_OUT_OF_ORDER = 34
    CALL_CANNOT_BE_IDENTIFIED = 38
