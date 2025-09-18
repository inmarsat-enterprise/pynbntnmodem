"""Basic NB-NTN modem example sending periodic messages via NIDD.
"""
import logging
import os
import time
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from typing import Optional

from pynbntnmodem import (
    CeregMode,
    MoMessage,
    MtMessage,
    NbntnModem,
    UrcType,
    mutate_modem,
)

TEST_APN = 'viasat.poc'
SIGNAL_LOG_INTERVAL = 60    # seconds
TRANSMIT_INTERVAL = 3600    # seconds

LOG_DIR = './logs'
loglvl = logging.DEBUG
logfmt = ('%(asctime)s,[%(levelname)s],%(message)s')
formatter = logging.Formatter(logfmt)
formatter.converter = time.gmtime
console = logging.StreamHandler()
console.setFormatter(formatter)
console.setLevel(loglvl)
logging.basicConfig(
    level=loglvl,
    format=logfmt,
    datefmt='%Y-%m-%dT%H:%M:%SZ',
    handlers=[console],
)
logger = logging.getLogger()
logging.getLogger('pyatcommand').setLevel(logging.WARNING)


def build_mo_message(modem: Optional[NbntnModem] = None) -> bytes:
    """Generate a Mobile-Originated / Uplink message with optional modem info."""
    return b'TEST'


def handle_mt_message(data: bytes):
    """Handle a received Mobile-Terminated / Downlink message."""
    logger.info('Received %d-bytes downlink: %r', len(data), data)


def main():
    modem = NbntnModem(apn=TEST_APN)
    identified = False
    modem.connect()
    
    try:
        modem = mutate_modem(modem)
        identified = True
        model = modem.model
        imsi = modem.imsi
        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')
        os.makedirs(LOG_DIR, exist_ok=True)
        logfile = RotatingFileHandler(
            filename=os.path.join(LOG_DIR, f'{model}-{imsi}-{timestamp}.log'),
        )
        logfile.setFormatter(formatter)
        logfile.setLevel(logging.INFO)
        logger.addHandler(logfile)
    except ModuleNotFoundError:
        logger.warning('Unable to find model-specific subclass for %s %s',
                       modem.manufacturer, modem.get_model().name)
    
    try:
        if not identified:
            raise IOError('Unable to determine model-specific commands')
        
        logger.info('>>> NIDD demo using %s %s',
                    modem.manufacturer, modem.model)
        if (not modem.get_reginfo().is_registered() or
            modem.apn != TEST_APN):
            logger.info('Initializing modem for NTN operation')
            modem.initialize_ntn()
        modem.set_regconfig(CeregMode.STATUS_LOC_EMM_PSM)
        modem.enable_nidd_urc()
        
        last_signal_log = 0
        last_transmit_attempt = 0
        transmissions = 0
        while True:
            
            # 1) Check Unsolicited Result Codes
            urc = modem.get_urc()
            if urc:
                event = modem.get_urc_type(urc)
                
                if event == UrcType.REGISTRATION:
                    reg_info = modem.get_reginfo()
                    if reg_info.is_registered():
                        logger.info('Modem registered')
                        if transmissions == 0:
                            last_transmit_attempt = 0
                    else:
                        logger.warning('Modem not registered')
                
                elif event == UrcType.NIDD_MT_RCVD:
                    downlink = modem.receive_message_nidd(urc)
                    if isinstance(downlink, MtMessage):
                        handle_mt_message(downlink.payload)
            
            if time.monotonic() - last_signal_log > SIGNAL_LOG_INTERVAL:
                last_signal_log = time.monotonic()
                reg_info = modem.get_reginfo()
                sig_info = modem.get_siginfo()
                logger.info('%s %s', reg_info, sig_info)
            
            if time.monotonic() - last_transmit_attempt > TRANSMIT_INTERVAL:
                last_transmit_attempt = time.monotonic()
                reg_info = modem.get_reginfo()
                if reg_info.is_registered():
                    uplink = modem.send_message_nidd(build_mo_message(modem))
                    if isinstance(uplink, MoMessage):
                        logger.info('Sent %d-bytes uplink: %r',
                                    uplink.size, uplink.payload)
                        transmissions += 1
                    else:
                        logger.warning('Problem sending uplink')
                else:
                    logger.warning('Cannot send uplink - modem not registered'
                                   ' - try again in %d seconds',
                                   TRANSMIT_INTERVAL)
                
    except Exception as e:
        logger.exception(e)
        raise e
    finally:
        if modem and modem.is_connected():
            modem.disconnect()


if __name__ == '__main__':
    main()
