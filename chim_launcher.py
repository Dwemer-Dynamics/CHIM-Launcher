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
import http.server
import socketserver
import urllib.parse
import io # Added for reading request body
import tkinter.filedialog # Added for save dialog

# --- HTTP Proxy Classes ---
class ProxyHandler(http.server.BaseHTTPRequestHandler):
    def _forward_request(self):
        launcher = self.server.launcher
        # Make sure to update UI from the main thread - REMOVED update_ui_callback lambda
        # update_ui_callback = lambda status, latency_ms=None: launcher.after(0, launcher.update_proxy_status_ui, status, latency_ms)
        
        target_ip = launcher.get_wsl_ip()

        if not target_ip:
            # Log failure only if connection was previously reported as ok AND server was ready
            if launcher.wsl_connection_reported and launcher.wsl_server_ready:
                 launcher.after(0, launcher.append_output, "WSL Connection to Skyrim Lost!\n", "red")
            # launcher.wsl_connection_reported = False # REMOVE: Don't reset on error
            self.send_error(503, "WSL Service Unavailable (Could not get IP)")
            # launcher.append_output("Proxy Error: Could not get WSL IP to forward request.\n") # Hidden log
            # update_ui_callback("error", None) # Removed UI update
            return

        target_port = 8081 # Port inside WSL
        target_url = f"http://{target_ip}:{target_port}{self.path}"
        # launcher.append_output(f"Proxy forwarding {self.command} request to: {target_url}\n") # Hidden log

        req_headers = {k: v for k, v in self.headers.items()}
        req_body = None
        content_length = self.headers.get('Content-Length')
        if content_length:
            try:
                body_bytes = self.rfile.read(int(content_length))
                req_body = body_bytes
            except Exception as e:
                # Log failure only if connection was previously reported as ok AND server was ready
                if launcher.wsl_connection_reported and launcher.wsl_server_ready:
                     launcher.after(0, launcher.append_output, f"WSL Connection to Skyrim Lost!\n", "red")
                # launcher.wsl_connection_reported = False # REMOVE: Don't reset on error
                self.send_error(400, f"Error reading request body: {e}")
                # launcher.append_output(f"Proxy Error: Failed reading request body: {e}\n") # Hidden log
                # update_ui_callback("error", None) # Removed UI update
                return
        
        try:
            response = requests.request(
                method=self.command,
                url=target_url,
                headers=req_headers,
                data=req_body, 
                timeout=10,
                stream=True
            )

            self.send_response(response.status_code)
            excluded_headers = ['content-encoding', 'transfer-encoding', 'connection']
            for key, value in response.headers.items():
                 if key.lower() not in excluded_headers:
                    self.send_header(key, value)
            self.end_headers()

            try:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        self.wfile.write(chunk)
            except Exception as e:
                 # launcher.append_output(f"Proxy Error: Failed writing response body: {e}\n") # Hidden log
                 # Don't mark as connection lost here, client might have disconnected
                 pass

            # Calculate latency (though we aren't displaying it anymore, response.elapsed is still useful)
            latency_ms = response.elapsed.total_seconds() * 1000
            
            # Log established connection only once AND only after server is ready
            if not launcher.wsl_connection_reported and launcher.wsl_server_ready:
                launcher.after(0, launcher.append_output, "WSL Connection to Skyrim Established!\n", "green")
                launcher.wsl_connection_reported = True
                
            # launcher.append_output(f"Proxy forwarded request successfully ({response.status_code}).\n") # Hidden log
            # update_ui_callback("ok", latency_ms) # Removed UI update
            response.close()

        # Add back essential exception handling, without connection status logic
        except requests.exceptions.ConnectionError:
            self.send_error(503, "WSL Service Unavailable (Connection Error)")
        except requests.exceptions.Timeout:
            self.send_error(504, "Gateway Timeout")
        except requests.exceptions.RequestException as e:
            self.send_error(500, f"Internal Proxy Error: {e}")
        except Exception as e:
            try:
                self.send_error(500, "Internal Server Error")
            except Exception:
                pass

    def do_GET(self):
        self._forward_request()
    def do_POST(self):
        self._forward_request()
    def do_PUT(self):
        self._forward_request()
    def do_DELETE(self):
        self._forward_request()
    def do_HEAD(self):
        self._forward_request()
    def do_OPTIONS(self):
        self._forward_request()

    def log_message(self, format, *args):
        return # Suppress default logging

class ProxiedTCPServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    def __init__(self, server_address, RequestHandlerClass, launcher_instance):
        super().__init__(server_address, RequestHandlerClass)
        self.launcher = launcher_instance
# --- End HTTP Proxy Classes ---

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
        # Make window wider and taller, disable resizing
        self.geometry("870x870") 
        self.configure(bg="#2C2C2C")
        self.resizable(False, False) # Disable resizing

        self.bold_font = font.Font(family="Trebuchet MS", size=12, weight="bold")
        
        # Link handling for output area
        self.link_tag_counter = 0
        self.link_tags = {}

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

        # Proxy variables
        self.wsl_ip = None
        self.proxy_server = None
        self.proxy_thread = None
        self.proxy_port = 7513 # Port the launcher will listen on
        # self.proxy_status = "neutral" # Removed proxy status tracking

        # Add flag for connection status logging - REMOVED
        # self.wsl_connection_reported = False
        self.wsl_server_ready = False # Flag to track if WSL server reported ready

        self.create_widgets()

        # Set the window icon
        self.set_window_icon('CHIM.png') 

        # Bind the window close event to on_close method
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        
        # Start the update check in a separate thread
        threading.Thread(target=self.check_for_updates, daemon=True).start()
        
        # Start the proxy server
        self.start_proxy_server()

    def start_proxy_server(self):
        """Starts the HTTP proxy server in a separate thread."""
        try:
            # Note: Handler class needs to be defined before this is called - DEFINED ABOVE NOW
            # We will use a placeholder for now and inject the real classes later - NO LONGER PLACEHOLDERS
            # This is a limitation of applying edits sequentially - REMOVED PLACEHOLDERS
            # class PlaceholderHandler(http.server.BaseHTTPRequestHandler): 
            #      def handle(self): pass # Do nothing for placeholder
            
            # Need to define ProxiedTCPServer before use too - DEFINED ABOVE NOW
            # class PlaceholderTCPServer(socketserver.ThreadingTCPServer):
            #      allow_reuse_address = True
            #      def __init__(self, server_address, RequestHandlerClass, launcher_instance):
            #          super().__init__(server_address, RequestHandlerClass)
            #          self.launcher = launcher_instance

            # Use the actual classes now defined above
            self.proxy_server = ProxiedTCPServer(("127.0.0.1", self.proxy_port), ProxyHandler, self)
            self.proxy_thread = threading.Thread(target=self.proxy_server.serve_forever, daemon=True)
            self.proxy_thread.start()
            self.append_output(f"CHIM Proxy listening on 127.0.0.1:{self.proxy_port}\n")
            
            # Attempt to get WSL IP immediately after starting proxy
            threading.Thread(target=self.get_wsl_ip, daemon=True).start()
            
        except OSError as e:
            if e.errno == 98 or e.errno == 10048: # Address already in use
                 error_msg = f"Proxy Error: Port {self.proxy_port} is already in use. Is another instance running?\n"
                 messagebox.showerror("Proxy Error", f"Port {self.proxy_port} is already in use. Cannot start proxy.\nEnsure no other CHIM Launcher or application is using this port.")
                 self.append_output(error_msg)
            else:
                error_msg = f"Proxy Error: Could not start proxy server: {e}\n"
                messagebox.showerror("Proxy Error", f"Could not start proxy server: {e}")
                self.append_output(error_msg)
            self.proxy_server = None
            self.proxy_thread = None
        except Exception as e:
            error_msg = f"Proxy Error: An unexpected error occurred starting proxy server: {e}\n"
            messagebox.showerror("Proxy Error", f"An unexpected error occurred starting proxy: {e}")
            self.append_output(error_msg)
            self.proxy_server = None
            self.proxy_thread = None
            
    def get_wsl_ip(self, force_refresh=False):
        """Get the IP address of the WSL instance. Caches the result. Only logs if IP changes."""
        current_ip = self.wsl_ip # Store current cached IP
        
        if current_ip and not force_refresh:
            return current_ip

        new_ip = None # Initialize new_ip
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE
            
            cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "hostname", "-I"]
            result = subprocess.run(
                cmd, 
                capture_output=True, 
                text=True, 
                check=True, 
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            ip_address = result.stdout.strip().split()[0]
            if ip_address:
                new_ip = ip_address # Store the successfully found IP
            else:
                self.append_output("Failed to parse WSL IP address from output.\n")
                # Keep self.wsl_ip as is (or None if it was None)
                return current_ip # Return previous IP if parsing failed

        except FileNotFoundError:
            self.append_output("Error: 'wsl' command not found. Is WSL installed and in PATH?\n")
            self.wsl_ip = None # Can't get IP, clear it
            return None
        except subprocess.CalledProcessError as e:
            # Check if the error is specifically because the distro is not found
            distro_not_found_msg = "no distribution with the supplied name"
            if e.stderr and distro_not_found_msg in e.stderr.lower():
                error_message = (
                    "Dwemer Distro is not installed! Download it here:\n"
                    "https://www.nexusmods.com/skyrimspecialedition/mods/126330?tab=files"
                )
                self.append_output(f"Error: {error_message}\n", "red")
                # Use after() to ensure messagebox runs on the main thread
                self.after(0, lambda: messagebox.showerror("Distro Not Found", error_message))
            else:
                # Log other CalledProcessErrors as before
                self.append_output(f"Error checking WSL IP: {e}\nStderr: {e.stderr}\n")
            self.wsl_ip = None # Assume IP is invalid if command fails
            return None
        except Exception as e:
            self.append_output(f"An unexpected error occurred while getting WSL IP: {e}\n")
            self.wsl_ip = None
            return None
            
        # Only log and update cache if the new IP is valid and different from the current one
        if new_ip and new_ip != current_ip:
             self.append_output(f"DwemerDistro WSL IP: {new_ip}\n")
             self.wsl_ip = new_ip
        elif new_ip and not current_ip: # First time finding a valid IP
             self.append_output(f"DwemerDistro WSL IP: {new_ip}\n")
             self.wsl_ip = new_ip
             
        return self.wsl_ip # Return the newly found/cached IP

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
        # Configure main window grid (2 columns)
        self.grid_rowconfigure(0, weight=1) # Make row 0 expandable
        self.grid_columnconfigure(0, weight=1) # Column 0: Left controls
        self.grid_columnconfigure(1, weight=1) # Column 1: Log area 
        # self.grid_columnconfigure(2, weight=1) # REMOVED Column 2

        # --- Left Frame for Controls (Column 0) --- 
        left_frame = tk.Frame(self, bg="#2C2C2C", width=350)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        left_frame.grid_propagate(False)
        
        # --- Middle Frame for Link Buttons (REMOVED) --- 
        # middle_frame = tk.Frame(self, bg="#2C2C2C")
        # middle_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=10)
        
        # --- Output Area Frame (Column 1) ---
        output_frame = tk.Frame(self, bg="#1e1e1e")
        output_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 10), pady=10)
        output_frame.grid_rowconfigure(0, weight=1)
        output_frame.grid_columnconfigure(0, weight=1)

        # Create the Text widget
        self.output_area = tk.Text(
            output_frame, # Place inside the frame
            bg="#1e1e1e",
            fg="white",
            font=("Consolas", 10),
            wrap=tk.WORD,
            borderwidth=0, # Remove text border
            highlightthickness=0, # Remove highlight border
            width=40 # Add initial width hint
        )
        self.output_area.grid(row=0, column=0, sticky="nsew")

        # Create the ttk Scrollbar
        self.output_scrollbar = ttk.Scrollbar(
            output_frame, # Place inside the frame
            orient=tk.VERTICAL,
            command=self.output_area.yview # Link scrollbar to text view
        )
        self.output_scrollbar.grid(row=0, column=1, sticky="ns")

        # Link text view scrolling to scrollbar
        self.output_area.config(yscrollcommand=self.output_scrollbar.set)

        # Configure basic color tags
        self.output_area.tag_config('green', foreground='lime green')
        self.output_area.tag_config('red', foreground='red')
        
        # We'll initialize ANSI color tags on first use in process_ansi_escape_sequences
        # Mark that we haven't initialized them yet
        self._ansi_tags_initialized = False

        # Initial state
        self.output_area.config(state=tk.DISABLED)

        # --- Style the ttk Scrollbar ---
        style = ttk.Style()
        style.theme_use('clam') # Use the 'clam' theme for a cleaner base

        # Configure the style for Vertical.TScrollbar
        style.configure(
            "Vertical.TScrollbar",
            gripcount=0,              # Number of grip dots (0 for none)
            background="#505050",      # Color of the slider (thumb)
            darkcolor="#3a3a3a",       # Border dark color (may not be visible with flat relief)
            lightcolor="#3a3a3a",      # Border light color (may not be visible with flat relief)
            troughcolor="#1e1e1e",    # Color of the channel the slider moves in
            bordercolor="#1e1e1e",    # Border color of the trough
            arrowcolor="#cccccc",      # Color of the arrows (if visible)
            relief="flat"             # Make it flat
        )
        # Optionally remove arrows by redefining the layout (can be theme-dependent)
        # style.layout("Vertical.TScrollbar",
        #     [('Vertical.Scrollbar.trough', {'children':
        #         [('Vertical.Scrollbar.thumb', {'expand': '1', 'sticky': 'nswe'})],
        #     'sticky': 'ns'})])

        # Apply the style to our specific scrollbar instance
        self.output_scrollbar.config(style="Vertical.TScrollbar")

        # --- Content for Left Frame --- 
        # Load the image
        image_path = get_resource_path('CHIM_title.png')
        try:
            image = Image.open(image_path)
            photo = ImageTk.PhotoImage(image)
        except Exception as e:
            print(f"Error loading image: {e}")
            photo = None

        if photo:
            image_label = tk.Label(left_frame, image=photo, bg="#2C2C2C")
            image_label.photo = photo
            image_label.pack(pady=10)
        else:
            title_label = tk.Label(
                left_frame,
                text="CHIM",
                fg="white",
                bg="#2C2C2C",
                font=("Trebuchet MS", 24)
            )
            title_label.pack(pady=10)

        # --- LabelFrame Styles --- 
        labelframe_style = {
            'bg': "#2C2C2C", 
            'fg': "white", 
            'font': ("Trebuchet MS", 11, "bold"),
            'padx': 5,
            'pady': 5
        }
        button_style = {
            'bg': '#5E0505',         # Deep red
            'fg': 'white',          
            'activebackground': '#4A0404',
            'activeforeground': 'white',
            'padx': 10,              
            'pady': 5,               
            'cursor': 'hand2',
            'relief': 'flat',        # Changed from 'groove' to 'flat'
            'borderwidth': 0,        # Changed from 2 to 0
            'highlightthickness': 0,
            'font': ("Trebuchet MS", 12, "bold")
        }

        # Define standard button colors for hover effect
        standard_button_bg = '#5E0505'
        standard_button_hover_bg = '#4A0404'

        # --- Start Servers Group --- 
        start_servers_frame = tk.LabelFrame(left_frame, text="Server Controls", **labelframe_style)
        start_servers_frame.pack(pady=10, padx=5, fill=tk.X)
        
        self.start_button = tk.Button(
            start_servers_frame,
            text=self.original_start_text,
            command=self.start_wsl,
            **button_style
        )
        self.start_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.start_button, standard_button_bg, standard_button_hover_bg)

        self.stop_button = tk.Button(
            start_servers_frame,
            text="Stop Server",
            command=self.stop_wsl,
            state=tk.DISABLED,
            **button_style
        )
        self.stop_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.stop_button, standard_button_bg, standard_button_hover_bg)

        self.force_stop_button = tk.Button(
            start_servers_frame,
            text="Force Stop Server",
            command=self.force_stop_wsl,
            **button_style
        )
        self.force_stop_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.force_stop_button, standard_button_bg, standard_button_hover_bg)

        # --- Server Updates Group --- 
        server_updates_frame = tk.LabelFrame(left_frame, text="Update Controls", **labelframe_style)
        server_updates_frame.pack(pady=10, padx=5, fill=tk.X)

        # Replace separate update buttons with a single Update button
        self.update_button = tk.Button(
            server_updates_frame,
            text="Update",
            command=self.update_all,
            **button_style
        )
        self.update_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.update_button, standard_button_bg, standard_button_hover_bg)

        # Create and pack the update status label
        self.update_status_label = tk.Label(
            server_updates_frame,
            text="Checking for Updates...",
            fg="white",
            bg="#2C2C2C",
            font=("Trebuchet MS", 10)
        )
        self.update_status_label.pack(pady=5, fill=tk.X)

        # --- Server Configuration Group --- 
        server_config_frame = tk.LabelFrame(left_frame, text="Server Configuration", **labelframe_style)
        server_config_frame.pack(pady=10, padx=5, fill=tk.X)
        
        self.open_folder_button = tk.Button(
            server_config_frame, # Put in correct frame
            text="Open Server Folder",
            command=self.open_chim_server_folder,
            **button_style
        )
        self.open_folder_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.open_folder_button, standard_button_bg, standard_button_hover_bg)

        self.install_components_button = tk.Button(
            server_config_frame, # Put in correct frame
            text="Install Components",
            command=self.open_install_components_menu,
            **button_style
        )
        self.install_components_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.install_components_button, standard_button_bg, standard_button_hover_bg)

        self.configure_button = tk.Button(
            server_config_frame, # Put in correct frame
            text="Configure Installed Components",
            command=self.configure_installed_components,
            **button_style
        )
        self.configure_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.configure_button, standard_button_bg, standard_button_hover_bg)
        
        self.debugging_button = tk.Button(
            server_config_frame, # Put in correct frame
            text="Debugging",
            command=self.open_debugging_menu,
            **button_style
        )
        self.debugging_button.pack(fill=tk.X, pady=5)
        self.add_hover_effects(self.debugging_button, standard_button_bg, standard_button_hover_bg)

        # --- External Links Group --- 
        external_links_frame = tk.LabelFrame(left_frame, text="External Links", **labelframe_style)
        external_links_frame.pack(pady=10, padx=5, fill=tk.X)

        # Create an inner frame to hold the buttons for centering
        inner_link_frame = tk.Frame(external_links_frame, bg="#2C2C2C")
        # Pack the inner frame (removed anchor=tk.CENTER, added pady)
        inner_link_frame.pack(pady=5)

        # Add Link Buttons to Inner Frame 
        # Define base link button style (common settings)
        base_link_button_style = {
            'width': 10,
            'font': ("Trebuchet MS", 10, "bold"),
            'fg': 'white',
            'activeforeground': 'white',
            'relief': 'flat',        # Changed from 'groove' to 'flat'
            'borderwidth': 0,        # Changed from 2 to 0
            'highlightthickness': 0,
            'cursor': 'hand2'
        }

        # GitHub Button
        github_bg = "#20661B" # Dark Green
        github_hover_bg = "#154411" # Darker Green
        github_style = base_link_button_style.copy()
        github_style.update({'bg': github_bg, 'activebackground': github_hover_bg})
        github_button = tk.Button(
            inner_link_frame, 
            text="GitHub", # Icon removed
            command=lambda: webbrowser.open_new("https://github.com/abeiro/HerikaServer/tree/aiagent"),
            **github_style
        )
        github_button.pack(side=tk.LEFT, pady=5, padx=5, anchor=tk.CENTER)
        self.add_hover_effects(github_button, github_bg, github_hover_bg) # Pass colors to hover handler

        # Wiki Button
        wiki_bg = "#808080" # Grey
        wiki_hover_bg = "#606060" # Darker Grey
        wiki_style = base_link_button_style.copy()
        wiki_style.update({'bg': wiki_bg, 'activebackground': wiki_hover_bg})
        wiki_button = tk.Button(
            inner_link_frame, 
            text="Wiki", # Icon removed
            command=lambda: webbrowser.open_new("https://dwemerdynamics.hostwiki.io/"),
            **wiki_style
        )
        wiki_button.pack(side=tk.LEFT, pady=5, padx=5, anchor=tk.CENTER)
        self.add_hover_effects(wiki_button, wiki_bg, wiki_hover_bg) # Pass colors

        # Discord Button
        discord_bg = "#5865F2" # Discord Blurple/Purple
        discord_hover_bg = "#454FBF" # Darker Blurple
        discord_style = base_link_button_style.copy()
        discord_style.update({'bg': discord_bg, 'activebackground': discord_hover_bg})
        discord_button = tk.Button(
            inner_link_frame, 
            text="Discord", # Icon removed
            command=lambda: webbrowser.open_new("https://discord.com/invite/NDn9qud2ug"),
            **discord_style
        )
        discord_button.pack(side=tk.LEFT, pady=5, padx=5, anchor=tk.CENTER)
        self.add_hover_effects(discord_button, discord_bg, discord_hover_bg) # Pass colors
        
    def add_hover_effects(self, button, normal_bg, hover_bg):
        # Updated hover handler to use passed colors
        def on_enter(e):
            button['background'] = hover_bg  # Use passed hover color
        def on_leave(e):
            button['background'] = normal_bg  # Use passed normal color
        button.bind('<Enter>', on_enter)
        button.bind('<Leave>', on_leave)

    def start_animation(self):
        """Start the animated dots on the Start button."""
        if not self.animation_running:
            self.animation_running = True
            self.animation_dots = 0
            self.start_button.config(text="Server is Starting")  # Set initial text
            self.update_animation()

    def update_animation(self):
        """Update the Start button's text with animated dots."""
        if self.animation_running and self.server_starting:
            dots = '.' * self.animation_dots
            # Pad the dots with spaces to maintain consistent button width
            dots = dots.ljust(3)  # Always use 3 spaces for dots
            self.start_button.config(text=f"Server is Starting {dots}")
            self.animation_dots = (self.animation_dots % 3) + 1
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

        # Reset connection flags on start - REMOVED wsl_connection_reported
        # self.wsl_connection_reported = False
        self.wsl_server_ready = False
        
        # Update flags and button states
        self.server_starting = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)

        # Start the animation
        self.original_start_text = "Start Server"
        self.start_button.config(text="Server is Starting")  # Set initial text
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
                    self.wsl_server_ready = True # Set the flag here
                    # Trigger WSL IP check now that server is ready
                    self.after(100, lambda: threading.Thread(target=self.get_wsl_ip, args=(True,), daemon=True).start()) # Force refresh
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
                    self.append_output("DwemerDistro process killed after timeout.\n") # Clarified message
            else:
                self.append_output("DwemerDistro process not running or already stopped.\n") # Clarified message

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
            self.append_output("DwemerDistro terminated.\n") # Clarified message

            # Reset connection flags after successful stop - REMOVED wsl_connection_reported
            # self.wsl_connection_reported = False
            self.wsl_server_ready = False

        except Exception as e:
            self.append_output(f"An error occurred during stop: {e}\n")

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
                check=True, # Note: This might throw if already stopped, consider remove check=True
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            self.append_output("DwemerDistro force terminated command sent.\n")

            # If the process object exists and is still running, kill it
            if hasattr(self, 'process') and self.process and self.process.poll() is None:
                self.process.kill()
                self.append_output("DwemerDistro process force killed.\n")
            
            # Reset connection flags after successful force stop - REMOVED wsl_connection_reported
            # self.wsl_connection_reported = False
            self.wsl_server_ready = False

        except Exception as e:
            self.append_output(f"An error occurred during force stop: {e}\n")

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
            # Confirm update with the user
            confirm = messagebox.askyesno("Update Server", "This will update the CHIM server. Are you sure?")
            if not confirm:
                self.append_output("Update canceled.\n")
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

            # Get the current branch for the success message
            current_branch = self.get_current_branch() or "unknown"
            self.append_output(f"Update completed successfully. Branch: {current_branch}\n", "green")
            
            # Set update status to show it's up-to-date immediately
            # Make sure to update the main thread UI directly
            def update_status_label():
                self.update_status_label.config(
                    text=f"Up-to-date ({current_branch})",
                    fg="lime green"
                )
            self.after(0, update_status_label)

        except Exception as e:
            self.append_output(f"Error during update: {e}\n", "red")
        finally:
            # We don't need to run the check immediately since we've already updated the label
            # But keep it for verification after a delay
            self.after(1000, lambda: threading.Thread(target=self.check_for_updates, daemon=True).start())

    def update_distro(self):
        threading.Thread(target=self.update_distro_thread, daemon=True).start()

    def update_distro_thread(self):
        try:
            # Confirm update with the user
            confirm = messagebox.askyesno("Update Distro", "This will update the CHIM distro. Are you sure?")
            if not confirm:
                self.append_output("Distro update canceled.\n")
                return

            self.append_output("Starting distro update...\n")
            
            # Run git pull command to update the repository
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # 0 = SW_HIDE

            # First, check if the directory exists, create it if not
            check_dir_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                         "mkdir -p /home/dwemer/dwemerdistro"]
            
            subprocess.run(
                check_dir_cmd,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            # Check if this is a git repository already
            check_git_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                         "cd /home/dwemer/dwemerdistro && git status 2>/dev/null || echo 'Not a git repository'"]
            
            result = subprocess.run(
                check_git_cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            # If not a git repository, clone it
            if "Not a git repository" in result.stdout:
                self.append_output("Cloning dwemerdistro repository...\n")
                clone_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                          "cd /home/dwemer && git clone https://github.com/abeiro/dwemerdistro.git"]
                
                clone_process = subprocess.Popen(
                    clone_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                # Read output line by line
                for line in clone_process.stdout:
                    self.append_output(line)
                
                clone_process.wait()
            else:
                # Update the existing repository
                self.append_output("Updating dwemerdistro repository...\n")
                pull_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                         "cd /home/dwemer/dwemerdistro && git fetch origin && git reset --hard origin/main"]
                
                pull_process = subprocess.Popen(
                    pull_cmd,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                # Read output line by line
                for line in pull_process.stdout:
                    self.append_output(line)
                
                pull_process.wait()
            
            # Get repository version before running update script
            get_repo_version_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                          "cd /home/dwemer/dwemerdistro && cat .version.txt"]
            
            repo_version_result = subprocess.run(
                get_repo_version_cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            repo_version = repo_version_result.stdout.strip()
            
            # Run the update.sh script
            self.append_output("Running update script...\n")
            
            # Run the script with sudo
            update_script_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                           "cd /home/dwemer/dwemerdistro && chmod +x update.sh && echo 'dwemer' | sudo -S ./update.sh"]
            
            update_script_process = subprocess.Popen(
                update_script_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Read output line by line
            for line in update_script_process.stdout:
                self.append_output(line)
            
            update_script_process.wait()
            
            # Simple verification by checking if the process completed successfully
            if update_script_process.returncode == 0:
                # Update was successful, now make sure the version file exists in both locations
                if repo_version:
                    # Update both possible locations to ensure consistency
                    update_version_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                                      f"echo '{repo_version}' | sudo tee /etc/.version.txt > /dev/null && " +
                                      f"echo '{repo_version}' | tee /home/dwemer/dwemerdistro/.version.txt > /dev/null"]
                    
                    subprocess.run(
                        update_version_cmd,
                        startupinfo=startupinfo,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    self.append_output(f"Distro updated to version {repo_version}.\n", "green")
                    
                    # Use the server version check after update
                    self.after(0, lambda: self.update_status_label.config(
                        text="Checking for Updates...",
                        fg="white"
                    ))
                    self.after(1000, lambda: threading.Thread(target=self.check_for_updates, daemon=True).start())
                else:
                    self.append_output("Distro update completed successfully.\n", "green")
                    
                    # Use the server version check after update
                    self.after(0, lambda: self.update_status_label.config(
                        text="Checking for Updates...",
                        fg="white"
                    ))
                    self.after(1000, lambda: threading.Thread(target=self.check_for_updates, daemon=True).start())
            else:
                self.append_output(f"Distro update may have encountered issues (exit code: {update_script_process.returncode}).\n", "red")

        except Exception as e:
            self.append_output(f"Error during distro update: {e}\n", "red")
        finally:
            # Check status after a delay to verify
            self.after(1000, lambda: threading.Thread(target=self.check_for_updates, daemon=True).start())

    def refresh_distro_version(self):
        """Refreshes the distro version display after an update."""
        self.check_distro_version()

    def on_close(self):
        # Confirm exit with the user
        if messagebox.askokcancel("Quit", "Do you really want to quit? This will stop the server if running."):
            # Stop the proxy server first
            if self.proxy_server:
                self.append_output("Shutting down proxy server...\n")
                try:
                    self.proxy_server.shutdown()
                    self.proxy_server.server_close()
                    self.append_output("Proxy server shut down.\n")
                except Exception as e:
                    self.append_output(f"Error shutting down proxy server: {e}\n")
                    
            # Force stop the WSL distribution
            threading.Thread(target=self.force_stop_wsl_thread, daemon=True).start()
            
            # Destroy the window 
            self.destroy()

    def _on_link_enter(self, event, tag_name):
        """Handle mouse entering a link tag."""
        self.output_area.config(cursor="hand2")

    def _on_link_leave(self, event, tag_name):
        """Handle mouse leaving a link tag."""
        self.output_area.config(cursor="")

    def _on_link_click(self, event, tag_name):
        """Handle mouse clicking a link tag."""
        url = self.link_tags.get(tag_name)
        if url:
            try:
                webbrowser.open_new(url)
            except Exception as e:
                print(f"Error opening link '{url}': {e}")
                self.append_output(f"Error opening link: {e}\n", "red")

    def append_output(self, text, tag=None):
        # Process ANSI escape sequences in the text instead of removing them
        processed_text, ansi_tags = self.process_ansi_escape_sequences(text)

        # Check if the cleaned text matches unwanted patterns
        if self.is_unwanted_line(processed_text):
            return  # Skip appending this line

        # Regex to find URLs
        url_regex = re.compile(r'(https?://\S+)')

        # Append text to the output area in a thread-safe way
        def update_text():
            self.output_area.config(state=tk.NORMAL)
            
            # If we have ANSI color tags, use them for styling
            if ansi_tags:
                current_pos = 0
                for start, end, color in ansi_tags:
                    # Insert text before the colored segment with regular tag
                    if start > current_pos:
                        pre_text = processed_text[current_pos:start]
                        # Process URLs in this segment
                        self._insert_with_url_detection(pre_text, tag)
                    
                    # Insert the colored segment with its color tag
                    colored_text = processed_text[start:end]
                    # Process URLs in the colored segment
                    self._insert_with_url_detection(colored_text, color)
                    
                    current_pos = end
                
                # Insert any remaining text after the last colored segment
                if current_pos < len(processed_text):
                    remaining_text = processed_text[current_pos:]
                    self._insert_with_url_detection(remaining_text, tag)
            else:
                # No ANSI colors, just insert with regular tag and URL detection
                self._insert_with_url_detection(processed_text, tag)
            
            self.output_area.see(tk.END)
            self.output_area.config(state=tk.DISABLED)

        self.output_area.after(0, update_text)
    
    def _insert_with_url_detection(self, text, tag=None):
        """Helper method to insert text with URL detection and optional tag."""
        url_regex = re.compile(r'(https?://\S+)')
        last_end = 0
        found_link = False
        
        for match in url_regex.finditer(text):
            found_link = True
            start, end = match.span()
            url = match.group(0)

            # Insert text before the link
            if start > last_end:
                if tag:
                    self.output_area.insert(tk.END, text[last_end:start], tag)
                else:
                    self.output_area.insert(tk.END, text[last_end:start])

            # Create unique tag for this link
            link_tag_name = f"link_{self.link_tag_counter}"
            self.link_tag_counter += 1
            self.link_tags[link_tag_name] = url

            # Insert the link text with its unique tag and the original tag (if any)
            tags_to_apply = (link_tag_name,)
            if tag:
                tags_to_apply += (tag,)
            self.output_area.insert(tk.END, url, tags_to_apply)

            # Configure the link tag appearance and bindings
            self.output_area.tag_config(link_tag_name, foreground="#6495ED", underline=True) # Cornflower blue
            self.output_area.tag_bind(link_tag_name, "<Enter>", lambda e, name=link_tag_name: self._on_link_enter(e, name))
            self.output_area.tag_bind(link_tag_name, "<Leave>", lambda e, name=link_tag_name: self._on_link_leave(e, name))
            self.output_area.tag_bind(link_tag_name, "<Button-1>", lambda e, name=link_tag_name: self._on_link_click(e, name))

            last_end = end

        # Insert any remaining text after the last link (or the whole text if no links)
        if last_end < len(text):
            if tag:
                self.output_area.insert(tk.END, text[last_end:], tag)
            else:
                self.output_area.insert(tk.END, text[last_end:])

    def process_ansi_escape_sequences(self, text):
        """Process ANSI escape sequences in text, returning cleaned text and color tags.
        
        Returns:
            tuple: (cleaned_text, list_of_tags)
            - cleaned_text: Text with ANSI escape sequences removed
            - list_of_tags: List of (start, end, tag_name) tuples for colored regions
        """
        # Regular expression to match ANSI color codes
        ansi_color_pattern = re.compile(r'\x1B\[((?:\d+;)*\d+)m')
        
        # ANSI color code to Tkinter tag mapping
        ansi_to_tag = {
            '0': None,       # Reset
            '1': 'bold',     # Bold
            '2': None,       # Dim (not supported)
            '3': None,       # Italic (not supported)
            '4': None,       # Underline (not supported)
            '22': None,      # Reset bold
            '30': 'black',   # Black
            '31': 'red',     # Red
            '32': 'green',   # Green
            '33': 'yellow',  # Yellow
            '34': 'blue',    # Blue
            '35': 'purple',  # Purple/Magenta
            '36': 'cyan',    # Cyan
            '37': 'white',   # White
            '39': None,      # Default foreground color
            '90': 'gray',    # Bright Black (gray)
            '91': 'bright_red',    # Bright Red
            '92': 'bright_green',  # Bright Green
            '93': 'bright_yellow', # Bright Yellow
            '94': 'bright_blue',   # Bright Blue
            '95': 'bright_purple', # Bright Magenta
            '96': 'bright_cyan',   # Bright Cyan
            '97': 'bright_white',  # Bright White
            # Bold + color combinations
            '1;30': 'bold_black',     # Bold Black
            '1;31': 'bold_red',       # Bold Red
            '1;32': 'bold_green',     # Bold Green
            '1;33': 'bold_yellow',    # Bold Yellow
            '1;34': 'bold_blue',      # Bold Blue
            '1;35': 'bold_purple',    # Bold Purple/Magenta
            '1;36': 'bold_cyan',      # Bold Cyan
            '1;37': 'bold_white',     # Bold White
            '1;90': 'bold_gray',      # Bold Gray
            '1;91': 'bold_bright_red',     # Bold Bright Red
            '1;92': 'bold_bright_green',   # Bold Bright Green
            '1;93': 'bold_bright_yellow',  # Bold Bright Yellow
            '1;94': 'bold_bright_blue',    # Bold Bright Blue
            '1;95': 'bold_bright_purple',  # Bold Bright Purple
            '1;96': 'bold_bright_cyan',    # Bold Bright Cyan
            '1;97': 'bold_bright_white',   # Bold Bright White
        }
        
        # Ensure we have all the color tags defined in the text widget
        if not hasattr(self, '_ansi_tags_initialized'):
            # Basic styles
            self.output_area.tag_config('bold', font=('Consolas', 10, 'bold'))
            
            # Basic colors
            self.output_area.tag_config('black', foreground='black')
            self.output_area.tag_config('red', foreground='red')
            self.output_area.tag_config('green', foreground='lime green')
            self.output_area.tag_config('yellow', foreground='#FFD700')  # Gold
            self.output_area.tag_config('blue', foreground='#1E90FF')    # Dodger Blue
            self.output_area.tag_config('purple', foreground='#DA70D6')  # Orchid
            self.output_area.tag_config('cyan', foreground='#00FFFF')    # Cyan
            self.output_area.tag_config('white', foreground='white')
            self.output_area.tag_config('gray', foreground='#A9A9A9')    # Dark Gray
            
            # Bright colors
            self.output_area.tag_config('bright_red', foreground='#FF6347')    # Tomato
            self.output_area.tag_config('bright_green', foreground='#00FF00')  # Lime
            self.output_area.tag_config('bright_yellow', foreground='#FFFF00') # Yellow
            self.output_area.tag_config('bright_blue', foreground='#00BFFF')   # Deep Sky Blue
            self.output_area.tag_config('bright_purple', foreground='#FF00FF') # Fuchsia
            self.output_area.tag_config('bright_cyan', foreground='#00FFFF')   # Aqua
            self.output_area.tag_config('bright_white', foreground='#FFFFFF')  # White
            
            # Bold colors
            self.output_area.tag_config('bold_black', foreground='black', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_red', foreground='red', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_green', foreground='lime green', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_yellow', foreground='#FFD700', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_blue', foreground='#1E90FF', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_purple', foreground='#DA70D6', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_cyan', foreground='#00FFFF', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_white', foreground='white', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_gray', foreground='#A9A9A9', font=('Consolas', 10, 'bold'))
            
            # Bold bright colors
            self.output_area.tag_config('bold_bright_red', foreground='#FF6347', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_bright_green', foreground='#00FF00', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_bright_yellow', foreground='#FFFF00', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_bright_blue', foreground='#00BFFF', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_bright_purple', foreground='#FF00FF', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_bright_cyan', foreground='#00FFFF', font=('Consolas', 10, 'bold'))
            self.output_area.tag_config('bold_bright_white', foreground='#FFFFFF', font=('Consolas', 10, 'bold'))
            
            self._ansi_tags_initialized = True
        
        # Start with clean text and no tags
        cleaned_text = ""
        color_tags = []
        current_tag = None
        
        # Split the text by ANSI escape sequences
        segments = ansi_color_pattern.split(text)
        i = 0
        
        while i < len(segments):
            if i % 2 == 0:
                # This is text content
                segment_text = segments[i]
                start_pos = len(cleaned_text)
                cleaned_text += segment_text
                end_pos = len(cleaned_text)
                
                # If we have a current tag and this segment has text, add a tag entry
                if current_tag is not None and segment_text:
                    color_tags.append((start_pos, end_pos, current_tag))
            else:
                # This is a color code
                color_code = segments[i]
                # Handle multiple color codes separated by semicolons
                if ';' in color_code:
                    # For combined codes, first check if the whole code is defined
                    if color_code in ansi_to_tag:
                        current_tag = ansi_to_tag[color_code]
                    else:
                        # Otherwise try to find the most important code
                        codes = color_code.split(';')
                        # First check for known combined codes
                        if '1' in codes:  # Bold indicator
                            # Try to find a color code
                            for code in codes:
                                if code in ['30', '31', '32', '33', '34', '35', '36', '37', '90', '91', '92', '93', '94', '95', '96', '97']:
                                    bold_color_code = f"1;{code}"
                                    if bold_color_code in ansi_to_tag:
                                        current_tag = ansi_to_tag[bold_color_code]
                                        break
                        else:
                            # Use the last recognized code
                            for code in reversed(codes):
                                if code in ansi_to_tag:
                                    current_tag = ansi_to_tag[code]
                                    break
                elif color_code == '0':
                    # Reset code
                    current_tag = None
                else:
                    # For simple codes
                    current_tag = ansi_to_tag.get(color_code, current_tag)
            
            i += 1
        
        # Also remove any remaining ANSI sequences we didn't handle
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
        cleaned_text = ansi_escape.sub('', cleaned_text)
        
        return cleaned_text, color_tags

    def remove_ansi_escape_sequences(self, text):
        """Legacy method for backward compatibility."""
        cleaned_text, _ = self.process_ansi_escape_sequences(text)
        return cleaned_text

    def is_unwanted_line(self, text):
        # Define unwanted patterns
        unwanted_patterns = [
            r'^[\s_¯]+$',          # Lines that contain only whitespace, underscores, or '¯' characters
            r'^_+$',               # Lines that contain only underscores
            r'^¯+$',               # Lines that contain only '¯' characters
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
        submenu_window.geometry("500x860")  
        submenu_window.configure(bg="#2C2C2C")
        submenu_window.resizable(False, False)
        # Set the window icon to CHIM.png
        try:
            icon_path = get_resource_path('CHIM.png')  # Ensure CHIM.png exists
            img = Image.open(icon_path)
            photo = ImageTk.PhotoImage(img)  # Convert to Tkinter-compatible photo
            submenu_window.iconphoto(False, photo)  # Set the icon
        except Exception as e:
            print(f"Error setting icon: {e}")
            
        # Load NVIDIA and AMD icons
        try:
            nvidia_icon_path = get_resource_path('nvidia.png')
            amd_icon_path = get_resource_path('amd.png')
            nvidia_img = Image.open(nvidia_icon_path)
            amd_img = Image.open(amd_icon_path)
            
            # Resize images to be appropriate for buttons (24x24 pixels)
            nvidia_img = nvidia_img.resize((24, 24), Image.Resampling.LANCZOS)
            amd_img = amd_img.resize((24, 24), Image.Resampling.LANCZOS)
            
            # Convert to Tkinter PhotoImage
            nvidia_icon = ImageTk.PhotoImage(nvidia_img)
            amd_icon = ImageTk.PhotoImage(amd_img)
            
            # Store them to prevent garbage collection
            submenu_window.nvidia_icon = nvidia_icon
            submenu_window.amd_icon = amd_icon
        except Exception as e:
            print(f"Error loading GPU icons: {e}")
            nvidia_icon = None
            amd_icon = None

        # Style options for buttons
        button_style = {
            'bg': "#5E0505",  # Deep red
            'fg': "white",
            'activebackground': "#4A0404",  # Hover color
            'activeforeground': "white",
            'font': ("Trebuchet MS", 12, "bold"),
            'relief': 'flat',        # Changed from 'groove' to 'flat'
            'borderwidth': 0,        # Changed from 2 to 0
            'highlightthickness': 0,
            'width': 30,
            'cursor': 'hand2'
        }

        # Define standard button colors locally for hover effect
        standard_button_bg = '#5E0505'
        standard_button_hover_bg = '#4A0404'

        # --- Component Description Section ---
        desc_frame = tk.LabelFrame(
            submenu_window,
            text="Component Description",
            bg="#2C2C2C",
            fg="white",
            font=("Trebuchet MS", 11, "bold"),
            padx=10, pady=5
        )
        desc_frame.pack(pady=(10, 5), padx=10, fill=tk.X)

        desc_label = tk.Label(
            desc_frame,
            text="Hover over a component below to see its description.", # Initial text
            bg="#2C2C2C",
            fg="white",
            font=("Trebuchet MS", 10),
            wraplength=460, # Wrap text within the frame width
            justify="left",
            height=4 # Allocate space for ~3 lines + padding
        )
        desc_label.pack(fill=tk.X, pady=5)

        # --- Buttons Section ---
        button_frame = tk.Frame(submenu_window, bg="#2C2C2C")
        button_frame.pack(pady=5)

        # --- Descriptions Dictionary ---
        component_descriptions = {
            "CUDA": "Nvidia's special software that lets AI tools work with their graphics cards, without it programs like CHIM XTTS won't work. Install this first if you have a Nvidia GPU.",
            "CHIM XTTS": "A High-quality and realistic Text-to-Speech (TTS) service. Requires an Nvidia GPU with sufficient VRAM (4GB+) and CUDA installed. Provides immersive NPC voices with the ability to generate new ones automatically ingame.",
            "MeloTTS": "A fast, and efficient Text-to-Speech (TTS) service ideal for low-end systems. Runs efficiently on CPU, making it a great option for systems without Nvidia GPUs or for lower resource usage.",
            "Minime-T5": "A tiny helper Large Language Model (LLM). Used by CHIM to improve AI NPC responses. Also comes with TXT2VEC, an efficent vector service. Runs on GPU or CPU using only 400MB of memory.",
            "Mimic3": "An older but fast Text-to-Speech (TTS) service. Does not come with Skyrim voices.",
            "LocalWhisper": "Offline Speech-to-Text (STT) service based on OpenAI's Whisper. Allows you to use your microphone to chat with NPCs."
        }

        # --- Hover Handler for Install Buttons ---
        def install_button_hover_handler(button, normal_bg, hover_bg, component_key, description_label):
            desc_text = component_descriptions.get(component_key, "No description available.")
            def on_enter(e):
                button['background'] = hover_bg
                description_label.config(text=desc_text)
            def on_leave(e):
                button['background'] = normal_bg
                # Reset to initial text when mouse leaves *any* button
                description_label.config(text="Hover over a component below to see its description.")
            button.bind('<Enter>', on_enter)
            button.bind('<Leave>', on_leave)

        # Helper function to create buttons with icons
        def create_component_button(parent, text, command, component_key, show_nvidia=True, show_amd=False):
            # Create a frame that will act as our button
            btn_frame = tk.Frame(parent, bg=standard_button_bg)
            btn_frame.pack(pady=5, fill=tk.X, padx=2)  # Further reduce outer padding to use more screen width

            # Create inner frame to hold everything with proper padding
            inner_frame = tk.Frame(btn_frame, bg=standard_button_bg, padx=25, pady=10)  # Increased padding for wider buttons
            inner_frame.pack(fill=tk.X, expand=True)  # Added expand=True to fill horizontal space
            
            # Extract emoji and regular text from the button text
            # Most emoji are 1-2 characters followed by a space
            parts = text.split(" ", 1)
            emoji = parts[0] + " " if len(parts) > 1 else ""
            regular_text = parts[1] if len(parts) > 1 else text
            
            # Create a left container for icons
            icon_container = tk.Frame(inner_frame, bg=standard_button_bg)
            icon_container.pack(side=tk.LEFT, padx=(0, 10))  # Add space after the icons
            
            # Add Nvidia icon if requested
            if show_nvidia and nvidia_icon:
                nvidia_label = tk.Label(icon_container, image=nvidia_icon, bg=standard_button_bg)
                nvidia_label.pack(side=tk.LEFT, padx=(0, 2))
            
            # Add AMD icon if requested
            if show_amd and amd_icon:
                amd_label = tk.Label(icon_container, image=amd_icon, bg=standard_button_bg)
                amd_label.pack(side=tk.LEFT, padx=2)
            
            # Create emoji label
            if emoji:
                emoji_label = tk.Label(
                    inner_frame, 
                    text=emoji,
                    bg=standard_button_bg,
                    fg="white",
                    font=("Trebuchet MS", 12, "bold")
                )
                emoji_label.pack(side=tk.LEFT, padx=(0, 0))
            
            # Create text label
            text_label = tk.Label(
                inner_frame, 
                text=regular_text,
                bg=standard_button_bg,
                fg="white",
                font=("Trebuchet MS", 12, "bold")
            )
            text_label.pack(side=tk.LEFT, padx=5)  # Added padding around text for spacing
            
            # Right spacer to push content to the left
            right_spacer = tk.Frame(inner_frame, bg=standard_button_bg)
            right_spacer.pack(side=tk.RIGHT, fill=tk.X, expand=True)
            
            # Bind click events to the entire frame and all children
            btn_frame.bind("<Button-1>", lambda e: command())
            inner_frame.bind("<Button-1>", lambda e: command())
            icon_container.bind("<Button-1>", lambda e: command())
            right_spacer.bind("<Button-1>", lambda e: command())
            if emoji:
                emoji_label.bind("<Button-1>", lambda e: command())
            text_label.bind("<Button-1>", lambda e: command())
            
            if show_nvidia and nvidia_icon:
                nvidia_label.bind("<Button-1>", lambda e: command())
            if show_amd and amd_icon:
                amd_label.bind("<Button-1>", lambda e: command())
            
            # Apply hover effects to the entire button frame
            def on_enter(e):
                btn_frame.config(background=standard_button_hover_bg)
                inner_frame.config(background=standard_button_hover_bg)
                icon_container.config(background=standard_button_hover_bg)
                right_spacer.config(background=standard_button_hover_bg)
                if emoji:
                    emoji_label.config(background=standard_button_hover_bg)
                text_label.config(background=standard_button_hover_bg)
                if show_nvidia and nvidia_icon:
                    nvidia_label.config(background=standard_button_hover_bg)
                if show_amd and amd_icon:
                    amd_label.config(background=standard_button_hover_bg)
                desc_label.config(text=component_descriptions.get(component_key, "No description available."))
            
            def on_leave(e):
                btn_frame.config(background=standard_button_bg)
                inner_frame.config(background=standard_button_bg)
                icon_container.config(background=standard_button_bg)
                right_spacer.config(background=standard_button_bg)
                if emoji:
                    emoji_label.config(background=standard_button_bg)
                text_label.config(background=standard_button_bg)
                if show_nvidia and nvidia_icon:
                    nvidia_label.config(background=standard_button_bg)
                if show_amd and amd_icon:
                    amd_label.config(background=standard_button_bg)
                desc_label.config(text="Hover over a component below to see its description.")
            
            btn_frame.bind('<Enter>', on_enter)
            btn_frame.bind('<Leave>', on_leave)
            
            # Make cursor change to hand when over any part of the button
            btn_frame.bind("<Enter>", lambda e: btn_frame.config(cursor="hand2"))
            btn_frame.bind("<Leave>", lambda e: btn_frame.config(cursor=""))
            
            # Also bind hover events to inner elements to ensure they propagate properly
            inner_frame.bind('<Enter>', on_enter)
            inner_frame.bind('<Leave>', on_leave)
            icon_container.bind('<Enter>', on_enter)
            icon_container.bind('<Leave>', on_leave)
            right_spacer.bind('<Enter>', on_enter)
            right_spacer.bind('<Leave>', on_leave)
            if emoji:
                emoji_label.bind('<Enter>', on_enter)
                emoji_label.bind('<Leave>', on_leave)
            text_label.bind('<Enter>', on_enter)
            text_label.bind('<Leave>', on_leave)
            
            if show_nvidia and nvidia_icon:
                nvidia_label.bind('<Enter>', on_enter)
                nvidia_label.bind('<Leave>', on_leave)
            if show_amd and amd_icon:
                amd_label.bind('<Enter>', on_enter)
                amd_label.bind('<Leave>', on_leave)
            
            return btn_frame

        # Create the buttons with icons
        # CUDA - Only NVIDIA
        cuda_button = create_component_button(
            button_frame, "    💽 CUDA", self.install_cuda, "CUDA", 
            show_nvidia=True, show_amd=False
        )
        
        # Minime & TXT2VEC - NVIDIA and AMD
        minime_button = create_component_button(
            button_frame, "🧠Minime&TXT2VEC", self.install_minime_t5, "Minime-T5", 
            show_nvidia=True, show_amd=True
        )
        
        # CHIM XTTS - Only NVIDIA
        xtts_button = create_component_button(
            button_frame, "    🗣 CHIM XTTS", self.install_xtts, "CHIM XTTS", 
            show_nvidia=True, show_amd=False
        )
        
        # MeloTTS - NVIDIA and AMD
        melotts_button = create_component_button(
            button_frame, "🗣MeloTTS", self.install_melotts, "MeloTTS", 
            show_nvidia=True, show_amd=True
        )
        
        # Mimic3 - NVIDIA and AMD
        mimic3_button = create_component_button(
            button_frame, "🗣Mimic3", self.install_mimic3, "Mimic3", 
            show_nvidia=True, show_amd=True
        )
        
        # LocalWhisper - NVIDIA and AMD
        localwhisper_button = create_component_button(
            button_frame, "🎙LocalWhisper", self.install_localwhisper, "LocalWhisper", 
            show_nvidia=True, show_amd=True
        )

        # README Section
        readme_frame = tk.LabelFrame(
            submenu_window,
            text="READ THIS!",
            bg="#2C2C2C",
            fg="white",
            font=("Trebuchet MS", 12, "bold")
        )
        readme_frame.pack(fill="both", expand=True, padx=10, pady=10)

        # NVIDIA Users Section
        nvidia_header = tk.Label(
            readme_frame,
            text="NVIDIA GPU users:",
            bg="#2C2C2C",
            fg="white",
            font=("Trebuchet MS", 10, "bold"),
            anchor="w"
        )
        nvidia_header.pack(pady=(10, 0), padx=0, fill="x")

        nvidia_text = (
            "Install CUDA first! Then any of the other components you wish to use."
        )
        nvidia_label = tk.Label(
            readme_frame,
            text=nvidia_text,
            bg="#2C2C2C",
            fg="white",
            wraplength=480,  # Adjust wrap length as needed
            justify="left",
            font=("Trebuchet MS", 10),
            anchor="w"
        )
        nvidia_label.pack(pady=(0, 10), padx=0, fill="x")

        # AMD Users Section
        amd_header = tk.Label(
            readme_frame,
            text="AMD GPU users:",
            bg="#2C2C2C",
            fg="white",
            font=("Trebuchet MS", 10, "bold"),
            anchor="w"
        )
        amd_header.pack(pady=(10, 0), padx=0, fill="x")

        amd_text = (
            "You can only install MeloTTS, Mimic3, LocalWhisper and Minime-T5 in CPU mode only! "
            "This is because AMD cards do not support CUDA. They will run a bit slower."
        )
        amd_label = tk.Label(
            readme_frame,
            text=amd_text,
            bg="#2C2C2C",
            fg="white",
            wraplength=480,  # Adjust wrap length as needed
            justify="left",
            font=("Trebuchet MS", 10),
            anchor="w"
        )
        amd_label.pack(pady=(0, 10), padx=0, fill="x")

        # GPU Usage Section
        gpu_header = tk.Label(
            readme_frame,
            text="GPU Usage",
            bg="#2C2C2C",
            fg="white",
            font=("Trebuchet MS", 12, "bold"),
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
            ("Minime & TXT2VEC", "Less than 1GB VRAM")
        ]
        
        for component, vram in gpu_data:
            gpu_tree.insert("", "end", values=(component, vram))
        
        # Style the Treeview
        style = ttk.Style()
        style.theme_use("default")
        style.configure("Treeview",
                        background="#2C2C2C",
                        foreground="white",
                        fieldbackground="#2C2C2C",
                        font=("Trebuchet MS", 10))
        style.configure("Treeview.Heading",
                        background="#5E0505",  # Deep red
                        foreground="white",
                        font=("Trebuchet MS", 10, "bold"))
        # Remove hover effect by setting active color same as normal
        style.map("Treeview",
                background=[('selected', '#2C2C2C')],
                foreground=[('selected', 'white')])
        style.map("Treeview.Heading",
                background=[('active', "#5E0505")],  # Same as normal state
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
        debug_window.geometry("440x600")  # Increased height
        debug_window.configure(bg="#2C2C2C")
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
            'bg': "#5E0505",  # Deep red
            'fg': "white",
            'activebackground': "#4A0404",  # Hover color
            'activeforeground': "white",
            'font': ("Trebuchet MS", 12, "bold"),
            'relief': 'flat',        # Changed from 'groove' to 'flat'
            'borderwidth': 0,        # Changed from 2 to 0
            'highlightthickness': 0,
            'width': 29,
            'cursor': 'hand2'
        }

        # Create a frame for the buttons
        debug_button_frame = tk.Frame(debug_window, bg="#2C2C2C")
        debug_button_frame.pack(pady=20)

        # Define standard button colors locally for hover effect
        standard_button_bg = '#5E0505'
        standard_button_hover_bg = '#4A0404'

        # --- Generate Diagnostics Section (Moved to Top) ---
        tk.Label(debug_button_frame, text="--- Diagnostics ---", bg="#2C2C2C", fg="white", font=("Trebuchet MS", 10, "bold")).pack(pady=(0, 5))
        generate_diagnostics_btn = tk.Button(
            debug_button_frame,
            text="Create Diagnostic File",
            command=self.generate_diagnostics,
            **debug_button_style
        )
        generate_diagnostics_btn.pack(pady=5)
        self.add_hover_effects(generate_diagnostics_btn, standard_button_bg, standard_button_hover_bg)
        ttk.Separator(debug_button_frame, orient='horizontal').pack(fill='x', pady=10) # Separator

        # Get current branch for the button text
        current_branch = self.get_current_branch()
        branch_display = f"Switch Branch (Current: {current_branch})" if current_branch else "Switch Branch"

        # --- Actions Section ---
        tk.Label(debug_button_frame, text="--- Distro Actions ---", bg="#2C2C2C", fg="white", font=("Trebuchet MS", 10, "bold")).pack(pady=(0, 5))
        action_commands = [
            ("Open Terminal", self.open_terminal),
            ("View Memory Usage", self.view_memory_usage),
            (branch_display, lambda: self.switch_branch(debug_window)),
            ("Clean All Logs", self.clean_logs),
        ]
        for text, command in action_commands:
            btn = tk.Button(
                debug_button_frame,
                text=text,
                command=command,
                **debug_button_style
            )
            btn.pack(pady=5)
            self.add_hover_effects(btn, standard_button_bg, standard_button_hover_bg)
        ttk.Separator(debug_button_frame, orient='horizontal').pack(fill='x', pady=10) # Separator

        # --- View Logs Section ---
        tk.Label(debug_button_frame, text="--- View Logs ---", bg="#2C2C2C", fg="white", font=("Trebuchet MS", 10, "bold")).pack(pady=(0, 5))
        log_view_commands = [
            ("View CHIM XTTS Logs", self.view_xtts_logs),
            ("View MeloTTS Logs", self.view_melotts_logs),
            ("View LocalWhisper Logs", self.view_localwhisper_logs),
            ("View Apache Logs", self.view_apacheerror_logs),
        ]
        for text, command in log_view_commands:
            btn = tk.Button(
                debug_button_frame,
                text=text,
                command=command,
                **debug_button_style
            )
            btn.pack(pady=5)
            self.add_hover_effects(btn, standard_button_bg, standard_button_hover_bg)


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
        
    def clean_logs(self):
        """Opens a new window to clean log files."""
        # Create the batch file content
        batch_content = '''@echo -------------------------------------------------------------------------------
@echo This will backup and delete your log files! 
@echo Existing log files will be renamed to log_name.bak  
@echo Existing backups will be overwritten. 
@echo Make sure the server is not running. 
@echo -------------------------------------------------------------------------------

@%SystemRoot%\\System32\\choice.exe /C YN /N /M "Are you sure you want to delete log files? [Y/N] "
@IF NOT ErrorLevel 2 (
  @echo Deleting log files...
  IF EXIST "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\log\\apache2\\error.log" (
    del "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\log\\apache2\\error.bak"
    ren "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\log\\apache2\\error.log" "error.bak"
  )
  IF EXIST "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\log\\apache2\\other_vhosts_access.log" (
    del "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\log\\apache2\\other_vhosts_access.bak"
    ren "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\log\\apache2\\other_vhosts_access.log" "other_vhosts_access.bak"
  )
  IF EXIST "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\debugStream.log" (
    del "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\debugStream.bak"
    ren "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\debugStream.log" "debugStream.bak"
  )
  IF EXIST "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\context_sent_to_llm.log" (
    del "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\context_sent_to_llm.bak"
    ren "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\context_sent_to_llm.log" "context_sent_to_llm.bak"
  )
  IF EXIST "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\output_from_llm.log" (
    del "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\output_from_llm.bak"
    ren "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\output_from_llm.log" "output_from_llm.bak"
  )
  IF EXIST "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\output_to_plugin.log" (
    del "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\output_to_plugin.bak"
    ren "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\output_to_plugin.log" "output_to_plugin.bak"
  )
  IF EXIST "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\minai.log" (
    del "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\minai.bak"
    ren "\\\\wsl.localhost\\DwemerAI4Skyrim3\\var\\www\\html\\HerikaServer\\log\\minai.log" "minai.bak"
  )
  @echo Log files deleted. 
) ELSE (
  @echo Quit without deleting log files. 
)
@pause'''

        # Create a temporary batch file
        temp_batch = os.path.join(os.getenv('TEMP'), 'clean_logs.bat')
        with open(temp_batch, 'w') as f:
            f.write(batch_content)

        # Run the batch file
        threading.Thread(target=self.run_command_in_new_window, args=(temp_batch,), daemon=True).start()
        
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
                    
                    # Check for updates after switching branch
                    self.after(1000, lambda: threading.Thread(target=self.check_for_updates, daemon=True).start())
                    
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
                    
                    # Check for updates after switching branch
                    self.after(1000, lambda: threading.Thread(target=self.check_for_updates, daemon=True).start())
                    
            else:
                # Unexpected branch, switch back to aiagent
                if messagebox.askyesno("Switch Branch", f"Currently on unexpected branch ({current_branch}). Switch to Release branch?"):
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
                    
                    # Check for updates after switching branch
                    self.after(1000, lambda: threading.Thread(target=self.check_for_updates, daemon=True).start())

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
        """Get the latest server version from GitHub based on current branch."""
        try:
            # Get current branch first
            current_branch = self.get_current_branch()
            if not current_branch:
                print("Could not determine current branch")
                return None
                
            # Construct URL based on branch
            url = f"https://raw.githubusercontent.com/abeiro/HerikaServer/{current_branch}/.version.txt"
            
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
        """Compare two version strings. Works with both semantic versions like "1.2.3" 
        and single numeric versions like "2025050619" (date-based).

        Returns:
            -1 if v1 < v2
             0 if v1 == v2
             1 if v1 > v2
        """
        # Handle case when versions are exactly the same strings
        if v1 == v2:
            return 0
            
        try:
            # Check if both are simple numeric strings (like date-based versions)
            if v1.isdigit() and v2.isdigit():
                # Compare as integers
                v1_int = int(v1)
                v2_int = int(v2)
                
                if v1_int < v2_int:
                    return -1
                elif v1_int > v2_int:
                    return 1
                else:
                    return 0
            
            # Otherwise, handle as semantic versions with dots
            # Split version strings by dots and convert to integers
            v1_parts = [int(part) for part in v1.strip().split('.')]
            v2_parts = [int(part) for part in v2.strip().split('.')]
            
            # Pad the shorter version with zeros
            length = max(len(v1_parts), len(v2_parts))
            v1_parts.extend([0] * (length - len(v1_parts)))
            v2_parts.extend([0] * (length - len(v2_parts)))
            
            # Compare components
            for i in range(length):
                if v1_parts[i] < v2_parts[i]:
                    return -1
                elif v1_parts[i] > v2_parts[i]:
                    return 1
                    
            # If we reach here, they're equal
            return 0
        except (ValueError, AttributeError) as e:
            # If there's any error parsing versions, fall back to string comparison
            self.append_output(f"[DEBUG] Version parsing error: {e}. Using string comparison.\n")
            if v1 < v2:
                return -1
            elif v1 > v2:
                return 1
            else:
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

    def check_for_updates(self):
        """Check if a newer server version is available and update the status label."""
        # Use after(0, ...) to ensure UI updates happen on the main thread
        update_label_config = lambda config: self.after(0, self.update_status_label.config, config)

        # Initial state while checking
        update_label_config({"text": "Checking for Updates...", "fg": "white"})

        # Start threads to get versions and branch concurrently
        current_version = [None]
        git_version = [None]
        current_branch = [None]

        def get_current_version_thread():
            current_version[0] = self.get_current_server_version()
        def get_git_version_thread():
            git_version[0] = self.get_git_version()
        def get_branch_thread():
            current_branch[0] = self.get_current_branch()

        threads = [
            threading.Thread(target=get_current_version_thread),
            threading.Thread(target=get_git_version_thread),
            threading.Thread(target=get_branch_thread)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join() # Wait for all threads to complete

        branch_text = f" ({current_branch[0]})" if current_branch[0] else ""
        final_text = ""
        text_color = "white" # Default color

        if current_version[0] and git_version[0]:
            comparison = self.compare_versions(current_version[0], git_version[0])
            if comparison < 0:
                # Update available
                final_text = f"Update Available!{branch_text}"
                text_color = "red"
            else:
                # Up-to-date
                final_text = f"Up-to-date{branch_text}"
                text_color = "lime green"
        else:
            # Could not retrieve version information
            final_text = f"Version Check Failed{branch_text}"
            text_color = "yellow" # Use yellow for check failure
            
        # Update the label with final text and color
        update_label_config({"text": final_text, "fg": text_color})

    def generate_diagnostics(self):
        """Starts the diagnostics generation process in a new thread."""
        # Show a warning message before proceeding
        warning = messagebox.askokcancel(
            "Diagnostic Information Warning", 
            "Heads Up! Information generated will include the latest interactions you have had with CHIM.\n\nDo you want to continue?",
            icon=messagebox.WARNING
        )
        
        if warning:
            threading.Thread(target=self.generate_diagnostics_thread, daemon=True).start()
        else:
            self.append_output("Diagnostic file creation cancelled.\n")

    def generate_diagnostics_thread(self):
        """Gathers logs from specified files in WSL and saves them to a user-chosen file."""
        self.append_output("Starting diagnostic log generation...")
        
        log_files = [
            # SERVER logs
            "/var/www/html/HerikaServer/log/output_from_llm.log",
            "/var/www/html/HerikaServer/log/chim.log",
            "/var/www/html/HerikaServer/log/output_to_plugin.log",
            "/var/www/html/HerikaServer/log/context_sent_to_llm.log",
            # DISTRO logs
            "/home/dwemer/xtts-api-server/log.txt",
            "/home/dwemer/minime-t5/log.txt",
            "/home/dwemer/remote-faster-whisper/log.txt",
            "/home/dwemer/MeloTTS/melo/log.txt", # Corrected path
            "/home/dwemer/mimic3/log.txt"
        ]
        
        combined_log_content = "" # Initialize empty string for combined logs
        files_not_found = []

        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0  # SW_HIDE

        for log_file in log_files:
            self.append_output(f"Reading {log_file}...")
            cmd = [
                "wsl", "-d", "DwemerAI4Skyrim3", "--",
                "tail", "-n", "1000", log_file
            ]
            try:
                # Use run instead of Popen to capture output directly
                result = subprocess.run(
                    cmd, 
                    capture_output=True, 
                    text=True, 
                    check=False, # Don't raise error if tail fails (e.g., file not found)
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                    encoding='utf-8', errors='ignore' # Handle potential encoding issues
                )

                if result.returncode == 0:
                    combined_log_content += f"--- Start of {log_file} ---\n"
                    combined_log_content += result.stdout
                    combined_log_content += f"\n--- End of {log_file} ---\n\n"
                else:
                    # Handle cases where tail fails (file not found, permission error, etc.)
                    files_not_found.append(log_file)
                    error_message = result.stderr.strip() if result.stderr else "Unknown error"
                    self.append_output(f"  -> Could not read {log_file}: {error_message}\n", "red")
            except FileNotFoundError:
                 self.append_output("Error: 'wsl' command not found. Is WSL installed and in PATH?\n", "red")
                 return # Cannot proceed without WSL
            except Exception as e:
                self.append_output(f"Error running tail for {log_file}: {e}\n", "red")
                files_not_found.append(log_file)

        if files_not_found:
            self.append_output(f"Warning: Could not read the following files: {', '.join(files_not_found)}\n", "yellow")

        if not combined_log_content:
            self.append_output("No log content was gathered. Diagnostics file not created.\n", "red")
            return

        self.append_output("Log gathering complete. Please choose where to save the diagnostics file.")

        # Prompt user for save location (must run in main thread)
        def ask_save_file():
            try:
                # Default filename suggestion with timestamp
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                default_filename = f"chim_diagnostics_{timestamp}.cfg"
                
                save_path = tkinter.filedialog.asksaveasfilename(
                    title="Save Diagnostics File",
                    defaultextension=".cfg",
                    filetypes=[("Config files", "*.cfg"), ("All files", "*.*")],
                    initialfile=default_filename
                )

                if save_path:
                    try:
                        with open(save_path, 'w', encoding='utf-8') as f:
                            f.write(combined_log_content)
                        self.append_output(f"\nDiagnostics file saved to: {save_path}\n", "green") # Added newline at the start
                        # Add the user message about AIAgent.log
                        user_message = (
                            "MAKE SURE TO SHARE YOUR AIAgent.log\n"
                            "Located in:\n"
                            r"C:\Users\YOURUSER\Documents\My Games\Skyrim Special Edition\SKSE\Plugins\AIAgent.log"
                            "\nOR\n"
                            r"C:\Users\YOURUSER\Documents\My Games\Skyrim\SKSE\Plugins\AIAgent.log"
                        )
                        self.append_output(f"\n{user_message}\n", "yellow") # Use yellow for visibility
                    except Exception as e:
                        self.append_output(f"Error saving diagnostics file: {e}\n", "red")
                        messagebox.showerror("Save Error", f"Could not save the diagnostics file:\n{e}")
                else:
                    self.append_output("Save operation cancelled.\n")
            except Exception as e:
                # Catch potential errors during filedialog display
                self.append_output(f"Error opening save dialog: {e}\n", "red")
                messagebox.showerror("Dialog Error", f"Could not open the save file dialog:\n{e}")
                
        # Schedule the save dialog in the main GUI thread
        self.after(0, ask_save_file)

    def check_distro_version(self):
        """Check if a newer distro version is available and update the status label."""
        # Use after(0, ...) to ensure UI updates happen on the main thread
        update_label_config = lambda config: self.after(0, self.distro_version_label.config, config)

        # Initial state while checking
        update_label_config({"text": "Checking Distro Version...", "fg": "white"})

        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0

            # Check repository version directly with curl for consistency
            check_repo_version_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                                "curl -s https://raw.githubusercontent.com/abeiro/dwemerdistro/main/.version.txt"]
            
            repo_version_result = subprocess.run(
                check_repo_version_cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            repo_version = repo_version_result.stdout.strip()
            
            # Remove debug output
            # self.append_output(f"[DEBUG] Repository version: {repo_version}\n")
            
            if not repo_version:
                final_text = "Repository version not found"
                text_color = "yellow"
                update_label_config({"text": final_text, "fg": text_color})
                return

            # Check current installed version - check both possible locations
            check_current_version_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                                   "cat /home/dwemer/dwemerdistro/.version.txt 2>/dev/null || cat /etc/.version.txt 2>/dev/null || echo 'not_installed'"]
            
            current_version_result = subprocess.run(
                check_current_version_cmd,
                capture_output=True,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            current_version = current_version_result.stdout.strip()
            
            # Remove debug output
            # self.append_output(f"[DEBUG] Local version: {current_version}\n")
            
            # Force update local version if it's different from repo (for testing)
            force_update = False
            if force_update and current_version != "not_installed" and current_version != repo_version:
                update_version_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                                 f"echo '{repo_version}' | sudo tee /home/dwemer/dwemerdistro/.version.txt > /dev/null"]
                subprocess.run(
                    update_version_cmd,
                    startupinfo=startupinfo,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                # Remove debug output
                # self.append_output(f"[DEBUG] Forced local version update to: {repo_version}\n")
                current_version = repo_version
            
            final_text = ""
            text_color = "white" # Default color

            if current_version == "not_installed":
                # No version file found - likely first run
                final_text = f"Distro Update Available!"
                text_color = "red"
            elif current_version:
                # Simple string comparison first for exact match
                if current_version == repo_version:
                    final_text = f"Distro is Up-to-date"
                    text_color = "lime green"
                else:
                    # Use semantic version comparison as backup
                    comparison = self.compare_versions(current_version, repo_version)
                    # Remove debug output
                    # self.append_output(f"[DEBUG] Version comparison result: {comparison}\n")
                    
                    if comparison < 0:
                        # Update available
                        final_text = f"Distro Update Available!"
                        text_color = "red"
                    else:
                        # Up-to-date or newer
                        final_text = f"Distro is Up-to-date"
                        text_color = "lime green"
            else:
                # Error checking current version 
                final_text = "Error checking local version"
                text_color = "yellow"
        except Exception as e:
            final_text = f"Distro Version Check Failed: {e}"
            text_color = "yellow"
        
        # Update the label with final text and color
        update_label_config({"text": final_text, "fg": text_color})

    def update_all(self):
        """Perform a complete update of both distro and server components."""
        threading.Thread(target=self.update_all_thread, daemon=True).start()

    def update_all_thread(self):
        try:
            # First confirm the update with the user
            confirm = messagebox.askyesno("Update System", "This will update both the CHIM distro and server components. Are you sure?")
            if not confirm:
                self.append_output("Update canceled.\n")
                return

            # Update status to indicate we're working
            self.after(0, lambda: self.update_status_label.config(
                text="Running update...",
                fg="white"
            ))

            self.append_output("Starting full system update...\n")
            
            # Run everything in a single command
            self.append_output("\nSTEP 1: Core System Update\n", "green")
            self.append_output("Running update script...\n")
            
            # Prepare the combined update command
            # This will run the distro update and then echo a marker, then run the server update
            combined_cmd = ["wsl", "-d", "DwemerAI4Skyrim3", "-u", "dwemer", "--", "bash", "-c", 
                        "cd /home/dwemer/dwemerdistro && " +
                        "git fetch origin && git reset --hard origin/main && " +
                        "chmod +x update.sh && echo 'dwemer' | sudo -S ./update.sh && " +
                        "echo '=====MARKER:BEGIN_SERVER_UPDATE=====' && " +
                        "/usr/local/bin/update_gws"]
            
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # 0 = SW_HIDE
            
            # Start the combined process
            update_process = subprocess.Popen(
                combined_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
            
            # Variables to track update phases
            distro_update_complete = False
            server_update_started = False
            server_update_complete = False
            
            # Read output line by line
            for line in update_process.stdout:
                # Check for our marker line
                if "=====MARKER:BEGIN_SERVER_UPDATE=====" in line:
                    distro_update_complete = True
                    server_update_started = True
                    self.append_output("\nSTEP 2: CHIM Server & Components Update\n", "green")
                    continue  # Skip the marker line itself
                
                # Output the line
                self.append_output(line)
                
                # Check if server update is complete (look for common completion messages)
                if server_update_started and ("Successfully" in line or "Completed" in line):
                    server_update_complete = True
            
            # Process has ended
            update_process.wait()
            
            # Check the final state
            if update_process.returncode == 0 and distro_update_complete:
                # Get the current branch for the success message
                current_branch = self.get_current_branch() or "unknown"
                
                if server_update_complete:
                    self.append_output(f"Full system update completed successfully! Branch: {current_branch}\n", "green")
                else:
                    self.append_output(f"Update completed. Branch: {current_branch}\n", "green")
                    
                # Set update status to show it's up-to-date
                self.after(0, lambda: self.update_status_label.config(
                    text=f"Up-to-date ({current_branch})",
                    fg="lime green"
                ))
            else:
                # Something went wrong
                if not distro_update_complete:
                    self.append_output("Distro update did not complete successfully.\n", "red")
                elif not server_update_complete:
                    self.append_output("Server update may not have completed successfully.\n", "red")
                
                self.after(0, lambda: self.update_status_label.config(
                    text="Update may have issues - see log",
                    fg="red"
                ))
                
        except Exception as e:
            self.append_output(f"Error during update: {str(e)}\n", "red")
            import traceback
            self.append_output(f"Traceback: {traceback.format_exc()}\n", "red")
            self.after(0, lambda: self.update_status_label.config(
                text="Update error - see log",
                fg="red"
            ))
        finally:
            # Run the check for updates after a short delay to verify
            self.after(2000, lambda: threading.Thread(target=self.check_for_updates, daemon=True).start())

if __name__ == "__main__":
    app = CHIMLauncher()
    app.mainloop()
