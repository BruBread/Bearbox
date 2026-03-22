#!/usr/bin/env python3
"""
BearBox Network — Main Entry Point
Call run() after boot animation, before idle_main.

Flow:
  connected     → sync time → done
  not connected → warning
    CONNECT     → adapter → scan → list → connect
                  hotspot? → popup → yes/no
    GO OFFLINE  → animated warning → done
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../.."))
from network.net_utils import is_connected, sync_time, HOTSPOT_SSID

def run():
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

    while True:  # ← wrap everything in a loop so back returns here
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
            ssid = show_list(networks)

            if ssid is None:
                break  # ← break inner loop → back to warning screen

            if ssid == HOTSPOT_SSID:
                if not show_hotspot():
                    continue

            success = do_connect(ssid)
            if success:
                return

if __name__ == "__main__":
    run()
