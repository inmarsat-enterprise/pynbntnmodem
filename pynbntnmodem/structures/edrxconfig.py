"""Data class helper for Extended Discontinuous Reception.

eDRX handles Idle mode power consumption by creating short listening windows
when the modem can receive mobile-terminated data.

The device requests eDRX parameters during ATTACH and TAU procedures, and
the mobile network will respond with the requested value or a different value.
The device must use the network-granted value.
"""

from dataclasses import dataclass

from pynbntnmodem.constants import EdrxCycle, EdrxPtw


@dataclass
class EdrxConfig:
    """Extended Discontiguous Receive mode configuration attributes.
    
    Attributes:
        cycle_bitmask (str): The bitmask used to configure or report eDRX cycle
        ptw_bitmask (str): The bitmask used to configure or report paging time window
    """
    cycle_bitmask: str = ''
    ptw_bitmask: str = ''

    @staticmethod
    def edrx_cycle_seconds(bitmask: str) -> int:
        """Calculate approximate eDRX cycle time in seconds from the bitmask.
        
        The bitmask is 4 bits representing enumerated values between about
        20 seconds and 10485 seconds (just under 3 hours), defined in 3GPP.
        
        Args:
            bitmask (str): The eDRX cycle bimask (4 bits).
        
        Returns:
            Nearest integer seconds of the enumerated value.
        
        Raises:
            `ValueError` if the bitmask is invalid.
        """
        if not bitmask:
            return 0
        if len(bitmask) != 4 or not all(b in '01' for b in bitmask):
            raise ValueError('Invalid bitmask must be 8 binary values')
        try:
            tvu = int(bitmask, 2)
            if tvu > 15:
                raise ValueError('Invalid bitmask')
            return int(EdrxCycle(tvu).name.split('_')[1])
        except ValueError:
            return 0
    
    @staticmethod
    def seconds_to_edrx_cycle(seconds: 'int|float') -> str:
        """Convert nearest seconds to eDRX cycle bitmask.
        
        Args:
            seconds (int|float): The target number of seconds eDRX cycle.
        
        Returns:
            Bitmask of 4 bits with nearest eDRX cycle configuration.
        """
        MAX_EDRX_CYCLE = 10485
        if seconds > MAX_EDRX_CYCLE:
            seconds = MAX_EDRX_CYCLE
        edrx_values = [5, 10, 20, 40, 60, 80, 160, 325, 655, 1310, 2620, 5240]
        for i, v in enumerate(edrx_values):
            if seconds <= v:
                return f'{EdrxCycle(i).value:04b}'
        return f'{EdrxCycle.S_10485.value:04b}'
    
    @staticmethod
    def edrx_ptw_seconds(bitmask: str) -> int:
        """Calculate the eDRX paging time window from the bitmask.
        
        The bitmask is 4 bits representing enumerated values between about
        2.5 seconds and 41 seconds, defined in 3GPP.
        
        Args:
            bitmask (str): The eDRX ptw bimask (4 bits).
        
        Returns:
            Nearest integer seconds of the enumerated value.
        
        Raises:
            `ValueError` if the bitmask is invalid.
        """
        if not bitmask:
            return 0
        if len(bitmask) != 4 or not all(b in '01' for b in bitmask):
            raise ValueError('Invalid bitmask must be 8 binary values')
        try:
            tvu = int(bitmask, 2)
            if tvu > 15:
                raise ValueError('Invalid bitmask')
            return int(EdrxPtw(tvu).name.split('_')[1])
        except ValueError:
            return 0
    
    @staticmethod
    def seconds_to_edrx_ptw(seconds: 'int|float') -> str:
        """Convert seconds to Paging Time Window bitmask.
        
        Args:
            seconds (int|float): The target number of seconds eDRX PTW.
        
        Returns:
            Bitmask of 4 bits with nearest eDRX PTW configuration.
        """
        MAX_PTW = 40
        if seconds > MAX_PTW:
            seconds = MAX_PTW
        ptw_values = [2, 5, 7, 10, 12, 15, 17, 20, 23, 25, 28, 30, 33, 35, 38]
        for i, v in enumerate(ptw_values):
            if seconds <= v:
                return f'{EdrxPtw(i).value:04b}'
        return f'{EdrxPtw.S_40.value:04b}'
    
    @property
    def cycle_s(self) -> float:
        """The requested eDRX cycle time in seconds."""
        return EdrxConfig.edrx_cycle_seconds(self.cycle_bitmask)
    
    @property
    def ptw_s(self) -> float:
        """The requested eDRX Paging Time Window in seconds."""
        return EdrxConfig.edrx_ptw_seconds(self.ptw_bitmask)
