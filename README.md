# Wi-Fi Hotspot

This package lets a Linux computer share its working Ethernet internet as a
Wi-Fi network for a Chromebook. It cannot provide internet if the Ethernet
connection itself is offline.

## Install

After `wifi-hotspot` has been published to PyPI, install it in a virtual
environment:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install wifi-hotspot
```

## Connect the Chromebook

You need a Linux computer with internet working over Ethernet and a Wi-Fi
adapter that supports hotspot mode. Run these steps on the Linux computer
itself, not in a Codespaces terminal.

1. Plug the Ethernet cable into the Linux computer and check that it can open
   a website.
2. Start the hotspot:

   ```sh
   sudo "$(command -v wifi-hotspot)" start --ssid "Chromebook Internet"
   ```

3. Enter your Linux password if asked. NetworkManager will ask you to choose a
   password for the new Wi-Fi network. Remember it.
4. On the Chromebook, open the network menu, turn on Wi-Fi, and select
   **Chromebook Internet**.
5. Enter the Wi-Fi password and open a website to check the connection.

Stop the hotspot from the Linux computer when finished:

```sh
sudo "$(command -v wifi-hotspot)" stop
```

If the helper cannot find a suitable Wi-Fi adapter, the adapter may not support
hotspot mode. If Ethernet does not provide internet to the Linux computer, the
hotspot cannot provide internet to the Chromebook.

The package also provides `network-resilience status` for network diagnostics.
The PWA files in this repository are a separate offline status screen; they
are not part of the PyPI package.

## Build and Publish

From the project directory, build and check the package:

```sh
python3 -m pip install --upgrade build twine
python3 -m build
python3 -m twine check dist/wifi_hotspot-*
```

Create a PyPI API token in your PyPI account. Upload without putting the token
in the command or saving it in the project:

```sh
export TWINE_USERNAME=__token__
read -rsp "PyPI token: " TWINE_PASSWORD
printf '\n'
python3 -m twine upload dist/wifi_hotspot-*
unset TWINE_USERNAME TWINE_PASSWORD
```

`wifi-hotspot` returned as available when checked, but another user may claim
the name before upload. This package also retains `dnss-hotspot` as an alias.
Never share your PyPI token or commit it to the repository.