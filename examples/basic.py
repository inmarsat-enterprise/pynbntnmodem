"""Basic NB-NTN modem example sending periodic messages via NIDD.
"""
import logging
import time

from pynbntnmodem import (
    CeregMode,
    MoMessage,
    MtMessage,
    NbntnModem,
    UrcType,
    mutate_modem,
)

TRANSMIT_INTERVAL_S = 60

logger = logging.getLogger()
logging.Formatter.converter = time.gmtime
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)


def main():
    modem = NbntnModem(apn='viasat.poc')
    modem.connect()
    try:
        modem = mutate_modem(modem)
    except ModuleNotFoundError:
        logger.warning('Unable to find model-specific subclass for %s %s',
                       modem.manufacturer, modem.get_model().name)
    try:
        modem.initialize_ntn()
        modem.set_regconfig(CeregMode.STATUS_LOC_PSM)
        modem.enable_nidd_urc()
        last_transmit_attempt_time = 0
        while True:
            urc = modem.get_urc()
            if urc:
                event = modem.get_urc_type(urc)
                if event == UrcType.REGISTRATION:
                    reg_info = modem.get_reginfo()
                    if reg_info.is_registered():
                        logger.info('Modem registered')
                    else:
                        logger.warning('Modem not registered')
                elif event == UrcType.NIDD_MT_RCVD:
                    downlink = modem.receive_message_nidd(urc)
                    if isinstance(downlink, MtMessage):
                        logger.info('Received %d-bytes downlink: %r',
                                    downlink.size, downlink.payload)
            if time.time() - last_transmit_attempt_time > TRANSMIT_INTERVAL_S:
                reg_info = modem.get_reginfo()
                if reg_info.is_registered():
                    uplink = modem.send_message_nidd(b'TEST')
                    if isinstance(uplink, MoMessage):
                        logger.info('Sent %d-bytes uplink: %r',
                                    uplink.size, uplink.payload)
                    else:
                        logger.warning('Problem sending uplink')
                else:
                    logger.warning('Cannot send uplink - modem not registered'
                                   ' - try again in %d seconds',
                                   TRANSMIT_INTERVAL_S)
                last_transmit_attempt_time = time.time()
    except Exception as e:
        logger.exception(e)
        raise e
    finally:
        if modem and modem.is_connected():
            modem.disconnect()


if __name__ == '__main__':
    main()
