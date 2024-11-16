import tkinter as tk
from tkinter import font, scrolledtext, messagebox
import subprocess
import threading
import re
import requests
import webbrowser
import datetime
import sys
import os
from PIL import Image, ImageTk, ImageSequence

def get_resource_path(filename):
    """Get the absolute path to a resource, works for PyInstaller."""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, filename)


class CHIMLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CHIM")
        self.geometry("500x750")  # Adjusted window size
        self.configure(bg="#212529")
        self.resizable(False, False)  # Make window size fixed and unchangeable

        self.bold_font = font.Font(family="Arial", size=12, weight="bold")
        
        # Initialize server running state
        self.server_running = False

        # Initialize spinner attributes
        self.spinner_index = 0
        self.spinner_animation = self.after(100, self.animate_spinner)  # Adjust delay as needed


        self.create_widgets()

        # Set the window icon
        self.set_window_icon('CHIM.png')  # Changed to use CHIM.png

        # Start the WSL process on launch
        self.after(0, self.start_wsl)

        # Bind the window close event to on_close method
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
    def set_window_icon(self, icon_filename):
        """Sets the window icon for the application."""
        icon_path = get_resource_path(icon_filename)
        print(f"Attempting to set icon using path: {icon_path}")  # For debugging

        try:
            icon_image = tk.PhotoImage(file=icon_path)
            self.iconphoto(False, icon_image)
        except Exception as e:
            print(f"Error setting icon: {e}")

    def create_widgets(self):
        # Create a frame for the top widgets
        top_frame = tk.Frame(self, bg="#212529")
        top_frame.pack(side=tk.TOP, fill=tk.X, pady=10)

        # Load the image
        image_path = get_resource_path('CHIM_title.png')
        try:
            image = Image.open(image_path)
            photo = ImageTk.PhotoImage(image)
        except Exception as e:
            print(f"Error loading image: {e}")
            photo = None

        if photo:
            image_label = tk.Label(top_frame, image=photo, bg="#212529")
            image_label.photo = photo  # Keep a reference to prevent garbage collection
            image_label.pack(pady=10)
        else:
            # If image could not be loaded, use a placeholder label
            title_label = tk.Label(
                top_frame,
                text="CHIM",
                fg="white",
                bg="#212529",
                font=("Arial", 24)
            )
            title_label.pack(pady=10)

        # Create a frame for buttons within top_frame
        button_frame = tk.Frame(top_frame, bg="#212529")
        button_frame.pack(pady=10)

        # Style options for buttons
        button_style = {
            'bg': '#031633',         # Background color
            'fg': 'white',           # Text color
            'activebackground': '#021b4d',
            'activeforeground': 'white',
            'padx': 10,              # Padding on x-axis
            'pady': 5,               # Padding on y-axis
            'cursor': 'hand2'        # Cursor changes to hand on hover
        }

        # Arrange buttons vertically using pack
        self.start_button = tk.Button(
            button_frame,
            text="Start Server",
            command=self.start_wsl,
            font=self.bold_font,
            **button_style
        )
        self.start_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.start_button)

        self.stop_button = tk.Button(
            button_frame,
            text="Stop Server",
            command=self.stop_wsl,
            state=tk.DISABLED,
            font=self.bold_font,
            **button_style
        )
        self.stop_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.stop_button)

        self.force_stop_button = tk.Button(
            button_frame,
            text="Force Stop Server",
            command=self.force_stop_wsl,
            font=self.bold_font,
            **button_style
        )
        self.force_stop_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.force_stop_button)

        self.update_button = tk.Button(
            button_frame,
            text="Update Server",
            command=self.update_wsl,
            font=self.bold_font,
            **button_style
        )
        self.update_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.update_button)

        self.open_folder_button = tk.Button(
            button_frame,
            text="Open Server Folder",
            command=self.open_chim_server_folder,
            font=self.bold_font,
            **button_style
        )
        self.open_folder_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.open_folder_button)

        # Add the "Install Components" button
        self.install_components_button = tk.Button(
            button_frame,
            text="Install Components",
            command=self.open_install_components_menu,
            font=self.bold_font, 
            **button_style
        )
        self.install_components_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.install_components_button)

        self.configure_button = tk.Button(
            button_frame,
            text="Configure Installed Components",
            command=self.configure_installed_components,
            font=self.bold_font,
            **button_style
        )
        self.configure_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.configure_button)

        # Display latest commit info
        commit_info = self.get_latest_commit_info()
        commit_label = tk.Label(
            top_frame,
            text=commit_info,
            fg="white",
            bg="#212529",
            font=("Arial", 8)  # Made font size smaller
        )
        commit_label.pack(pady=5)

        # Add a link to the repository (Optional)
        repo_link = tk.Label(
            top_frame,
            text="View on GitHub",
            fg="blue",
            bg="#212529",
            font=("Arial", 10),
            cursor="hand2"
        )
        repo_link.pack(pady=5)
        repo_link.bind("<Button-1>", lambda e: webbrowser.open_new("https://github.com/abeiro/HerikaServer/tree/aiagent"))

        # Create the main frame to hold loading_frame and output_area
        self.main_frame = tk.Frame(self, bg="#212529")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.main_frame.grid_rowconfigure(0, weight=3)  # Loading frame row (30%)
        self.main_frame.grid_rowconfigure(1, weight=7)  # Output area row (70%)
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Create the loading frame but do not pack it yet
        self.loading_frame = tk.Frame(self.main_frame, bg="#212529")
        self.loading_label = tk.Label(
            self.loading_frame,
            fg="white",
            bg="#212529",
            font=("Arial", 12)
        )
        self.loading_label.pack(side=tk.LEFT, padx=5)

        # Load the spinner GIF
        spinner_path = get_resource_path('spinner.gif')
        try:
            print(f"Attempting to load spinner GIF from {spinner_path}")
            spinner_image = Image.open(spinner_path)
            # Resize the spinner to 30x30 pixels (adjust as needed)
            spinner_image = spinner_image.resize((30, 30), Image.ANTIALIAS)
            self.spinner_frames = [ImageTk.PhotoImage(frame.copy()) for frame in ImageSequence.Iterator(spinner_image)]
            print(f"Loaded {len(self.spinner_frames)} frames for spinner GIF.")
            self.spinner_label = tk.Label(self.loading_frame, bg="#212529")
            self.spinner_label.pack(side=tk.LEFT, padx=5)
        except Exception as e:
            print(f"Error loading spinner GIF: {e}")
            self.spinner_frames = None
            self.spinner_label = None

        # Add the scrolled text area
        self.output_area = scrolledtext.ScrolledText(
            self.main_frame,
            bg="#1e1e1e",
            fg="white",
            font=("Consolas", 10),
            wrap=tk.WORD
        )
        self.output_area.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0,10))
        self.output_area.config(state=tk.DISABLED)
        

    def add_hover_effects(self, button):
        def on_enter(e):
            button['background'] = '#021b4d'  # Hover color
        def on_leave(e):
            button['background'] = '#031633'  # Original color
        button.bind('<Enter>', on_enter)
        button.bind('<Leave>', on_leave)

    def get_latest_commit_info(self):
        try:
            # Corrected the GitHub API URL to fetch commits from the 'aiagent' branch
            response = requests.get("https://api.github.com/repos/abeiro/HerikaServer/commits?sha=aiagent")
            if response.status_code == 200:
                commit_data = response.json()[0]
                commit_date = commit_data['commit']['author']['date']
                # Format the date
                date_obj = datetime.datetime.strptime(commit_date, "%Y-%m-%dT%H:%M:%SZ")
                formatted_date = date_obj.strftime("%Y-%m-%d %H:%M:%S")
                return f"Last server update was on {formatted_date}"
            else:
                return f"Unable to fetch latest update date: {response.status_code}"
        except Exception as e:
            return f"Error fetching update info: {e}"

    def start_wsl(self):
         # Disable the Start button and enable the Stop button
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        # Start the spinner and show loading label
        self.loading = True
        self.loading_label.config(text="Server is starting up")
        self.loading_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
        self.start_spinner()

        # Start the WSL command in the background
        threading.Thread(target=self.run_wsl_silently, daemon=True).start()

    def run_wsl_silently(self):
        try:
            # Start the WSL process without showing a window
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # 0 = SW_HIDE

            self.process = subprocess.Popen(
                ["wsl", "-d", "DwemerAI4Skyrim3", "--", "/etc/start_env"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            self.server_running = True

            self.append_output("DwemerDistro is starting up.\n")

            # Read output line by line
            for line in self.process.stdout:
                self.append_output(line)

                # Stop spinner when "Installed Components:" is output
                if "Installed Components:" in line:
                    self.loading = False
                    self.after(0, self.stop_spinner)
                    self.after(0, self.hide_loading_widgets)

            self.process.wait()

            # When process ends, re-enable Start button and disable Stop button
            self.update_buttons_after_process()

        except Exception as e:
            self.append_output(f"An error occurred: {e}\n")
            self.update_buttons_after_process()

    def hide_loading_widgets(self):
        self.loading_frame.grid_remove()


    def update_buttons_after_process(self):
        def update_buttons():
            self.server_running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
        self.after(0, update_buttons)

    def stop_wsl(self):
        threading.Thread(target=self.stop_wsl_thread, daemon=True).start()

    def stop_wsl_thread(self):
        try:
            # Send newline to the process's stdin to simulate pressing ENTER
            if self.process and self.process.poll() is None:
                self.process.stdin.write('\n')
                self.process.stdin.flush()
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    self.process.kill()
                    self.append_output("DwemerDistro has been stopped.\n")
            else:
                self.append_output("DwemerDistro is not running.\n")

            # Terminate the WSL distribution (optional)
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # 0 = SW_HIDE

            subprocess.run(
                ["wsl", "-t", "DwemerAI4Skyrim3"],
                check=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.append_output("DwemerDistro has stopped.\n")

        except Exception as e:
            self.append_output(f"An error occurred: {e}\n")

        # Re-enable the Start button and disable the Stop button
        self.after(0, lambda: self.start_button.config(state=tk.NORMAL))
        self.after(0, lambda: self.stop_button.config(state=tk.DISABLED))

        # Server is no longer running
        self.server_running = False

        # Stop the spinner if it's still running
        if self.loading:
            self.loading = False
            self.after(0, self.stop_spinner)
            self.after(0, self.hide_loading_widgets)

    def force_stop_wsl(self):
        threading.Thread(target=self.force_stop_wsl_thread, daemon=True).start()

    def force_stop_wsl_thread(self):
        try:
            # Force terminate the WSL distribution
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # 0 = SW_HIDE

            subprocess.run(
                ["wsl", "-t", "DwemerAI4Skyrim3"],
                check=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.append_output("DwemerDistro has been forcefully stopped.\n")

            # If the process is still running, kill it
            if self.process and self.process.poll() is None:
                self.process.kill()
                self.append_output("DwemerDistro has been forcefully stopped.\n")

        except Exception as e:
            self.append_output(f"An error occurred: {e}\n")

        # Re-enable the Start button and disable the Stop button
        self.after(0, lambda: self.start_button.config(state=tk.NORMAL))
        self.after(0, lambda: self.stop_button.config(state=tk.DISABLED))

        # Server is no longer running
        self.server_running = False

        # Stop the spinner if it's still running
        if self.loading:
            self.loading = False
            self.after(0, self.stop_spinner)
            self.after(0, self.hide_loading_widgets)

    def update_wsl(self):
        threading.Thread(target=self.update_wsl_thread, daemon=True).start()

    def update_wsl_thread(self):
        try:
            # Confirm update with the user
            confirm = messagebox.askyesno("Update Server", "This will update the CHIM server. Are you sure?")
            if not confirm:
                self.append_output("Update canceled by the user.\n")
                return

            # Start the spinner and show loading label
            self.loading = True
            self.loading_label.config(text="Updating Server...")
            # Replace pack with grid
            self.loading_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=5)
            self.start_spinner()

            # Run the update command
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # 0 = SW_HIDE

            update_process = subprocess.Popen(
                ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "/usr/local/bin/update_gws"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            self.append_output("Update command started.\n")

            # Read output line by line
            for line in update_process.stdout:
                self.append_output(line)

            update_process.wait()

            self.append_output("Update completed.\n")

        except Exception as e:
            self.append_output(f"An error occurred during update: {e}\n")

        finally:
            # Stop the spinner
            if self.loading:
                self.loading = False
                self.after(0, self.stop_spinner)
                self.after(0, self.hide_loading_widgets)

    def on_close(self):
        # Force stop the WSL distribution when the window is closed
        self.force_stop_wsl()
        # Destroy the window after force stopping
        self.destroy()

    def append_output(self, text):
        # Remove ANSI escape sequences from the text
        clean_text = self.remove_ansi_escape_sequences(text)

        # Check if the cleaned text matches unwanted patterns
        if self.is_unwanted_line(clean_text):
            return  # Skip appending this line

        # Append text to the output area in a thread-safe way
        def update_text():
            self.output_area.config(state=tk.NORMAL)
            self.output_area.insert(tk.END, clean_text)
            self.output_area.see(tk.END)
            self.output_area.config(state=tk.DISABLED)

        self.output_area.after(0, update_text)

    def remove_ansi_escape_sequences(self, text):
        # Regular expression to match ANSI escape sequences
        ansi_escape = re.compile(r'''
            \x1B  # ESC
            (?:   # 7-bit C1 Fe (except CSI)
                [@-Z\\-_]
            |     # or [ for CSI, followed by control codes
                \[
                [0-?]*  # Parameter bytes
                [ -/]*  # Intermediate bytes
                [@-~]   # Final byte
            )
        ''', re.VERBOSE)
        return ansi_escape.sub('', text)

    def is_unwanted_line(self, text):
        # Define unwanted patterns
        unwanted_patterns = [
            r'^[\s_¯]+$',          # Lines that contain only whitespace, underscores, or '¯' characters
            r'^_+$',               # Lines that contain only underscores
            r'^¯+$',               # Lines that contain only '¯' characters
            r'^-+$',               # Lines that contain only hyphens
            r'^=+$',               # Lines that contain only equal signs
            r'^\s*$',              # Empty or whitespace-only lines
            r'^(__|¯¯){3,}$',      # Lines with repeated '__' or '¯¯' patterns
            r'^(\s*_{5,}\s*)+$',   # Lines with 5 or more underscores
            r'^(\s*¯{5,}\s*)+$',   # Lines with 5 or more '¯' characters
            r'^.*¯Â.*$',           # Lines that contain '¯Â' anywhere
            r'^.*Press Enter to shutdown DwemerDistro.*$',  # Lines that contain the shutdown message
        ]
        for pattern in unwanted_patterns:
            if re.match(pattern, text):
                return True  # This is an unwanted line
        return False  # This line is acceptable

    def start_spinner(self):
        if self.spinner_frames and not self.spinner_animation:
            self.animate_spinner()

    def stop_spinner(self):
        if self.spinner_animation:
            self.after_cancel(self.spinner_animation)
            self.spinner_animation = None
        self.spinner_index = 0

    def animate_spinner(self):
        if self.spinner_frames:
            frame = self.spinner_frames[self.spinner_index]
            self.spinner_label.configure(image=frame)
            self.spinner_label.image = frame  # Keep a reference to prevent garbage collection
            self.spinner_index = (self.spinner_index + 1) % len(self.spinner_frames)
            self.spinner_animation = self.after(100, self.animate_spinner)  # Adjust delay as needed

    def configure_installed_components(self):
        threading.Thread(target=self.configure_installed_components_thread, daemon=True).start()

    def configure_installed_components_thread(self):
        try:
            # Open a new command window and run the specified command
            cmd = 'wsl -d DwemerAI4Skyrim3 -u dwemer -- /usr/local/bin/conf_services'
            subprocess.Popen(['cmd', '/k', cmd])
            self.append_output("Opened configuration for installed components.\n")
        except Exception as e:
            self.append_output(f"An error occurred while opening configuration: {e}\n")

    def open_chim_server_folder(self):
        threading.Thread(target=self.open_chim_server_folder_thread, daemon=True).start()

    def open_chim_server_folder_thread(self):
        try:
            # Run the command to open the folder
            folder_path = r'\\wsl.localhost\DwemerAI4Skyrim3\var\www\html\HerikaServer'
            subprocess.Popen(['explorer', folder_path])
            self.append_output("Opened Server Folder.\n")
        except Exception as e:
            self.append_output(f"An error occurred while opening the folder: {e}\n")

    def open_install_components_menu(self):
        # Create a new Toplevel window
        submenu_window = tk.Toplevel(self)
        submenu_window.title("Install Components")
        submenu_window.geometry("400x200")
        submenu_window.configure(bg="#212529")
        submenu_window.resizable(False, False)
        
        # Set the window icon to CHIM.ico
        try:
            icon_path = get_resource_path('CHIM.ico')
            submenu_window.iconbitmap(icon_path)
        except Exception as e:
            print(f"Error setting icon: {e}")

        # Style options for buttons
        button_style = {
            'bg': "#031633",  # Updated button color
            'fg': "white",
            'activebackground': "#021b4d",  # Updated active button color
            'activeforeground': "white",
            'font': ("Arial", 12, "bold"),  # Specify font here
            'bd': 1,
            'relief': tk.GROOVE,
            'highlightthickness': 0,
            'width': 30,
            'cursor': 'hand2'  # Change cursor on hover
        }

        # Create buttons
        install_cuda_button = tk.Button(
            submenu_window,
            text="Install CUDA",
            command=self.install_cuda,
            **button_style
        )
        install_cuda_button.pack(pady=5)
        self.add_hover_effects(install_cuda_button)

        install_xtts_button = tk.Button(
            submenu_window,
            text="Install XTTS",
            command=self.install_xtts,
            **button_style
        )
        install_xtts_button.pack(pady=5)
        self.add_hover_effects(install_xtts_button)

        install_melotts_button = tk.Button(
            submenu_window,
            text="Install MeloTTS",
            command=self.install_melotts,
            **button_style
        )
        install_melotts_button.pack(pady=5)
        self.add_hover_effects(install_melotts_button)

        install_minime_t5_button = tk.Button(
            submenu_window,
            text="Install Minime-T5",
            command=self.install_minime_t5,
            **button_style
        )
        install_minime_t5_button.pack(pady=5)
        self.add_hover_effects(install_minime_t5_button)

        install_mimic3_button = tk.Button(
            submenu_window,
            text="Install Mimic3",
            command=self.install_mimic3,
            **button_style
        )
        install_mimic3_button.pack(pady=5)
        self.add_hover_effects(install_mimic3_button)

    def run_command_in_new_window(self, cmd):
        try:
            # Open a new command window and run the specified command
            subprocess.Popen(['cmd', '/k', cmd])
            self.append_output(f"Command started: {cmd}\n")
        except Exception as e:
            self.append_output(f"An error occurred while running command: {e}\n")

    def install_cuda(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d  DwemerAI4Skyrim3 -- /usr/local/bin/install_full_packages',), daemon=True).start()

    def install_xtts(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d  DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/xtts-api-server/ddistro_install.sh',), daemon=True).start()

    def install_melotts(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d  DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/MeloTTS/ddistro_install.sh',), daemon=True).start()

    def install_minime_t5(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d  DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/minime-t5/ddistro_install.sh',), daemon=True).start()

    def install_mimic3(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d  DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/mimic3/ddistro_install.sh',), daemon=True).start()


if __name__ == "__main__":
    app = CHIMLauncher()
    app.mainloop()
