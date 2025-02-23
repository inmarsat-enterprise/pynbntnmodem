# NB-NTN Modem Interface

A generic model for interfacing to a NB-IoT modem compatible with 3GPP R17
Non-Terrestrial Network.

Provides an base class **`NbntnBaseModem`** that abstracts specific AT commands
to common methods used for communicating using NB-IoT over satellite.
The class is intended to be subclassed and extended for specific modem variants
from various manufacturers.

## Modem Subclassing

Since modem implementations differ across make/model, this library is intended
to be used to create `NbntnBaseModem` subclasses with specific AT commands and
responses. An example `DefaultModem` is included which covers the most basic
operations that should be supported by any 3GPP NTN compliant modem.

### Initialization Sequence

The `ntninit` submodule describes the format and an example template for the
AT command sequence required by a particular modem variant.

The `ntn_init` list of init objects may be customized and included at the top of 
a specific modem subclass.

### Importing a Modem Subclass

A common approach to importing a modem subclass is as follows:
```
import importlib
from pkgutil import iter_modules

from pynbntnmodem import NbntnBaseModem, DefaultModem


for mod in iter_modules(modems.__path__):
    submodule = importlib.import_module(f'{path_to_module_file}')
    for attr_name in dir(submodule):
        attr = getattr(submodule, attr_name)
        if (isinstance(attr, type) and
            issubclass(attr, NbntnBaseModem) and
            attr is not DefaultModem):
            
            modem = attr()
```

## Common Workflow

* **`connect()`** using either `.env` variables, default or programmatic values
for `SERIAL_PORT`/`port` and `SERIAL_BAUDRATE`/`baudrate`.

* **`initialize_ntn()`** to run the modem-specific configuration sequence

* Run a loop that continually runs `check_urc()`, queues and then processes
each `get_urc_type()`

## URC injection

Some modems do not emit any URC on important events such as the completion of
a MO message sending. In such cases the `inject_urc()` method is provided to
simulate a modem-generated URC.