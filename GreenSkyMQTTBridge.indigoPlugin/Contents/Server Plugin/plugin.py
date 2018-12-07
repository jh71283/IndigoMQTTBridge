#! /usr/bin/env python
# -*- coding: utf-8 -*-
####################
# Indigo Copyright (c) 2013, Perceptive Automation, LLC. All rights reserved.
# http://www.indigodomotics.com


import indigo

import os
import sys
import signal
import Queue
import threading
import subprocess
import exceptions
import argparse
import socket
import time
import thread
import datetime
import paho.mqtt.client as mqtt
import json
# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.
from raygun4py import raygunprovider

pVer = 0


class Plugin(indigo.PluginBase):
    ########################################
    # Main Functions
    ######################

    def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
        indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
        pVer = pluginVersion
        # ptvsd.enable_attach(u"my_secret", address = (u'0.0.0.0', 3000))
        self.MQTT_SERVER = ''
        self.MQTT_PORT = 0
        self.topicList = {}
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.connected = False

        self.sentMessages = []
        self.LastConnectionWarning = datetime.datetime.now() - datetime.timedelta(days=1)
        self.debug = False

        self.MQTT_SERVER = u'localhost'
        self.MQTT_PORT = 1883
        self.username = u""
        self.password = u""
        self.DevicesToLog = []
        self.superBridgePatternOut = u'indigo/devices/{DeviceName}/{State}'
        self.superBridgePatternIn = u'indigo/devices/{DeviceName}/{State}/set'
        self.superBridgePatternActionGroup = u'indigo/actionGroups/{ActionGroup}/execute'
        self.superBridgeRetain = False
        indigo.devices.subscribeToChanges()

        self.updatePrefs(pluginPrefs)

    def __del__(self):
        indigo.PluginBase.__del__(self)

    def updatePrefs(self, prefs):
        self.debug = prefs.get(u"showDebugInfo", False)
        self.MQTT_SERVER = prefs.get(u"serverAddress", u'localhost')
        self.MQTT_PORT = int(prefs.get(u"serverPort", 1883))
        self.username = prefs.get(u"serverUsername", "")
        self.password = prefs.get(u"serverPassword", "")
        self.DevicesToLog = prefs.get(u"devicesToLog", [])
        self.superBridgePatternOut = prefs.get(u"superBridgePatternOut", u'indigo/devices/{DeviceName}/{State}')
        self.superBridgePatternIn = prefs.get(u"superBridgePatternIn", u'indigo/devices/{DeviceName}/{State}/set')
        self.superBridgePatternActionGroup = prefs.get(u"superBridgePatternActionGroup", u'indigo/actionGroups/{ActionGroup}/execute')
        self.superBridgeRetain = prefs.get(u"superBridgeRetain", False)
        if self.debug:
            self.debugLog(u"logger debugging enabled")
        else:
            self.debugLog(u"logger debugging disabled")

    def handle_exception(self, exc_type, exc_value, exc_traceback):
        self.logger.error(u'Exception trapped:' + unicode(exc_value))

    def runConcurrentThread(self):
        while True:
            if not self.connected:
                self.connectToMQTTBroker()

            self.sleep(60)

    def connectToMQTTBroker(self):
        try:
            self.logger.info("Connecting to the MQTT Server...")
            self.populateTopicList()
            self.client.disconnect()
            self.client.loop_stop()
            self.client.username_pw_set(username=self.username, password=self.password)
            self.client.connect(self.MQTT_SERVER, self.MQTT_PORT, 59)
            self.logger.info("Connected!")

            self.client.loop_start()
        except Exception:
            t, v, tb = sys.exc_info()
            if v.errno == 61:
                self.logger.critical(u"Connection Refused when connecting to broker.")
            elif v.errno == 60:
                self.logger.error(u"Timeout when connecting to broker.")
            else:
                self.handle_exception(t, v, tb)
                raise

    def devicesList(self, filter="", valuesDict=None, typeId="", targetId=0):
        try:
            returnListA = []
            for var in indigo.devices:
                returnListA.append((var.id, var.name))

            returnListA = sorted(returnListA, key=lambda var: var[1])

            return returnListA
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def getFullyQualifiedDeviceName(self, devID):
        try:
            var = indigo.devices[devID]
            if var.folderId == 0:
                return var.name
            else:
                folder = indigo.devices.folders[var.folderId]
                return folder.name + '.' + var.name
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def transformValue(self, value):
        try:
            if value == u'true':
                return u'1'
            elif value == u'false':
                return u'0'
            else:
                return value
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def populateTopicList(self):
        try:
            self.topicList = {}
            for dev in indigo.devices.iter(u"self"):
                self.topicList[dev.pluginProps[u"stateTopic"]] = u"d:" + unicode(dev.id)
            for dev in indigo.devices:
                self.topicList[self.superBridgePatternIn.replace(u"{DeviceName}", dev.name).replace(u'{State}', u'switch')] = u"d:" + unicode(dev.id)
                self.topicList[self.superBridgePatternIn.replace(u"{DeviceName}", dev.name).replace(u'{State}', u'level')] = u"d:" + unicode(dev.id)
                self.topicList[self.superBridgePatternIn.replace(u"{DeviceName}", unicode(dev.id)).replace(u'{State}', u'switch')] = u"d:" + unicode(dev.id)
                self.topicList[self.superBridgePatternIn.replace(u"{DeviceName}", unicode(dev.id)).replace(u'{State}', u'level')] = u"d:" + unicode(dev.id)
            for ag in indigo.actionGroups:
                self.topicList[self.superBridgePatternActionGroup.replace(u"{ActionGroup}", ag.name)] = u"ag:" + unicode(ag.id)
                self.topicList[self.superBridgePatternActionGroup.replace(u"{ActionGroup}", unicode(ag.id))] = u"ag:" + unicode(ag.id)

        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)
            raise

    def deviceCreated(self, newDev):
        self.debugLog(u"Device Created")

    def deviceUpdated(self, origDev, newDev):
        try:
            # call the base's implementation first just to make sure all the right things happen elsewhere
            indigo.PluginBase.deviceUpdated(self, origDev, newDev)

            ddiff = self.dict_diff(origDev.states, newDev.states)
            dev = newDev.name
            devid = unicode(newDev.id)
            # indigo.server.log(u"Device updated: " + unicode(ddiff))

            for state in ddiff.keys():

                mqttTopic = self.superBridgePatternOut.replace(u"{DeviceName}", dev).replace(u"{State}", state)
                mqttTopic2 = self.superBridgePatternOut.replace(u"{DeviceName}", devid).replace(u"{State}", state)

                self.debugLog(u"Started processing update for " + mqttTopic)
                self.debugLog(u"Started processing update for " + mqttTopic2)
                newval = unicode(ddiff[state])

                data = {u'deviceName': newDev.name, u'state': state, u'newValue': newval}

                if state in origDev.states:
                    data[u'oldValue'] = unicode(origDev.states[state])
                else:
                    data[u'oldValue'] = u''

                val = json.dumps(data)
                self.debugLog(u"json ready: " + val)
                if state == u'alertMode' and data[u'newValue'] == '' and data[u'oldValue'] == u'none':
                    self.debugLog(u"Ignoring update for " + mqttTopic)
                    # This is a workaround for some odd behaviour in Hue Lights
                    continue
                else:
                    self.debugLog(u"Publishing new Value for " + mqttTopic + u": " + val)
                    self.publish(mqttTopic, val, 0, self.superBridgeRetain)
                    self.debugLog(u"Publishing new Value for " + mqttTopic2 + u": " + val)
                    self.publish(mqttTopic2, val, 0, self.superBridgeRetain)

        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)
            raise

    def closedPrefsConfigUi(self, valuesDict, userCancelled):
        # Since the dialog closed we want to set the debug flag - if you don't directly use
        # a plugin's properties (and for debugLog we don't) you'll want to translate it to
        # the appropriate stuff here.
        if not userCancelled:
            self.updatePrefs(valuesDict)

    def getDeviceIDFromTopic(self, topic):
        try:
            deviceID = 0
            if self.topicList.has_key(topic) and self.topicList[topic].startswith(u"d:"):
                deviceID = int(self.topicList[topic][2:])

            return deviceID
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def getActionGroupIDFromTopic(self, topic):
        try:
            agID = 0
            if self.topicList.has_key(topic) & self.topicList[topic].startswith(u"ag:"):
                agID = int(self.topicList[topic][3:])

            return agID
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def startup(self):
        self.debugLog(u"startup called")

    def shutdown(self):
        self.debugLog(u"shutdown called")

    def dateDiff(self, d1, d2):
        try:
            diff = d1 - d2

            return (diff.days * 86400) + diff.seconds
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def dict_diff(self, first, second):
        try:
            """ Return a dict of keys that differ with another config object.  If a value is
                    not found in one fo the configs, it will be represented by KEYNOTFOUND.
                @param first:    Fist dictionary to diff.
                @param second:  Second dictionary to diff.
                @return diff:    Dict of Key => (first.val, second.val)
            """
            diff = {k: second[k] for k, _ in set(second.items()) - set(first.items())}
            # diff = {}
            # Check all keys in first dict
            # for key in first.keys():
            #    if (not second.has_key(key)):
            #        a=1#diff[key] = (first[key], KEYNOTFOUND)
            #    elif (first[key] != second[key]):
            #        diff[key] = (first[key], second[key])
            # Check all keys in second dict to find missing
            # for key in second.keys():
            #    if (not first.has_key(key)):
            #        diff[key] = (KEYNOTFOUND, second[key])
            return diff
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def extract_json_value(self, data, path):
        if type(data) is not dict:
            working_data = json.loads(data)
        else:
            working_data = data.copy()
        keys = path.split('->')
        for k in keys:
            try:
                self.logger.debug("Looking for %s in %s" % (k, working_data))
                working_data = working_data[k]
            except:
                self.logger.error("Unable to extract data using path '%s'" % path)
                return None
        self.logger.debug("extracted: %s" % working_data)
        return working_data

    # The callback for when the client receives a CONNACK response from the server.
    def on_connect(self, client, userdata, flags, rc):
        try:
            self.debugLog(u"Connected with result code " + unicode(rc))
            if rc == 0:
                # self.client.subscribe(u"$SYS/#")

                self.connected = True
                for topic in self.topicList:
                    t = topic
                    self.debugLog(u"Subscribing to " + t)
                    try:
                        self.client.subscribe(t)
                    except UnicodeDecodeError:
                        self.logger.warn(u'Failed to subscribe to ' + t + u' as it contains non-ascii characters.')

                autoDiscoverTopic = u"/GS-Indigo-Autodiscover"

                devicesdict = []
                for device in indigo.devices:
                    devicesdict.append({'id': device.id, 'name': unicode(device.name)})

                actionsdict = []
                for action in indigo.actionGroups:
                    actionsdict.append({'id': action.id, 'name': unicode(action.name)})

                variablesdict = []
                for variable in indigo.variables:
                    variablesdict.append({'id': variable.id, 'name': unicode(variable.name)})

                data = {u'superBridgePatternIn': self.superBridgePatternIn,
                        u'superBridgePatternOut': self.superBridgePatternOut,
                        u'superBridgePatternActionGroup': self.superBridgePatternActionGroup,
                        u'devices': devicesdict,
                        u'variables': variablesdict,
                        u'actions': actionsdict}

                self.debugLog(u'Publishing AutoDiscover information to ' + autoDiscoverTopic)
                json_data = json.dumps(data)

                self.publish(autoDiscoverTopic, json_data, 0, True)

            if rc == 1:
                indigo.server.log(u"Error: Invalid Protocol Version.")
            if rc == 2:
                indigo.server.log(u"Error: Invalid Client Identifier.")

            if rc == 3:
                indigo.server.log(u"Error: Server Unavailable.")
            if rc == 4:
                indigo.server.log(u"Error: Bad Username or Password.")
            if rc == 5:
                indigo.server.log(u"Error: Not Authorised.")
        except Exception:
            t, v, tb = sys.exc_info()
            self.debugLog({t, v, tb})
            self.handle_exception(t, v, tb)

    def on_disconnect(self):
        self.logger.warn(u"Disconnected from Broker. ")
        self.connected = False

    # The callback for when a PUBLISH message is received from the server.
    def on_message(self, client, userdata, msg):
        try:
            self.debugLog(u"Message recd: " + msg.topic + " | " + unicode(msg.payload))
            thread.start_new_thread(self.processMessage, (client, userdata, msg))
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def publish(self, topic, payload, qos=0, retain=False):
        try:
            self.logger.debug(u"Message sent: " + topic + " | " + unicode(payload))
            self.client.publish(topic, payload, qos, retain)
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def processMessage(self, client, userdata, msg):
        try:
            # self.debugLog(u"Processing Message " + unicode(msg))
            devID = self.getDeviceIDFromTopic(msg.topic)
            agID = self.getActionGroupIDFromTopic(msg.topic)

            if agID + devID == 0:
                self.debugLog(u"Message did not match a known Device or Action Group.")

            if devID > 0:
                self.debugLog(u"DevID: " + unicode(devID))
                dev = indigo.devices[devID]

                # self.debugLog(u"Matched Device: " + unicode(dev.name))
                #self.logger.info("%s recieved mqtt message from %s" % (dev.name, msg.topic))
                self.logger.debug("payload: %s" % msg.payload)
                if dev.deviceTypeId == u"MQTTrelay":
                    if msg.payload == dev.pluginProps[u"payloadOn"]:
                        indigo.server.log("%s set to On" % dev.name)
                        dev.updateStateOnServer(u"onOffState", True)
                    if msg.payload == dev.pluginProps[u"payloadOff"]:
                        indigo.server.log("%s set to Off" % dev.name)
                        dev.updateStateOnServer(u"onOffState", False)
                elif dev.deviceTypeId == u"MQTTBinarySensor":
                    if msg.payload == dev.pluginProps[u"payloadOn"]:
                        indigo.server.log("%s set to On" % dev.name)
                        dev.updateStateOnServer(u"onOffState", True)
                        dev.updateStateOnServer(u"display", u"on")
                        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
                    if msg.payload == dev.pluginProps[u"payloadOff"]:
                        indigo.server.log("%s set to Off" % dev.name)
                        dev.updateStateOnServer(u"onOffState", False)
                        dev.updateStateOnServer(u"display", u"off")
                        dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
                elif dev.deviceTypeId == u"MQTTSensor":
                    value = msg.payload
                    offset = float(dev.pluginProps[u"offset"]) if dev.pluginProps[u"offset"] else 0
                    precision = int(dev.pluginProps[u"precision"]) if dev.pluginProps[u"precision"] else 0

                    # Get data from the payload
                    if dev.pluginProps[u"payloadExtraction"] is not "":
                        value = self.extract_json_value(msg.payload, dev.pluginProps[u"payloadExtraction"])

                    self.logger.debug("Got data: %s" % value)

                    # Apply Formula
                    if dev.pluginProps[u"formula"]:
                        x = value
                        value = eval(dev.pluginProps[u"formula"])

                    self.logger.debug("After Formula: %s" % value)

                    # Apply Offset
                    if offset is not None and value is not None:
                        value += offset

                    self.logger.debug("After Offset: %s" % value)

                    status = "%s%s" % (round(value, precision), dev.pluginProps[u"unit"])
                    self.logger.info("%s set to %s" % (dev.name, status))
                    dev.updateStateOnServer(u"sensorValue", value=value, decimalPlaces=precision, uiValue=status)
                elif dev.deviceTypeId == u"MQTTWeatherSensor":
                    temperature = None
                    humidity = None
                    pressure = None
                    temperatureUnit = dev.pluginProps[u"temperatureUnit"]
                    humidityUnit = dev.pluginProps[u"humidityUnit"]
                    pressureUnit = dev.pluginProps[u"pressureUnit"]
                    temperatureOffset = float(dev.pluginProps[u"temperatureOffset"]) if dev.pluginProps[u"temperatureOffset"] else 0
                    humidityOffset = float(dev.pluginProps[u"humidityOffset"]) if dev.pluginProps[u"humidityOffset"] else 0
                    pressureOffset = float(dev.pluginProps[u"pressureOffset"]) if dev.pluginProps[u"pressureOffset"] else 0
                    temperaturePrecision = int(dev.pluginProps[u"temperaturePrecision"]) if dev.pluginProps[u"temperaturePrecision"] else 0
                    humidityPrecision = int(dev.pluginProps[u"humidityPrecision"]) if dev.pluginProps[u"humidityPrecision"] else 0
                    pressurePrecision = int(dev.pluginProps[u"pressurePrecision"]) if dev.pluginProps[u"pressurePrecision"] else 0

                    self.logger.debug("%s / %s / %s" % (temperature, humidity, pressure))

                    # Get the data from the payload
                    if dev.pluginProps[u"temperaturePayloadExtraction"]:
                        temperature = self.extract_json_value(msg.payload, dev.pluginProps[u"temperaturePayloadExtraction"])
                    if dev.pluginProps[u"humidityPayloadExtraction"]:
                        humidity = self.extract_json_value(msg.payload, dev.pluginProps[u"humidityPayloadExtraction"])
                    if dev.pluginProps[u"pressurePayloadExtraction"]:
                        pressure = self.extract_json_value(msg.payload, dev.pluginProps[u"pressurePayloadExtraction"])

                    self.logger.debug("Got data: %s / %s / %s" % (temperature, humidity, pressure))

                    # Apply Formulas
                    if dev.pluginProps[u"temperatureFormula"]:
                        x = temperature
                        temperature = eval(dev.pluginProps[u"temperatureFormula"])
                    if dev.pluginProps[u"humidityFormula"]:
                        x = humidity
                        humidity = eval(dev.pluginProps[u"humidityFormula"])
                    if dev.pluginProps[u"pressureFormula"]:
                        x = pressure
                        pressure = eval(dev.pluginProps[u"pressureFormula"])

                    self.logger.debug("After Formulas: %s / %s / %s" % (temperature, humidity, pressure))

                    # Apply offsets
                    if temperatureOffset is not None and temperature is not None:
                        temperature += temperatureOffset
                    if humidityOffset is not None and humidity is not None:
                        humidity += humidityOffset
                    if pressureOffset is not None and pressure is not None:
                        pressure += pressureOffset

                    self.logger.debug("After Offsets: %s / %s / %s" % (temperature, humidity, pressure))

                    status = []
                    if temperature is not None:
                        dev.updateStateOnServer('temperature', value=temperature, decimalPlaces=temperaturePrecision)
                        status.append(u"%s°%s" % (round(temperature, temperaturePrecision), temperatureUnit))
                    if humidity is not None:
                        dev.updateStateOnServer('humidity', value=humidity, decimalPlaces=humidityPrecision)
                        status.append(u"%s%s" % (round(humidity, humidityPrecision), humidityUnit))
                    if pressure is not None:
                        dev.updateStateOnServer('pressure', value=pressure, decimalPlaces=pressurePrecision)
                        status.append(u"%s%s" % (round(pressure, pressurePrecision), pressureUnit))
                    if len(status) is not 0:
                        status_string = u' / '.join(status)
                        self.logger.info(u"%s set to %s" % (dev.name, status_string))
                        dev.updateStateOnServer('status', status_string, uiValue=status_string)
                        dev.updateStateImageOnServer(indigo.kStateImageSel.TemperatureSensorOn)
                else:
                    self.debugLog(u"Dissecting Topic")
                    statelesstopic = self.superBridgePatternIn.replace(u"{DeviceName}", indigo.devices[devID].name)
                    beforestate = statelesstopic.split(u"{State}")[0]
                    afterstate = statelesstopic.split(u"{State}")[1]
                    self.debugLog(u"BeforeState: " + beforestate)

                    self.debugLog(u"AfterState: " + afterstate)
                    state = msg.topic.replace(beforestate, "").replace(afterstate, "")

                    self.debugLog(u"State Is " + state)
                    if state == u"switch":
                        if msg.payload == True or unicode(msg.payload) == u"on" or unicode(msg.payload) == u"True":
                            self.debugLog(u"Turning On")
                            indigo.device.turnOn(devID)
                        elif msg.payload == False or unicode(msg.payload) == u"off" or unicode(msg.payload) == u"False":
                            self.debugLog(u"Turning Off")
                            indigo.device.turnOff(devID)
                        else:
                            self.debugLog(u"Payload did not match any conditions.")
                    elif state == u"level":
                        self.debugLog(u"setting brightness")
                        indigo.dimmer.setBrightness(devID, value=int(msg.payload))
                    elif state == u"setpointHeatx":
                        self.debugLog(u"setting heat setpoint")
                        indigo.thermostat.setHeatSetpoint(devID, value=int(msg.payload))
                    else:
                        self.debugLog(u"Unsupported State")
            if agID > 0:
                self.debugLog(u"Executing Action Group " + unicode(agID))
                indigo.actionGroup.execute(agID)
        except TypeError:
            a = 1
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)

    def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):
        self.client.subscribe(valuesDict[u"stateTopic"])
        self.connectToMQTTBroker()

    # dev = indigo.devices[devId]
    # if dev.deviceTypeId in [u"MQTTrelay", u"MQTTBinarySensor", u"MQTTSensor", u"MQTTWeatherSensor"]:
    # props = dev.pluginProps
    # props.update({"address": props["stateTopic"]})
    # dev.replacePluginPropsOnServer(props)

    def actionControlDevice(self, action, dev):
        try:
            topic = dev.pluginProps[u"commandTopic"]
            ###### TURN ON ######
            if action.deviceAction == indigo.kDeviceAction.TurnOn:
                # Command hardware module (dev) to turn ON here:
                payload = dev.pluginProps[u"payloadOn"]
                self.publish(topic, payload, int(dev.pluginProps[u"qos"]), False)

                sendSuccess = True  # Set to False if it failed.

                if sendSuccess:
                    # If success then log that the command was successfully sent.
                    indigo.server.log(u"sent \"%s\" %s" % (dev.name, u"on"))

                    # And then tell the Indigo Server to update the state.
                    dev.updateStateOnServer(u"onOffState", True)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    indigo.server.log(u"send \"%s\" %s failed" % (dev.name, u"on"), isError=True)

            ###### TURN OFF ######
            elif action.deviceAction == indigo.kDeviceAction.TurnOff:
                # Command hardware module (dev) to turn OFF here:
                payload = dev.pluginProps[u"payloadOff"]
                self.publish(topic, payload)
                sendSuccess = True  # Set to False if it failed.

                if sendSuccess:
                    # If success then log that the command was successfully sent.
                    indigo.server.log(u"sent \"%s\" %s" % (dev.name, u"off"))

                    # And then tell the Indigo Server to update the state:
                    dev.updateStateOnServer(u"onOffState", False)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    indigo.server.log(u"send \"%s\" %s failed" % (dev.name, u"off"), isError=True)

            ###### TOGGLE ######
            elif action.deviceAction == indigo.kDeviceAction.Toggle:
                # Command hardware module (dev) to toggle here:
                newOnState = not dev.onState
                sendSuccess = True  # Set to False if it failed.

                if sendSuccess:
                    # If success then log that the command was successfully sent.
                    indigo.server.log(u"sent \"%s\" %s" % (dev.name, u"toggle"))

                    # And then tell the Indigo Server to update the state:
                    dev.updateStateOnServer(u"onOffState", newOnState)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    indigo.server.log(u"send \"%s\" %s failed" % (dev.name, u"toggle"), isError=True)

            ###### SET BRIGHTNESS ######
            elif action.deviceAction == indigo.kDeviceAction.SetBrightness:
                # Command hardware module (dev) to set brightness here:
                # ** IMPLEMENT ME **
                newBrightness = action.actionValue
                sendSuccess = True  # Set to False if it failed.

                if sendSuccess:
                    # If success then log that the command was successfully sent.
                    indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, u"set brightness", newBrightness))

                    # And then tell the Indigo Server to update the state:
                    dev.updateStateOnServer(u"brightnessLevel", newBrightness)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, u"set brightness", newBrightness),
                                      isError=True)

            ###### BRIGHTEN BY ######
            elif action.deviceAction == indigo.kDeviceAction.BrightenBy:
                # Command hardware module (dev) to do a relative brighten here:
                # ** IMPLEMENT ME **
                newBrightness = dev.brightness + action.actionValue
                if newBrightness > 100:
                    newBrightness = 100
                sendSuccess = True  # Set to False if it failed.

                if sendSuccess:
                    # If success then log that the command was successfully sent.
                    indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, u"brighten", newBrightness))

                    # And then tell the Indigo Server to update the state:
                    dev.updateStateOnServer(u"brightnessLevel", newBrightness)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, u"brighten", newBrightness),
                                      isError=True)

            ###### DIM BY ######
            elif action.deviceAction == indigo.kDeviceAction.DimBy:
                # Command hardware module (dev) to do a relative dim here:
                # ** IMPLEMENT ME **
                newBrightness = dev.brightness - action.actionValue
                if newBrightness < 0:
                    newBrightness = 0
                sendSuccess = True  # Set to False if it failed.

                if sendSuccess:
                    # If success then log that the command was successfully sent.
                    indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, u"dim", newBrightness))

                    # And then tell the Indigo Server to update the state:
                    dev.updateStateOnServer(u"brightnessLevel", newBrightness)
                else:
                    # Else log failure but do NOT update state on Indigo Server.
                    indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, u"dim", newBrightness), isError=True)
        except Exception:
            t, v, tb = sys.exc_info()
            self.handle_exception(t, v, tb)