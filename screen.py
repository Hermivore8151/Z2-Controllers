import serial
import sys
import time
import ctypes
import os

VIRTUAL_COM_PORT = 'COM13'          # Python side. org gets COM12
BAUD_RATE = 115200                  # nominal - com0com ignores baud rate
FPS = 60

GRID_W, GRID_H = 60, 32
NUM_LEDS = GRID_W * GRID_H          # 1920 (match in org)
PACKET_SIZE = 1 + 3 * NUM_LEDS + 2  # 0xAA + RGB per LED + 2 checksum

# framebuffer
MAPPING = "HSERP"
MODE   = "H"     # "H" = row-packed, "V" = column/page-packed
MSB    = True
FLIP_X = False
FLIP_Y = False
OX, OY = 0, 0

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

def encode(grid):
    """grid = flat GRID_W*GRID_H array of 0/1 -> 256-byte framebuffer"""
    fb = bytearray(256)
    for y in range(GRID_H):
        for x in range(GRID_W):
            if not grid[y * GRID_W + x]:
                continue
            x = GRID_W-1-x if FLIP_X else x
            y = GRID_H-1-y if FLIP_Y else y
            cx, cy = x+OX, y+OY
            if MODE == "V":
                fb[(cy//8)*64 + cx] |= 1 << (cy % 8)
            else:
                fb[cy*8 + cx//8] |= 1 << ((7-(cx % 8)) if MSB else (cx % 8))
    return bytes(fb)

def frame_to_grid(packet):
    grid = bytearray(NUM_LEDS)
    for i in range(NUM_LEDS):
        on = 1 if max(packet[1+i*3], packet[2+i*3], packet[3+i*3]) > 127 else 0
        if MAPPING == "HSERP":                 # rows snake (your current ORG map)
            y, k = divmod(i, GRID_W)
            x = (GRID_W-1-k) if (y & 1) else k
        elif MAPPING == "VSERP":               # columns snake (your proposed map)
            x, k = divmod(i, GRID_H)
            y = (GRID_H-1-k) if (x & 1) else k
        else:                                  # plain row-major
            y, x = divmod(i, GRID_W)
        grid[y * GRID_W + x] = on
    return grid

def probe_grid(x, y):
    return x == 0 or y == 0 or x == GRID_W-1 or y == GRID_H-1 or x == y

os.system("title Z2 Screen Bridge")

def main():
    x1 = X1API()
    if not x1.connect():
        print("Failed to connect to X1 API. Exiting.")
        return

    if "--probe" in sys.argv:       # one-shot calibration image
        grid = bytearray(probe_grid(x, y) for y in range(GRID_H) for x in range(GRID_W))
        fb = encode(grid)
        res = x1.send(f"OLED Image {fb.hex().upper()}")
        print(f"Probe sent. Response: {res}")
        x1.close()
        return

    print(f"Opening COM Port {VIRTUAL_COM_PORT}...")
    ser = serial.Serial(VIRTUAL_COM_PORT, BAUD_RATE, timeout=0.1)
    print(f"Listening on {VIRTUAL_COM_PORT} for {NUM_LEDS} LEDs...")

    buf = bytearray()
    last_fb = None
    m_time = 1 / FPS

    try:
        while True:
            t_start = time.perf_counter()
            if ser.in_waiting:
                buf += ser.read(ser.in_waiting)

            while buf:
                if buf[0] != 0xAA:                      # resync
                    i = buf.find(b'\xAA')
                    del buf[:i if i != -1 else len(buf)]
                    continue

                if len(buf) < PACKET_SIZE:
                    break

                packet = buf[:PACKET_SIZE]
                del buf[:PACKET_SIZE]

                fb = encode(frame_to_grid(packet))
                if fb != last_fb:                       # only hit API on change
                    res = x1.send(f"OLED Image {fb.hex().upper()}")
                    print("Commited an image")
                    if res and res.startswith("ERR"):
                        print(f"X1 API Error: {res}")
                    last_fb = fb

            t_end = time.perf_counter()
            timetaken = t_end - t_start

            if m_time > timetaken: # time spent doing things is shorter than target time
                time.sleep(m_time - timetaken) # delay to meet target
    except KeyboardInterrupt:
        print("\nShutting down...")
    except Exception as e:
        print(f"Error: {e}")
    finally:
        ser.close()
        x1.close()

# hide_taskbar_icon()
main()