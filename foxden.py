#!/usr/bin/env python3
import os
import sys
import subprocess
import re
import json
import platform
import pwd
import grp
import shutil
import threading
import time
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Union

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gio, GLib, GdkPixbuf, Pango

# Set up logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SystemAdminApp(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='com.arinovais.foxden')
        self.connect('activate', self.on_activate)

        # System detection
        self.system = platform.system()
        self.distro = self._detect_distro()
        self.package_manager = self._detect_package_manager()

        # Initialize data
        self.users = []
        self.groups = []
        self.packages = []
        self.installed_packages = []
        self.network_interfaces = []
        self.firewall_rules = []
        self.services = []
        self.system_logs = []

        # UI state
        self.current_view = None
        self.process_running = False
        self.status_message = ""

    def _detect_distro(self) -> str:
        """Detect the Linux distribution or macOS version"""
        if self.system == "Darwin":
            return f"macOS {platform.mac_ver()[0]}"
        elif self.system == "Linux":
            try:
                with open("/etc/os-release", "r") as f:
                    for line in f:
                        if line.startswith("PRETTY_NAME="):
                            return line.split("=")[1].strip('"')
            except:
                pass
        return self.system

    def _detect_package_manager(self) -> str:
        """Detect the available package manager"""
        if self.system == "Darwin":
            return "brew"
        elif self.system == "Linux":
            for pm in ["apt", "dnf", "pacman", "zypper"]:
                if shutil.which(pm):
                    return pm
        return "unknown"

    def refresh_all_data(self):
        """Refresh all data"""
        self.win.refresh_users()
        self.win.refresh_firewall()
        self.win.refresh_network()
        self.win.refresh_packages()
        self.win.refresh_services()
        self.win.refresh_logs()
        self.win.refresh_system()

    def on_activate(self, app):
        """Initialize the application"""
        self.win = MainWindow(application=app, system_admin=self)
        self.win.present()

        # Load initial data
        self.refresh_all_data()

class MainWindow(Gtk.ApplicationWindow):
    def __init__(self, **kwargs):
        super().__init__(application=kwargs.get('application'))
        self.system_admin = kwargs.get('system_admin')
        self.set_title("Foxden")
        self.set_default_size(1200, 800)

        # Create main layout
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        self.set_child(self.main_box)

        # Create header bar
        self.header_bar = Gtk.HeaderBar()
        self.main_box.append(self.header_bar)

        # Create main content
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.main_box.append(self.content_box)

        # Create sidebar
        self.create_sidebar()

        # Create content area
        self.create_content_area()

        # Create status bar
        self.create_status_bar()

        # Show initial view
        self.switch_view("dashboard")

    def create_sidebar(self):
        """Create the navigation sidebar"""
        self.sidebar = Gtk.ListBox()
        self.sidebar.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.sidebar.connect("row-selected", self.on_sidebar_selected)

        # Add sidebar items
        items = [
            ("dashboard", "Dashboard", "view-grid-symbolic"),
            ("users", "Users", "system-users-symbolic"),
            ("firewall", "Firewall", "firewall-symbolic"),
            ("network", "Network", "network-wired-symbolic"),
            ("packages", "Packages", "package-x-generic-symbolic"),
            ("services", "Services", "emblem-system-symbolic"),
            ("logs", "Logs", "document-text-symbolic"),
            ("system", "System Info", "computer-symbolic"),
        ]

        for item_id, title, icon_name in items:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_child(box)

            icon = Gtk.Image.new_from_icon_name(icon_name)
            icon.set_icon_size(Gtk.IconSize.LARGE)
            box.append(icon)

            label = Gtk.Label(label=title)
            box.append(label)

            row.set_name(item_id)
            self.sidebar.append(row)

        # Add sidebar to a scrolled window
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_child(self.sidebar)
        scrolled.set_size_request(250, -1)

        # Add to a frame
        frame = Gtk.Frame()
        frame.set_child(scrolled)
        self.content_box.append(frame)

    def create_content_area(self):
        """Create the main content area"""
        self.content_stack = Gtk.Stack()
        self.content_stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)

        # Create views
        self.create_dashboard_view()
        self.create_users_view()
        self.create_firewall_view()
        self.create_network_view()
        self.create_packages_view()
        self.create_services_view()
        self.create_logs_view()
        self.create_system_view()

        self.content_box.append(self.content_stack)

    def create_status_bar(self):
        """Create the status bar"""
        self.status_bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.status_bar.set_margin_top(5)
        self.status_bar.set_margin_bottom(5)
        self.status_bar.set_margin_start(10)
        self.status_bar.set_margin_end(10)

        self.status_label = Gtk.Label(label="Ready")
        self.status_label.set_halign(Gtk.Align.START)
        self.status_bar.append(self.status_label)

        self.spinner = Gtk.Spinner()
        self.status_bar.append(self.spinner)

        self.main_box.append(self.status_bar)

    def on_sidebar_selected(self, listbox, row):
        """Handle sidebar selection"""
        if row:
            view_name = row.get_name()
            self.switch_view(view_name)

    def switch_view(self, view_name):
        """Switch to the specified view"""
        self.content_stack.set_visible_child_name(view_name)
        self.system_admin.current_view = view_name

        # Refresh data for the selected view
        if view_name == "users":
            self.refresh_users()
        elif view_name == "firewall":
            self.refresh_firewall()
        elif view_name == "network":
            self.refresh_network()
        elif view_name == "packages":
            self.refresh_packages()
        elif view_name == "services":
            self.refresh_services()
        elif view_name == "logs":
            self.refresh_logs()
        elif view_name == "system":
            self.refresh_system()

    def set_status(self, message, show_spinner=False):
        """Update the status bar"""
        self.status_label.set_text(message)
        if show_spinner:
            self.spinner.start()
        else:
            self.spinner.stop()

    def show_message(self, title, message, message_type=Gtk.MessageType.INFO):
        """Show a message dialog"""
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=message_type,
            buttons=Gtk.ButtonsType.OK,
            text=title
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label=message)
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Show the dialog
        dialog.present()

        # Connect response signal to close the dialog
        def on_response(dialog, response):
            dialog.close()

        dialog.connect("response", on_response)

    def run_command(self, command, callback=None):
        """Run a command in a thread and optionally call a callback with the result"""
        def thread_func():
            try:
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                stdout, stderr = process.communicate()
                result = {
                    "returncode": process.returncode,
                    "stdout": stdout,
                    "stderr": stderr
                }
                if callback:
                    GLib.idle_add(callback, result)
            except Exception as e:
                logger.error(f"Error running command: {command}: {e}")
                if callback:
                    GLib.idle_add(callback, {"returncode": -1, "stdout": "", "stderr": str(e)})

        thread = threading.Thread(target=thread_func)
        thread.daemon = True
        thread.start()

    # View creation methods
    def create_dashboard_view(self):
        """Create the dashboard view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        # Title
        title = Gtk.Label(label="System Dashboard")
        title.add_css_class("title-1")
        box.append(title)

        # System info
        info_frame = Gtk.Frame(label="System Information")
        info_frame.set_margin_top(10)
        info_grid = Gtk.Grid()
        info_grid.set_row_spacing(5)
        info_grid.set_column_spacing(10)
        info_grid.set_margin_top(10)
        info_grid.set_margin_bottom(10)
        info_grid.set_margin_start(10)
        info_grid.set_margin_end(10)

        info_grid.attach(Gtk.Label(label="Operating System:"), 0, 0, 1, 1)
        info_grid.attach(Gtk.Label(label=self.system_admin.distro), 1, 0, 1, 1)

        info_grid.attach(Gtk.Label(label="Package Manager:"), 0, 1, 1, 1)
        info_grid.attach(Gtk.Label(label=self.system_admin.package_manager), 1, 1, 1, 1)

        info_grid.attach(Gtk.Label(label="Kernel:"), 0, 2, 1, 1)
        info_grid.attach(Gtk.Label(label=platform.release()), 1, 2, 1, 1)

        info_grid.attach(Gtk.Label(label="Architecture:"), 0, 3, 1, 1)
        info_grid.attach(Gtk.Label(label=platform.machine()), 1, 3, 1, 1)

        info_frame.set_child(info_grid)
        box.append(info_frame)

        # Quick actions
        actions_frame = Gtk.Frame(label="Quick Actions")
        actions_frame.set_margin_top(10)
        actions_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        actions_box.set_margin_top(10)
        actions_box.set_margin_bottom(10)
        actions_box.set_margin_start(10)
        actions_box.set_margin_end(10)

        update_btn = Gtk.Button(label="Update System")
        update_btn.connect("clicked", self.on_update_system)
        actions_box.append(update_btn)

        clean_btn = Gtk.Button(label="Clean System")
        clean_btn.connect("clicked", self.on_clean_system)
        actions_box.append(clean_btn)

        actions_frame.set_child(actions_box)
        box.append(actions_frame)

        # Resource usage
        resource_frame = Gtk.Frame(label="Resource Usage")
        resource_frame.set_margin_top(10)
        resource_grid = Gtk.Grid()
        resource_grid.set_row_spacing(10)
        resource_grid.set_column_spacing(10)
        resource_grid.set_margin_top(10)
        resource_grid.set_margin_bottom(10)
        resource_grid.set_margin_start(10)
        resource_grid.set_margin_end(10)

        # CPU usage
        resource_grid.attach(Gtk.Label(label="CPU Usage:"), 0, 0, 1, 1)
        cpu_progress = Gtk.ProgressBar()
        cpu_progress.set_text("0%")
        cpu_progress.set_show_text(True)
        cpu_progress.set_size_request(200, -1)
        resource_grid.attach(cpu_progress, 1, 0, 1, 1)

        # Memory usage
        resource_grid.attach(Gtk.Label(label="Memory Usage:"), 0, 1, 1, 1)
        mem_progress = Gtk.ProgressBar()
        mem_progress.set_text("0%")
        mem_progress.set_show_text(True)
        mem_progress.set_size_request(200, -1)
        resource_grid.attach(mem_progress, 1, 1, 1, 1)

        # Disk usage
        resource_grid.attach(Gtk.Label(label="Disk Usage:"), 0, 2, 1, 1)
        disk_progress = Gtk.ProgressBar()
        disk_progress.set_text("0%")
        disk_progress.set_show_text(True)
        disk_progress.set_size_request(200, -1)
        resource_grid.attach(disk_progress, 1, 2, 1, 1)

        resource_frame.set_child(resource_grid)
        box.append(resource_frame)

        # Add to stack
        self.content_stack.add_named(box, "dashboard")

        # Store references for updating
        self.dashboard_cpu_progress = cpu_progress
        self.dashboard_mem_progress = mem_progress
        self.dashboard_disk_progress = disk_progress

        # Start resource monitoring
        self.start_resource_monitoring()

    def create_users_view(self):
        """Create the users management view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        # Title
        title = Gtk.Label(label="User Management")
        title.add_css_class("title-1")
        box.append(title)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar.set_margin_bottom(10)

        add_user_btn = Gtk.Button(label="Add User")
        add_user_btn.connect("clicked", self.on_add_user)
        toolbar.append(add_user_btn)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", self.refresh_users)
        toolbar.append(refresh_btn)

        box.append(toolbar)

        # Users list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self.users_list = Gtk.ListBox()
        self.users_list.connect("row-activated", self.on_user_selected)
        scrolled.set_child(self.users_list)

        box.append(scrolled)

        # Add to stack
        self.content_stack.add_named(box, "users")

    def create_firewall_view(self):
        """Create the firewall management view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        # Title
        title = Gtk.Label(label="Firewall Management")
        title.add_css_class("title-1")
        box.append(title)

        # Status
        status_frame = Gtk.Frame(label="Firewall Status")
        status_frame.set_margin_top(10)
        status_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        status_box.set_margin_top(10)
        status_box.set_margin_bottom(10)
        status_box.set_margin_start(10)
        status_box.set_margin_end(10)

        status_box.append(Gtk.Label(label="Status:"))
        self.firewall_status_label = Gtk.Label(label="Unknown")
        status_box.append(self.firewall_status_label)

        # Toggle switch
        self.firewall_switch = Gtk.Switch()
        self.firewall_switch.connect("notify::active", self.on_firewall_toggle)
        status_box.append(self.firewall_switch)

        status_frame.set_child(status_box)
        box.append(status_frame)

        # Rules
        rules_frame = Gtk.Frame(label="Firewall Rules")
        rules_frame.set_margin_top(10)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar.set_margin_bottom(10)

        add_rule_btn = Gtk.Button(label="Add Rule")
        add_rule_btn.connect("clicked", self.on_add_firewall_rule)
        toolbar.append(add_rule_btn)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", self.refresh_firewall)
        toolbar.append(refresh_btn)

        # Rules list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_size_request(-1, 300)

        self.firewall_rules_list = Gtk.ListBox()
        scrolled.set_child(self.firewall_rules_list)

        # Add toolbar and scrolled to a box
        rules_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        rules_box.append(toolbar)
        rules_box.append(scrolled)

        rules_frame.set_child(rules_box)
        box.append(rules_frame)

        # Add to stack
        self.content_stack.add_named(box, "firewall")

    def create_network_view(self):
        """Create the network management view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        # Title
        title = Gtk.Label(label="Network Management")
        title.add_css_class("title-1")
        box.append(title)

        # Interfaces
        interfaces_frame = Gtk.Frame(label="Network Interfaces")
        interfaces_frame.set_margin_top(10)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar.set_margin_bottom(10)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", self.refresh_network)
        toolbar.append(refresh_btn)

        # Interfaces list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)
        scrolled.set_size_request(-1, 300)

        self.network_interfaces_list = Gtk.ListBox()
        scrolled.set_child(self.network_interfaces_list)

        # Add toolbar and scrolled to a box
        interfaces_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        interfaces_box.append(toolbar)
        interfaces_box.append(scrolled)

        interfaces_frame.set_child(interfaces_box)
        box.append(interfaces_frame)

        # Connections
        connections_frame = Gtk.Frame(label="Network Connections")
        connections_frame.set_margin_top(10)

        # Connections list
        scrolled2 = Gtk.ScrolledWindow()
        scrolled2.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled2.set_vexpand(True)
        scrolled2.set_size_request(-1, 300)

        self.network_connections_list = Gtk.ListBox()
        scrolled2.set_child(self.network_connections_list)

        connections_frame.set_child(scrolled2)
        box.append(connections_frame)

        # Add to stack
        self.content_stack.add_named(box, "network")

    def create_packages_view(self):
        """Create the package management view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        # Title
        title = Gtk.Label(label="Package Management")
        title.add_css_class("title-1")
        box.append(title)

        # Search bar
        search_bar = Gtk.SearchBar()
        search_entry = Gtk.SearchEntry()
        search_bar.connect_entry(search_entry)
        search_entry.connect("search-changed", self.on_package_search)

        box.append(search_bar)
        box.append(search_entry)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar.set_margin_bottom(10)

        install_btn = Gtk.Button(label="Install")
        install_btn.connect("clicked", self.on_install_package)
        toolbar.append(install_btn)

        remove_btn = Gtk.Button(label="Remove")
        remove_btn.connect("clicked", self.on_remove_package)
        toolbar.append(remove_btn)

        update_btn = Gtk.Button(label="Update")
        update_btn.connect("clicked", self.on_update_package)
        toolbar.append(update_btn)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", self.refresh_packages)
        toolbar.append(refresh_btn)

        box.append(toolbar)

        # Package tabs
        notebook = Gtk.Notebook()

        # Installed packages tab
        installed_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        scrolled_installed = Gtk.ScrolledWindow()
        scrolled_installed.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_installed.set_vexpand(True)

        self.installed_packages_list = Gtk.ListBox()
        self.installed_packages_list.connect("row-activated", self.on_package_selected)
        scrolled_installed.set_child(self.installed_packages_list)

        installed_tab.append(scrolled_installed)
        notebook.append_page(installed_tab, Gtk.Label(label="Installed"))

        # Available packages tab
        available_tab = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        scrolled_available = Gtk.ScrolledWindow()
        scrolled_available.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled_available.set_vexpand(True)

        self.available_packages_list = Gtk.ListBox()
        self.available_packages_list.connect("row-activated", self.on_package_selected)
        scrolled_available.set_child(self.available_packages_list)

        available_tab.append(scrolled_available)
        notebook.append_page(available_tab, Gtk.Label(label="Available"))

        box.append(notebook)

        # Add to stack
        self.content_stack.add_named(box, "packages")

        # Store reference for search
        self.package_search_entry = search_entry

    def create_services_view(self):
        """Create the services management view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        # Title
        title = Gtk.Label(label="Service Management")
        title.add_css_class("title-1")
        box.append(title)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar.set_margin_bottom(10)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", self.refresh_services)
        toolbar.append(refresh_btn)

        box.append(toolbar)

        # Services list
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self.services_list = Gtk.ListBox()
        scrolled.set_child(self.services_list)

        box.append(scrolled)

        # Add to stack
        self.content_stack.add_named(box, "services")

    def create_logs_view(self):
        """Create the logs viewer view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        # Title
        title = Gtk.Label(label="System Logs")
        title.add_css_class("title-1")
        box.append(title)

        # Log source selector
        log_source_frame = Gtk.Frame(label="Log Source")
        log_source_frame.set_margin_top(10)
        log_source_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        log_source_box.set_margin_top(10)
        log_source_box.set_margin_bottom(10)
        log_source_box.set_margin_start(10)
        log_source_box.set_margin_end(10)

        log_source_box.append(Gtk.Label(label="Select Log Source:"))
        self.log_source_combo = Gtk.ComboBoxText()
        self.log_source_combo.append_text("System Log")
        self.log_source_combo.append_text("Authentication Log")
        self.log_source_combo.append_text("Kernel Log")
        self.log_source_combo.append_text("Package Log")
        self.log_source_combo.connect("changed", self.on_log_source_changed)
        log_source_box.append(self.log_source_combo)

        log_source_frame.set_child(log_source_box)
        box.append(log_source_frame)

        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        toolbar.set_margin_bottom(10)

        refresh_btn = Gtk.Button(label="Refresh")
        refresh_btn.connect("clicked", self.refresh_logs)
        toolbar.append(refresh_btn)

        clear_btn = Gtk.Button(label="Clear")
        clear_btn.connect("clicked", self.on_clear_logs)
        toolbar.append(clear_btn)

        export_btn = Gtk.Button(label="Export")
        export_btn.connect("clicked", self.on_export_logs)
        toolbar.append(export_btn)

        box.append(toolbar)

        # Log viewer
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_vexpand(True)

        self.log_text_view = Gtk.TextView()
        self.log_text_view.set_editable(False)
        self.log_text_view.set_monospace(True)

        scrolled.set_child(self.log_text_view)

        box.append(scrolled)

        # Add to stack
        self.content_stack.add_named(box, "logs")

    def create_system_view(self):
        """Create the system information view"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.set_margin_top(20)
        box.set_margin_bottom(20)
        box.set_margin_start(20)
        box.set_margin_end(20)

        # Title
        title = Gtk.Label(label="System Information")
        title.add_css_class("title-1")
        box.append(title)

        # System info
        system_frame = Gtk.Frame(label="System Information")
        system_frame.set_margin_top(10)
        system_grid = Gtk.Grid()
        system_grid.set_row_spacing(5)
        system_grid.set_column_spacing(10)
        system_grid.set_margin_top(10)
        system_grid.set_margin_bottom(10)
        system_grid.set_margin_start(10)
        system_grid.set_margin_end(10)

        system_grid.attach(Gtk.Label(label="Hostname:"), 0, 0, 1, 1)
        system_grid.attach(Gtk.Label(label=platform.node()), 1, 0, 1, 1)

        system_grid.attach(Gtk.Label(label="Operating System:"), 0, 1, 1, 1)
        system_grid.attach(Gtk.Label(label=self.system_admin.distro), 1, 1, 1, 1)

        system_grid.attach(Gtk.Label(label="Kernel:"), 0, 2, 1, 1)
        system_grid.attach(Gtk.Label(label=platform.release()), 1, 2, 1, 1)

        system_grid.attach(Gtk.Label(label="Architecture:"), 0, 3, 1, 1)
        system_grid.attach(Gtk.Label(label=platform.machine()), 1, 3, 1, 1)

        system_grid.attach(Gtk.Label(label="Uptime:"), 0, 4, 1, 1)
        self.system_uptime_label = Gtk.Label(label="Unknown")
        system_grid.attach(self.system_uptime_label, 1, 4, 1, 1)

        system_frame.set_child(system_grid)
        box.append(system_frame)

        # Hardware info
        hardware_frame = Gtk.Frame(label="Hardware Information")
        hardware_frame.set_margin_top(10)
        hardware_grid = Gtk.Grid()
        hardware_grid.set_row_spacing(5)
        hardware_grid.set_column_spacing(10)
        hardware_grid.set_margin_top(10)
        hardware_grid.set_margin_bottom(10)
        hardware_grid.set_margin_start(10)
        hardware_grid.set_margin_end(10)

        hardware_grid.attach(Gtk.Label(label="CPU:"), 0, 0, 1, 1)
        self.system_cpu_label = Gtk.Label(label="Unknown")
        hardware_grid.attach(self.system_cpu_label, 1, 0, 1, 1)

        hardware_grid.attach(Gtk.Label(label="Memory:"), 0, 1, 1, 1)
        self.system_memory_label = Gtk.Label(label="Unknown")
        hardware_grid.attach(self.system_memory_label, 1, 1, 1, 1)

        hardware_grid.attach(Gtk.Label(label="Disk:"), 0, 2, 1, 1)
        self.system_disk_label = Gtk.Label(label="Unknown")
        hardware_grid.attach(self.system_disk_label, 1, 2, 1, 1)

        hardware_frame.set_child(hardware_grid)
        box.append(hardware_frame)

        # Software info
        software_frame = Gtk.Frame(label="Software Information")
        software_frame.set_margin_top(10)
        software_grid = Gtk.Grid()
        software_grid.set_row_spacing(5)
        software_grid.set_column_spacing(10)
        software_grid.set_margin_top(10)
        software_grid.set_margin_bottom(10)
        software_grid.set_margin_start(10)
        software_grid.set_margin_end(10)

        software_grid.attach(Gtk.Label(label="Python:"), 0, 0, 1, 1)
        software_grid.attach(Gtk.Label(label=platform.python_version()), 1, 0, 1, 1)

        software_grid.attach(Gtk.Label(label="GTK:"), 0, 1, 1, 1)
        software_grid.attach(Gtk.Label(label=f"{Gtk.get_major_version()}.{Gtk.get_minor_version()}.{Gtk.get_micro_version()}"), 1, 1, 1, 1)

        software_frame.set_child(software_grid)
        box.append(software_frame)

        # Add to stack
        self.content_stack.add_named(box, "system")

    # Data refresh methods
    def refresh_users(self):
        """Refresh the users list"""
        def callback(result):
            if result["returncode"] == 0:
                self.system_admin.users = []
                for line in result["stdout"].splitlines():
                    parts = line.split(":")
                    if len(parts) >= 7:
                        user = {
                            "username": parts[0],
                            "password": parts[1],
                            "uid": parts[2],
                            "gid": parts[3],
                            "info": parts[4],
                            "home": parts[5],
                            "shell": parts[6]
                        }
                        self.system_admin.users.append(user)

                # Update UI
                self.update_users_list()
                self.set_status("Users refreshed")
            else:
                self.set_status(f"Error refreshing users: {result['stderr']}")
                self.show_message("Error", f"Error refreshing users: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Refreshing users...", True)
        self.run_command("cat /etc/passwd", callback)

    def update_users_list(self):
        """Update the users list in the UI"""
        # Clear existing rows
        child = self.users_list.get_first_child()
        while child:
            self.users_list.remove(child)
            child = self.users_list.get_first_child()

        # Add users
        for user in self.system_admin.users:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            row.set_child(box)

            title_label = Gtk.Label(label=user["username"])
            title_label.add_css_class("heading")
            box.append(title_label)

            subtitle_label = Gtk.Label(label=f"UID: {user['uid']}, Home: {user['home']}")
            subtitle_label.add_css_class("caption")
            box.append(subtitle_label)

            # Add action buttons
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

            edit_btn = Gtk.Button(label="Edit")
            edit_btn.connect("clicked", lambda btn, u=user: self.on_edit_user(u))
            button_box.append(edit_btn)

            delete_btn = Gtk.Button(label="Delete")
            delete_btn.connect("clicked", lambda btn, u=user: self.on_delete_user(u))
            button_box.append(delete_btn)

            box.append(button_box)

            self.users_list.append(row)

    def refresh_firewall(self):
        """Refresh the firewall status and rules"""
        def callback(result):
            if result["returncode"] == 0:
                # Parse firewall status
                if "active" in result["stdout"]:
                    self.firewall_switch.set_active(True)
                    self.firewall_status_label.set_text("Active")
                else:
                    self.firewall_switch.set_active(False)
                    self.firewall_status_label.set_text("Inactive")

                # Parse firewall rules
                self.system_admin.firewall_rules = []
                for line in result["stdout"].splitlines():
                    if line.strip() and not line.startswith("Status:"):
                        self.system_admin.firewall_rules.append(line.strip())

                # Update UI
                self.update_firewall_rules_list()
                self.set_status("Firewall refreshed")
            else:
                self.set_status(f"Error refreshing firewall: {result['stderr']}")
                self.show_message("Error", f"Error refreshing firewall: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Refreshing firewall...", True)

        # Use different commands based on the system
        if self.system_admin.system == "Linux":
            if shutil.which("ufw"):
                self.run_command("ufw status verbose", callback)
            elif shutil.which("firewalld"):
                self.run_command("firewall-cmd --list-all", callback)
            elif shutil.which("iptables"):
                self.run_command("iptables -L -n -v", callback)
            else:
                self.set_status("No supported firewall found")
                self.show_message("Error", "No supported firewall found", Gtk.MessageType.ERROR)
        elif self.system_admin.system == "Darwin":
            self.run_command("sudo pfctl -s rules", callback)
        else:
            self.set_status("Unsupported system for firewall management")
            self.show_message("Error", "Unsupported system for firewall management", Gtk.MessageType.ERROR)

    def update_firewall_rules_list(self):
        """Update the firewall rules list in the UI"""
        # Clear existing rows
        child = self.firewall_rules_list.get_first_child()
        while child:
            self.firewall_rules_list.remove(child)
            child = self.firewall_rules_list.get_first_child()

        # Add rules
        for rule in self.system_admin.firewall_rules:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.set_child(box)

            label = Gtk.Label(label=rule)
            label.set_wrap(True)
            box.append(label)

            # Add action buttons
            delete_btn = Gtk.Button(label="Delete")
            delete_btn.connect("clicked", lambda btn, r=rule: self.on_delete_firewall_rule(r))
            box.append(delete_btn)

            self.firewall_rules_list.append(row)

    def refresh_network(self):
        """Refresh the network interfaces and connections"""
        def interfaces_callback(result):
            if result["returncode"] == 0:
                # Parse network interfaces
                self.system_admin.network_interfaces = []
                for line in result["stdout"].splitlines():
                    if line.strip():
                        parts = line.split()
                        if len(parts) >= 2:
                            interface = {
                                "name": parts[0],
                                "status": parts[1] if len(parts) > 1 else "Unknown",
                                "ip": parts[2] if len(parts) > 2 else "Unknown",
                                "mac": parts[3] if len(parts) > 3 else "Unknown"
                            }
                            self.system_admin.network_interfaces.append(interface)

                # Update UI
                self.update_network_interfaces_list()
                self.set_status("Network refreshed")
            else:
                self.set_status(f"Error refreshing network: {result['stderr']}")
                self.show_message("Error", f"Error refreshing network: {result['stderr']}", Gtk.MessageType.ERROR)

        def connections_callback(result):
            if result["returncode"] == 0:
                # Parse network connections
                connections = []
                for line in result["stdout"].splitlines():
                    if line.strip() and not line.startswith("Proto"):
                        parts = line.split()
                        if len(parts) >= 4:
                            connection = {
                                "protocol": parts[0],
                                "local": parts[3],
                                "foreign": parts[4] if len(parts) > 4 else "N/A",
                                "state": parts[5] if len(parts) > 5 else "N/A"
                            }
                            connections.append(connection)

                # Update UI
                self.update_network_connections_list(connections)
            else:
                self.set_status(f"Error refreshing network connections: {result['stderr']}")
                self.show_message("Error", f"Error refreshing network connections: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Refreshing network...", True)

        # Use different commands based on the system
        if self.system_admin.system == "Linux":
            self.run_command("ip addr show", interfaces_callback)
            self.run_command("netstat -tuln", connections_callback)
        elif self.system_admin.system == "Darwin":
            self.run_command("ifconfig", interfaces_callback)
            self.run_command("netstat -an", connections_callback)
        else:
            self.set_status("Unsupported system for network management")
            self.show_message("Error", "Unsupported system for network management", Gtk.MessageType.ERROR)

    def update_network_interfaces_list(self):
        """Update the network interfaces list in the UI"""
        # Clear existing rows
        child = self.network_interfaces_list.get_first_child()
        while child:
            self.network_interfaces_list.remove(child)
            child = self.network_interfaces_list.get_first_child()

        # Add interfaces
        for interface in self.system_admin.network_interfaces:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            row.set_child(box)

            title_label = Gtk.Label(label=interface["name"])
            title_label.add_css_class("heading")
            box.append(title_label)

            subtitle_label = Gtk.Label(label=f"Status: {interface['status']}, IP: {interface['ip']}")
            subtitle_label.add_css_class("caption")
            box.append(subtitle_label)

            # Add action buttons
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

            config_btn = Gtk.Button(label="Configure")
            config_btn.connect("clicked", lambda btn, i=interface: self.on_configure_interface(i))
            button_box.append(config_btn)

            box.append(button_box)

            self.network_interfaces_list.append(row)

    def update_network_connections_list(self, connections):
        """Update the network connections list in the UI"""
        # Clear existing rows
        child = self.network_connections_list.get_first_child()
        while child:
            self.network_connections_list.remove(child)
            child = self.network_connections_list.get_first_child()

        # Add connections
        for connection in connections:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            row.set_child(box)

            title_label = Gtk.Label(label=f"{connection['protocol']} - {connection['local']}")
            title_label.add_css_class("heading")
            box.append(title_label)

            subtitle_label = Gtk.Label(label=f"Foreign: {connection['foreign']}, State: {connection['state']}")
            subtitle_label.add_css_class("caption")
            box.append(subtitle_label)

            self.network_connections_list.append(row)

    def refresh_packages(self, *args):
        """Refresh the packages list"""
        def installed_callback(result):
            if result["returncode"] == 0:
                # Parse installed packages
                self.system_admin.installed_packages = []
                for line in result["stdout"].splitlines():
                    if line.strip():
                        if self.system_admin.package_manager == "apt":
                            parts = line.split()
                            if len(parts) >= 2:
                                package = {
                                    "name": parts[0],
                                    "version": parts[1],
                                    "status": "installed"
                                }
                                self.system_admin.installed_packages.append(package)
                        elif self.system_admin.package_manager == "dnf":
                            parts = line.split()
                            if len(parts) >= 2:
                                package = {
                                    "name": parts[0],
                                    "version": parts[1],
                                    "status": "installed"
                                }
                                self.system_admin.installed_packages.append(package)
                        elif self.system_admin.package_manager == "pacman":
                            parts = line.split()
                            if len(parts) >= 2:
                                package = {
                                    "name": parts[0],
                                    "version": parts[1],
                                    "status": "installed"
                                }
                                self.system_admin.installed_packages.append(package)
                        elif self.system_admin.package_manager == "zypper":
                            parts = line.split("|")
                            if len(parts) >= 3:
                                package = {
                                    "name": parts[1].strip(),
                                    "version": parts[2].strip(),
                                    "status": "installed"
                                }
                                self.system_admin.installed_packages.append(package)
                        elif self.system_admin.package_manager == "brew":
                            parts = line.split()
                            if len(parts) >= 2:
                                package = {
                                    "name": parts[0],
                                    "version": parts[1],
                                    "status": "installed"
                                }
                                self.system_admin.installed_packages.append(package)

                # Update UI
                self.update_installed_packages_list()
                self.set_status("Installed packages refreshed")
            else:
                self.set_status(f"Error refreshing installed packages: {result['stderr']}")
                self.show_message("Error", f"Error refreshing installed packages: {result['stderr']}", Gtk.MessageType.ERROR)

        def available_callback(result):
            if result["returncode"] == 0:
                # Parse available packages
                self.system_admin.packages = []
                for line in result["stdout"].splitlines():
                    if line.strip():
                        if self.system_admin.package_manager == "apt":
                            parts = line.split("/")
                            if len(parts) >= 1:
                                package = {
                                    "name": parts[0],
                                    "version": "unknown",
                                    "status": "available"
                                }
                                self.system_admin.packages.append(package)
                        elif self.system_admin.package_manager == "dnf":
                            parts = line.split()
                            if len(parts) >= 1:
                                package = {
                                    "name": parts[0],
                                    "version": "unknown",
                                    "status": "available"
                                }
                                self.system_admin.packages.append(package)
                        elif self.system_admin.package_manager == "pacman":
                            parts = line.split()
                            if len(parts) >= 1:
                                package = {
                                    "name": parts[0],
                                    "version": "unknown",
                                    "status": "available"
                                }
                                self.system_admin.packages.append(package)
                        elif self.system_admin.package_manager == "zypper":
                            parts = line.split("|")
                            if len(parts) >= 2:
                                package = {
                                    "name": parts[1].strip(),
                                    "version": parts[2].strip() if len(parts) > 2 else "unknown",
                                    "status": "available"
                                }
                                self.system_admin.packages.append(package)
                        elif self.system_admin.package_manager == "brew":
                            parts = line.split()
                            if len(parts) >= 1:
                                package = {
                                    "name": parts[0],
                                    "version": "unknown",
                                    "status": "available"
                                }
                                self.system_admin.packages.append(package)

                # Update UI
                self.update_available_packages_list()
                self.set_status("Available packages refreshed")
            else:
                self.set_status(f"Error refreshing available packages: {result['stderr']}")
                self.show_message("Error", f"Error refreshing available packages: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Refreshing packages...", True)

        # Use different commands based on the package manager
        if self.system_admin.package_manager == "apt":
            self.run_command("dpkg -l", installed_callback)
            self.run_command("apt-cache search .", available_callback)
        elif self.system_admin.package_manager == "dnf":
            self.run_command("dnf list installed", installed_callback)
            self.run_command("dnf list available", available_callback)
        elif self.system_admin.package_manager == "pacman":
            self.run_command("pacman -Q", installed_callback)
            self.run_command("pacman -Sl", available_callback)
        elif self.system_admin.package_manager == "zypper":
            self.run_command("zypper search -i", installed_callback)
            self.run_command("zypper search", available_callback)
        elif self.system_admin.package_manager == "brew":
            self.run_command("brew list --versions", installed_callback)
            self.run_command("brew search", available_callback)
        else:
            self.set_status("Unsupported package manager")
            self.show_message("Error", "Unsupported package manager", Gtk.MessageType.ERROR)

    def update_installed_packages_list(self):
        """Update the installed packages list in the UI"""
        # Clear existing rows
        child = self.installed_packages_list.get_first_child()
        while child:
            self.installed_packages_list.remove(child)
            child = self.installed_packages_list.get_first_child()

        # Add packages
        for package in self.system_admin.installed_packages:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            row.set_child(box)

            title_label = Gtk.Label(label=package["name"])
            title_label.add_css_class("heading")
            box.append(title_label)

            subtitle_label = Gtk.Label(label=f"Version: {package['version']}")
            subtitle_label.add_css_class("caption")
            box.append(subtitle_label)

            # Add action buttons
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

            remove_btn = Gtk.Button(label="Remove")
            remove_btn.connect("clicked", lambda btn, p=package: self.on_remove_package(p))
            button_box.append(remove_btn)

            update_btn = Gtk.Button(label="Update")
            update_btn.connect("clicked", lambda btn, p=package: self.on_update_package(p))
            button_box.append(update_btn)

            box.append(button_box)

            self.installed_packages_list.append(row)

    def update_available_packages_list(self):
        """Update the available packages list in the UI"""
        # Clear existing rows
        child = self.available_packages_list.get_first_child()
        while child:
            self.available_packages_list.remove(child)
            child = self.available_packages_list.get_first_child()

        # Add packages
        for package in self.system_admin.packages:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            row.set_child(box)

            title_label = Gtk.Label(label=package["name"])
            title_label.add_css_class("heading")
            box.append(title_label)

            subtitle_label = Gtk.Label(label=f"Version: {package['version']}")
            subtitle_label.add_css_class("caption")
            box.append(subtitle_label)

            # Add action buttons
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

            install_btn = Gtk.Button(label="Install")
            install_btn.connect("clicked", lambda btn, p=package: self.on_install_package(p))
            button_box.append(install_btn)

            box.append(button_box)

            self.available_packages_list.append(row)

    def refresh_services(self, *args):
        """Refresh the services list"""
        def callback(result):
            if result["returncode"] == 0:
                # Parse services
                self.system_admin.services = []
                for line in result["stdout"].splitlines():
                    if line.strip() and not line.startswith("UNIT"):
                        parts = line.split()
                        if len(parts) >= 4:
                            service = {
                                "name": parts[0],
                                "load": parts[1],
                                "active": parts[2],
                                "sub": parts[3],
                                "description": " ".join(parts[4:]) if len(parts) > 4 else ""
                            }
                            self.system_admin.services.append(service)

                # Update UI
                self.update_services_list()
                self.set_status("Services refreshed")
            else:
                self.set_status(f"Error refreshing services: {result['stderr']}")
                self.show_message("Error", f"Error refreshing services: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Refreshing services...", True)

        # Use different commands based on the system
        if self.system_admin.system == "Linux":
            if shutil.which("systemctl"):
                self.run_command("systemctl list-units --type=service --all", callback)
            elif shutil.which("service"):
                self.run_command("service --status-all", callback)
            else:
                self.set_status("No supported service manager found")
                self.show_message("Error", "No supported service manager found", Gtk.MessageType.ERROR)
        elif self.system_admin.system == "Darwin":
            self.run_command("launchctl list", callback)
        else:
            self.set_status("Unsupported system for service management")
            self.show_message("Error", "Unsupported system for service management", Gtk.MessageType.ERROR)

    def update_services_list(self):
        """Update the services list in the UI"""
        # Clear existing rows
        child = self.services_list.get_first_child()
        while child:
            self.services_list.remove(child)
            child = self.services_list.get_first_child()

        # Add services
        for service in self.system_admin.services:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            row.set_child(box)

            title_label = Gtk.Label(label=service["name"])
            title_label.add_css_class("heading")
            box.append(title_label)

            subtitle_label = Gtk.Label(label=f"Status: {service['active']}/{service['sub']}, Description: {service['description']}")
            subtitle_label.add_css_class("caption")
            subtitle_label.set_wrap(True)
            box.append(subtitle_label)

            # Add action buttons
            button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)

            if service["active"] == "active":
                stop_btn = Gtk.Button(label="Stop")
                stop_btn.connect("clicked", lambda btn, s=service: self.on_stop_service(s))
                button_box.append(stop_btn)

                restart_btn = Gtk.Button(label="Restart")
                restart_btn.connect("clicked", lambda btn, s=service: self.on_restart_service(s))
                button_box.append(restart_btn)
            else:
                start_btn = Gtk.Button(label="Start")
                start_btn.connect("clicked", lambda btn, s=service: self.on_start_service(s))
                button_box.append(start_btn)

            box.append(button_box)

            self.services_list.append(row)

    def refresh_logs(self, *args):
        """Refresh the logs"""
        def callback(result):
            if result["returncode"] == 0:
                # Update UI
                buffer = self.log_text_view.get_buffer()
                buffer.set_text(result["stdout"])
                self.set_status("Logs refreshed")
            else:
                self.set_status(f"Error refreshing logs: {result['stderr']}")
                self.show_message("Error", f"Error refreshing logs: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Refreshing logs...", True)

        # Get the selected log source
        log_source = self.log_source_combo.get_active()

        # Map index to log source
        log_sources = ["system", "auth", "kern", "package"]
        if log_source < 0 or log_source >= len(log_sources):
            log_source = 0
        log_source = log_sources[log_source]

        # Use different commands based on the log source
        if log_source == "system":
            if self.system_admin.system == "Linux":
                if shutil.which("journalctl"):
                    self.run_command("journalctl -n 100", callback)
                else:
                    self.run_command("tail -n 100 /var/log/syslog", callback)
            elif self.system_admin.system == "Darwin":
                self.run_command("log show --last 1h", callback)
        elif log_source == "auth":
            if self.system_admin.system == "Linux":
                if shutil.which("journalctl"):
                    self.run_command("journalctl -n 100 -u auth", callback)
                else:
                    self.run_command("tail -n 100 /var/log/auth.log", callback)
            elif self.system_admin.system == "Darwin":
                self.run_command("log show --predicate 'process == \"authd\"' --last 1h", callback)
        elif log_source == "kern":
            if self.system_admin.system == "Linux":
                if shutil.which("journalctl"):
                    self.run_command("journalctl -n 100 -k", callback)
                else:
                    self.run_command("tail -n 100 /var/log/kern.log", callback)
            elif self.system_admin.system == "Darwin":
                self.run_command("log show --predicate 'category == \"kernel\"' --last 1h", callback)
        elif log_source == "package":
            if self.system_admin.package_manager == "apt":
                self.run_command("tail -n 100 /var/log/dpkg.log", callback)
            elif self.system_admin.package_manager == "dnf":
                self.run_command("tail -n 100 /var/log/dnf.log", callback)
            elif self.system_admin.package_manager == "pacman":
                self.run_command("tail -n 100 /var/log/pacman.log", callback)
            elif self.system_admin.package_manager == "zypper":
                self.run_command("tail -n 100 /var/log/zypper.log", callback)
            elif self.system_admin.package_manager == "brew":
                self.run_command("brew log --all", callback)
        else:
            self.set_status("Invalid log source")
            self.show_message("Error", "Invalid log source", Gtk.MessageType.ERROR)

    def refresh_system(self):
        """Refresh the system information"""
        def uptime_callback(result):
            if result["returncode"] == 0:
                self.system_uptime_label.set_text(result["stdout"].strip())
            else:
                self.system_uptime_label.set_text("Unknown")

        def cpu_callback(result):
            if result["returncode"] == 0:
                self.system_cpu_label.set_text(result["stdout"].strip())
            else:
                self.system_cpu_label.set_text("Unknown")

        def memory_callback(result):
            if result["returncode"] == 0:
                self.system_memory_label.set_text(result["stdout"].strip())
            else:
                self.system_memory_label.set_text("Unknown")

        def disk_callback(result):
            if result["returncode"] == 0:
                self.system_disk_label.set_text(result["stdout"].strip())
            else:
                self.system_disk_label.set_text("Unknown")

        self.set_status("Refreshing system information...", True)

        # Use different commands based on the system
        if self.system_admin.system == "Linux":
            self.run_command("uptime -p", uptime_callback)
            self.run_command("lscpu | grep 'Model name' | cut -d':' -f2 | xargs", cpu_callback)
            self.run_command("free -h | grep Mem | awk '{print $2}'", memory_callback)
            self.run_command("df -h / | tail -1 | awk '{print $2}'", disk_callback)
        elif self.system_admin.system == "Darwin":
            self.run_command("uptime", uptime_callback)
            self.run_command("sysctl -n machdep.cpu.brand_string", cpu_callback)
            self.run_command("sysctl -n hw.memsize | awk '{print $1/1024/1024/1024 \" GB\"}'", memory_callback)
            self.run_command("df -h / | tail -1 | awk '{print $2}'", disk_callback)
        else:
            self.set_status("Unsupported system for system information")
            self.show_message("Error", "Unsupported system for system information", Gtk.MessageType.ERROR)

    def start_resource_monitoring(self):
        """Start monitoring system resources"""
        def update_resources():
            def cpu_callback(result):
                if result["returncode"] == 0:
                    try:
                        # Parse CPU usage
                        usage = float(result["stdout"].strip())
                        self.dashboard_cpu_progress.set_fraction(usage / 100)
                        self.dashboard_cpu_progress.set_text(f"{usage:.1f}%")
                    except:
                        pass

            def mem_callback(result):
                if result["returncode"] == 0:
                    try:
                        # Parse memory usage
                        usage = float(result["stdout"].strip())
                        self.dashboard_mem_progress.set_fraction(usage / 100)
                        self.dashboard_mem_progress.set_text(f"{usage:.1f}%")
                    except:
                        pass

            def disk_callback(result):
                if result["returncode"] == 0:
                    try:
                        # Parse disk usage
                        usage = float(result["stdout"].strip())
                        self.dashboard_disk_progress.set_fraction(usage / 100)
                        self.dashboard_disk_progress.set_text(f"{usage:.1f}%")
                    except:
                        pass

            # Use different commands based on the system
            if self.system_admin.system == "Linux":
                self.run_command("top -bn1 | grep 'Cpu(s)' | sed 's/.*, *\\([0-9.]*\\)%* id.*/\\1/' | awk '{print 100 - $1}'", cpu_callback)
                self.run_command("free | grep Mem | awk '{print ($3/$2) * 100.0}'", mem_callback)
                self.run_command("df -h / | tail -1 | awk '{print $5}' | sed 's/%//'", disk_callback)
            elif self.system_admin.system == "Darwin":
                self.run_command("top -l 1 | grep 'CPU usage' | awk '{print $3}' | sed 's/%//'", cpu_callback)
                self.run_command("top -l 1 | grep 'PhysMem' | awk '{print $2}' | sed 's/M//'", mem_callback)
                self.run_command("df -h / | tail -1 | awk '{print $5}' | sed 's/%//'", disk_callback)

            # Schedule next update
            GLib.timeout_add_seconds(5, update_resources)

        # Start monitoring
        GLib.timeout_add_seconds(1, update_resources)

    # Event handlers
    def on_update_system(self, button):
        """Handle system update"""
        def callback(result):
            if result["returncode"] == 0:
                self.set_status("System updated successfully")
                self.show_message("Success", "System updated successfully", Gtk.MessageType.INFO)
                self.refresh_packages()
            else:
                self.set_status(f"Error updating system: {result['stderr']}")
                self.show_message("Error", f"Error updating system: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Updating system...", True)

        # Use different commands based on the package manager
        if self.system_admin.package_manager == "apt":
            self.run_command("sudo apt update && sudo apt upgrade -y", callback)
        elif self.system_admin.package_manager == "dnf":
            self.run_command("sudo dnf update -y", callback)
        elif self.system_admin.package_manager == "pacman":
            self.run_command("sudo pacman -Syu --noconfirm", callback)
        elif self.system_admin.package_manager == "zypper":
            self.run_command("sudo zypper update -y", callback)
        elif self.system_admin.package_manager == "brew":
            self.run_command("brew update && brew upgrade", callback)
        else:
            self.set_status("Unsupported package manager")
            self.show_message("Error", "Unsupported package manager", Gtk.MessageType.ERROR)

    def on_clean_system(self, button):
        """Handle system cleanup"""
        def callback(result):
            if result["returncode"] == 0:
                self.set_status("System cleaned successfully")
                self.show_message("Success", "System cleaned successfully", Gtk.MessageType.INFO)
            else:
                self.set_status(f"Error cleaning system: {result['stderr']}")
                self.show_message("Error", f"Error cleaning system: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Cleaning system...", True)

        # Use different commands based on the package manager
        if self.system_admin.package_manager == "apt":
            self.run_command("sudo apt autoremove -y && sudo apt autoclean", callback)
        elif self.system_admin.package_manager == "dnf":
            self.run_command("sudo dnf autoremove -y", callback)
        elif self.system_admin.package_manager == "pacman":
            self.run_command("sudo pacman -Rns $(pacman -Qtdq) --noconfirm", callback)
        elif self.system_admin.package_manager == "zypper":
            self.run_command("sudo zypper packages --unneeded | awk '{print $3}' | xargs sudo zypper remove -y", callback)
        elif self.system_admin.package_manager == "brew":
            self.run_command("brew cleanup", callback)
        else:
            self.set_status("Unsupported package manager")
            self.show_message("Error", "Unsupported package manager", Gtk.MessageType.ERROR)

    def on_add_user(self, button):
        """Handle adding a user"""
        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Add User"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label="Enter the details for the new user")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Create form
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        username_entry = Gtk.Entry()
        username_entry.set_placeholder_text("Username")
        box.append(username_entry)

        password_entry = Gtk.Entry()
        password_entry.set_visibility(False)
        password_entry.set_placeholder_text("Password")
        box.append(password_entry)

        home_entry = Gtk.Entry()
        home_entry.set_placeholder_text("Home Directory (optional)")
        box.append(home_entry)

        shell_entry = Gtk.Entry()
        shell_entry.set_placeholder_text("Shell (optional)")
        box.append(shell_entry)

        content_area.append(box)
        dialog.present()

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.OK:
                username = username_entry.get_text()
                password = password_entry.get_text()
                home = home_entry.get_text()
                shell = shell_entry.get_text()

                if not username or not password:
                    self.show_message("Error", "Username and password are required", Gtk.MessageType.ERROR)
                    return

                def callback(result):
                    if result["returncode"] == 0:
                        self.set_status("User added successfully")
                        self.show_message("Success", "User added successfully", Gtk.MessageType.INFO)
                        self.refresh_users()
                    else:
                        self.set_status(f"Error adding user: {result['stderr']}")
                        self.show_message("Error", f"Error adding user: {result['stderr']}", Gtk.MessageType.ERROR)

                self.set_status("Adding user...", True)

                # Build command
                cmd = f"sudo useradd -m"
                if home:
                    cmd += f" -d {home}"
                if shell:
                    cmd += f" -s {shell}"
                cmd += f" {username}"

                # Run command
                self.run_command(cmd, lambda r: self.run_command(f"echo '{username}:{password}' | sudo chpasswd", callback))

            dialog.close()

        dialog.connect("response", on_response)

    def on_edit_user(self, user):
        """Handle editing a user"""
        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Edit User: {user['username']}"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label="Edit the user details")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Create form
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        password_entry = Gtk.Entry()
        password_entry.set_visibility(False)
        password_entry.set_placeholder_text("New Password (leave empty to keep current)")
        box.append(password_entry)

        home_entry = Gtk.Entry()
        home_entry.set_text(user["home"])
        home_entry.set_placeholder_text("Home Directory")
        box.append(home_entry)

        shell_entry = Gtk.Entry()
        shell_entry.set_text(user["shell"])
        shell_entry.set_placeholder_text("Shell")
        box.append(shell_entry)

        content_area.append(box)
        dialog.present()

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.OK:
                password = password_entry.get_text()
                home = home_entry.get_text()
                shell = shell_entry.get_text()

                def callback(result):
                    if result["returncode"] == 0:
                        self.set_status("User updated successfully")
                        self.show_message("Success", "User updated successfully", Gtk.MessageType.INFO)
                        self.refresh_users()
                    else:
                        self.set_status(f"Error updating user: {result['stderr']}")
                        self.show_message("Error", f"Error updating user: {result['stderr']}", Gtk.MessageType.ERROR)

                self.set_status("Updating user...", True)

                # Build command
                if password:
                    self.run_command(f"echo '{user['username']}:{password}' | sudo chpasswd", callback)

                if home != user["home"] or shell != user["shell"]:
                    cmd = f"sudo usermod"
                    if home != user["home"]:
                        cmd += f" -d {home}"
                    if shell != user["shell"]:
                        cmd += f" -s {shell}"
                    cmd += f" {user['username']}"

                    self.run_command(cmd, callback)

            dialog.close()

        dialog.connect("response", on_response)

    def on_delete_user(self, user):
        """Handle deleting a user"""
        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Delete User: {user['username']}"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label="Are you sure you want to delete this user? This action cannot be undone.")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.YES:
                def callback(result):
                    if result["returncode"] == 0:
                        self.set_status("User deleted successfully")
                        self.show_message("Success", "User deleted successfully", Gtk.MessageType.INFO)
                        self.refresh_users()
                    else:
                        self.set_status(f"Error deleting user: {result['stderr']}")
                        self.show_message("Error", f"Error deleting user: {result['stderr']}", Gtk.MessageType.ERROR)

                self.set_status("Deleting user...", True)
                self.run_command(f"sudo userdel -r {user['username']}", callback)

            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()

    def on_user_selected(self, listbox, row):
        """Handle user selection"""
        # Get the user data
        index = row.get_index()
        if 0 <= index < len(self.system_admin.users):
            user = self.system_admin.users[index]
            self.on_edit_user(user)

    def on_firewall_toggle(self, switch, param):
        """Handle firewall toggle"""
        active = switch.get_active()

        def callback(result):
            if result["returncode"] == 0:
                self.set_status(f"Firewall {'enabled' if active else 'disabled'} successfully")
                self.show_message("Success", f"Firewall {'enabled' if active else 'disabled'} successfully", Gtk.MessageType.INFO)
                self.refresh_firewall()
            else:
                self.set_status(f"Error {'enabling' if active else 'disabling'} firewall: {result['stderr']}")
                self.show_message("Error", f"Error {'enabling' if active else 'disabling'} firewall: {result['stderr']}", Gtk.MessageType.ERROR)
                # Reset switch
                switch.set_active(not active)

        self.set_status(f"{'Enabling' if active else 'Disabling'} firewall...", True)

        # Use different commands based on the system
        if self.system_admin.system == "Linux":
            if shutil.which("ufw"):
                self.run_command(f"sudo ufw {'enable' if active else 'disable'}", callback)
            elif shutil.which("firewalld"):
                self.run_command(f"sudo systemctl {'start' if active else 'stop'} firewalld", callback)
            elif shutil.which("iptables"):
                self.show_message("Info", "iptables management not implemented", Gtk.MessageType.INFO)
                switch.set_active(not active)
            else:
                self.set_status("No supported firewall found")
                self.show_message("Error", "No supported firewall found", Gtk.MessageType.ERROR)
                switch.set_active(not active)
        elif self.system_admin.system == "Darwin":
            self.run_command(f"sudo pfctl {'-e' if active else '-d'}", callback)
        else:
            self.set_status("Unsupported system for firewall management")
            self.show_message("Error", "Unsupported system for firewall management", Gtk.MessageType.ERROR)
            switch.set_active(not active)

    def on_add_firewall_rule(self, button):
        """Handle adding a firewall rule"""
        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text="Add Firewall Rule"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label="Enter the details for the new firewall rule")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Create form
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        action_combo = Gtk.ComboBoxText()
        action_combo.append_text("Allow")
        action_combo.append_text("Deny")
        action_combo.append_text("Reject")
        action_combo.set_active(0)
        box.append(action_combo)

        protocol_combo = Gtk.ComboBoxText()
        protocol_combo.append_text("TCP")
        protocol_combo.append_text("UDP")
        protocol_combo.append_text("ICMP")
        protocol_combo.set_active(0)
        box.append(protocol_combo)

        port_entry = Gtk.Entry()
        port_entry.set_placeholder_text("Port (e.g., 22 or 80,443)")
        box.append(port_entry)

        source_entry = Gtk.Entry()
        source_entry.set_placeholder_text("Source IP (optional)")
        box.append(source_entry)

        content_area.append(box)
        dialog.present()

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.OK:
                action = action_combo.get_active_text().lower()
                protocol = protocol_combo.get_active_text().lower()
                port = port_entry.get_text()
                source = source_entry.get_text()

                if not port:
                    self.show_message("Error", "Port is required", Gtk.MessageType.ERROR)
                    return

                def callback(result):
                    if result["returncode"] == 0:
                        self.set_status("Firewall rule added successfully")
                        self.show_message("Success", "Firewall rule added successfully", Gtk.MessageType.INFO)
                        self.refresh_firewall()
                    else:
                        self.set_status(f"Error adding firewall rule: {result['stderr']}")
                        self.show_message("Error", f"Error adding firewall rule: {result['stderr']}", Gtk.MessageType.ERROR)

                self.set_status("Adding firewall rule...", True)

                # Build command
                cmd = f"sudo ufw {action} {port}/{protocol}"
                if source:
                    cmd += f" from {source}"

                # Run command
                self.run_command(cmd, callback)

            dialog.close()

        dialog.connect("response", on_response)

    def on_delete_firewall_rule(self, rule):
        """Handle deleting a firewall rule"""
        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Delete Firewall Rule"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label=f"Are you sure you want to delete this rule?\n\n{rule}")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.YES:
                def callback(result):
                    if result["returncode"] == 0:
                        self.set_status("Firewall rule deleted successfully")
                        self.show_message("Success", "Firewall rule deleted successfully", Gtk.MessageType.INFO)
                        self.refresh_firewall()
                    else:
                        self.set_status(f"Error deleting firewall rule: {result['stderr']}")
                        self.show_message("Error", f"Error deleting firewall rule: {result['stderr']}", Gtk.MessageType.ERROR)

                self.set_status("Deleting firewall rule...", True)

                # Extract rule details
                # This is a simplified approach - in a real implementation, you'd need to parse the rule more carefully
                parts = rule.split()
                if len(parts) >= 4 and parts[0] in ["ALLOW", "DENY", "REJECT"]:
                    action = parts[0].lower()
                    port_protocol = parts[3]

                    # Build command
                    cmd = f"sudo ufw delete {action} {port_protocol}"

                    # Run command
                    self.run_command(cmd, callback)
                else:
                    self.show_message("Error", "Cannot parse rule for deletion", Gtk.MessageType.ERROR)

            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()

    def on_configure_interface(self, interface):
        """Handle configuring a network interface"""
        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.OK_CANCEL,
            text=f"Configure Interface: {interface['name']}"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label="Configure the network interface settings")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Create form
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)

        method_combo = Gtk.ComboBoxText()
        method_combo.append_text("DHCP")
        method_combo.append_text("Static")
        method_combo.set_active(0)
        box.append(method_combo)

        ip_entry = Gtk.Entry()
        ip_entry.set_placeholder_text("IP Address (for static)")
        ip_entry.set_sensitive(False)
        box.append(ip_entry)

        netmask_entry = Gtk.Entry()
        netmask_entry.set_placeholder_text("Netmask (for static)")
        netmask_entry.set_sensitive(False)
        box.append(netmask_entry)

        gateway_entry = Gtk.Entry()
        gateway_entry.set_placeholder_text("Gateway (for static)")
        gateway_entry.set_sensitive(False)
        box.append(gateway_entry)

        dns_entry = Gtk.Entry()
        dns_entry.set_placeholder_text="DNS (for static)"
        dns_entry.set_sensitive(False)
        box.append(dns_entry)

        # Connect method change
        def on_method_changed(combo):
            method = combo.get_active_text()
            is_static = method == "Static"
            ip_entry.set_sensitive(is_static)
            netmask_entry.set_sensitive(is_static)
            gateway_entry.set_sensitive(is_static)
            dns_entry.set_sensitive(is_static)

        method_combo.connect("changed", on_method_changed)

        content_area.append(box)
        dialog.present()

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.OK:
                method = method_combo.get_active_text()
                ip = ip_entry.get_text()
                netmask = netmask_entry.get_text()
                gateway = gateway_entry.get_text()
                dns = dns_entry.get_text()

                if method == "Static" and not (ip and netmask):
                    self.show_message("Error", "IP address and netmask are required for static configuration", Gtk.MessageType.ERROR)
                    return

                def callback(result):
                    if result["returncode"] == 0:
                        self.set_status("Interface configured successfully")
                        self.show_message("Success", "Interface configured successfully", Gtk.MessageType.INFO)
                        self.refresh_network()
                    else:
                        self.set_status(f"Error configuring interface: {result['stderr']}")
                        self.show_message("Error", f"Error configuring interface: {result['stderr']}", Gtk.MessageType.ERROR)

                self.set_status("Configuring interface...", True)

                # Build command
                if method == "DHCP":
                    cmd = f"sudo dhclient {interface['name']}"
                else:
                    # This is a simplified approach - in a real implementation, you'd need to handle network configuration files
                    cmd = f"sudo ifconfig {interface['name']} {ip} netmask {netmask}"
                    if gateway:
                        cmd += f" && sudo route add default gw {gateway}"
                    if dns:
                        cmd += f" && echo 'nameserver {dns}' | sudo tee /etc/resolv.conf"

                # Run command
                self.run_command(cmd, callback)

            dialog.close()

        dialog.connect("response", on_response)

    def on_package_search(self, entry):
        """Handle package search"""
        query = entry.get_text().lower()

        # Filter installed packages
        for row in self.installed_packages_list:
            package_name = row.get_child().get_first_child().get_text().lower()
            row.set_visible(query in package_name)

        # Filter available packages
        for row in self.available_packages_list:
            package_name = row.get_child().get_first_child().get_text().lower()
            row.set_visible(query in package_name)

    def on_package_selected(self, listbox, row):
        """Handle package selection"""
        # Get the package data
        index = row.get_index()

        if listbox == self.installed_packages_list:
            if 0 <= index < len(self.system_admin.installed_packages):
                package = self.system_admin.installed_packages[index]
                self.show_package_details(package)
        elif listbox == self.available_packages_list:
            if 0 <= index < len(self.system_admin.packages):
                package = self.system_admin.packages[index]
                self.show_package_details(package)

    def show_package_details(self, package):
        """Show package details"""
        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            text=f"Package Details: {package['name']}"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label=f"Version: {package['version']}\nStatus: {package['status']}")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Connect response
        def on_response(dialog, response):
            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()

    def on_install_package(self, package=None):
        """Handle installing a package"""
        if package is None:
            # Get selected package from available packages list
            row = self.available_packages_list.get_selected_row()
            if row:
                index = row.get_index()
                if 0 <= index < len(self.system_admin.packages):
                    package = self.system_admin.packages[index]

        if not package:
            self.show_message("Info", "No package selected", Gtk.MessageType.INFO)
            return

        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Install Package: {package['name']}"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label=f"Are you sure you want to install {package['name']}?")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.YES:
                def callback(result):
                    if result["returncode"] == 0:
                        self.set_status("Package installed successfully")
                        self.show_message("Success", "Package installed successfully", Gtk.MessageType.INFO)
                        self.refresh_packages()
                    else:
                        self.set_status(f"Error installing package: {result['stderr']}")
                        self.show_message("Error", f"Error installing package: {result['stderr']}", Gtk.MessageType.ERROR)

                self.set_status("Installing package...", True)

                # Build command
                if self.system_admin.package_manager == "apt":
                    cmd = f"sudo apt install -y {package['name']}"
                elif self.system_admin.package_manager == "dnf":
                    cmd = f"sudo dnf install -y {package['name']}"
                elif self.system_admin.package_manager == "pacman":
                    cmd = f"sudo pacman -S --noconfirm {package['name']}"
                elif self.system_admin.package_manager == "zypper":
                    cmd = f"sudo zypper install -y {package['name']}"
                elif self.system_admin.package_manager == "brew":
                    cmd = f"brew install {package['name']}"
                else:
                    self.set_status("Unsupported package manager")
                    self.show_message("Error", "Unsupported package manager", Gtk.MessageType.ERROR)
                    return

                # Run command
                self.run_command(cmd, callback)

            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()

    def on_remove_package(self, package=None):
        """Handle removing a package"""
        if package is None:
            # Get selected package from installed packages list
            row = self.installed_packages_list.get_selected_row()
            if row:
                index = row.get_index()
                if 0 <= index < len(self.system_admin.installed_packages):
                    package = self.system_admin.installed_packages[index]

        if not package:
            self.show_message("Info", "No package selected", Gtk.MessageType.INFO)
            return

        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text=f"Remove Package: {package['name']}"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label=f"Are you sure you want to remove {package['name']}? This may remove dependencies.")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.YES:
                def callback(result):
                    if result["returncode"] == 0:
                        self.set_status("Package removed successfully")
                        self.show_message("Success", "Package removed successfully", Gtk.MessageType.INFO)
                        self.refresh_packages()
                    else:
                        self.set_status(f"Error removing package: {result['stderr']}")
                        self.show_message("Error", f"Error removing package: {result['stderr']}", Gtk.MessageType.ERROR)

                self.set_status("Removing package...", True)

                # Build command
                if self.system_admin.package_manager == "apt":
                    cmd = f"sudo apt remove -y {package['name']}"
                elif self.system_admin.package_manager == "dnf":
                    cmd = f"sudo dnf remove -y {package['name']}"
                elif self.system_admin.package_manager == "pacman":
                    cmd = f"sudo pacman -R --noconfirm {package['name']}"
                elif self.system_admin.package_manager == "zypper":
                    cmd = f"sudo zypper remove -y {package['name']}"
                elif self.system_admin.package_manager == "brew":
                    cmd = f"brew uninstall {package['name']}"
                else:
                    self.set_status("Unsupported package manager")
                    self.show_message("Error", "Unsupported package manager", Gtk.MessageType.ERROR)
                    return

                # Run command
                self.run_command(cmd, callback)

            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()

    def on_update_package(self, package=None):
        """Handle updating a package"""
        if package is None:
            # Get selected package from installed packages list
            row = self.installed_packages_list.get_selected_row()
            if row:
                index = row.get_index()
                if 0 <= index < len(self.system_admin.installed_packages):
                    package = self.system_admin.installed_packages[index]

        if not package:
            self.show_message("Info", "No package selected", Gtk.MessageType.INFO)
            return

        def callback(result):
            if result["returncode"] == 0:
                self.set_status("Package updated successfully")
                self.show_message("Success", "Package updated successfully", Gtk.MessageType.INFO)
                self.refresh_packages()
            else:
                self.set_status(f"Error updating package: {result['stderr']}")
                self.show_message("Error", f"Error updating package: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Updating package...", True)

        # Build command
        if self.system_admin.package_manager == "apt":
            cmd = f"sudo apt update && sudo apt upgrade -y {package['name']}"
        elif self.system_admin.package_manager == "dnf":
            cmd = f"sudo dnf update -y {package['name']}"
        elif self.system_admin.package_manager == "pacman":
            cmd = f"sudo pacman -Sy --noconfirm {package['name']}"
        elif self.system_admin.package_manager == "zypper":
            cmd = f"sudo zypper update -y {package['name']}"
        elif self.system_admin.package_manager == "brew":
            cmd = f"brew upgrade {package['name']}"
        else:
            self.set_status("Unsupported package manager")
            self.show_message("Error", "Unsupported package manager", Gtk.MessageType.ERROR)
            return

        # Run command
        self.run_command(cmd, callback)

    def on_start_service(self, service):
        """Handle starting a service"""
        def callback(result):
            if result["returncode"] == 0:
                self.set_status("Service started successfully")
                self.show_message("Success", "Service started successfully", Gtk.MessageType.INFO)
                self.refresh_services()
            else:
                self.set_status(f"Error starting service: {result['stderr']}")
                self.show_message("Error", f"Error starting service: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Starting service...", True)

        # Build command
        if self.system_admin.system == "Linux":
            if shutil.which("systemctl"):
                cmd = f"sudo systemctl start {service['name']}"
            elif shutil.which("service"):
                cmd = f"sudo service {service['name']} start"
            else:
                self.set_status("No supported service manager found")
                self.show_message("Error", "No supported service manager found", Gtk.MessageType.ERROR)
                return
        elif self.system_admin.system == "Darwin":
            cmd = f"sudo launchctl start {service['name']}"
        else:
            self.set_status("Unsupported system for service management")
            self.show_message("Error", "Unsupported system for service management", Gtk.MessageType.ERROR)
            return

        # Run command
        self.run_command(cmd, callback)

    def on_stop_service(self, service):
        """Handle stopping a service"""
        def callback(result):
            if result["returncode"] == 0:
                self.set_status("Service stopped successfully")
                self.show_message("Success", "Service stopped successfully", Gtk.MessageType.INFO)
                self.refresh_services()
            else:
                self.set_status(f"Error stopping service: {result['stderr']}")
                self.show_message("Error", f"Error stopping service: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Stopping service...", True)

        # Build command
        if self.system_admin.system == "Linux":
            if shutil.which("systemctl"):
                cmd = f"sudo systemctl stop {service['name']}"
            elif shutil.which("service"):
                cmd = f"sudo service {service['name']} stop"
            else:
                self.set_status("No supported service manager found")
                self.show_message("Error", "No supported service manager found", Gtk.MessageType.ERROR)
                return
        elif self.system_admin.system == "Darwin":
            cmd = f"sudo launchctl stop {service['name']}"
        else:
            self.set_status("Unsupported system for service management")
            self.show_message("Error", "Unsupported system for service management", Gtk.MessageType.ERROR)
            return

        # Run command
        self.run_command(cmd, callback)

    def on_restart_service(self, service):
        """Handle restarting a service"""
        def callback(result):
            if result["returncode"] == 0:
                self.set_status("Service restarted successfully")
                self.show_message("Success", "Service restarted successfully", Gtk.MessageType.INFO)
                self.refresh_services()
            else:
                self.set_status(f"Error restarting service: {result['stderr']}")
                self.show_message("Error", f"Error restarting service: {result['stderr']}", Gtk.MessageType.ERROR)

        self.set_status("Restarting service...", True)

        # Build command
        if self.system_admin.system == "Linux":
            if shutil.which("systemctl"):
                cmd = f"sudo systemctl restart {service['name']}"
            elif shutil.which("service"):
                cmd = f"sudo service {service['name']} restart"
            else:
                self.set_status("No supported service manager found")
                self.show_message("Error", "No supported service manager found", Gtk.MessageType.ERROR)
                return
        elif self.system_admin.system == "Darwin":
            cmd = f"sudo launchctl stop {service['name']} && sudo launchctl start {service['name']}"
        else:
            self.set_status("Unsupported system for service management")
            self.show_message("Error", "Unsupported system for service management", Gtk.MessageType.ERROR)
            return

        # Run command
        self.run_command(cmd, callback)

    def on_log_source_changed(self, combo):
        """Handle log source change"""
        self.refresh_logs()

    def on_clear_logs(self, button):
        """Handle clearing logs"""
        # Create dialog
        dialog = Gtk.MessageDialog(
            transient_for=self,
            modal=True,
            message_type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            text="Clear Logs"
        )

        # Create a label for the secondary text
        content_area = dialog.get_content_area()
        secondary_label = Gtk.Label(label="Are you sure you want to clear the logs? This action cannot be undone.")
        secondary_label.set_wrap(True)
        secondary_label.set_margin_top(10)
        content_area.append(secondary_label)

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.YES:
                def callback(result):
                    if result["returncode"] == 0:
                        self.set_status("Logs cleared successfully")
                        self.show_message("Success", "Logs cleared successfully", Gtk.MessageType.INFO)
                        self.refresh_logs()
                    else:
                        self.set_status(f"Error clearing logs: {result['stderr']}")
                        self.show_message("Error", f"Error clearing logs: {result['stderr']}", Gtk.MessageType.ERROR)

                self.set_status("Clearing logs...", True)

                # Get the selected log source
                log_source = self.log_source_combo.get_active()

                # Map index to log source
                log_sources = ["system", "auth", "kern", "package"]
                if log_source < 0 or log_source >= len(log_sources):
                    log_source = 0
                log_source = log_sources[log_source]

                # Build command
                if log_source == "system":
                    if self.system_admin.system == "Linux":
                        if shutil.which("journalctl"):
                            cmd = "sudo journalctl --vacuum-time=1s"
                        else:
                            cmd = "sudo truncate -s 0 /var/log/syslog"
                    elif self.system_admin.system == "Darwin":
                        cmd = "sudo log erase --all"
                elif log_source == "auth":
                    if self.system_admin.system == "Linux":
                        if shutil.which("journalctl"):
                            cmd = "sudo journalctl --vacuum-time=1s -u auth"
                        else:
                            cmd = "sudo truncate -s 0 /var/log/auth.log"
                    elif self.system_admin.system == "Darwin":
                        cmd = "sudo log erase --predicate 'process == \"authd\"'"
                elif log_source == "kern":
                    if self.system_admin.system == "Linux":
                        if shutil.which("journalctl"):
                            cmd = "sudo journalctl --vacuum-time=1s -k"
                        else:
                            cmd = "sudo truncate -s 0 /var/log/kern.log"
                    elif self.system_admin.system == "Darwin":
                        cmd = "sudo log erase --predicate 'category == \"kernel\"'"
                elif log_source == "package":
                    if self.system_admin.package_manager == "apt":
                        cmd = "sudo truncate -s 0 /var/log/dpkg.log"
                    elif self.system_admin.package_manager == "dnf":
                        cmd = "sudo truncate -s 0 /var/log/dnf.log"
                    elif self.system_admin.package_manager == "pacman":
                        cmd = "sudo truncate -s 0 /var/log/pacman.log"
                    elif self.system_admin.package_manager == "zypper":
                        cmd = "sudo truncate -s 0 /var/log/zypper.log"
                    elif self.system_admin.package_manager == "brew":
                        cmd = "brew cleanup"
                else:
                    self.set_status("Invalid log source")
                    self.show_message("Error", "Invalid log source", Gtk.MessageType.ERROR)
                    return

                # Run command
                self.run_command(cmd, callback)

            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()

    def on_export_logs(self, button):
        """Handle exporting logs"""
        # Create file chooser dialog
        dialog = Gtk.FileChooserDialog(
            title="Export Logs",
            action=Gtk.FileChooserAction.SAVE,
            transient_for=self
        )
        dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
        dialog.add_button("Export", Gtk.ResponseType.ACCEPT)

        # Set default filename
        log_source = self.log_source_combo.get_active()

        # Map index to log source
        log_sources = ["system", "auth", "kern", "package"]
        if log_source < 0 or log_source >= len(log_sources):
            log_source = 0
        log_source = log_sources[log_source]

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dialog.set_current_name(f"{log_source}_logs_{timestamp}.txt")

        # Connect response
        def on_response(dialog, response):
            if response == Gtk.ResponseType.ACCEPT:
                filename = dialog.get_filename()

                # Get log content
                buffer = self.log_text_view.get_buffer()
                start, end = buffer.get_bounds()
                content = buffer.get_text(start, end, True)

                # Write to file
                try:
                    with open(filename, "w") as f:
                        f.write(content)

                    self.set_status("Logs exported successfully")
                    self.show_message("Success", "Logs exported successfully", Gtk.MessageType.INFO)
                except Exception as e:
                    self.set_status(f"Error exporting logs: {str(e)}")
                    self.show_message("Error", f"Error exporting logs: {str(e)}", Gtk.MessageType.ERROR)

            dialog.close()

        dialog.connect("response", on_response)
        dialog.present()

if __name__ == "__main__":
    app = SystemAdminApp()
    app.run(sys.argv)
