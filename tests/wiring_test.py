"""Static circuit checks, separate from MQTT/GPIO tests (not optical feedback)."""
import json
import re
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
# Canonical pin names: https://github.com/wokwi/wokwi-boards/blob/main/boards/esp32-devkit-v1/board.json
ESP32_PINS=set('EN VN VP D34 D35 D32 D33 D25 D26 D27 D14 D12 D13 GND.2 VIN 3V3 GND.1 D15 D2 D4 RX2 TX2 D5 D18 D19 D21 RX0 TX0 D22 D23'.split())
PIN_NAMES={
    'wokwi-esp32-devkit-v1':ESP32_PINS,
    'wokwi-dht22':{'VCC','SDA','NC','GND'},
    'wokwi-pushbutton':{'1.l','1.r','2.l','2.r'},
    'wokwi-led':{'A','C'},
    'wokwi-resistor':{'1','2'},
}

class WiringTest(unittest.TestCase):
    def setUp(self):
        self.diagram=json.loads((ROOT/'firmware/diagram.json').read_text(encoding='utf-8'))
        self.parts={part['id']:part for part in self.diagram['parts']}
        self.graph={}
        for source,target,*_ in self.diagram['connections']:
            self.graph.setdefault(source,set()).add(target)
            self.graph.setdefault(target,set()).add(source)
        # Both grounds are internally connected on the ESP32 board.
        self.graph.setdefault('esp32:GND.1',set()).add('esp32:GND.2')
        self.graph.setdefault('esp32:GND.2',set()).add('esp32:GND.1')

    def connected(self,source,target):
        pending=[source];seen=set()
        while pending:
            node=pending.pop()
            if node==target:return True
            if node not in seen:seen.add(node);pending.extend(self.graph.get(node,()))
        return False

    def test_part_ids_and_all_endpoints(self):
        self.assertEqual(len(self.parts),len(self.diagram['parts']))
        self.assertFalse(any('relay' in part['type'] for part in self.parts.values()))
        self.assertFalse(any('pir' in part['type'] for part in self.parts.values()))
        for connection in self.diagram['connections']:
            for endpoint in connection[:2]:
                part,pin=endpoint.split(':',1)
                if part=='$serialMonitor':self.assertIn(pin,{'RX','TX'});continue
                self.assertIn(part,self.parts)
                self.assertIn(pin,PIN_NAMES[self.parts[part]['type']],endpoint+' is not a valid Wokwi pin')

    def test_five_complete_led_circuits_and_no_output_shorts(self):
        drivers=['RX2','TX2','D18','D19','D23']
        for i,driver in enumerate(drivers):
            led='light'+str(i+1) if i<4 else 'fanIndicator'
            resistor='r'+str(i+1) if i<4 else 'rFan'
            output='esp32:'+driver
            self.assertEqual(self.parts[resistor]['attrs']['value'],'220')
            self.assertTrue(self.connected(output,resistor+':1'))
            self.assertTrue(self.connected(resistor+':2',led+':A'))
            self.assertTrue(self.connected(led+':C','esp32:GND.1'))
            self.assertFalse(self.connected(output,'esp32:GND.1'))
            self.assertFalse(self.connected(output,led+':A'),'LED must have a series resistor')
            for other in drivers[i+1:]:self.assertFalse(self.connected(output,'esp32:'+other))

    def test_sensors_and_firmware_match(self):
        config=(ROOT/'firmware/config.h').read_text(encoding='utf-8')
        pins=[int(pin) for pin in re.search(r'GPIO_LIGHTS\[4\]\s*=\s*\{([^}]+)\}',config)[1].split(',')]
        self.assertEqual(pins,[16,17,18,19])
        self.assertRegex(config,r'GPIO_FAN\s*=\s*23\s*;')
        self.assertRegex(config,r'GPIO_IR_A\s*=\s*13\s*;')
        self.assertRegex(config,r'GPIO_IR_B\s*=\s*27\s*;')
        for source,target in [('dht:VCC','esp32:3V3'),('dht:SDA','esp32:D15'),('dht:GND','esp32:GND.1'),
                              ('gateA:1.r','esp32:D13'),('gateA:2.l','esp32:GND.2'),
                              ('gateB:1.r','esp32:D27'),('gateB:2.l','esp32:GND.2')]:
            self.assertTrue(self.connected(source,target))
        for gate in ['gateA','gateB']:
            self.assertFalse(self.connected(gate+':1.r','esp32:GND.1'),'Unpressed gate must not be shorted to GND')
        self.assertFalse(self.connected('gateA:1.r','gateB:1.r'))
        self.assertNotIn('dht:NC',self.graph,'DHT22 NC is intentionally unconnected')

if __name__=='__main__':unittest.main(verbosity=2)
