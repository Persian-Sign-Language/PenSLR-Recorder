from serial.tools.list_ports import comports

def get_ports():
    return [port.device for port in comports(include_links=False)]