import serial
import hid
import time
import sys

VIRTUAL_COM_PORT = 'COM11' # COM port to listen to, other port should be a virtual port (com0com ?)
BAUD_RATE = 115200

NUM_LEDS = 1 # number of LEDs, should be safe to change? probably not because i changed the loop

# Swiftpoint Z2 USB IDs
VID = 0x214E
PID = 0x001E

# Packet size: 1 (header) + 3*NUM_LEDS (RGB) + 2 (checksum)
PACKET_SIZE = 1 + (3 * NUM_LEDS) + 2

def pad_report(prefix):
    report = bytearray(64)
    for i in range(min(len(prefix), 64)):
        report[i] = prefix[i]
    return report

def send_hid_report(device, report):
    device.write(report)

def set_mouse_color(device, r, g, b):
    begin  = pad_report([0x29, 0x01, 0x5E, 0x01, 0x00, 0x41, 0x01, 0x00])
    commit = pad_report([0x29, 0x01, 0x5E, 0x01, 0x00, 0x41, 0x00, 0x00])
    rgb    = pad_report([0x29, 0x01, 0x9E, 0x02, 0x00, 0x47, 0x01, 0xFF, 0xF4, 0x01, r, g, b])
    
    send_hid_report(device, begin)
    send_hid_report(device, rgb)
    send_hid_report(device, commit)

def main():
    print(f"Connecting Z2 ({hex(VID)}:{hex(PID)})...")
    mouse = hid.device()
    mouse.open(VID, PID)
    print("Mouse connected.")

    print(f"Opening COM Port {VIRTUAL_COM_PORT}...")
    ser = serial.Serial(VIRTUAL_COM_PORT, BAUD_RATE, timeout=0.1)
    print("Serial port open. Waiting for OpenRGB data...")

    packet_index = 0
    led_packet = bytearray(PACKET_SIZE)
    
    last_r, last_g, last_b = -1, -1, -1

    try:
        while True:
            if ser.in_waiting > 0:
                incoming = ser.read(1)[0]

                if packet_index == 0 and incoming != 0xAA:
                    continue
                
                led_packet[packet_index] = incoming
                packet_index += 1

                if packet_index == PACKET_SIZE:
                    r = led_packet[1]
                    g = led_packet[2]
                    b = led_packet[3]

                    if r != last_r or g != last_g or b != last_b:
                        print(f"Color update: R={r}, G={g}, B={b}")
                        set_mouse_color(mouse, r, g, b)
                        last_r, last_g, last_b = r, g, b
                        
                    packet_index = 0
            else:
                time.sleep(0.001) # should be fast enough?
                
    except KeyboardInterrupt:
        print("\nShutting down bridge...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ser.close()
        mouse.close()

main()