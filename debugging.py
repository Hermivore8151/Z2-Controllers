import os

def sc(command):
    pipe_path = r'\\.\pipe\swiftpoint.x1.v2.command'
    
    # Open the pipe for reading and writing
    pipe = os.open(pipe_path, os.O_RDWR)
    
    # Send the command
    os.write(pipe, (command + "\n").encode("utf-8"))
    
    # Read the response (1024 bytes)
    response_bytes = os.read(pipe, 1024)
    response = response_bytes.decode("utf-8").strip()
    print(response)
    
    os.close(pipe)

sc("RGB Fixed #FF0000")