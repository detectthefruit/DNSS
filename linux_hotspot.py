"""Share an existing Linux internet connection over a Wi-Fi access point."""

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys


PROFILE_NAME = "DNSS Internet Hotspot"


def run(command):
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as error:
        raise RuntimeError("Required system command not found: " + command[0]) from error
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "Command failed: " + " ".join(command[:3]))
    return result.stdout.strip()


def check_environment():
    if platform.system() != "Linux":
        raise RuntimeError("Run this helper on the Linux machine that will host the hotspot.")
    if not hasattr(os, "geteuid") or os.geteuid() != 0:
        raise PermissionError("Run with sudo so NetworkManager can configure the hotspot.")
    if not shutil.which("nmcli"):
        raise RuntimeError("NetworkManager's system nmcli command is required.")
    if not shutil.which("ip"):
        raise RuntimeError("The ip command is required to detect the internet uplink.")
    if run(["nmcli", "-t", "-f", "RUNNING", "general"]).lower() != "running":
        raise RuntimeError("NetworkManager is not running.")


def default_uplink():
    routes = run(["ip", "route", "show", "default"])
    for route in routes.splitlines():
        match = re.search(r"\bdev\s+(\S+)", route)
        if match:
            return match.group(1)
    raise RuntimeError("No default internet route found. Connect Ethernet or another uplink first.")


def wifi_devices():
    devices = run(["nmcli", "-t", "-f", "DEVICE,TYPE", "device", "status"])
    return [line.split(":", 1)[0] for line in devices.splitlines() if ":wifi" in line]


def supports_access_point(interface):
    capability = run(["nmcli", "-g", "WIFI-PROPERTIES.AP", "device", "show", interface])
    return capability.strip().lower() == "yes"


def choose_wifi_device(requested, uplink):
    devices = [device for device in wifi_devices() if device != uplink]
    if requested:
        if requested not in devices:
            raise RuntimeError(requested + " is not an available Wi-Fi adapter separate from the uplink.")
        candidates = [requested]
    else:
        candidates = [device for device in devices if supports_access_point(device)]
        if len(candidates) > 1:
            raise RuntimeError("Multiple AP-capable Wi-Fi adapters found; specify --wifi-interface.")
        if not candidates:
            raise RuntimeError("No AP-capable Wi-Fi adapter found separate from the internet uplink.")
    if not supports_access_point(candidates[0]):
        raise RuntimeError(candidates[0] + " does not report Wi-Fi access-point support.")
    return candidates[0]


def connection_names():
    output = run(["nmcli", "-t", "-f", "NAME", "connection", "show"])
    return output.splitlines()


def configure_profile(interface, ssid):
    if PROFILE_NAME in connection_names():
        connection_type = run([
            "nmcli", "-g", "connection.type", "connection", "show", "id", PROFILE_NAME,
        ])
        if connection_type != "802-11-wireless":
            raise RuntimeError("A non-Wi-Fi NetworkManager profile already uses " + PROFILE_NAME)
    else:
        run([
            "nmcli", "connection", "add", "type", "wifi", "ifname", interface,
            "con-name", PROFILE_NAME, "ssid", ssid,
        ])
    run([
        "nmcli", "connection", "modify", PROFILE_NAME,
        "connection.interface-name", interface,
        "connection.autoconnect", "no",
        "802-11-wireless.ssid", ssid,
        "802-11-wireless.mode", "ap",
        "802-11-wireless.band", "bg",
        "802-11-wireless-security.key-mgmt", "wpa-psk",
        "ipv4.method", "shared",
        "ipv6.method", "ignore",
    ])


def start_hotspot(args):
    if not args.ssid or len(args.ssid.encode("utf-8")) > 32 or "\n" in args.ssid:
        raise ValueError("SSID must contain 1 to 32 UTF-8 bytes and no newline.")
    detected_uplink = default_uplink()
    uplink = args.upstream or detected_uplink
    if uplink != detected_uplink:
        raise RuntimeError("--upstream must be the current default-route interface (" + detected_uplink + ").")
    wifi_interface = choose_wifi_device(args.wifi_interface, uplink)

    configure_profile(wifi_interface, args.ssid)
    print("NetworkManager will prompt for the hotspot password.")
    result = subprocess.run([
        "nmcli", "--ask", "connection", "up", "id", PROFILE_NAME,
        "ifname", wifi_interface,
    ], check=False)
    if result.returncode:
        raise RuntimeError("Could not start the hotspot; check the password and adapter support.")
    print("Hotspot is running: " + args.ssid)
    print("Wi-Fi adapter: " + wifi_interface)
    print("Internet uplink: " + uplink)
    print("Connect the Chromebook to this Wi-Fi network.")


def stop_hotspot():
    if PROFILE_NAME not in connection_names():
        print("No DNSS hotspot profile exists.")
        return
    active = run(["nmcli", "-t", "-f", "NAME", "connection", "show", "--active"])
    if PROFILE_NAME not in active.splitlines():
        print("Hotspot is already stopped.")
        return
    run(["nmcli", "connection", "down", "id", PROFILE_NAME])
    print("Hotspot stopped. Its NetworkManager profile was kept for next time.")


def show_status():
    uplink = default_uplink()
    active = run(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"])
    if any(line.startswith(PROFILE_NAME + ":") for line in active.splitlines()):
        print("Hotspot: running")
    else:
        print("Hotspot: stopped")
    print("Default internet uplink: " + uplink)
    access_points = [
        device for device in wifi_devices()
        if device != uplink and supports_access_point(device)
    ]
    print("AP-capable Wi-Fi adapters: " + (", ".join(access_points) or "none detected"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    start_parser = actions.add_parser("start", help="Share the current default internet route over Wi-Fi")
    start_parser.add_argument("--ssid", required=True, help="Wi-Fi network name for the Chromebook")
    start_parser.add_argument("--wifi-interface", help="AP-capable Wi-Fi adapter; detected if unambiguous")
    start_parser.add_argument("--upstream", help="Internet interface; defaults to the current default route")
    actions.add_parser("stop", help="Stop the DNSS hotspot without deleting its profile")
    actions.add_parser("status", help="Show uplink and hotspot readiness")
    args = parser.parse_args()

    try:
        check_environment()
        if args.action == "start":
            start_hotspot(args)
        elif args.action == "stop":
            stop_hotspot()
        else:
            show_status()
    except (OSError, PermissionError, RuntimeError, ValueError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())