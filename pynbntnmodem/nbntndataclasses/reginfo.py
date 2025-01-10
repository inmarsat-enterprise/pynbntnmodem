"""Data class helper for Registration Information.

Registration information from the NB-NTN modem is obtained through the 3GPP
standard command `+CEREG` which can be queried or unsolicited.
"""

from dataclasses import dataclass
from typing import Optional

from pynbntnmodem.constants import RegistrationState, EmmRejectionCause
from .psmconfig import PsmConfig


@dataclass
class RegInfo:
    """Attributes of NTN registration state.
    
    Attributes:
        state (RegistrationState): The current registration state on the network.
        tac (str): The Tracking Area Code of the cell/beam in use.
        ci (str): The Cell ID of the cell/beam in use.
        cause_type (int): A rejection type defined in 3GPP
        reject_cause (int): A numeric rejection cause defined in 3GPP
        tau_t3412_bitmask (str): The T3412 timer value default or granted by the network.
        act_t3324_bitmask (str): The T3324 timer value granted by the network.
    """
    state: RegistrationState = RegistrationState.UNKNOWN
    tac: str = ''
    ci: str = ''
    cause_type: Optional[int] = None
    reject_cause: Optional[int] = None
    act_t3324_bitmask: str = ''
    tau_t3412_bitmask: str = ''
    
    def is_registered(self) -> bool:
        """Check if the modem is registered (HOME/ROAMING)."""
        return self.state in [RegistrationState.HOME, RegistrationState.ROAMING]
    
    def get_psm_granted(self) -> PsmConfig:
        """Get the network-granted Power Save Mode configuration."""
        return PsmConfig(self.tau_t3412_bitmask, self.act_t3324_bitmask)
    
    def is_emm_rejection(self) -> bool:
        return self.cause_type == 0
    
    def get_emm_rejection(self) -> 'EmmRejectionCause|None':
        if not self.is_emm_rejection():
            return None
        try:
            return EmmRejectionCause(self.reject_cause)
        except ValueError:
            return EmmRejectionCause(-1)
