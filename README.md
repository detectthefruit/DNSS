switch to another network, change Wi-Fi/DNS/gateway settings, or launch the Python
or restoration of the router's internet service. On ChromeOS, Wi-Fi recovery and
# Share Ethernet Internet with a Chromebook

This guide explains how to use a Linux computer to share its working Ethernet
internet as a Wi-Fi network for your Chromebook. The Linux computer makes the
Wi-Fi network; the Chromebook joins it like any other Wi-Fi network.

The PWA in this project is only an offline status screen. It does not create
the hotspot or provide internet access.

## Before You Start

You need:

- A Linux computer with this project available on it
- An Ethernet cable and an internet connection that works on the Linux computer
- A Wi-Fi adapter in the Linux computer that supports hotspot mode

The Linux computer and Chromebook are separate devices. Run the commands below
on the Linux computer itself, not in a Codespaces terminal.

## Start the Hotspot

1. Plug the Ethernet cable into the Linux computer.
2. Check that the Linux computer can open a website over Ethernet.
3. Open a terminal in the project folder and run:

   ```sh
   sudo python3 linux_hotspot.py start --ssid "Chromebook Internet"
   ```

4. Enter your Linux password if asked. NetworkManager will then ask for a
   password for the new Wi-Fi network. Choose one and remember it.
5. On the Chromebook, open the network menu, turn on Wi-Fi, and select
   **Chromebook Internet**.
6. Enter the Wi-Fi password you chose. Open a website to check that the
   Chromebook has internet access.

## Stop the Hotspot

When you are finished, run this on the Linux computer:

```sh
sudo python3 linux_hotspot.py stop
```

## If It Does Not Work

- If the Linux computer cannot browse the internet over Ethernet, the hotspot
  cannot provide internet to the Chromebook.
- If the script reports that it cannot find a suitable Wi-Fi adapter, the
  adapter may not support hotspot mode. You may need another adapter.
- If you are using Codespaces, run the helper from the project on the physical
  Linux computer instead. Codespaces cannot control that computer's network
  hardware.