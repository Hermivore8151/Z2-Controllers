import serial
import hid
import sys
import time

VIRTUAL_COM_PORT = 'COM13'          # Python side. org gets COM12
BAUD_RATE = 115200                  # nominal - com0com ignores baud rate
FPS = 60

GRID_W, GRID_H = 60, 32
NUM_LEDS = GRID_W * GRID_H          # 1920 (match in org)
PACKET_SIZE = 1 + 3 * NUM_LEDS + 2  # 0xAA + RGB per LED + 2 checksum

VID, PID = 0x214E, 0x001E

# framebuffer
MAPPING = "HSERP"
MODE   = "H"     # "H" = row-packed, "V" = column/page-packed
MSB    = True
FLIP_X = False
FLIP_Y = False
OX, OY = 0, 0

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

# HID transaction
OLED_BEGIN = bytes([0x29,0x01,0x63,0x01,0x00,0x41,0x01,0x00]).ljust(64, b"\0")
OLED_END   = bytes([0x29,0x01,0x63,0x01,0x00,0x41,0x00,0x00]).ljust(64, b"\0")
CHUNK_FLAGS = [0xFA, 0xBA, 0xBA, 0xBA, 0x18]
CHUNK_OFFS  = [0, 58, 116, 174, 232]
CHUNK_LENS  = [58, 58, 58, 58, 24]

def send_oled(mouse, fb):
    mouse.write(OLED_BEGIN)
    for i in range(5):
        rep = bytearray(64)
        rep[0:6] = bytes([0x29, 0x01, 0xA3, 0x05, i, CHUNK_FLAGS[i]])
        rep[6:6+CHUNK_LENS[i]] = fb[CHUNK_OFFS[i]:CHUNK_OFFS[i]+CHUNK_LENS[i]]
        mouse.write(bytes(rep))
    mouse.write(OLED_END)

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

def main():
    mouse = hid.device()
    mouse.open(VID, PID)
    print("Mouse connected.")

    if "--probe" in sys.argv:       # one-shot calibration image
        send_oled(mouse, encode(bytearray(probe_grid(x, y) for y in range(GRID_H) for x in range(GRID_W))))
        print("Probe sent.")
        return

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
                if fb != last_fb:                       # only hit HID on change
                    send_oled(mouse, fb)
                    last_fb = fb

            t_end = time.perf_counter()
            timetaken = t_end - t_start

            if m_time > timetaken: # time spent doing things is shorter than target time
                time.sleep(m_time - timetaken) # delay to meet target
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        ser.close()
        mouse.close()

main()