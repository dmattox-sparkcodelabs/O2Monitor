#!/usr/bin/env python3
"""Scan for the O2 device to populate BlueZ cache."""
import dbus
import sys
import time

def scan_for_device(mac, timeout=10):
    bus = dbus.SystemBus()
    adapter = dbus.Interface(
        bus.get_object('org.bluez', '/org/bluez/hci1'),
        'org.bluez.Adapter1'
    )
    
    print(f"Scanning for {mac}...")
    adapter.StartDiscovery()
    time.sleep(timeout)
    adapter.StopDiscovery()
    
    # Check if found
    manager = dbus.Interface(
        bus.get_object('org.bluez', '/'),
        'org.freedesktop.DBus.ObjectManager'
    )
    for path, interfaces in manager.GetManagedObjects().items():
        if 'org.bluez.Device1' in interfaces:
            props = interfaces['org.bluez.Device1']
            if props.get('Address', '').upper() == mac.upper():
                print(f"Found: {props.get('Name', 'Unknown')}")
                return True
    
    print("Device not found")
    return False

if __name__ == "__main__":
    mac = sys.argv[1] if len(sys.argv) > 1 else "C8:F1:6B:56:7B:F1"
    sys.exit(0 if scan_for_device(mac) else 1)
