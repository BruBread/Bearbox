#!/usr/bin/env python3
"""
BearBox Network — Main Entry Point
- Restores last saved time on boot
- Syncs via NTP if connected
- Shows network setup flow if not connected
"""

import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from network.net_utils import is_connected, sync_time, run_cmd, HOTSPOT_SSID

TIME_FILE = "/home/bearbox/bearbox/.last_time"

def _restore_time():
    """Restore last saved time if no internet — better than epoch."""
    try:
        with open(TIME_FILE) as f:
            last = float(f.read().strip())
        # only restore if saved time is more recent than current system time
        if last > time.time():
            run_cmd(f"sudo date -s '@{int(last)}'")
            print(f">> Time restored from file: {time.ctime(last)}")
        else:
            print(f">> Saved time is older than system time, skipping restore")
    except:
        print(">> No saved time file found")

def run():
    # always try to restore time first
    _restore_time()

    if is_connected():
        sync_time()
        return

    from network.net_warning    import run as show_warning
    from network.net_adapter    import run as wait_adapter
    from network.net_scan       import run as do_scan
    from network.net_list       import run as show_list
    from network.net_hotspot    import run as show_hotspot
    from network.net_connecting import run as do_connect
    from network.net_offline    import run as go_offline

    while True:
        choice = show_warning()

        if choice == "offline":
            go_offline()
            return

        # CONNECT flow
        wait_adapter()
        networks = do_scan()

        if not networks:
            go_offline()
            return

        while True:
            ssid, password = show_list(networks)

            if ssid is None:
                break   # back to warning screen

            if ssid == HOTSPOT_SSID:
                if not show_hotspot():
                    continue

            success = do_connect(ssid, password)
            if success:
                return  # connected → idle

if __name__ == "__main__":
    run()
