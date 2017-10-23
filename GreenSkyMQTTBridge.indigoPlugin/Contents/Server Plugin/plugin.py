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
import datetime
import paho.mqtt.client as mqtt

# Note the "indigo" module is automatically imported and made available inside
# our global name space by the host process.


class Plugin(indigo.PluginBase):
	########################################
	# Main Functions
	######################

	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		self.MQTT_SERVER = ''
		self.MQTT_PORT = 0
		self.topicList = []
		self.client = mqtt.Client()
		self.client.on_connect = self.on_connect
		self.client.on_disconnect = self.on_disconnect
		self.client.on_message = self.on_message
		self.connected = False
		self.updatePrefs(pluginPrefs)
		self.LastConnectionWarning = datetime.datetime.now()-datetime.timedelta(days=1)
		#indigo.devices.subscribeToChanges()
	
		
	def __del__(self):
		indigo.PluginBase.__del__(self)


	def updatePrefs(self, prefs):
		self.debug = prefs.get("showDebugInfo", False)
		self.MQTT_SERVER = prefs.get("serverAddress", 'localhost')
		self.MQTT_PORT = int(prefs.get("serverPort", 1883))
		self.DevicesToLog = prefs.get("devicesToLog",[])
		

		if self.debug == True:
			self.debugLog("logger debugging enabled")
		else:
			self.debugLog("logger debugging disabled")
			
		
	def runConcurrentThread(self):
		while True:
			if self.connected == False:
				self.connectToMQTTBroker()
				
			self.sleep(60)
		
	def connectToMQTTBroker(self):
		self.populateTopicList()
		self.client.disconnect()
		self.client.connect(self.MQTT_SERVER, self.MQTT_PORT, 59)	
		self.client.loop_start()
		
	def devicesList(self, filter="", valuesDict=None, typeId="", targetId=0):

		returnListA = []
		for var in indigo.devices:
			returnListA.append((var.id,var.name))
		
				
		returnListA = sorted(returnListA,key=lambda var: var[1])
		
		
		return returnListA 
	
	def getFullyQualifiedDeviceName(self, devID):
		var = indigo.devices[devID]
		if var.folderId == 0:
			return	var.name
		else:
			folder = indigo.devices.folders[var.folderId]
			return  folder.name + '.' + var.name
		
	def transformValue(self, value):
		if value=='true':
			return '1'
		elif value=='false':
			return '0'
		else:
			return value

	def populateTopicList(self):
		self.topicList =[]
		for dev in indigo.devices.iter("self"):
			self.topicList.append(dev.pluginProps["stateTopic"])
			self.debugLog("adding " + dev.pluginProps["stateTopic"] + " to topic list")
	
	def deviceCreated(self, newDev):
		self.debugLog("Device Created")
				

	def deviceUpdated(self, origDev, newDev):
		# call the base's implementation first just to make sure all the right things happen elsewhere
		indigo.PluginBase.deviceUpdated(self, origDev, newDev)
		if str(newDev.id) in self.DevicesToLog:
			ddiff = self.dict_diff(origDev.states, newDev.states)
			#indigo.server.log("Device updated: " + str(ddiff))
			for k in ddiff.keys():
				mqttTopic= "indigo/devices/" + newDev.name.replace(" ", "_") + "/" + k
				self.debugLog("New Value for " + mqttTopic + ": " + unicode(ddiff[k][1]))
				self.client.publish(mqttTopic,unicode(ddiff[k][1]))

	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		# Since the dialog closed we want to set the debug flag - if you don't directly use
		# a plugin's properties (and for debugLog we don't) you'll want to translate it to
		# the appropriate stuff here. 
		if not userCancelled:
			self.updatePrefs(valuesDict)

	def startup(self):
		self.debugLog("startup called")
	
	def shutdown(self):
		self.debugLog("shutdown called")

	def dateDiff(self,d1,d2):
		diff = d1-d2
		
		return (diff.days * 86400) + diff.seconds
		
	
	def dict_diff(self, first, second):
		""" Return a dict of keys that differ with another config object.  If a value is
				not found in one fo the configs, it will be represented by KEYNOTFOUND.
			@param first:	Fist dictionary to diff.
			@param second:  Second dicationary to diff.
			@return diff:	Dict of Key => (first.val, second.val)
		"""
		diff = {}
		# Check all keys in first dict
		for key in first.keys():
			if (not second.has_key(key)):
				diff[key] = (first[key], KEYNOTFOUND)
			elif (first[key] != second[key]):
				diff[key] = (first[key], second[key])
		# Check all keys in second dict to find missing
		for key in second.keys():
			if (not first.has_key(key)):
				diff[key] = (KEYNOTFOUND, second[key])
		return diff

	# The callback for when the client receives a CONNACK response from the server.
	def on_connect(self, client, userdata, flags, rc):
		self.debugLog("Connected with result code " + str(rc))
		#self.client.subscribe("$SYS/#")
		self.connected=True
		for topic in self.topicList:
			self.client.subscribe(topic)
			self.debugLog("Subscribing to " + topic)

	def on_disconnect(self):
		self.connected=False


	# The callback for when a PUBLISH message is received from the server.
	def on_message(self,client, userdata, msg):
		self.debugLog("Message recd: " + msg.topic + " " + str(msg.payload))
		if msg.topic in self.topicList:
			#loop plugin's own devices, looking for a matching state change topic
			for dev in indigo.devices.iter("self"):
				if dev.pluginProps["stateTopic"] == msg.topic:
					self.debugLog("Matched Device: " + dev.name)
					if dev.deviceTypeId == "MQTTrelay":
						if msg.payload == dev.pluginProps["payloadOn"]:
							dev.updateStateOnServer("onOffState", True)
						if msg.payload == dev.pluginProps["payloadOff"]:
							dev.updateStateOnServer("onOffState", False)
					if dev.deviceTypeId == "MQTTBinarySensor":
						if msg.payload == dev.pluginProps["payloadOn"]:
							dev.updateStateOnServer("onOffState", True)
							dev.updateStateOnServer("display", "on")
							dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
						
						if msg.payload == dev.pluginProps["payloadOff"]:
							dev.updateStateOnServer("onOffState", False)
							dev.updateStateOnServer("display", "off")
							dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
							
					if dev.deviceTypeId == "MQTTSensor":
							dev.updateStateOnServer("display", msg.payload + dev.pluginProps["unit"] )
							dev.updateStateOnServer("sensorValue", msg.payload )
				

	def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):
		self.client.subscribe(valuesDict["stateTopic"])
		self.connectToMQTTBroker()

	def actionControlDevice(self, action, dev):
		topic = dev.pluginProps["commandTopic"]
		###### TURN ON ######
		if action.deviceAction == indigo.kDeviceAction.TurnOn:
				# Command hardware module (dev) to turn ON here:
				payload = dev.pluginProps["payloadOn"]
				self.client.publish(topic, payload, int(dev.pluginProps["qos"]), True)

				sendSuccess = True		# Set to False if it failed.

				if sendSuccess:
					# If success then log that the command was successfully sent.
					indigo.server.log(u"sent \"%s\" %s" % (dev.name, "on"))

					# And then tell the Indigo Server to update the state.
					dev.updateStateOnServer("onOffState", True)
				else:
					# Else log failure but do NOT update state on Indigo Server.
					indigo.server.log(u"send \"%s\" %s failed" % (dev.name, "on"), isError=True)

		###### TURN OFF ######
		elif action.deviceAction == indigo.kDeviceAction.TurnOff:
				# Command hardware module (dev) to turn OFF here:
				payload = dev.pluginProps["payloadOff"]
				self.client.publish(topic, payload)
				sendSuccess = True		# Set to False if it failed.

				if sendSuccess:
					# If success then log that the command was successfully sent.
					indigo.server.log(u"sent \"%s\" %s" % (dev.name, "off"))

					# And then tell the Indigo Server to update the state:
					dev.updateStateOnServer("onOffState", False)
				else:
					# Else log failure but do NOT update state on Indigo Server.
					indigo.server.log(u"send \"%s\" %s failed" % (dev.name, "off"), isError=True)

		###### TOGGLE ######
		elif action.deviceAction == indigo.kDeviceAction.Toggle:
				# Command hardware module (dev) to toggle here:
				newOnState = not dev.onState
				sendSuccess = True		# Set to False if it failed.

				if sendSuccess:
					# If success then log that the command was successfully sent.
					indigo.server.log(u"sent \"%s\" %s" % (dev.name, "toggle"))

					# And then tell the Indigo Server to update the state:
					dev.updateStateOnServer("onOffState", newOnState)
				else:
					# Else log failure but do NOT update state on Indigo Server.
					indigo.server.log(u"send \"%s\" %s failed" % (dev.name, "toggle"), isError=True)

		###### SET BRIGHTNESS ######
		elif action.deviceAction == indigo.kDeviceAction.SetBrightness:
				# Command hardware module (dev) to set brightness here:
				# ** IMPLEMENT ME **
				newBrightness = action.actionValue
				sendSuccess = True		# Set to False if it failed.

				if sendSuccess:
					# If success then log that the command was successfully sent.
					indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, "set brightness", newBrightness))

					# And then tell the Indigo Server to update the state:
					dev.updateStateOnServer("brightnessLevel", newBrightness)
				else:
					# Else log failure but do NOT update state on Indigo Server.
					indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, "set brightness", newBrightness), isError=True)

		###### BRIGHTEN BY ######
		elif action.deviceAction == indigo.kDeviceAction.BrightenBy:
				# Command hardware module (dev) to do a relative brighten here:
				# ** IMPLEMENT ME **
				newBrightness = dev.brightness + action.actionValue
				if newBrightness > 100:
					newBrightness = 100
				sendSuccess = True		# Set to False if it failed.

				if sendSuccess:
					# If success then log that the command was successfully sent.
					indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, "brighten", newBrightness))

					# And then tell the Indigo Server to update the state:
					dev.updateStateOnServer("brightnessLevel", newBrightness)
				else:
					# Else log failure but do NOT update state on Indigo Server.
					indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, "brighten", newBrightness), isError=True)

		###### DIM BY ######
		elif action.deviceAction == indigo.kDeviceAction.DimBy:
				# Command hardware module (dev) to do a relative dim here:
				# ** IMPLEMENT ME **
				newBrightness = dev.brightness - action.actionValue
				if newBrightness < 0:
					newBrightness = 0
				sendSuccess = True		# Set to False if it failed.

				if sendSuccess:
					# If success then log that the command was successfully sent.
					indigo.server.log(u"sent \"%s\" %s to %d" % (dev.name, "dim", newBrightness))

					# And then tell the Indigo Server to update the state:
					dev.updateStateOnServer("brightnessLevel", newBrightness)
				else:
					# Else log failure but do NOT update state on Indigo Server.
					indigo.server.log(u"send \"%s\" %s to %d failed" % (dev.name, "dim", newBrightness), isError=True)


		
		