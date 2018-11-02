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
def handle_exception(exc_type, exc_value, exc_traceback):
  cl = raygunprovider.RaygunSender("fsf/EFrrM7efzeAxZjgpeQ==")
  cl.set_version(pVer)
  cl.send_exception(exc_info=(exc_type, exc_value, exc_traceback))


class Plugin(indigo.PluginBase):
	########################################
	# Main Functions
	######################

	def __init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs):
		indigo.PluginBase.__init__(self, pluginId, pluginDisplayName, pluginVersion, pluginPrefs)
		pVer = pluginVersion
		#ptvsd.enable_attach("my_secret", address = ('0.0.0.0', 3000))
		self.MQTT_SERVER = ''
		self.MQTT_PORT = 0
		self.topicList = {}
		self.client = mqtt.Client()
		self.client.on_connect = self.on_connect
		self.client.on_disconnect = self.on_disconnect
		self.client.on_message = self.on_message
		self.connected = False
		self.updatePrefs(pluginPrefs)
		self.sentMessages = []
		self.LastConnectionWarning = datetime.datetime.now()-datetime.timedelta(days=1)
		indigo.devices.subscribeToChanges()
	
		
	def __del__(self):
		indigo.PluginBase.__del__(self)


	def updatePrefs(self, prefs):
		self.debug = prefs.get("showDebugInfo", False)
		self.MQTT_SERVER = prefs.get("serverAddress", 'localhost')
		self.MQTT_PORT = int(prefs.get("serverPort", 1883))
		self.username = prefs.get("serverUsername", "")
		self.password = prefs.get("serverPassword", "")
		self.DevicesToLog = prefs.get("devicesToLog",[])
		self.superBridgePatternOut = prefs.get("superBridgePatternOut", 'indigo/devices/{DeviceName}/{State}')
		self.superBridgePatternIn = prefs.get("superBridgePatternIn", 'indigo/devices/{DeviceName}/{State}/set')
		self.superBridgePatternActionGroup = prefs.get("superBridgePatternActionGroup", 'indigo/actionGroups/{ActionGroup}/execute')
		
		
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
		try:
			self.populateTopicList()
			self.client.disconnect()
			self.client.username_pw_set(username=self.username,password=self.password)
			self.client.connect(self.MQTT_SERVER, self.MQTT_PORT, 59)

			self.client.loop_start()
		except Exception:
			t, v, tb = sys.exc_info()
			if v == "[Errno 61] Connection refused":
				indigo.server.log("Connection Refused when connecting to broker.")
			elif v == "[Errno 60] Operation timed out":
				indigo.server.log("Timeout when connecting to broker.")
			else:
				handle_exception(t,v,tb)
		
	def devicesList(self, filter="", valuesDict=None, typeId="", targetId=0):
		try:
			returnListA = []
			for var in indigo.devices:
				returnListA.append((var.id,var.name))
			
					
			returnListA = sorted(returnListA,key=lambda var: var[1])
			
			
			return returnListA 
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)
	
	def getFullyQualifiedDeviceName(self, devID):
		try:
			var = indigo.devices[devID]
			if var.folderId == 0:
				return	var.name
			else:
				folder = indigo.devices.folders[var.folderId]
				return  folder.name + '.' + var.name
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)
		
	def transformValue(self, value):
		try:
			if value=='true':
				return '1'
			elif value=='false':
				return '0'
			else:
				return value
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)

	def populateTopicList(self):
		try:
			self.topicList ={}
			for dev in indigo.devices.iter("self"):
				self.topicList[dev.pluginProps["stateTopic"]] = "d:" + unicode(dev.id)
				#self.debugLog("adding " + dev.pluginProps["stateTopic"] + " to topic list")

			for dev in indigo.devices:

				#self.topicList[self.superBridgePattern.replace("{DeviceName}", dev.name).replace('{State}','#')]= dev.id
				self.topicList[self.superBridgePatternIn.replace("{DeviceName}", dev.name).replace('{State}','switch')]= "d:" + unicode(dev.id)
				self.topicList[self.superBridgePatternIn.replace("{DeviceName}", dev.name).replace('{State}','level')]= "d:" + unicode(dev.id)
				#self.debugLog("adding " + mqttTopic + " to topic list")
				#for state in dev.states:
				#	mqttTopic = self.superBridgePattern.replace("{DeviceName}", dev.name.replace(" "," ")).replace('{State}',state)
				#	self.topicList[mqttTopic]= dev.id
				#	self.debugLog("adding " + mqttTopic + " to topic list") '''
			for ag in indigo.actionGroups:

				#self.topicList[self.superBridgePattern.replace("{DeviceName}", dev.name).replace('{State}','#')]= dev.id
				self.topicList[self.superBridgePatternActionGroup.replace("{ActionGroup}", ag.name)]= "ag:" + unicode(ag.id)
				#self.debugLog("adding " + mqttTopic + " to topic list")
				
			#self.debugLog("Topic List:")
			#for key in self.topicList.keys():
			#	self.debugLog("\t" + key)
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)
			
	def deviceCreated(self, newDev):
		self.debugLog("Device Created")
				

	def deviceUpdated(self, origDev, newDev):
		try:
			# call the base's implementation first just to make sure all the right things happen elsewhere
			indigo.PluginBase.deviceUpdated(self, origDev, newDev)
			
			ddiff = self.dict_diff(origDev.states, newDev.states)
			dev = newDev.name
			#indigo.server.log("Device updated: " + unicode(ddiff))
			for state in ddiff.keys():
				
				mqttTopic= self.superBridgePatternOut.replace("{DeviceName}",dev).replace("{State}",state)
				self.debugLog("Started processing update for " + mqttTopic )
				newval = unicode(ddiff[state])
				
				data = {}
				data['deviceName'] = newDev.name
				data['state'] = state
				data['newValue'] = newval
				data['oldValue'] = unicode(origDev.states[state])
				val = json.dumps(data)
				self.debugLog("json ready: " + val )
				if (state=='alertMode' and data['newValue'] == '' and data['oldValue']== 'none'):
					self.debugLog("Ignoring update for " + mqttTopic )
					#This is a workaround for some odd behaviour in Hue Lights
					continue
				else:
					self.debugLog("Publishing new Value for " + mqttTopic + ": " + val)
					self.publish(mqttTopic,val)

		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)

	def closedPrefsConfigUi(self, valuesDict, userCancelled):
		# Since the dialog closed we want to set the debug flag - if you don't directly use
		# a plugin's properties (and for debugLog we don't) you'll want to translate it to
		# the appropriate stuff here. 
		if not userCancelled:
			self.updatePrefs(valuesDict)

	def getDeviceIDFromTopic(self,topic):
		try:
			deviceID=0
			if self.topicList.has_key(topic) & self.topicList[topic].startswith("d:"):
				deviceID = int( self.topicList[topic][2:])
			

			return deviceID
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)

	def getActionGroupIDFromTopic(self,topic):
		try:
			agID=0
			if self.topicList.has_key(topic) & self.topicList[topic].startswith("ag:"):
				agID = int(self.topicList[topic][3:])



			return agID
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)

	def startup(self):
		self.debugLog("startup called")
	
	def shutdown(self):
		self.debugLog("shutdown called")

	def dateDiff(self,d1,d2):
		try:
			diff = d1-d2
			
			return (diff.days * 86400) + diff.seconds
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)
	
	def dict_diff(self, first, second):
		try:
			""" Return a dict of keys that differ with another config object.  If a value is
					not found in one fo the configs, it will be represented by KEYNOTFOUND.
				@param first:	Fist dictionary to diff.
				@param second:  Second dicationary to diff.
				@return diff:	Dict of Key => (first.val, second.val)
			"""
			diff = { k : second[k] for k, _ in set(second.items()) - set(first.items()) }
			#diff = {}
			# Check all keys in first dict
			#for key in first.keys():
			#	if (not second.has_key(key)):
			#		a=1#diff[key] = (first[key], KEYNOTFOUND)
			#	elif (first[key] != second[key]):
			#		diff[key] = (first[key], second[key])
			# Check all keys in second dict to find missing
			#for key in second.keys():
			#	if (not first.has_key(key)):
			#		diff[key] = (KEYNOTFOUND, second[key])
			return diff
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)

	# The callback for when the client receives a CONNACK response from the server.
	def on_connect(self, client, userdata, flags, rc):
		try:
			self.debugLog("Connected with result code " + unicode(rc))
			if rc ==0:
				#self.client.subscribe("$SYS/#")
				self.connected=True
				for topic in self.topicList:
					t = unicode(topic)
					self.client.subscribe(t)
					self.debugLog("Subscribing to " + t)

				autoDiscoverTopic = "/GS-Indigo-Autodiscover"

				data = {}
				data['superBridgePatternIn'] = self.superBridgePatternIn
				data['superBridgePatternOut'] = self.superBridgePatternOut
				data['superBridgePatternActionGroup'] = self.superBridgePatternActionGroup
				self.debugLog('Publishing AutoDiscover information to ' + autoDiscoverTopic)
				json_data = json.dumps(data)
				
				self.publish(autoDiscoverTopic,json_data,0,True)

			if rc ==1:
				indigo.server.log("Error: Invalid Protocol Version.")
			if rc ==2:
				indigo.server.log("Error: Invalid Client Identifier.")

			if rc ==3:
				indigo.server.log("Error: Server Unavailable.")
			if rc ==4:
				indigo.server.log("Error: Bad Username or Password.")
			if rc ==5:
				indigo.server.log("Error: Not Authorised.")
		except Exception:
			t, v, tb = sys.exc_info()
			self.debugLog({t, v, tb})
			handle_exception(t,v,tb)

	def on_disconnect(self):
		self.debugLog("Disconnected from Broker. ")
		self.connected=False


	# The callback for when a PUBLISH message is received from the server.
	def on_message(self,client, userdata, msg):
		try:
			self.debugLog("Message recd: " + msg.topic + " | " + unicode(msg.payload))
			thread.start_new_thread(self.processMessage,(client,userdata,msg))
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)
	
	def publish(self, topic, payload, qos=0, retain=False):
		try:
			self.debugLog("Message sent: " + topic + " | " + unicode(payload))
			self.client.publish(topic,payload,qos,retain)
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)

	def processMessage(self,client,userdata,msg):
		try:
			#self.debugLog("Processing Message " + unicode(msg))
			devID = self.getDeviceIDFromTopic(msg.topic)
			agID = self.getActionGroupIDFromTopic(msg.topic)

			if agID + devID == 0:
				self.debugLog("Message did not match a known Device or Action Group.")

			if devID > 0:
				self.debugLog("DevID: "+ unicode(devID))
				dev = indigo.devices[devID]

				self.debugLog("Matched Device: " + unicode(dev.name))
				if dev.deviceTypeId == "MQTTrelay":
					if msg.payload == dev.pluginProps["payloadOn"]:
						dev.updateStateOnServer("onOffState", True)
					if msg.payload == dev.pluginProps["payloadOff"]:
						dev.updateStateOnServer("onOffState", False)
				elif dev.deviceTypeId == "MQTTBinarySensor":
					if msg.payload == dev.pluginProps["payloadOn"]:
						dev.updateStateOnServer("onOffState", True)
						dev.updateStateOnServer("display", "on")
						dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOn)
					
					if msg.payload == dev.pluginProps["payloadOff"]:
						dev.updateStateOnServer("onOffState", False)
						dev.updateStateOnServer("display", "off")
						dev.updateStateImageOnServer(indigo.kStateImageSel.SensorOff)
						
				elif dev.deviceTypeId == "MQTTSensor":
					dev.updateStateOnServer("display", msg.payload + dev.pluginProps["unit"] )
					dev.updateStateOnServer("sensorValue", msg.payload )
				else:
					self.debugLog("Dissecting Topic")
					statelesstopic = self.superBridgePatternIn.replace("{DeviceName}", indigo.devices[devID].name)
					beforestate = statelesstopic.split("{State}")[0]
					afterstate = statelesstopic.split("{State}")[1]
					self.debugLog("BeforeState: " + beforestate)

					self.debugLog("AfterState: " + afterstate)
					state = msg.topic.replace(beforestate,"").replace(afterstate,"")
					
					self.debugLog("State Is " + state)
					if state == "switch":
						if msg.payload == True or unicode(msg.payload)== "on" or unicode(msg.payload)== "True":
							self.debugLog("Turning On")
							indigo.device.turnOn(devID)
						elif msg.payload == False or unicode(msg.payload) == "off" or unicode(msg.payload)== "False":
							self.debugLog("Turning Off")
							indigo.device.turnOff(devID)
						else:
							elf.debugLog("Payload did not match any conditions.")
					elif state == "level":
						self.debugLog("setting brightness")
						indigo.dimmer.setBrightness(devID, value=int(msg.payload))
					elif state == "setpointHeatx":
						self.debugLog("setting heat setpoint")
						indigo.thermostat.setHeatSetpoint(devID, value=int(msg.payload))
					else:
						self.debugLog("Unsupported State")
			if agID > 0:
				self.debugLog("Executing Action Group " + unicode(agID))
				indigo.actionGroup.execute(agID)
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)

		

			

				

	def closedDeviceConfigUi(self, valuesDict, userCancelled, typeId, devId):
		self.client.subscribe(valuesDict["stateTopic"])
		self.connectToMQTTBroker()

	def actionControlDevice(self, action, dev):
		try:
			topic = dev.pluginProps["commandTopic"]
			###### TURN ON ######
			if action.deviceAction == indigo.kDeviceAction.TurnOn:
					# Command hardware module (dev) to turn ON here:
					payload = dev.pluginProps["payloadOn"]
					self.publish(topic, payload, int(dev.pluginProps["qos"]), False)

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
					self.publish(topic, payload)
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
		except Exception:
			t, v, tb = sys.exc_info()
			handle_exception(t,v,tb)


		
		