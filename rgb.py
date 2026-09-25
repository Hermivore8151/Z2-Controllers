import serial
import time
import ctypes
import os

VIRTUAL_COM_PORT = 'COM11' # COM port to listen to, other port should be a virtual port (com0com ?)
BAUD_RATE = 115200

NUM_LEDS = 1 # number of LEDs, should be safe to change? probably not because i changed the loop
PACKET_SIZE = 1 + (3 * NUM_LEDS) + 2

os.system("title Z2 RGB Bridge")

def hide_taskbar_icon():
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        # GWL_EXSTYLE = -20, WS_EX_APPWINDOW = 0x00040000, WS_EX_TOOLWINDOW = 0x00000080
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, 0x80)  # Set as a "tool window" (no taskbar icon)
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW = 5 (Keep window visible)

class X1API:
    def __init__(self):
        self.pipe_path = r'\\.\pipe\swiftpoint.x1.v2.command'
        self.pipe = None

    def connect(self):
        if self.pipe is not None:
            return True
        try:
            self.pipe = os.open(self.pipe_path, os.O_RDWR)
            print("Connected to X1 Control Panel pipe.")
            return True
        except FileNotFoundError:
            print(f"Error: Pipe not found at {self.pipe_path}. Is X1 Control Panel running with API enabled?")
            return False
        except Exception as e:
            print(f"Error opening pipe: {e}")
            return False

    def send(self, command):
        if not self.connect():
            return None
        try:
            os.write(self.pipe, (command + "\n").encode("utf-8"))
            response_bytes = os.read(self.pipe, 1024)
            return response_bytes.decode("utf-8").strip()
        except Exception as e:
            print(f"Error sending command: {e}")
            self.close()
            return None

    def close(self):
        if self.pipe is not None:
            try:
                os.close(self.pipe)
            except:
                pass
            self.pipe = None

def main():
    print(f"Opening COM Port {VIRTUAL_COM_PORT}...")
    ser = serial.Serial(VIRTUAL_COM_PORT, BAUD_RATE, timeout=0.1)
    print("Serial port open. Waiting for OpenRGB data...")

    x1 = X1API()

    packet_index = 0
    led_packet = bytearray(PACKET_SIZE)
    
    last_r, last_g, last_b = -1, -1, -1

    try:
        while True:
            if ser.in_waiting > 0:
                byte_in = ser.read(1)
                if not byte_in:
                    continue
                incoming = byte_in[0]

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
                        res = x1.send(f"RGB Fixed #{r:02X}{g:02X}{b:02X}")
                        if res and res.startswith("ERR"):
                            print(f"X1 API Error: {res}")
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
        x1.close()

# hide_taskbar_icon()
main()