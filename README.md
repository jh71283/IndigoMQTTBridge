# IndigoMQTTBridge

This Plugin allows Indigo to connect to an MQTT broker to share messages with other systems such as SmartThings, HASS.io etc.

# Using The Payload Extraction
If you have a sensor pyload that is JSON data, you may want to get a specific value by key, or even by nested keys. For this example our data from our device will be:
```
{"AM2301": {"Temperature": 78.8}}
```
and we want to extract the `78.8` and use it as the sensor value. We can use the payload extraction feature in the MQTTSensor and MQTTWeatherSensor devices to get this specific value. The format to get this would be
```
AM2301->Temperature
```
The `->` is used to enter into a key and get the value. This also works for multiple layers of nesting.

# MQTTSensor Data Flow
1) The value is taken from the payload
2) If populated, the value will be extracted via the Payload Extraction field
3) If populated, the value will be overwritten by the formula field (using `x` as the existing value)
4) If populated, the offset will be added to the value (positive offsets will be added, negative offsets will be subtracted)
5) If populated, the final vakue will be rounded to the number of decimal places supplied in the precision field.

# MQTTSensor Formulas
The formula field is helpful in cases where you want to convert any data you collect into a more useful unit. An example of this would be if you sensor outputs temperature in celsius and you would prefer to have Indigo see it as fahrenheit.

As described in the Data Flow, the value `x` can be used to represent the value taken from the payload. In this case of converting from celsius to fahrenheit, we would populate the formula with: 
```
(9/5)*x+32
```
Use `+` for adding, `-` for subtracting, `*` for multiplication, `/` or division, and `^` for powers. You need to keep in mind `PEMDAS` when writing formulas. Operations will occur in the following order: 
1) Parenthasis
2) Exponents
3) Multiplication
4) Division
5) Addition
6) Subtraction

In the formula above, `9/5` will be evaulated first since it is in parenthasis. The equation will become `1.8*x+32`. Then Multiplication will occur leading to `x` being multiplied by `1.8`. Finally, `32` will be added.

The result of the formula will be stored and passed on to the next step in the process, the offset step.

# MQTTSensor Offsets
If you have a sensor that seems to report value too low or high, you can use the offset to correct inaccuracies or errors from the sensor. This is useful when a temperature sensor is not properly calibrated.

#### Example 1
Lets say we have a temperature sensor that is reporting a temperature of 66°F and it is actually 67.2°F. In the offset field, you would put an offset of `1.2`.

#### Example 2
Lets say we have a temperature sensor that is reporting a temperature of 68°F and it is actually 66.2°F. In the offset field, you would put an offset of `-1.8`.

# MQTTSensor Precision
This value simply sets the number of decimal places you want to report. By default, 1 decimal place will always be present.
