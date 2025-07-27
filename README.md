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

### Method 1: PyInstaller (Recommended)

Install the prerequisites and run these commands:

```bash
pip install Pillow requests

pip install pyinstaller

pyinstaller --onefile --windowed --icon=CHIM.ico --name CHIM --add-data "CHIM.png;." --add-data "CHIM_title.png;." --add-data "nvidia.png;." --add-data "amd.png;." --exclude-module ImageSequence --upx-dir upx-4.2.4-win64 --version-file=file_version_info.txt chim_launcher.py
```

After the compilation process completes, you'll find the CHIM.exe file in the dist directory within your project folder.

**Note**: The `--version-file` parameter includes license and version information to help reduce antivirus false positives.

### Method 2: Running Directly with Python (No Compilation)

If you have Python installed and want to avoid potential antivirus issues with compiled executables:

1. Install the required packages:
```bash
pip install Pillow requests
```

2. Rename `chim_launcher.py` to `chim_launcher.pyw` (optional, hides console window)

3. Run directly:
```bash
python chim_launcher.py
# or double-click chim_launcher.pyw if renamed
```

### Alternative Compilation Methods

If you're experiencing antivirus false positives with PyInstaller:

#### cx_Freeze (Less likely to trigger antivirus)
```bash
pip install cx_Freeze
```
Note: cx_Freeze produces executables that are less likely to be flagged by antivirus software but creates a folder distribution rather than a single file.

#### Nuitka (Advanced users)
```bash
pip install nuitka
```
Note: Nuitka can create optimized executables but may still trigger some antivirus software due to its compilation method.

## Troubleshooting Antivirus False Positives

If your antivirus software flags the compiled executable as suspicious, this is likely a false positive. Common causes include:

- **UPX compression**: The executable is compressed, which some antivirus software finds suspicious
- **WSL interactions**: The launcher communicates with Windows Subsystem for Linux
- **Network requests**: The application makes web requests for updates
- **File system operations**: Opening folders and managing files

### Solutions:
1. **Add an exception** in your antivirus software for the CHIM.exe file
2. **Use Method 2** (running directly with Python) to avoid compilation entirely
3. **Try alternative compilation methods** like cx_Freeze
4. **Compile yourself** using the provided instructions to ensure the source is trusted

### License
This project is licensed under the MIT License.