# NB-NTN Modem Interface

A generic model for interfacing to a NB-IoT modem compatible with 3GPP R17
Non-Terrestrial Network.

Provides a generic class **`NbntnModem`** that abstracts specific AT commands to
common functional operations used for communicating using NB-IoT over satellite.
The class is intended to be subclassed and extended for specific modem variants
from various manufacturers.

## Modem Subclassing

Since modem implementations differ across make/model, this library is intended
to be used to create `NbntnModem` subclasses with specific AT commands and
responses.

### Initialization Sequence

The `ntninit` submodule describes the format and an example template for the
AT command sequence required by a particular modem variant.

The `ntn_init` list of dictionaries may be customized and included at the top of 
a specific modem subclass.

### MODEM_SUBCLASS

To allow for automatic selection between different subclassed modems, use the
`MODEM_SUBCLASS` declaration at the bottom of your subclass template.

## Common Workflow

* **`connect()`** using either `.env` variables, default or programmatic values
for `SERIAL_PORT`/`port` and `SERIAL_BAUDRATE`/`baudrate`.
* **`initialize_ntn()`** to run the modem-specific configuration sequence
* Run a loop that continually runs `check_urc()`, queues and then processes
each `get_urc_type()`