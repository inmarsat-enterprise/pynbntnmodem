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
        latitude (float): The latitude in degrees.
        longitude (float): The longitude in degrees.
        altitude (float): The altitude in meters.
        speed_mps (float): The speed in meters per second.
        cog (float): Course Over Ground in degrees (from North).
        cep_rms (int): The Circular Error Probability Root Mean Squared.
        opmode (NtnOpMode): The operating mode mobile/stationary.
        fix_type (GnssFixType): The GNSS fix type.
        fix_timestamp (int): The GNSS fix time in seconds since epoch 1970.
        fix_time_iso (str): The ISO 8601 conversion of fix_timestamp.
        hdop (float): Horizontal Dilution of Precision, if available.
        satellites (int): The number of GNSS satellites used for the GNSS fix.
    """
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    altitude: Optional[float] = None
    speed_mps: Optional[float] = None
    cog: Optional[float] = None
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
