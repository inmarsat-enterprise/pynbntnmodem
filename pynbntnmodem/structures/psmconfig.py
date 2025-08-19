"""Data class helper for Power Saving Mode.

PSM provides a sleep mode for IoT devices, during which period the device
cannot receive any mobile-terminated data. The device connects to the network
periodically to send data, idles to receive data, then returns to PSM sleep.

The device may request PSM parameters during ATTACH and TAU procedures, by
negotiating two timers T3324 Active Timer and T3412 Extended TAU Timer.
The mobile network will respond with the requested value or a different value.
The device must use the network-granted value, and the resulting sleep period
is (T3412 - T3324).
"""

from dataclasses import dataclass
from typing import Any

from pynbntnmodem.constants import ActMultiplier, TauMultiplier


@dataclass
class PsmConfig:
    """Power Saving Mode configuration attributes."""
    mode: int = 0
    tau_t3412_bitmask: str = ''   # TAU timer - when the modem updates its location
    act_t3324_bitmask: str = ''   # Activity timer - how long the modem stays awake after TAU
    
    def __setattr__(self, name: str, value: Any) -> None:
        if name == 'mode':
            if value not in (0, 1, 2):
                raise ValueError('Mode must be integer 0..2')
        elif name in ('tau_t3412_bitmask', 'act_t3324_bitmask'):
            if (not isinstance(value, str) or len(value) > 8 or
                len(value) > 0 and not all(b in ('0', '1') for b in value)):
                raise ValueError(f'Invalid {name} must be bitmask byte or empty')
        else:
            raise ValueError('Invalid attribute')
        super().__setattr__(name, value)
    
    @staticmethod
    def tau_seconds(bitmask: str) -> int:
        """Convert a TAU bitmask to seconds."""
        if not bitmask:
            return 0
        tvu = (int(bitmask, 2) & 0b11100000) >> 5   # timer value unit
        bct = int(bitmask, 2) & 0b00011111   # binary coded timer value
        if TauMultiplier(tvu) == TauMultiplier.DEACTIVATED:
            return 0
        unit, multiplier = TauMultiplier(tvu).name.split('_')
        if unit == 'H':
            return bct * int(multiplier) * 3600
        if unit == 'M':
            return bct * int(multiplier) * 60
        return bct * int(multiplier)
    
    @staticmethod
    def seconds_to_tau(seconds: int) -> str:
        """Convert an integer value to a TAU bitmask."""
        if not isinstance(seconds, int) or seconds == 0:
            return f'{(TauMultiplier.DEACTIVATED << 5):08b}'
        MAX_TAU = 31 * 320 * 3600
        if seconds > MAX_TAU:
            seconds = MAX_TAU
        tvu_multipliers = {
            2: 'S_2',
            30: 'S_30',
            60: 'M_1',
            3600: 'H_1',
            10*3600: 'H_10',
        }
        bct = None   # binary coded timer value
        tvu = None   # timer value unit
        for k, v in tvu_multipliers.items():
            if seconds <= 31 * k:
                bct = int(seconds / k)
                tvu = TauMultiplier[v].value << 5
                break
        if tvu is None:
            bct = int(seconds / (320 * 3600))
            tvu = TauMultiplier.H_320.value << 5
        if bct is None or tvu is None:
            raise ValueError(f'Unable to calculate TAU bitmask for {seconds}')
        return f'{(tvu | bct):08b}'
    
    @staticmethod
    def act_seconds(bitmask: str) -> int:
        """Convert the bitmask to Active PSM seconds."""
        if not bitmask:
            return 0
        tvu = (int(bitmask, 2) & 0b11100000) >> 5   # timer value unit
        bct = int(bitmask, 2) & 0b00011111   # binary coded timer value
        if ActMultiplier(tvu) == ActMultiplier.DEACTIVATED:
            return 0
        unit, multiplier = ActMultiplier(tvu).name.split('_')
        if unit == 'H':
            return bct * int(multiplier) * 3600
        if unit == 'M':
            return bct * int(multiplier) * 60
        return bct * int(multiplier)
    
    @staticmethod
    def seconds_to_act(seconds: int) -> str:
        """Convert active time seconds to the ACT bitmask."""
        if not isinstance(seconds, int) or seconds == 0:
            return f'{(ActMultiplier.DEACTIVATED << 5):08b}'
        MAX_ACT = 31 * 6 * 60
        if seconds > MAX_ACT:
            seconds = MAX_ACT
        act_multipliers = {2: 'S_2', 60: 'M_1'}
        bct = None
        tvu = None
        for k, v in act_multipliers.items():
            if seconds <= (31 * k):
                bct = int(seconds / k)
                tvu = ActMultiplier[v].value << 5
                break
        if tvu is None:
            bct = int(seconds / (6 * 60))
            tvu = ActMultiplier.M_6 << 5
        if bct is None or tvu is None:
            raise ValueError(f'Unable to calculate ACT bitmask for {seconds}')
        return f'{(tvu | bct):08b}'
    
    @property
    def tau_s(self) -> int:
        """The requested TAU interval in seconds."""
        return PsmConfig.tau_seconds(self.tau_t3412_bitmask)
    
    @property
    def act_s(self) -> int:
        """The requested Activity duration in seconds."""
        return PsmConfig.act_seconds(self.act_t3324_bitmask)
