"""Data class helper for Signal Information for NB-NTN."""

from dataclasses import dataclass


@dataclass
class SigInfo:
    """Attributes of NB-NTN relevant signal level information.
    
    Attributes:
        rsrp (int): Reference Signal Received Power (dBm)
        rsrq (int): Reference Signal Received Quality (dB)
        sinr (int): Signal Interference + Noise Ratio (dB)
        rssi (int): Received Signal Strength Indicator (dB).
            Not typically useful for NB-NTN service.
        ber (float): Channel Bit Error Rate (%) provided by some modems.
    """
    rsrp: int = 255   # Reference Signal Received Power (dBm)
    rsrq: int = 255   # Reference Signal Received Quality (dB)
    sinr: int = 255   # Signal Interference + Noise Ratio (dB)
    rssi: int = 99   # Received signal strength indicator (dB)
    ber: float = 99.0   # Channel bit error rate %
