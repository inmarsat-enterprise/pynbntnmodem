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

from pynbntnmodem.constants import ActMultiplier, TauMultiplier


@dataclass
class PsmConfig:
    """Power Saving Mode configuration attributes."""
    enabled: bool = False
    tau_t3412_bitmask: str = ''   # TAU timer - when the modem updates its location
    act_t3324_bitmask: str = ''   # Activity timer - how long the modem stays awake after TAU
    
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
        multipliers = [2, 30, 60, 3600, 10*3600]
        bct = None
        tvu = None
        for i, m in enumerate(multipliers):
            if seconds <= 31 * m:
                bct = int(seconds / m)
                tvu = TauMultiplier(i).value << 5
                break
        if tvu is None:
            bct = int(seconds / (320 * 3600))
            tvu = TauMultiplier.H_320.value << 5
        return f'{(tvu & bct):08b}'
    
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
        multipliers = [2, 60]
        bct = None
        tvu = None
        for i, m in enumerate(multipliers):
            if seconds <= (31 * m):
                bct = int(seconds / m)
                tvu = ActMultiplier(i).value << 5
                break
        if tvu is None:
            bct = int(seconds / (6 * 60))
            tvu = ActMultiplier.M_6 << 5
        return f'{(tvu & bct):08b}'
    
    @property
    def tau_s(self) -> int:
        """The requested TAU interval in seconds."""
        return PsmConfig.tau_seconds(self.tau_t3412_bitmask)
    
    @property
    def act_s(self) -> int:
        """The requested Activity duration in seconds."""
        return PsmConfig.act_seconds(self.act_t3324_bitmask)
