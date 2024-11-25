"""Initialization sequences for supported modems.

Each supported modem is initialized by a sequence of AT commands represented
as a list of objects/dictionaries.

Each command/response is a dictionary represented by optional elements:

* `why` is for the reader/developer to understand the function being performed
* `hw` is an optional key indicating a need to assert or pulse a modem input line
* `duration` when combined with `hw` indicates a pulse duration otherwise hold
* `cmd` is the AT command to be sent. May include keywords for replacement
with configured values including "<pdn_type>", "<apn>"
* `res` is the expected AtErrorCode result from the command
* `timeout` is the response timeout (seconds)
* `response` is an optional string returned by the command before the result code
* `retry` allows { "count": <int>, "delay": <float> } between timeouts where
count=0 means retry indefinitely
* `urc` is an optional Unsoliticted Result Code that the main code should await
* `urctimeout` allows a timeout (seconds) waiting for the specified URC
* `delay` adds a delay (Python sleep) in the process

"""

from pyatcommand import AtErrorCode


generic = [
    {
        'cmd': 'AT+CFUN=0',
        'res': AtErrorCode.OK,
        'timeout': 5,
        'why': 'disable radio during configuration'
    },
    {
        'cmd': 'AT+CEREG=5',
        'res': AtErrorCode.OK,
        'timeout': 3,
        'why': 'enable verbose registration URC',
    },
    {
        'cmd': 'AT+CGDCONT=1,"<pdn_type>","<apn>"',
        'res': AtErrorCode.OK,
        'timeout': 5,
        'why': 'configure default PDP/PDN context (cid=1)'
    },
    {
        'cmd': 'AT+CFUN=1',
        'res': AtErrorCode.OK,
        'timeout': 5,
        'why': 'enable radio after configuration'
    },
]
