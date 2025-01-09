"""Data class helper for NB-NTN location.

Location is required for NTN operation to assist in coordination of time and/or
frequency synchronization. It is used during network registration and periodic
Tracking Area Update (TAU) procedures.

The location for NTN purposes need only be accurate to within about 100m with
Circular Error Probability (CEP) 95%.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from pynbntnmodem.constants import NtnOpMode, GnssFixType

@dataclass
class NtnLocation:
    """Attributes of a NTN location.
    
    Used for purposes of registration and/or Tracking Area Update.
    
    Attributes:
        lat_deg (float): The latitude in degrees.
        lon_deg (float): The longitude in degrees.
        alt_m (float): The altitude in meters.
        spd_mps (float): The speed in meters per second.
        cep_rms (int): The Circular Error Probability Root Mean Squared.
        opmode (NtnOpMode): The operating mode mobile/stationary.
        fix_type (GnssFixType): The GNSS fix type.
        fix_timestamp (int): The GNSS fix time in seconds since epoch 1970.
        fix_time_iso (str): The ISO 8601 conversion of fix_timestamp.
        hdop (float): Horizontal Dilution of Precision, if available.
        satellites (int): The number of GNSS satellites used for the GNSS fix.
    """
    lat_deg: Optional[float] = None
    lon_deg: Optional[float] = None
    alt_m: Optional[float] = None
    spd_mps: Optional[float] = None
    cep_rms: Optional[int] = None
    opmode: Optional[NtnOpMode] = None
    fix_type: Optional[GnssFixType] = None
    fix_timestamp: Optional[int] = None
    hdop: Optional[float] = None
    satellites: Optional[int] = None
    
    @property
    def fix_time_iso(self) -> str:
        if not self.fix_timestamp:
            return ''
        iso_time = datetime.fromtimestamp(self.fix_timestamp,
                                          tz=timezone.utc).isoformat()
        return f'{iso_time[:19]}Z'
