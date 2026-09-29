import serial
import sys
import time
import ctypes
import os
import threading

# region Config

# Screen Config
SCREEN_COM_PORT = 'COM13'
SCREEN_BAUD_RATE = 115200
SCREEN_FPS = 60
GRID_W, GRID_H = 64, 32 # 2048
NUM_LEDS_SCREEN = GRID_W * GRID_H
PACKET_SIZE_SCREEN = 1 + 3 * NUM_LEDS_SCREEN + 2

MAPPING = "HSERP"
MODE   = "H"
MSB    = True
FLIP_X = False
FLIP_Y = False
OX, OY = 0, 0

# RGB Config
RGB_COM_PORT = 'COM11'
RGB_BAUD_RATE = 115200
NUM_LEDS_RGB = 1
PACKET_SIZE_RGB = 1 + (3 * NUM_LEDS_RGB) + 2


def hide_taskbar_icon():
    hwnd = ctypes.windll.kernel32.GetConsoleWindow()
    if hwnd:
        # GWL_EXSTYLE = -20, WS_EX_APPWINDOW = 0x00040000, WS_EX_TOOLWINDOW = 0x00000080
        ctypes.windll.user32.SetWindowLongW(hwnd, -20, 0x80)  # Set as a "tool window" (no taskbar icon)
        ctypes.windll.user32.ShowWindow(hwnd, 5)  # SW_SHOW = 5 (Keep window visible)

# region x1api

class X1API:
    def __init__(self):
        self.pipe_path = r'\\.\pipe\swiftpoint.x1.v2.command'
        self.pipe = None
        self.lock = threading.Lock()  # Thread safety for pipe communication

    def connect(self):
        # Assumes this is called from within a lock or single-threaded context
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
        # The lock prevents threads from writing/reading to the pipe at the same time
        with self.lock:
            if not self.connect():
                return None
            try:
                os.write(self.pipe, (command + "\n").encode("utf-8"))
                response_bytes = os.read(self.pipe, 1024)
                return response_bytes.decode("utf-8").strip()
            except Exception as e:
                print(f"Error sending command: {e}")
                if self.pipe is not None:
                    try:
                        os.close(self.pipe)
                    except:
                        pass
                    self.pipe = None
                return None

    def close(self):
        with self.lock:
            if self.pipe is not None:
                try:
                    os.close(self.pipe)
                except:
                    pass
                self.pipe = None

# region Screen

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
    grid = bytearray(NUM_LEDS_SCREEN)
    for i in range(NUM_LEDS_SCREEN):
        on = 1 if max(packet[1+i*3], packet[2+i*3], packet[3+i*3]) > 127 else 0
        if MAPPING == "HSERP":                 # rows snake
            y, k = divmod(i, GRID_W)
            x = (GRID_W-1-k) if (y & 1) else k
        elif MAPPING == "VSERP":               # columns snake
            x, k = divmod(i, GRID_H)
            y = (GRID_H-1-k) if (x & 1) else k
        else:                                  # plain row-major
            y, x = divmod(i, GRID_W)
        grid[y * GRID_W + x] = on
    return grid

def probe_grid(x, y):
    return x == 0 or y == 0 or x == GRID_W-1 or y == GRID_H-1 or x == y

def screen_loop(x1, probe_mode):
    if probe_mode:
        grid = bytearray(probe_grid(x, y) for y in range(GRID_H) for x in range(GRID_W))
        fb = encode(grid)
        res = x1.send(f"OLED Image {fb.hex().upper()}")
        print(f"Probe sent. Response: {res}")
        return

    print(f"[Screen] Opening COM Port {SCREEN_COM_PORT}...")
    try:
        ser = serial.Serial(SCREEN_COM_PORT, SCREEN_BAUD_RATE, timeout=0.1)
    except Exception as e:
        print(f"[Screen] Failed to open COM port: {e}")
        return
        
    print(f"[Screen] Listening on {SCREEN_COM_PORT} for {NUM_LEDS_SCREEN} LEDs...")

    buf = bytearray()
    last_fb = None
    m_time = 1 / SCREEN_FPS

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

                if len(buf) < PACKET_SIZE_SCREEN:
                    break

                packet = buf[:PACKET_SIZE_SCREEN]
                del buf[:PACKET_SIZE_SCREEN]

                fb = encode(frame_to_grid(packet))
                if fb != last_fb:                       # only hit API on change
                    res = x1.send(f"OLED Image {fb.hex().upper()}")
                    print("[Screen] Commited an image")
                    if res and res.startswith("ERR"):
                        print(f"[Screen] X1 API Error: {res}")
                    last_fb = fb

            t_end = time.perf_counter()
            timetaken = t_end - t_start

            if m_time > timetaken: # time spent doing things is shorter than target time
                time.sleep(m_time - timetaken) # delay to meet target
    except Exception as e:
        print(f"[Screen] Error: {e}")
    finally:
        ser.close()

# region RGB

def rgb_loop(x1):
    print(f"[RGB] Opening COM Port {RGB_COM_PORT}...")
    try:
        ser = serial.Serial(RGB_COM_PORT, RGB_BAUD_RATE, timeout=0.1)
    except Exception as e:
        print(f"[RGB] Failed to open COM port: {e}")
        return
        
    print("[RGB] Serial port open. Waiting for OpenRGB data...")

    packet_index = 0
    led_packet = bytearray(PACKET_SIZE_RGB)
    
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

                if packet_index == PACKET_SIZE_RGB:
                    r = led_packet[1]
                    g = led_packet[2]
                    b = led_packet[3]

                    if r != last_r or g != last_g or b != last_b:
                        print(f"[RGB] Color update: R={r}, G={g}, B={b}")
                        res = x1.send(f"RGB Fixed #{r:02X}{g:02X}{b:02X}")
                        if res and res.startswith("ERR"):
                            print(f"[RGB] X1 API Error: {res}")
                        last_r, last_g, last_b = r, g, b
                        
                    packet_index = 0
            else:
                time.sleep(0.001)
                
    except Exception as e:
        print(f"[RGB] Error: {e}")
    finally:
        ser.close()

# ==========================================
# Main Execution
# ==========================================

def main():
    os.system("title Z2 Unified Bridge")
    
    x1 = X1API()
    if not x1.connect():
        print("Failed to connect to X1 API. Exiting.")
        return

    if "--probe" in sys.argv:       # one-shot calibration image
        screen_loop(x1, probe_mode=True)
        x1.close()
        return

    # Initialize independent loops in background daemon threads
    screen_thread = threading.Thread(target=screen_loop, args=(x1, False), daemon=True)
    rgb_thread = threading.Thread(target=rgb_loop, args=(x1,), daemon=True)

    screen_thread.start()
    rgb_thread.start()

    # Keep main thread alive until interrupted
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        x1.close()

if __name__ == "__main__":
    hide_taskbar_icon()
    main()