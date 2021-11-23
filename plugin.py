"""
# Govee domoticz Python Plugin

This plugin allows reading Govee BLE temperature / humidity sensors

## Installation

```bash
cd ~
git clone https://github.com/gaelj/sensor.goveetemp_bt_hci.git domoticz/plugins/Govee
chmod +x domoticz/plugins/Govee/plugin.py
sudo systemctl restart domoticz.service
```

For more details, see [Using Python Plugins](https://www.domoticz.com/wiki/Using_Python_plugins)
"""

"""
<plugin
    key="GoveeBLETemperatureHumidity"
    name="GoveeBLETempHum"
    author="gaelj"
    version="1.0.0"
    wikilink="https://github.com/gaelj/sensor.goveetemp_bt_hci/blob/master/README.md"
    externallink="https://github.com/gaelj/sensor.goveetemp_bt_hci">

    <description>
        <h2>Govee BLE</h2><br/>

        <h3>Devices</h3>
        <ul style="list-style-type:square">
            <li>Temperature</li>
            <li>Humidity</li>
        </ul>

        <h3>Configuration</h3>
        Configuration options...
    </description>

    <params>
        <param field="Address"  label="Domoticz IP Address"                                          width="200px" required="true"  default="localhost" />
        <param field="Port"     label="Port"                                                         width="40px"  required="true"  default="8080"      />
        <param field="Username" label="Username"                                                     width="200px" required="false" default=""          />
        <param field="Password" label="Password"                                                     width="200px" required="false" default=""          />
        <param field="Mode1" label="Logging Level" width="200px">
            <options>
                <option label="Normal" value="Normal" default="true"/>
                <option label="Verbose" value="Verbose"/>
                <option label="Debug - Python Only" value="2"/>
                <option label="Debug - Basic" value="62"/>
                <option label="Debug - Basic+Messages" value="126"/>
                <option label="Debug - Connections Only" value="16"/>
                <option label="Debug - Connections+Queue" value="144"/>
                <option label="Debug - All" value="-1"/>
            </options>
        </param>
        <param field="Mode2" label="MAC Address #1" width="200px" required="true" default=""/>
        <param field="Mode3" label="Name #1" width="200px" required="false" default=""/>
        <param field="Mode4" label="MAC Address #2" width="200px" required="false" default=""/>
        <param field="Mode5" label="Name #2" width="200px" required="false" default=""/>
        <param field="Mode6" label="MAC Address #3" width="200px" required="false" default=""/>
        <param field="Mode7" label="Name #3" width="200px" required="false" default=""/>
    </params>
</plugin>
"""

from typing import Dict, List
import Domoticz
from datetime import date, datetime, timedelta
import time
from enum import IntEnum
from DomoticzPluginHelper import DomoticzPluginHelper
import sensor2

z: DomoticzPluginHelper = None

class PluginConfig:
    """Plugin configuration (singleton)"""

    def __init__(self):
        global z
        self.macs = [
            {
                'mac': z.Parameters.Mode2,
                'name': z.Parameters.Mode3,
            },
        ]
        if z.Parameters.Mode4 is not None and z.Parameters.Mode4 != '':
            self.macs.append({
                'mac': z.Parameters.Mode4,
                'name': z.Parameters.Mode5,
            },)
        if z.Parameters.Mode6 is not None and z.Parameters.Mode6 != '':
            self.macs.append({
                'mac': z.Parameters.Mode6,
                'name': z.Parameters.Mode7,
            },)
        for x in self.macs:
            z.WriteLog(f"mac: {x['mac']}: {x['name']}")
        #sensor2.setup_platform_by_macs(self.macs)


class DeviceUnits(IntEnum):
    """Unit numbers of each virtual switch"""
    TempHum = 1

class PluginDevices:
    def __init__(self):
        self.config = PluginConfig()

pluginDevices: PluginDevices = None


def onStart():
    global z
    global pluginDevices

    # prod
    from DomoticzWrapperClass import \
         DomoticzTypeName, DomoticzDebugLevel, DomoticzPluginParameters, \
         DomoticzWrapper, DomoticzDevice, DomoticzConnection, DomoticzImage, \
         DomoticzDeviceType
    from DomoticzPluginHelper import \
        DomoticzPluginHelper, DeviceParam, ParseCSV, DomoticzDeviceTypes

    # dev
    # from DomoticzWrapper.DomoticzWrapperClass import \
    #     DomoticzTypeName, DomoticzDebugLevel, DomoticzPluginParameters, \
    #     DomoticzWrapper, DomoticzDevice, DomoticzConnection, DomoticzImage, \
    #     DomoticzDeviceType
    # from DomoticzWrapper.DomoticzPluginHelper import \
    #     DomoticzPluginHelper, DeviceParam, ParseCSV, DomoticzDeviceTypes

    z = DomoticzPluginHelper(
        Domoticz, Settings, Parameters, Devices, Images, {})
    z.onStart(3)

    pluginDevices = PluginDevices()
    TempHumDomoticzDeviceType = DomoticzDeviceTypes.TempHum()

    i = 1
    for x in pluginDevices.config.macs:
        mac = x['mac']
        name = x['name']
        z.InitDevice(f'Temp-Hum {name}', i,
                    DeviceType=TempHumDomoticzDeviceType,
                    Used=True,
                    defaultNValue=0,
                    defaultSValue="0")
        i += 1

def onStop():
    global z
    global pluginDevices
    z.onStop()


def onCommand(Unit, Command, Level, Color):
    global z
    global pluginDevices
    du = DeviceUnits(Unit)


def onHeartbeat():
    global z
    global pluginDevices
    z.onHeartbeat()
    #sensor2.update_ble_loop()
    #i = 1
    #for x in pluginDevices.config.macs:
    #    mac = x['mac']
    #    name = x['name']
    #    temp = sensor2.s.sensors_by_mac[mac][0].value
    #    hum = sensor2.s.sensors_by_mac[mac][1].value
    #    rssi = sensor2.s.sensors_by_mac[mac][0].rssi
    #    battery = sensor2.s.sensors_by_mac[mac][0].battery
    #    z.Devices[i].Update(BatteryLevel=battery * 255, SignalLevel=rssi * 255)
    #    i += 1
