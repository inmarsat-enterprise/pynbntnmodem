"""Initialization sequences for supported modems.

Each supported modem is initialized by a sequence of AT commands represented
as a list of objects/dictionaries.

"""

import json
from dataclasses import dataclass
from typing import Optional, Callable, Iterable, List

from pyatcommand import AtErrorCode
from pyatcommand.constants import AT_TIMEOUT, AT_URC_TIMEOUT


@dataclass
class NtnInitRetry:
    """Initialization retry structure.
    
    Attributes:
        count (int): The number of retries. 0 or less represents forever.
        delay (float): Optional delay in seconds between retries (default 1).
    """
    count: int = 0
    delay: Optional[float] = None
    
    def __post_init__(self):
        if not isinstance(self.count, int) or self.count < 0:
            raise ValueError('Count must be positive or zero')
        if self.delay is not None:
            if not isinstance(self.delay, float):
                self.delay = float(self.delay)
            if self.delay < 0:
                raise ValueError('Invalid delay must be 0 or higher, or None')


@dataclass
class NtnInitUrc:
    """Initialization URC instead of response.
    
    Attributes:
        urc (str): The URC output expected after the command.
        timeout (float): The maximum time in seconds to wait for the URC.
    """
    urc: str
    timeout: float = AT_URC_TIMEOUT
    
    def __post_init__(self):
        if not isinstance(self.urc, str) or not self.urc:
            raise ValueError('Invalid URC string')
        if not isinstance(self.timeout, float):
            self.timeout = float(self.timeout)
        if self.timeout <= 0:
            raise ValueError('URC timeout must be > 0')


@dataclass
class NtnHardwareAssert:
    """Initialization hardware trigger.
    
    Attributes:
        gpio_name (str): The name of the GPIO to assert.
        duration (float): The duration to assert the GPIO in seconds.
        callback (Callable): Optional callback to interface to physical IO.
            Accepts duration (float) and returns None.
    """
    gpio_name: str
    duration: float
    callback: Optional[Callable[[float], None]] = None
    
    def __post_init__(self):
        if not isinstance(self.gpio_name, str) or not self.gpio_name:
            raise ValueError('Invalid GPIO name')
        if not isinstance(self.duration, float):
            self.duration = float(self.duration)
        if self.duration <= 0:
            raise ValueError('Invalid duration must be > 0')
        if self.callback is not None and not callable(self.callback):
            raise ValueError('Invalid callback')


@dataclass
class NtnInitCommand:
    """An initialization command supporting parameters for modem interaction.
    
    Attributes:
        why (str): Reason why this operation is performed. Used for debug.
        cmd (str): The AT command to send. Special keys within the string
            are `<pdn_type>`, `<apn>` which will be substituted.
        res (AtErrorCode|None): The expected result code (default `OK`). May be
            specified as `None` which accepts any response.
        timeout (float|None): The maximum number of seconds to wait for result.
        gpio (NtnHardwareAssert|None): Optional instruction of a GPIO handle to 
            assert.
        delay (float|None): Optional delay seconds before sending `cmd`.
        retry (NtnInitRetry|None): Optional retry parameters.
        urc (NtnInitUrc|None): Optional triggered URC parameters.
    """
    why: str
    cmd: str = ''
    res: Optional[AtErrorCode] = AtErrorCode.OK
    timeout: Optional[float] = AT_TIMEOUT
    gpio: Optional[NtnHardwareAssert] = None
    delay: Optional[float] = None
    retry: Optional[NtnInitRetry] = None
    urc: Optional[NtnInitUrc] = None
    
    def __post_init__(self):
        if not isinstance(self.why, str):
            raise ValueError('Invalid reason why')
        if not isinstance(self.cmd, str):
            raise ValueError('Invalid cmd must be string (may be empty)')
        if self.res is not None and not isinstance(self.res, AtErrorCode):
            raise ValueError('Invalid result code')
        if self.timeout is not None:
            if not isinstance(self.timeout, float):
                self.timeout = float(self.timeout)
            if self.timeout < 0:
                raise ValueError('Invalid timeout must be >= 0')
        elif self.res:
            raise ValueError('Expected res must be None if timeout is None')
        if self.gpio is not None and not isinstance(self.gpio, NtnHardwareAssert):
            raise ValueError('Invalid GPIO NtnHardwareAssert')
        if self.delay is not None and not isinstance(self.delay, float):
            self.delay = float(self.delay)
        if self.retry is not None and not isinstance(self.retry, NtnInitRetry):
            raise ValueError('Invalid NtnInitRetry')
        if self.urc is not None and not isinstance(self.urc, NtnInitUrc):
            raise ValueError('Invalid NtnInitUrc')


class NtnInitSequence(List[NtnInitCommand]):
    def __init__(self, *args):
        for item in args:
            self._validate(item)
        super().__init__(args)
    
    def _validate(self, arg):
        if not isinstance(arg, NtnInitCommand):
            raise TypeError('Invalid NtnInitCommand')
        
    def append(self, item: NtnInitCommand):
        self._validate(item)
        super().append(item)
    
    def extend(self, iterable: Iterable):
        for item in iterable:
            self._validate(item)
        super().extend(iterable)
        
    def insert(self, index, item):
        self._validate(item)
        super().insert(index, item)
    
    def __repr__(self):
        return json.dumps([vars(item) for item in self])
    
    @classmethod
    def from_list_of_dict(cls, commands: 'list[dict]'):
        if (not isinstance(commands, list) or
            not all(isinstance(c, dict) for c in commands)):
            raise ValueError('Invalid list of commands')
        res = NtnInitSequence()
        for command in commands:
            if 'hw' in command:
                gpio = NtnHardwareAssert(gpio_name=command.get('hw'),
                                            duration=command.get('duration'))
            else:
                gpio = None
            if 'retry' in command:
                retry = NtnInitRetry(count=command['retry'].get('count'),
                                     delay=command['retry'].get('delay'))
            else:
                retry = None
            if 'urc' in command:
                urc = NtnInitUrc(urc=command.get('urc'),
                                    timeout=command.get('urctimeout'))
            else:
                urc = None
            res.append(NtnInitCommand(why=command.get('why'),
                                        cmd=command.get('cmd'),
                                        res=command.get('res'),
                                        timeout=command.get('timeout'),
                                        gpio=gpio,
                                        delay=command.get('delay'),
                                        retry=retry,
                                        urc=urc))
        return res
                


default_init = NtnInitSequence(
    NtnInitCommand(why='disable radio during configuration',
                   cmd='AT+CFUN=0',
                   res=AtErrorCode.OK,
                   timeout=15),
    NtnInitCommand(why='enable verbose registration URC',
                   cmd='AT+CEREG=5',
                   res=AtErrorCode.OK),
    NtnInitCommand(why='configure default PDP/PDN context (cid=1)',
                   cmd='AT+CGDCONT=1,"<pdn_type>","<apn>"',
                   res=AtErrorCode.OK),
    NtnInitCommand(why='enable radio after configuration',
                   cmd='AT+CFUN=1',
                   res=AtErrorCode.OK,
                   timeout=15),
)
