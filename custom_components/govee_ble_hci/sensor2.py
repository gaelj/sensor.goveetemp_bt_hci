"""Govee BLE monitor integration."""
from datetime import time, timedelta
from time import sleep
import logging
from typing import List, Optional, Dict, Set, Tuple

from bleson import get_provider  # type: ignore
from bleson.core.hci.constants import EVT_LE_ADVERTISING_REPORT  # type: ignore
from bleson.core.types import BDAddress  # type: ignore
from bleson.core.hci.type_converters import hex_string  # type: ignore

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

###############################################################################


#
# Configure for Home Assistant
#
def setup_platform(config) -> None:
    """Set up the sensor platform."""
    _LOGGER.debug("Starting Govee HCI Sensor")

    govee_devices: List[BLE_HT_data] = []  # Data objects of configured devices
    sensors_by_mac = {}  # HomeAssistant sensors by MAC address
    adapter = None

    def handle_meta_event(hci_packet) -> None:
        """Handle received BLE data."""
        # If received BLE packet is of type ADVERTISING_REPORT
        if hci_packet.subevent_code == EVT_LE_ADVERTISING_REPORT:
            packet_mac = hci_packet.data[3:9]

            for device in govee_devices:
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

    def init_configured_devices() -> None:
        """Initialize configured Govee devices."""
        for conf_dev in config[CONF_GOVEE_DEVICES]:
            # Initialize BLE HT data objects
            mac: str = conf_dev["mac"]
            given_name = conf_dev.get("name", None)

            device = BLE_HT_data(mac, given_name)
            device.log_spikes = config[CONF_LOG_SPIKES]
            device.maximum_temperature = config[CONF_TEMP_RANGE_MAX_CELSIUS]
            device.minimum_temperature = config[CONF_TEMP_RANGE_MIN_CELSIUS]

            if config[CONF_ROUNDING]:
                device.decimal_places = config[CONF_DECIMALS]
            govee_devices.append(device)

            # Initialize HA sensors
            name = conf_dev.get("name", mac)
            temp_sensor = TemperatureSensor(mac, name)
            hum_sensor = HumiditySensor(mac, name)
            sensors = [temp_sensor, hum_sensor]
            sensors_by_mac[mac] = sensors
            # add_entities(sensors)

    def update_ble_devices(config) -> None:
        """Discover Bluetooth LE devices."""
        _LOGGER.debug("Discovering Bluetooth LE devices")
        use_median = config[CONF_USE_MEDIAN]

        ATTR = "_device_state_attributes"
        textattr = "last median of" if use_median else "last mean of"

        for device in govee_devices:
            sensors = sensors_by_mac[device.mac]

            # if device.last_packet is not None:
            #     _LOGGER.debug(
            #         "Last mfg data for {}: {}".format(
            #             BDAddress(device.mac), device.last_packet
            #         )
            #     )

            if device.last_packet:
                if device.median_humidity is not None:
                    humstate_med = float(device.median_humidity)
                    getattr(sensors[1], ATTR)["median"] = humstate_med
                    if use_median:
                        setattr(sensors[1], "_state", humstate_med)
                    _LOGGER.debug(f"Median humidity {sensors[1].name}: {humstate_med}%")

                if device.mean_humidity is not None:
                    humstate_mean = float(device.mean_humidity)
                    getattr(sensors[1], ATTR)["mean"] = humstate_mean
                    if not use_median:
                        setattr(sensors[1], "_state", humstate_mean)
                    _LOGGER.debug(f"Mean humidity {sensors[1].name}: {humstate_mean}%")

                if device.median_temperature is not None:
                    tempstate_med = float(device.median_temperature)
                    getattr(sensors[0], ATTR)["median"] = tempstate_med
                    if use_median:
                        setattr(sensors[0], "_state", tempstate_med)
                    _LOGGER.debug(f"Median temperature {sensors[1].name}: {tempstate_med}°C")

                if device.mean_temperature is not None:
                    tempstate_mean = float(device.mean_temperature)
                    getattr(sensors[0], ATTR)["mean"] = tempstate_mean
                    if not use_median:
                        setattr(sensors[0], "_state", tempstate_mean)
                    _LOGGER.debug(f"Mean temperature {sensors[1].name}: {tempstate_mean}°C")

                for sensor in sensors:
                    last_packet = device.last_packet
                    getattr(sensor, ATTR)["last packet id"] = last_packet
                    getattr(sensor, ATTR)["rssi"] = device.rssi
                    sensor._battery = device.battery
                    getattr(sensor, ATTR)[textattr] = device.data_size
                    # sensor.async_schedule_update_ha_state()
                    _LOGGER.debug(f"RSSI {sensor.name}: {device.rssi}dB")
                    _LOGGER.debug(f"Battery {sensor.name}: {device.battery}%")

                device.reset()

    def update_ble_loop() -> None:
        """Lookup Bluetooth LE devices and update status."""
        # _LOGGER.debug("update_ble_loop called")
        adapter.start_scanning()

        try:
            # Time to make the dounuts
            update_ble_devices(config)
        except RuntimeError as error:
            _LOGGER.error("Error during Bluetooth LE scan: %s", error)

        # time_offset = dt_util.utcnow() + timedelta(seconds=config[CONF_PERIOD])
        # update_ble_loop() will be called again after time_offset
        # track_point_in_utc_time(update_ble_loop, time_offset)

        sleep(config[CONF_PERIOD])
        update_ble_loop()

    ###########################################################################

    # Initialize bluetooth adapter and begin scanning
    # XXX: will not work if there are more than 10 HCI devices
    try:
        adapter = get_provider().get_adapter(int(config[CONF_HCI_DEVICE][-1]))
        adapter._handle_meta_event = handle_meta_event
        # hass.bus.listen("homeassistant_stop", adapter.stop_scanning)
        adapter.start_scanning()
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
    init_configured_devices()
    # Begin sensor update loop
    update_ble_loop()


###############################################################################

#
# HomeAssistant Temperature Sensor Class
#
class TemperatureSensor():
    """Representation of a sensor."""

    def __init__(self, mac: str, name: str):
        """Initialize the sensor."""
        self._state = None
        self._battery = None
        self._unique_id = "t_" + mac.replace(":", "")
        self._name = name
        self._mac = mac.replace(":", "")
        self._device_state_attributes = {}

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "{} temp".format(self._name)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def device_class(self):
        """Return the unit of measurement."""
        return DEVICE_CLASS_TEMPERATURE

    @property
    def device_info(self) -> Optional[Dict[str, Set[Tuple[str, str]]]]:
        """Temperature Device Info."""
        return {
            "identifiers": {(DOMAIN, self._mac)},
            "name": self._name,
            "manufacturer": "Govee",
        }

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._device_state_attributes

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

    @property
    def force_update(self) -> bool:
        """Force update."""
        return True


#
# HomeAssistant Humidity Sensor Class
#
class HumiditySensor():
    """Representation of a Sensor."""

    def __init__(self, mac: str, name: str):
        """Initialize the sensor."""
        self._state = None
        self._battery = None
        self._name = name
        self._unique_id = "h_" + mac.replace(":", "")
        self._mac = mac.replace(":", "")
        self._device_state_attributes = {}

    @property
    def name(self) -> str:
        """Return the name of the sensor."""
        return "{} humidity".format(self._name)

    @property
    def state(self):
        """Return the state of the sensor."""
        return self._state

    @property
    def unit_of_measurement(self) -> str:
        """Return the unit of measurement."""
        return "%"

    @property
    def device_class(self):
        """Return the unit of measurement."""
        return DEVICE_CLASS_HUMIDITY

    @property
    def device_info(self) -> Optional[Dict[str, Set[Tuple[str, str]]]]:
        """Humidity Device Info."""
        return {
            "identifiers": {(DOMAIN, self._mac)},
            "name": self._name,
            "manufacturer": "Govee",
        }

    @property
    def should_poll(self) -> bool:
        """No polling needed."""
        return False

    @property
    def device_state_attributes(self):
        """Return the state attributes."""
        return self._device_state_attributes

    @property
    def unique_id(self) -> str:
        """Return a unique ID."""
        return self._unique_id

    @property
    def force_update(self) -> bool:
        """Force update."""
        return True

if __name__ == "__main__":
    config = {
        CONF_GOVEE_DEVICES: [
            {
                'mac': 'E3:8C:81:90:A0:A0',
                'name': 'Govee_H5179_A0A0',
            },
            {
                'mac': 'E3:8C:81:92:B4:D0',
                'name': 'Govee_H5179_B4D0',
            },
        ],
        CONF_LOG_SPIKES: False,
        CONF_ROUNDING: True,
        CONF_DECIMALS: 2,
        CONF_TEMP_RANGE_MAX_CELSIUS: 45,
        CONF_TEMP_RANGE_MIN_CELSIUS: 0,
        CONF_USE_MEDIAN: True,
        CONF_HCI_DEVICE: 'hci0',
        CONF_PERIOD: 1,
    }
    setup_platform(config)