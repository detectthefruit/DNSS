"""Small cross-platform DNS and default-gateway utility for resilience tests."""

import argparse
import ipaddress
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time


PUBLIC_DNS = ("1.1.1.1", "8.8.8.8")
PING_HOST = "8.8.8.8"
RESOLV_CONF = "/etc/resolv.conf"
RESOLV_CONF_BACKUP = "/var/lib/network_resilience/resolv.conf.backup"


def run(command):
    """Run a command without a shell and surface useful failures."""
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError as error:
        raise RuntimeError("Required command not found: " + command[0]) from error
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise RuntimeError(detail or "Command failed: " + command[0])
    return result.stdout.strip()


def os_family():
    name = platform.system().lower()
    if name == "windows":
        return "windows"
    if name == "darwin":
        return "macos"
    if name == "linux":
        return "linux"
    raise RuntimeError("Unsupported operating system: " + name)


def require_admin():
    if os_family() == "windows":
        try:
            import ctypes
            allowed = ctypes.windll.shell32.IsUserAnAdmin()
        except (AttributeError, OSError):
            allowed = False
    else:
        allowed = hasattr(os, "geteuid") and os.geteuid() == 0
    if not allowed:
        raise PermissionError("Run this operation from an elevated terminal (Administrator or sudo).")


def powershell(script):
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", script]


def ps_quote(value):
    return "'" + value.replace("'", "''") + "'"


def networkmanager_available():
    if not shutil.which("nmcli"):
        return False
    try:
        return run(["nmcli", "-t", "-f", "RUNNING", "general"]).lower() == "running"
    except RuntimeError:
        return False


def write_resolver_file(path, contents):
    mode = os.stat(path).st_mode & 0o777
    descriptor, temporary_path = tempfile.mkstemp(dir=os.path.dirname(path), text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as resolver_file:
            resolver_file.write(contents)
        os.chmod(temporary_path, mode)
        os.replace(temporary_path, path)
    finally:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)


def set_resolv_conf_dns(servers):
    if os.path.islink(RESOLV_CONF):
        raise RuntimeError("Cannot safely edit symlinked /etc/resolv.conf; use a system DNS manager.")
    with open(RESOLV_CONF, encoding="utf-8") as resolver_file:
        original = resolver_file.read()
    os.makedirs(os.path.dirname(RESOLV_CONF_BACKUP), exist_ok=True)
    if not os.path.exists(RESOLV_CONF_BACKUP):
        with open(RESOLV_CONF_BACKUP, "w", encoding="utf-8") as backup_file:
            backup_file.write(original)
    preserved = [line for line in original.splitlines() if line.lstrip().startswith(("search ", "options "))]
    updated = "".join("nameserver " + server + "\n" for server in servers)
    updated += "".join(line + "\n" for line in preserved)
    write_resolver_file(RESOLV_CONF, updated)


def restore_resolv_conf_dns():
    if not os.path.exists(RESOLV_CONF_BACKUP):
        raise RuntimeError("No saved resolver configuration exists; apply secure DNS first to enable rollback.")
    if os.path.islink(RESOLV_CONF):
        raise RuntimeError("Cannot safely restore symlinked /etc/resolv.conf; use a system DNS manager.")
    with open(RESOLV_CONF_BACKUP, encoding="utf-8") as backup_file:
        original = backup_file.read()
    write_resolver_file(RESOLV_CONF, original)
    os.remove(RESOLV_CONF_BACKUP)


def default_interface():
    family = os_family()
    if family == "linux":
        output = run(["ip", "route", "show", "default"])
        match = re.search(r"\bdev\s+(\S+)", output)
        if match:
            return match.group(1)
    elif family == "macos":
        output = run(["route", "-n", "get", "default"])
        match = re.search(r"\binterface:\s*(\S+)", output)
        if match:
            return match.group(1)
    else:
        output = run(powershell("(Get-NetRoute -DestinationPrefix '0.0.0.0/0' | Sort-Object RouteMetric | Select-Object -First 1).InterfaceAlias"))
        if output:
            return output
    raise RuntimeError("Could not detect the active default-route interface; pass --interface.")


def set_dns(interface, servers=PUBLIC_DNS):
    require_admin()
    family = os_family()
    if family == "windows":
        run(["netsh", "interface", "ipv4", "set", "dnsservers", 'name="' + interface + '"', "static", servers[0], "primary"])
        for server in servers[1:]:
            run(["netsh", "interface", "ipv4", "add", "dnsservers", 'name="' + interface + '"', server, "index=2"])
    elif family == "macos":
        run(["networksetup", "-setdnsservers", interface, *servers])
    else:
        if not networkmanager_available():
            set_resolv_conf_dns(servers)
            print("Warning: /etc/resolv.conf may be regenerated by the container's resolver service.")
        else:
            connection = run(["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", interface])
            if not connection or connection == "--":
                raise RuntimeError("No active NetworkManager connection for " + interface)
            run(["nmcli", "connection", "modify", connection, "ipv4.dns", ",".join(servers), "ipv4.ignore-auto-dns", "yes"])
            run(["nmcli", "connection", "up", connection])


def restore_dns(interface):
    """Return DNS selection to DHCP/automatic configuration."""
    require_admin()
    family = os_family()
    if family == "windows":
        run(["netsh", "interface", "ipv4", "set", "dnsservers", 'name="' + interface + '"', "source=dhcp"])
    elif family == "macos":
        run(["networksetup", "-setdnsservers", interface, "Empty"])
    else:
        if not networkmanager_available():
            restore_resolv_conf_dns()
        else:
            connection = run(["nmcli", "-g", "GENERAL.CONNECTION", "device", "show", interface])
            if not connection or connection == "--":
                raise RuntimeError("No active NetworkManager connection for " + interface)
            run(["nmcli", "connection", "modify", connection, "ipv4.dns", "", "ipv4.ignore-auto-dns", "no"])
            run(["nmcli", "connection", "up", connection])


def active_dns(interface):
    family = os_family()
    if family == "windows":
        script = "(Get-DnsClientServerAddress -InterfaceAlias " + ps_quote(interface) + " -AddressFamily IPv4).ServerAddresses -join ','"
        return run(powershell(script)) or "(none reported)"
    if family == "macos":
        return run(["networksetup", "-getdnsservers", interface]) or "(automatic or none reported)"
    if networkmanager_available():
        output = run(["nmcli", "-g", "IP4.DNS", "device", "show", interface])
        return output.replace("\n", ", ") or "(none reported)"
    try:
        with open("/etc/resolv.conf", encoding="utf-8") as config:
            nameservers = re.findall(r"^nameserver\s+(\S+)", config.read(), re.MULTILINE)
        return ", ".join(nameservers) or "(none reported)"
    except OSError as error:
        return "Unavailable: " + str(error)


def current_gateway(interface):
    family = os_family()
    if family == "linux":
        output = run(["ip", "route", "show", "default", "dev", interface])
        match = re.search(r"\bvia\s+(\S+)", output)
        return match.group(1) if match else "(none reported)"
    if family == "macos":
        output = run(["route", "-n", "get", "default"])
        match = re.search(r"\bgateway:\s*(\S+)", output)
        return match.group(1) if match else "(none reported)"
    script = "(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -InterfaceAlias " + ps_quote(interface) + " | Sort-Object RouteMetric | Select-Object -First 1).NextHop"
    return run(powershell(script)) or "(none reported)"


def set_gateway(interface, gateway):
    """Replace the default gateway and print the value needed to restore it."""
    gateway = str(ipaddress.ip_address(gateway))
    require_admin()
    previous = current_gateway(interface)
    if os_family() == "linux":
        run(["ip", "route", "replace", "default", "via", gateway, "dev", interface])
    elif os_family() == "macos":
        run(["route", "change", "default", gateway])
    else:
        run(["route", "change", "0.0.0.0", "mask", "0.0.0.0", gateway])
    print("Previous gateway: " + previous)
    print("To restore it, run: python network_resilience.py gateway --interface " + interface + " --address " + previous)


def ping_once(host):
    family = os_family()
    if family == "windows":
        command = ["ping", "-n", "1", "-w", "2000", host]
    else:
        command = ["ping", "-c", "1", "-W", "2", host]
    try:
        return subprocess.run(command, capture_output=True, text=True, check=False).returncode == 0
    except FileNotFoundError:
        try:
            with socket.create_connection((host, 53), timeout=2):
                return True
        except OSError:
            return False


def show_status(interface):
    try:
        resolved = socket.gethostbyname("www.google.com")
    except OSError:
        resolved = "failed"
    try:
        connectivity = "online" if ping_once(PING_HOST) else "offline"
        if not shutil.which("ping"):
            connectivity += " (TCP port 53 fallback; ping unavailable)"
    except RuntimeError as error:
        connectivity = "unavailable (" + str(error) + ")"
    print("Platform: " + platform.system())
    print("Interface/service: " + interface)
    print("DNS servers: " + active_dns(interface))
    print("Default gateway: " + current_gateway(interface))
    print("DNS lookup (www.google.com): " + resolved)
    print("Connectivity (" + PING_HOST + "): " + connectivity)


def watch(interface, interval, failures_before_switch, switch_on_failure):
    failures = 0
    switched = False
    method = "ping" if shutil.which("ping") else "TCP port 53 fallback"
    print("Monitoring " + PING_HOST + " via " + method + "; press Ctrl+C to stop.")
    try:
        while True:
            connected = ping_once(PING_HOST)
            print(time.strftime("%Y-%m-%d %H:%M:%S"), "online" if connected else "timeout", flush=True)
            failures = 0 if connected else failures + 1
            if switch_on_failure and not connected and failures >= failures_before_switch and not switched:
                print("Connectivity threshold reached; applying secure DNS.")
                set_dns(interface)
                switched = True
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", help="Network interface; on macOS use its network service name")
    subparsers = parser.add_subparsers(dest="action")
    subparsers.add_parser("status", help="Show DNS, gateway, name lookup, and connectivity")
    subparsers.add_parser("secure-dns", help="Set Cloudflare and Google DNS servers")
    subparsers.add_parser("dhcp-dns", help="Restore automatic DNS configuration")
    gateway_parser = subparsers.add_parser("gateway", help="Set the default gateway (save the printed previous value)")
    gateway_parser.add_argument("--address", required=True, help="IPv4 or IPv6 gateway address")
    start_parser = subparsers.add_parser("start", help="Show status and start monitoring")
    start_parser.add_argument("--interval", type=float, default=10.0)
    start_parser.add_argument("--failures", type=int, default=3)
    start_parser.add_argument("--switch-on-failure", action="store_true", help="Apply secure DNS after consecutive failures")
    watch_parser = subparsers.add_parser("watch", help="Periodically ping an external IP")
    watch_parser.add_argument("--interval", type=float, default=10.0)
    watch_parser.add_argument("--failures", type=int, default=3)
    watch_parser.add_argument("--switch-on-failure", action="store_true", help="Apply secure DNS after consecutive failures")
    args = parser.parse_args()
    if args.action is None:
        args.action = "start"
        args.interval = 10.0
        args.failures = 3
        args.switch_on_failure = False

    try:
        interface = args.interface or default_interface()
        if args.action == "status":
            show_status(interface)
        elif args.action == "secure-dns":
            set_dns(interface)
            print("DNS set to: " + ", ".join(PUBLIC_DNS))
        elif args.action == "dhcp-dns":
            restore_dns(interface)
            print("DNS restored to automatic/DHCP configuration.")
        elif args.action == "gateway":
            set_gateway(interface, args.address)
        elif args.action in ("start", "watch"):
            if args.interval <= 0 or args.failures <= 0:
                parser.error("--interval and --failures must be positive")
            if args.action == "start":
                show_status(interface)
            watch(interface, args.interval, args.failures, args.switch_on_failure)
    except (OSError, PermissionError, RuntimeError, ValueError) as error:
        print("Error: " + str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())