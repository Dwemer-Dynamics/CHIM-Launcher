import tkinter as tk
from tkinter import font, scrolledtext, messagebox
from tkinter import ttk  # Added import for ttk
import subprocess
import threading
import re
import requests
import webbrowser
import datetime
import sys
import os
from PIL import Image, ImageTk

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
        self.geometry("400x800")  
        self.configure(bg="#212529")
        self.resizable(False, False)  

        self.bold_font = font.Font(family="Arial", size=12, weight="bold")
        
        # Initialize server running state
        self.server_running = False
        self.server_starting = False  # Flag to indicate server is starting

        # Animation variables for the Start Server button
        self.animation_running = False
        self.animation_dots = 0
        self.original_start_text = "Start Server"

        # Animation variables for the update status label
        self.update_status_animation_running = False
        self.update_status_animation_dots = 0

        self.create_widgets()

        # Set the window icon
        self.set_window_icon('CHIM.png') 

        # Bind the window close event to on_close method
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Start the update check in a separate thread
        threading.Thread(target=self.check_for_updates, daemon=True).start()
        
    def set_window_icon(self, icon_filename):
        """Sets the window icon for the application."""
        icon_path = get_resource_path(icon_filename)
        print(f"Attempting to set icon using path: {icon_path}") 

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
            'bg': '#031633',         
            'fg': 'white',          
            'activebackground': '#021b4d',
            'activeforeground': 'white',
            'padx': 10,              
            'pady': 5,               
            'cursor': 'hand2'        
        }

        # Arrange buttons vertically using pack
        self.start_button = tk.Button(
            button_frame,
            text=self.original_start_text,
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
        
        self.debugging_button = tk.Button(
            button_frame,
            text="Debugging",
            command=self.open_debugging_menu,
            font=self.bold_font,
            **button_style
        )
        self.debugging_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.debugging_button)

        # Display update status
        self.update_status_label = tk.Label(
            top_frame,
            text="Checking for Updates",
            fg="white",
            bg="#212529",
            font=("Arial", 10)
        )
        self.update_status_label.pack(pady=5)

        # Add a link to the repository (Optional)
        repo_link = tk.Label(
            top_frame,
            text="View on GitHub",
            fg="white",
            bg="#212529",
            font=("Arial", 10),
            cursor="hand2"
        )
        repo_link.pack(pady=5)
        repo_link.bind("<Button-1>", lambda e: webbrowser.open_new("https://github.com/abeiro/HerikaServer/tree/aiagent"))
        
        manual_link = tk.Label(
            top_frame,
            text="Read the Manual",
            fg="white",
            bg="#212529",
            font=("Arial", 10),
            cursor="hand2"
        )
        manual_link.pack(pady=5)
        manual_link.bind("<Button-1>", lambda e: webbrowser.open_new("https://docs.google.com/document/d/12KBar_VTn0xuf2pYw9MYQd7CKktx4JNr_2hiv4kOx3Q/edit?tab=t.0"))


        # Create the main frame to hold loading_frame and output_area
        self.main_frame = tk.Frame(self, bg="#212529")
        self.main_frame.pack(fill=tk.BOTH, expand=True)
        self.main_frame.grid_rowconfigure(0, weight=3)  
        self.main_frame.grid_rowconfigure(1, weight=7)  
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
            button['background'] = '#021b4d'  
        def on_leave(e):
            button['background'] = '#031633' 
        button.bind('<Enter>', on_enter)
        button.bind('<Leave>', on_leave)

    def start_animation(self):
        """Start the animated dots on the Start button."""
        if not self.animation_running:
            self.animation_running = True
            self.animation_dots = 1
            self.update_animation()

    def update_animation(self):
        """Update the Start button's text with animated dots."""
        if self.animation_running and self.server_starting:
            dots = '.' * self.animation_dots
            self.start_button.config(text=f"Server is Starting {dots}")
            self.animation_dots = self.animation_dots % 3 + 1
            self.after(500, self.update_animation)  # Update every 500ms

    def stop_animation(self):
        """Stop the animated dots on the Start button and reset text."""
        if self.animation_running:
            self.animation_running = False
            self.start_button.config(text=self.original_start_text)

    def set_server_running(self):
        """Set the Start button to indicate that the server is running."""
        self.start_button.config(text="Server is Running", state=tk.DISABLED)

    def set_server_not_running(self):
        """Reset the Start button to its original state."""
        self.start_button.config(text=self.original_start_text, state=tk.NORMAL)

    def start_wsl(self):
        if self.server_running or self.server_starting:
            messagebox.showinfo("Server Status", "The server is already running or starting.")
            return

        # Update flags and button states
        self.server_starting = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        # Start the animation
        self.original_start_text = "Start Server"
        self.start_button.config(text="Server is Starting .")
        self.start_animation()

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

            self.append_output("DwemerDistro is starting up.\n")

            # Read output line by line
            for line in self.process.stdout:
                self.append_output(line)
                # Check if the server is ready
                if "AIAgent.ini Network Settings:" in line:
                    self.server_running = True
                    self.server_starting = False
                    self.after(0, self.stop_animation)
                    self.after(0, self.set_server_running)
                    self.append_output("Server is ready.\n")
                    # Continue reading output until the process ends

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
            self.server_starting = False
            self.set_server_not_running()
            self.stop_button.config(state=tk.DISABLED)
        self.after(0, update_buttons)

    def stop_wsl(self):
        if not self.server_running and not self.server_starting:
            messagebox.showinfo("Server Status", "The server is not currently running.")
            return

        threading.Thread(target=self.stop_wsl_thread, daemon=True).start()

    def stop_wsl_thread(self):
        try:
            # Send newline to the process's stdin to simulate pressing ENTER
            if hasattr(self, 'process') and self.process and self.process.poll() is None:
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
        self.after(0, self.set_server_not_running)
        self.after(0, lambda: self.stop_button.config(state=tk.DISABLED))

        # Server is no longer running
        self.server_running = False

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
            if hasattr(self, 'process') and self.process and self.process.poll() is None:
                self.process.kill()
                self.append_output("DwemerDistro has been forcefully stopped.\n")

        except Exception as e:
            self.append_output(f"An error occurred: {e}\n")

        # Re-enable the Start button and disable the Stop button
        self.after(0, self.set_server_not_running)
        self.after(0, lambda: self.stop_button.config(state=tk.DISABLED))

        # Server is no longer running
        self.server_running = False
        self.server_starting = False

    def update_wsl(self):
        threading.Thread(target=self.update_wsl_thread, daemon=True).start()

    def update_wsl_thread(self):
        try:
            # Disable the Update button to prevent multiple clicks
            self.after(0, lambda: self.update_button.config(state=tk.DISABLED))

            # Confirm update with the user
            confirm = messagebox.askyesno("Update Server", "This will update the CHIM server. Are you sure?")
            if not confirm:
                self.append_output("Update canceled.\n")
                self.after(0, lambda: self.update_button.config(state=tk.NORMAL))
                return

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

            self.append_output("Update started.\n")

            # Read output line by line
            for line in update_process.stdout:
                self.append_output(line)

            update_process.wait()

            self.append_output("Update completed.\n")

        except Exception as e:
            self.append_output(f"An error occurred during update: {e}\n")

        finally:
            # Re-enable the Update button
            self.after(0, lambda: self.update_button.config(state=tk.NORMAL))
            # After update, change status label to green text immediately
            self.after(0, lambda: self.update_status_label.config(
                text="CHIM Server is up-to-date",
                fg="green"
            ))

    def on_close(self):
        # Confirm exit with the user
        if messagebox.askokcancel("Quit", "Do you really want to quit?"):
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

    def configure_installed_components(self):
        threading.Thread(target=self.configure_installed_components_thread, daemon=True).start()

    def configure_installed_components_thread(self):
        # Open a new command window, run the specified command, and close the window after execution
        cmd = 'wsl -d DwemerAI4Skyrim3 -u dwemer -- /usr/local/bin/conf_services'
        subprocess.Popen(['cmd', '/c', cmd])

    def open_chim_server_folder(self):
        threading.Thread(target=self.open_chim_server_folder_thread, daemon=True).start()

    def open_chim_server_folder_thread(self):
        # Run the command to open the folder
        folder_path = r'\\wsl.localhost\DwemerAI4Skyrim3\var\www\html\HerikaServer'
        subprocess.Popen(['explorer', folder_path])

    def open_install_components_menu(self):
        # Create a new Toplevel window
        submenu_window = tk.Toplevel(self)
        submenu_window.title("Install Components")
        submenu_window.geometry("500x630")  # Adjusted size to accommodate the table
        submenu_window.configure(bg="#212529")
        submenu_window.resizable(False, False)

        # Set the window icon to CHIM.png
        try:
            icon_path = get_resource_path('CHIM.png')  # Ensure CHIM.png exists
            img = Image.open(icon_path)
            photo = ImageTk.PhotoImage(img)  # Convert to Tkinter-compatible photo
            submenu_window.iconphoto(False, photo)  # Set the icon
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

        # Create a frame for the buttons
        button_frame = tk.Frame(submenu_window, bg="#212529")
        button_frame.pack(pady=10)

        # Create buttons
        install_cuda_button = tk.Button(
            button_frame,
            text="Install CUDA",
            command=self.install_cuda,
            **button_style
        )
        install_cuda_button.pack(pady=5)
        self.add_hover_effects(install_cuda_button)

        install_xtts_button = tk.Button(
            button_frame,
            text="Install CHIM XTTS",
            command=self.install_xtts,
            **button_style
        )
        install_xtts_button.pack(pady=5)
        self.add_hover_effects(install_xtts_button)

        install_melotts_button = tk.Button(
            button_frame,
            text="Install MeloTTS",
            command=self.install_melotts,
            **button_style
        )
        install_melotts_button.pack(pady=5)
        self.add_hover_effects(install_melotts_button)

        install_minime_t5_button = tk.Button(
            button_frame,
            text="Install Minime-T5",
            command=self.install_minime_t5,
            **button_style
        )
        install_minime_t5_button.pack(pady=5)
        self.add_hover_effects(install_minime_t5_button)

        install_mimic3_button = tk.Button(
            button_frame,
            text="Install Mimic3",
            command=self.install_mimic3,
            **button_style
        )
        install_mimic3_button.pack(pady=5)
        self.add_hover_effects(install_mimic3_button)
        
        install_localwhisper_button = tk.Button(
            button_frame,
            text="Install LocalWhisper",
            command=self.install_localwhisper,
            **button_style
        )
        install_localwhisper_button.pack(pady=5)
        self.add_hover_effects(install_localwhisper_button)

        # README Section
        readme_frame = tk.LabelFrame(
            submenu_window,
            text="READ THIS!",
            bg="#212529",
            fg="white",
            font=("Arial", 12, "bold")
        )
        readme_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # NVIDIA Users Section
        nvidia_header = tk.Label(
            readme_frame,
            text="NVIDIA GPU users:",
            bg="#212529",
            fg="white",
            font=("Arial", 10, "bold"),
            anchor="w"
        )
        nvidia_header.pack(pady=(10, 0), padx=0, fill="x")

        nvidia_text = (
            "Install CUDA first! Then any of the other components you wish to use."
        )
        nvidia_label = tk.Label(
            readme_frame,
            text=nvidia_text,
            bg="#212529",
            fg="white",
            wraplength=480,  # Adjust wrap length as needed
            justify="left",
            font=("Arial", 10),
            anchor="w"
        )
        nvidia_label.pack(pady=(0, 10), padx=0, fill="x")

        # AMD Users Section
        amd_header = tk.Label(
            readme_frame,
            text="AMD GPU users:",
            bg="#212529",
            fg="white",
            font=("Arial", 10, "bold"),
            anchor="w"
        )
        amd_header.pack(pady=(10, 0), padx=0, fill="x")

        amd_text = (
            "You can only install MeloTTS, Mimic3 and Minime-T5 in CPU mode only! "
            "This is because AMD cards do not support CUDA."
        )
        amd_label = tk.Label(
            readme_frame,
            text=amd_text,
            bg="#212529",
            fg="white",
            wraplength=480,  # Adjust wrap length as needed
            justify="left",
            font=("Arial", 10),
            anchor="w"
        )
        amd_label.pack(pady=(0, 10), padx=0, fill="x")

        # GPU Usage Section
        gpu_header = tk.Label(
            readme_frame,
            text="GPU Usage",
            bg="#212529",
            fg="white",
            font=("Arial", 12, "bold"),
            anchor="w"
        )
        gpu_header.pack(pady=(10, 5), padx=0, fill="x")

        # Create a Treeview widget for the GPU Usage table
        columns = ("Component", "VRAM Usage")
        gpu_tree = ttk.Treeview(readme_frame, columns=columns, show='headings', height=5)
        
        # Define headings
        gpu_tree.heading("Component", text="Component")
        gpu_tree.heading("VRAM Usage", text="VRAM Usage")
        
        # Define column widths
        gpu_tree.column("Component", anchor="w", width=150)
        gpu_tree.column("VRAM Usage", anchor="w", width=150)
        
        # Insert data
        gpu_data = [
            ("CHIM XTTS", "4GB VRAM"),
            ("LocalWhisper", "2-4GB VRAM"),
            ("MeloTTS", "Less than 1GB VRAM"),
            ("Mimic3", "Less than 1GB VRAM"),
            ("Minime-T5", "Less than 1GB VRAM")
        ]
        
        for component, vram in gpu_data:
            gpu_tree.insert("", "end", values=(component, vram))
        
        # Style the Treeview
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#212529",
                        foreground="white",
                        fieldbackground="#212529",
                        font=("Arial", 10))
        style.configure("Treeview.Heading",
                        background="#031633",
                        foreground="white",
                        font=("Arial", 10, "bold"))
        style.map("Treeview.Heading",
                        background=[('active', "#031633")],
                        foreground=[('active', "white")])
        
        gpu_tree.pack(pady=(0, 10), padx=0, fill="x")

    def run_command_in_new_window(self, cmd):
        try:
            # Open a new command window and run the specified command
            subprocess.Popen(['cmd', '/c', cmd])
        except Exception as e:
            self.append_output(f"An error occurred while running command: {e}\n")

    def install_cuda(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d DwemerAI4Skyrim3 -- /usr/local/bin/install_full_packages',), daemon=True).start()

    def install_xtts(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/xtts-api-server/ddistro_install.sh',), daemon=True).start()

    def install_melotts(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/MeloTTS/ddistro_install.sh',), daemon=True).start()

    def install_minime_t5(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/minime-t5/ddistro_install.sh',), daemon=True).start()

    def install_mimic3(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/mimic3/ddistro_install.sh',), daemon=True).start()
    
    def install_localwhisper(self):
        threading.Thread(target=self.run_command_in_new_window, args=('wsl -d DwemerAI4Skyrim3 -u dwemer -- /home/dwemer/remote-faster-whisper/ddistro_install.sh',), daemon=True).start()
    
    def open_debugging_menu(self):
        # Create a new Toplevel window
        debug_window = tk.Toplevel(self)
        debug_window.title("Debugging")
        debug_window.geometry("440x350")  # Made window wider to accommodate wider buttons
        debug_window.configure(bg="#212529")
        debug_window.resizable(False, False)

        # Set the window icon to CHIM.png (optional)
        try:
            icon_path = get_resource_path('CHIM.png')  # Ensure CHIM.png exists
            img = Image.open(icon_path)
            photo = ImageTk.PhotoImage(img)  # Convert to Tkinter-compatible photo
            debug_window.iconphoto(False, photo)  # Set the icon
        except Exception as e:
            print(f"Error setting icon: {e}")

        # Style options for buttons
        debug_button_style = {
            'bg': "#031633",  # Button color
            'fg': "white",
            'activebackground': "#021b4d",  # Active button color
            'activeforeground': "white",
            'font': ("Arial", 12, "bold"),
            'bd': 1,
            'relief': tk.GROOVE,
            'highlightthickness': 0,
            'width': 29,  # Increased width from 25 to 29
            'cursor': 'hand2'  # Change cursor on hover
        }

        # Create a frame for the buttons
        debug_button_frame = tk.Frame(debug_window, bg="#212529")
        debug_button_frame.pack(pady=20)

        # Get current branch for the button text
        current_branch = self.get_current_branch()
        branch_display = f"Switch Branch (Current: {current_branch})" if current_branch else "Switch Branch"

        # Define the debugging buttons with their respective commands
        debugging_commands = [
            ("Open Terminal", self.open_terminal),
            ("View Memory Usage", self.view_memory_usage),
            ("View CHIM XTTS Logs", self.view_xtts_logs),
            ("View MeloTTS Logs", self.view_melotts_logs),
            ("View LocalWhisper Logs", self.view_localwhisper_logs),
            ("View Apache Logs", self.view_apacheerror_logs),
            (branch_display, lambda: self.switch_branch(debug_window))  # Pass debug_window to switch_branch
        ]

        for text, command in debugging_commands:
            btn = tk.Button(
                debug_button_frame,
                text=text,
                command=command,
                **debug_button_style
            )
            btn.pack(pady=5)
            self.add_hover_effects(btn)

    def open_terminal(self):
        """Opens a new terminal window with the specified command."""
        cmd = 'wsl -d DwemerAI4Skyrim3 -u dwemer -- /usr/local/bin/terminal'
        threading.Thread(target=self.run_command_in_new_window, args=(cmd,), daemon=True).start()

    def view_memory_usage(self):
        """Opens a new terminal window to view memory usage using htop."""
        cmd = 'wsl -d DwemerAI4Skyrim3 -- htop'
        threading.Thread(target=self.run_command_in_new_window, args=(cmd,), daemon=True).start()
    
    def view_melotts_logs(self):
        """Opens a new terminal window to view the MeloTTS logs."""
        cmd = 'wsl -d DwemerAI4Skyrim3 -u dwemer -- tail -n 100 -f /home/dwemer/MeloTTS/melo/log.txt'
        threading.Thread(target=self.run_command_in_new_window, args=(cmd,), daemon=True).start()

    def view_xtts_logs(self):
        """Opens a new terminal window to view the CHIM XTTS logs."""
        cmd = 'wsl -d DwemerAI4Skyrim3 -u dwemer -- tail -n 100 -f /home/dwemer/xtts-api-server/log.txt'
        threading.Thread(target=self.run_command_in_new_window, args=(cmd,), daemon=True).start()
    
    def view_localwhisper_logs(self):
        """Opens a new terminal window to view the LocalWhisper logs."""
        cmd = 'wsl -d DwemerAI4Skyrim3 -u dwemer -- tail -n 100 -f /home/dwemer/remote-faster-whisper/log.txt'
        threading.Thread(target=self.run_command_in_new_window, args=(cmd,), daemon=True).start()
        
    def view_apacheerror_logs(self):
        """Opens a new terminal window to view the Apache error logs."""
        cmd = 'wsl -d DwemerAI4Skyrim3 -u dwemer -- tail -n 100 -f /var/log/apache2/error.log'
        threading.Thread(target=self.run_command_in_new_window, args=(cmd,), daemon=True).start()
        
    def switch_branch(self, debug_window):
        """Switches between Release and Dev branches based on current branch."""
        try:
            # Get current branch
            current_branch = self.get_current_branch()
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
            if current_branch == "aiagent":
                # Currently on Release branch, switch to Dev
                if messagebox.askyesno("Switch Branch", "Currently on Release branch. Switch to Dev branch?"):
                    cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                          "cd /var/www/html/HerikaServer && "
                          "git stash save 'Auto-stash before switching branch' && "
                          "git fetch origin && "
                          "git checkout -B dev origin/dev"]
                    result = subprocess.run(cmd, 
                                         capture_output=True, 
                                         text=True,
                                         startupinfo=startupinfo,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                    
                    self.append_output(f"Switching to Dev branch...\n")
                    
                    if result.stderr and not any(msg in result.stderr for msg in [
                        "Reset branch",
                        "No local changes to save",
                        "Switched to"
                    ]):
                        self.append_output(f"Errors:\n{result.stderr}\n")
                    
                    self.append_output("Successfully switched to Dev branch.\n")
                    debug_window.destroy()  # Close the debug window
                    
            elif current_branch == "dev":
                # Currently on Dev branch, switch to Release
                if messagebox.askyesno("Switch Branch", "Currently on Dev branch. Switch to Release branch?"):
                    cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c",
                          "cd /var/www/html/HerikaServer && "
                          "git stash save 'Auto-stash before switching branch' && "
                          "git fetch origin && "
                          "git checkout -B aiagent origin/aiagent"]
                    result = subprocess.run(cmd, 
                                         capture_output=True, 
                                         text=True,
                                         startupinfo=startupinfo,
                                         creationflags=subprocess.CREATE_NO_WINDOW)
                    
                    self.append_output(f"Switching to Release branch...\n")
                    
                    if result.stderr and not any(msg in result.stderr for msg in [
                        "Reset branch",
                        "No local changes to save",
                        "Switched to"
                    ]):
                        self.append_output(f"Errors:\n{result.stderr}\n")
                    
                    self.append_output("Successfully switched to Release branch.\n")
                    debug_window.destroy()  # Close the debug window
            else:
                messagebox.showerror("Branch Error", f"Unexpected current branch: {current_branch}")
                return

            # Refresh the update status
            threading.Thread(target=self.check_for_updates, daemon=True).start()
            
        except Exception as e:
            self.append_output(f"Error switching branch: {str(e)}\n")

    # Updated methods for version checking
    def get_current_server_version(self):
        """Get the current server version by reading the version file directly."""
        try:
            version_file_path = r'\\wsl$\DwemerAI4Skyrim3\var\www\html\HerikaServer\.version.txt'
            with open(version_file_path, 'r') as file:
                version = file.read().strip()
                return version
        except Exception as e:
            print(f"Exception in get_current_server_version: {e}")
            return None

    def get_git_version(self):
        """Get the latest server version from GitHub."""
        url = "https://raw.githubusercontent.com/abeiro/HerikaServer/aiagent/.version.txt"
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return response.text.strip()
            else:
                print(f"get_git_version failed with status code: {response.status_code}")
                return None
        except Exception as e:
            print(f"Exception in get_git_version: {e}")
            return None

    def compare_versions(self, v1, v2):
        """Compare two version strings.

        Returns:
            -1 if v1 < v2
             0 if v1 == v2
             1 if v1 > v2
        """
        v1_parts = [int(part) for part in v1.strip().split('.')]
        v2_parts = [int(part) for part in v2.strip().split('.')]
        # Pad the shorter version with zeros
        length = max(len(v1_parts), len(v2_parts))
        v1_parts.extend([0] * (length - len(v1_parts)))
        v2_parts.extend([0] * (length - len(v2_parts)))
        for i in range(length):
            if v1_parts[i] < v2_parts[i]:
                return -1
            elif v1_parts[i] > v2_parts[i]:
                return 1
        return 0

    def get_current_branch(self):
        """Get the current git branch."""
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

            cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "cd", "/var/www/html/HerikaServer", "&&", "git", "rev-parse", "--abbrev-ref", "HEAD"]
            result = subprocess.run(cmd, 
                                  capture_output=True, 
                                  text=True, 
                                  startupinfo=startupinfo,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            return result.stdout.strip()
        except Exception as e:
            print(f"Exception in get_current_branch: {e}")
            return None

    def start_update_status_animation(self):
        """Start the animation for the update status label."""
        if not self.update_status_animation_running:
            self.update_status_animation_running = True
            self.update_status_animation_dots = 0
            self.update_update_status_animation()

    def update_update_status_animation(self):
        """Update the update status label with animated dots."""
        if self.update_status_animation_running:
            dots = '.' * (self.update_status_animation_dots % 4)
            self.update_status_label.config(text=f"Checking for Updates{dots}")
            self.update_status_animation_dots += 1
            self.after(500, self.update_update_status_animation)  # Update every 500ms

    def stop_update_status_animation(self):
        """Stop the animation for the update status label."""
        self.update_status_animation_running = False

    def check_for_updates(self):
        """Check if a newer server version is available and update the status label."""
        # Start the animation
        self.after(0, self.start_update_status_animation)

        # Start threads to get versions and branch concurrently
        current_version = [None]
        git_version = [None]
        current_branch = [None]

        def get_current_version():
            current_version[0] = self.get_current_server_version()

        def get_git_version():
            git_version[0] = self.get_git_version()

        def get_branch():
            current_branch[0] = self.get_current_branch()

        threads = [
            threading.Thread(target=get_current_version),
            threading.Thread(target=get_git_version),
            threading.Thread(target=get_branch)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Stop the animation
        self.after(0, self.stop_update_status_animation)

        branch_text = f" ({current_branch[0]})" if current_branch[0] else ""

        if current_version[0] and git_version[0]:
            comparison = self.compare_versions(current_version[0], git_version[0])
            if comparison < 0:
                # Update status label to indicate update is available (Red Text)
                self.after(0, lambda: self.update_status_label.config(
                    text=f"CHIM Server Update Available{branch_text}",
                    fg="red"
                ))
            else:
                # Update status label to indicate server is up to date (Green Text)
                self.after(0, lambda: self.update_status_label.config(
                    text=f"CHIM Server is up-to-date{branch_text}",
                    fg="green"
                ))
        else:
            # Could not retrieve version information
            self.after(0, lambda: self.update_status_label.config(
                text=f"Could not retrieve version information{branch_text}",
                fg="yellow"
            ))

if __name__ == "__main__":
    app = CHIMLauncher()
    app.mainloop()
