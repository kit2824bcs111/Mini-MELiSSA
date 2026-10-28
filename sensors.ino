// Reads DS18B20 temperature, TDS meter and turbidity sensor on an ESP32.
// Prints one line every 2 s over USB serial:  time_s,temp_C,tds_ppm,turbidity_V
// Install libraries: "OneWire" and "DallasTemperature". Board: ESP32 Dev Module. Serial speed: 115200.
#include <OneWire.h>
#include <DallasTemperature.h>

#define PIN_TEMP 4    // DS18B20 yellow wire (+ 4.7k resistor to 3V3)
#define PIN_TDS  34   // TDS board signal "A"
#define PIN_TURB 35   // turbidity board signal

OneWire oneWire(PIN_TEMP);
DallasTemperature tempSensor(&oneWire);

float readVolts(int pin) {            // average 30 readings, return volts (0 to 3.3)
  long sum = 0;
  for (int i = 0; i < 30; i++) { sum += analogRead(pin); delay(10); }
  return (sum / 30.0) / 4095.0 * 3.3;
}

void setup() {
  Serial.begin(115200);
  tempSensor.begin();
  analogReadResolution(12);
  analogSetAttenuation(ADC_11db);
  Serial.println("time_s,temp_C,tds_ppm,turbidity_V");
}

void loop() {
  tempSensor.requestTemperatures();
  float t = tempSensor.getTempCByIndex(0);
  if (t == DEVICE_DISCONNECTED_C) t = NAN;

  float v = readVolts(PIN_TDS);
  float comp = 1.0 + 0.02 * ((isnan(t) ? 25.0 : t) - 25.0);   // temperature compensation
  float vc = v / comp;
  float tds = (133.42 * vc * vc * vc - 255.86 * vc * vc + 857.39 * vc) * 0.5;

  float turb = readVolts(PIN_TURB);   // clear water = highest voltage, cloudy = lower

  Serial.printf("%lu,%.2f,%.0f,%.3f\n", millis() / 1000, t, tds, turb);
  delay(2000);
}
