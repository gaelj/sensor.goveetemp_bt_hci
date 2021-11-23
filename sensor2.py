"""Govee BLE monitor integration."""
from datetime import time, timedelta
from time import sleep
import logging
from typing import List, Optional, Dict, Set, Tuple

from bleson import get_provider  # type: ignore
from bleson.core.hci.constants import EVT_LE_ADVERTISING_REPORT  # type: ignore
from bleson.core.types import BDAddress  # type: ignore
from bleson.core.hci.type_converters import hex_string
from bleson.providers.linux.linux_adapter import BluetoothHCIAdapter  # type: ignore

from const import (
    CONF_DECIMALS,
    CONF_GOVEE_DEVICES,
    CONF_HCI_DEVICE,
    CONF_LOG_SPIKES,
    CONF_PERIOD,
    CONF_ROUNDING,
    CONF_TEMP_RANGE_MAX_CELSIUS,
    CONF_TEMP_RANGE_MIN_CELSIUS,
    CONF_USE_MEDIAN,
    DEFAULT_DECIMALS,
    DEFAULT_HCI_DEVICE,
    DEFAULT_LOG_SPIKES,
    DEFAULT_PERIOD,
    DEFAULT_ROUNDING,
    DEFAULT_TEMP_RANGE_MAX,
    DEFAULT_TEMP_RANGE_MIN,
    DEFAULT_USE_MEDIAN,
    DOMAIN,
)

from govee_advertisement import GoveeAdvertisement
from ble_ht import BLE_HT_data

###############################################################################

# _LOGGER = logging.getLogger(__name__)

class _LOGGER:
    def debug(text):
        print(text)
    def error(text):
        print(text)

###############################################################################


class govee_sensor:
    def __init__(self) -> None:
        """Set up the sensor platform."""
        _LOGGER.debug("Starting Govee HCI Sensor")
        self.govee_devices: List[BLE_HT_data] = []  # Data objects of configured devices
        self.sensors_by_mac: Dict[str, List[MeasurementSensor]] = {}  # HomeAssistant sensors by MAC address
        self.adapter: BluetoothHCIAdapter = None

    def setup_platform(self, config) -> None:
        self.config = config
        self.run()

    def handle_meta_event(self, hci_packet) -> None:
        """Handle received BLE data."""
        # If received BLE packet is of type ADVERTISING_REPORT
        if hci_packet.subevent_code == EVT_LE_ADVERTISING_REPORT:
            packet_mac = hci_packet.data[3:9]

            for device in self.govee_devices:
                # If received device data matches a configured govee device
                if BDAddress(device.mac) == BDAddress(packet_mac):
                    # _LOGGER.debug(
                    #     "Received packet data for {}: {}".format(
                    #         BDAddress(device.mac), hex_string(hci_packet.data)
                    #     )
                    # )
                    # parse packet data
                    ga = GoveeAdvertisement(hci_packet.data)

                    # If mfg data information is defined, update values
                    if ga.packet is not None:
                        device.update(ga.temperature, ga.humidity, ga.packet)

                    # Update RSSI and battery level
                    device.rssi = ga.rssi
                    device.battery = ga.battery

    def init_configured_devices(self) -> None:
        """Initialize configured Govee devices."""
        for conf_dev in self.config[CONF_GOVEE_DEVICES]:
            # Initialize BLE HT data objects
            mac: str = conf_dev["mac"]
            given_name = conf_dev.get("name", None)

            device = BLE_HT_data(mac, given_name)
            device.log_spikes = self.config[CONF_LOG_SPIKES]
            device.maximum_temperature = self.config[CONF_TEMP_RANGE_MAX_CELSIUS]
            device.minimum_temperature = self.config[CONF_TEMP_RANGE_MIN_CELSIUS]

            if self.config[CONF_ROUNDING]:
                device.decimal_places = self.config[CONF_DECIMALS]
            self.govee_devices.append(device)

            # Initialize HA sensors
            name = conf_dev.get("name", mac)
            temp_sensor = MeasurementSensor(mac, name)
            hum_sensor = MeasurementSensor(mac, name)
            sensors = [temp_sensor, hum_sensor]
            self.sensors_by_mac[mac] = sensors

    def update_ble_devices(self, config) -> None:
        """Discover Bluetooth LE devices."""
        # _LOGGER.debug("Discovering Bluetooth LE devices")
        use_median = config[CONF_USE_MEDIAN]

        for device in self.govee_devices:
            sensors = self.sensors_by_mac[device.mac]

            # if device.last_packet is not None:
            #     _LOGGER.debug(
            #         "Last mfg data for {}: {}".format(
            #             BDAddress(device.mac), device.last_packet
            #         )
            #     )

            if device.last_packet:
                if device.median_temperature is not None:
                    tempstate_med = float(device.median_temperature)
                    if use_median:
                        sensors[0].value = tempstate_med

                if device.mean_temperature is not None:
                    tempstate_mean = float(device.mean_temperature)
                    if not use_median:
                        sensors[0].value = tempstate_mean

                if device.median_humidity is not None:
                    humstate_med = float(device.median_humidity)
                    if use_median:
                        sensors[1].value = humstate_med

                if device.mean_humidity is not None:
                    humstate_mean = float(device.mean_humidity)
                    if not use_median:
                        sensors[1].value = humstate_mean

                for sensor in sensors:
                    sensor.rssi = device.rssi
                    sensor.battery = device.battery

                _LOGGER.debug(f"{sensor.name} - Temp {self.temp}°C - Hum {self.hum}% - RSSI {device.rssi}dB - Batt {device.battery}%")

                device.reset()

    def update_ble_loop(self) -> None:
        """Lookup Bluetooth LE devices and update status."""
        # _LOGGER.debug("update_ble_loop called")
        self.adapter.start_scanning()

        try:
            # Time to make the dounuts
            self.update_ble_devices(self.config)
        except RuntimeError as error:
            _LOGGER.debug("Error during Bluetooth LE scan: %s", error)

        # time_offset = dt_util.utcnow() + timedelta(seconds=config[CONF_PERIOD])
        # update_ble_loop() will be called again after time_offset
        # track_point_in_utc_time(update_ble_loop, time_offset)

        # sleep(self.config[CONF_PERIOD])
        # self.update_ble_loop()

    def run(self):
        # Initialize bluetooth adapter and begin scanning
        # XXX: will not work if there are more than 10 HCI devices
        try:
            self.adapter = get_provider().get_adapter(int(self.config[CONF_HCI_DEVICE][-1]))
            self.adapter._handle_meta_event = self.handle_meta_event
            # hass.bus.listen("homeassistant_stop", adapter.stop_scanning)
            self.adapter.start_scanning()
        except (RuntimeError, OSError, PermissionError) as error:
            error_msg = "Error connecting to Bluetooth adapter: {}\n\n".format(error)
            error_msg += "Bluetooth adapter troubleshooting:\n"
            error_msg += "  -If running HASS, ensure the correct HCI device is being"
            error_msg += " used. Check by logging into HA command line and execute:\n"
            error_msg += "          gdbus introspect --system --dest org.bluez --object-path /org/bluez | fgrep -i hci\n"
            error_msg += "  -If running Home Assistant in Docker, "
            error_msg += "make sure it run with the --privileged flag.\n"
            # _LOGGER.error(error_msg)
            raise Exception(error_msg) from error

        # Initialize configured Govee devices
        self.init_configured_devices()
        # Begin sensor update loop
        self.update_ble_loop()


###############################################################################

class MeasurementSensor():
    def __init__(self, mac, name) -> None:
        self._mac = mac
        self._name = name
        self._value: float = None
        self._battery: float = None
        self._rssi: float = None
    @property
    def name(self) -> float:
        return self._name
    @property
    def mac(self) -> float:
        return self._mac
    @property
    def value(self) -> float:
        return self._value
    @value.setter
    def value(self, value: float) -> None:
        self._value = value
    @property
    def battery(self) -> float:
        return self._battery
    @battery.setter
    def battery(self, value: float) -> None:
        self._battery = value
    @property
    def rssi(self) -> float:
        return self._rssi
    @rssi.setter
    def rssi(self, value: float) -> None:
        self._rssi = value


s = govee_sensor()

def setup_platform_by_macs(macs_names: List[Dict[str, str]]) -> None:
    config = {
        CONF_GOVEE_DEVICES: macs_names,
        CONF_LOG_SPIKES: False,
        CONF_ROUNDING: True,
        CONF_DECIMALS: 2,
        CONF_TEMP_RANGE_MAX_CELSIUS: 45,
        CONF_TEMP_RANGE_MIN_CELSIUS: 0,
        CONF_USE_MEDIAN: True,
        CONF_HCI_DEVICE: 'hci0',
        CONF_PERIOD: 30,
    }
    s.setup_platform(config)

def update_ble_loop():
    s.update_ble_loop()

if __name__ == "__main__":
    setup_platform_by_macs([
        {
            'mac': 'E3:8C:81:90:A0:A0',
            'name': 'Govee_H5179_Salon',
        },
        {
            'mac': 'E3:8C:81:92:B4:D0',
            'name': 'Govee_H5179_SdB',
        },
    ])
