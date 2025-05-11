# CHIM Launcher

## Description
CHIM Launcher is a Python-compiled executable designed to run the DwemerDistro for the CHIM Skyrim mod. If you prefer not to run pre-compiled executables for security reasons, you can compile the `.exe` yourself by following the instructions below.

It also acts as a port proxy (127.0.0.1:7513) between Skyrim and the DwemerDistro.

---

## Prerequisites
Before you begin, ensure you have met the following requirements:
- **Python 3.6 or higher**
- **pip**
- **PyInstaller**
---

## Installation and Compilation

Install the prerequisites and run these commands:

```
pip install Pillow requests

pip install pyinstaller

pyinstaller --onefile --windowed --icon=CHIM.ico --name CHIM --add-data "CHIM.png;." --add-data "CHIM_title.png;." --add-data "nvidia.png;." --add-data "amd.png;." --exclude-module ImageSequence --upx-dir upx-4.2.4-win64 chim_launcher.py
```
After the compilation process completes, you'll find the CHIM.exe file in the dist directory within your project folder.

### License
This project is licensed under the MIT License.