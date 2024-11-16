# CHIM Launcher

## Description
CHIM Launcher is a Python-compiled executable designed to run the DwemerDistro for the CHIM Skyrim mod. If you prefer not to run pre-compiled executables for security reasons, you can compile the `.exe` yourself by following the instructions below.

---

## Prerequisites
Before you begin, ensure you have met the following requirements:
- **Python 3.6 or higher**: Download from [python.org](https://python.org).
- **pip**: Python package installer (comes bundled with Python).
- **PyInstaller**: Tool to convert Python scripts into standalone executables.

---

## Installation and Compilation

### 1. Clone the Repository
Clone this repository to your local machine using Git:

```
pip install Pillow requests

pip install pyinstaller

pyinstaller --onefile --windowed --icon=CHIM.ico --name CHIM --add-data "CHIM.png;." --add-data "CHIM_title.png;." --add-data "spinner.gif;." --collect-all Pillow chim_launcher.py
```

### Command Breakdown:

--onefile: Creates a single executable file.
--windowed: Suppresses the console window (useful for GUI applications).
--icon=CHIM.ico: Sets the icon for the executable.
--name CHIM: Names the output executable CHIM.exe.
--add-data "CHIM.png;.": Includes CHIM.png in the executable directory.
--add-data "CHIM_title.png;.": Includes CHIM_title.png in the executable directory.
--collect-all Pillow: Ensures all Pillow library files are included.
chim_launcher.py: The main Python script to be compiled.
6. Locate the Compiled Executable
After the compilation process completes, you'll find the CHIM.exe file in the dist directory within your project folder.

### License
This project is licensed under the MIT License.