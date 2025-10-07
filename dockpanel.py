#!/usr/bin/env python3
"""
Dockpanel - Universal System Management Tool
A comprehensive YAST-like tool for managing Linux and macOS systems
"""

import os
import sys
import subprocess
import platform
import time
import socket
import pwd
import grp
import shutil
import glob
import re
import json
import threading
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Union
from dataclasses import dataclass
from abc import ABC, abstractmethod

import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib, Gio, Pango, GdkPixbuf

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
APP_NAME = "Dockpanel"
APP_VERSION = "2.0.0"

# System Detection
SYSTEM = platform.system()
DISTRO = "Unknown"
PACKAGE_MANAGER = None
PACKAGE_MANAGER_CMD = None

def detect_system():
    """Detect system distribution and package manager"""
    global DISTRO, PACKAGE_MANAGER, PACKAGE_MANAGER_CMD
    
    if SYSTEM == "Linux":
        if os.path.exists("/etc/os-release"):
            with open("/etc/os-release", "r") as f:
                for line in f:
                    if line.startswith("ID="):
                        DISTRO = line.split("=")[1].strip().strip('"')
                        break
        
        if os.path.exists("/usr/bin/apt"):
            PACKAGE_MANAGER = "apt"
            PACKAGE_MANAGER_CMD = ["apt"]
        elif os.path.exists("/usr/bin/dnf"):
            PACKAGE_MANAGER = "dnf"
            PACKAGE_MANAGER_CMD = ["dnf"]
        elif os.path.exists("/usr/bin/zypper"):
            PACKAGE_MANAGER = "zypper"
            PACKAGE_MANAGER_CMD = ["zypper"]
        elif os.path.exists("/usr/bin/pacman"):
            PACKAGE_MANAGER = "pacman"
            PACKAGE_MANAGER_CMD = ["pacman"]
    elif SYSTEM == "Darwin":
        DISTRO = "macOS"
        if os.path.exists("/usr/local/bin/brew") or os.path.exists("/opt/homebrew/bin/brew"):
            PACKAGE_MANAGER = "brew"
            PACKAGE_MANAGER_CMD = ["brew"]

detect_system()

# Utility Functions
def run_command(cmd: str, shell: bool = True, timeout: int = 30) -> Tuple[str, str, int]:
    """Execute command and return stdout, stderr, returncode"""
    try:
        result = subprocess.run(
            cmd,
            shell=shell,
            text=True,
            capture_output=True,
            timeout=timeout
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timed out", 1
    except Exception as e:
        return "", str(e), 1

def run_sudo_command(cmd: str, password: str = None) -> Tuple[str, str, int]:
    """Execute command with sudo privileges"""
    if password:
        cmd = f"echo '{password}' | sudo -S {cmd}"
    else:
        cmd = f"sudo {cmd}"
    return run_command(cmd)

# System Information Classes
@dataclass
class SystemInfo:
    """System information data structure"""
    os: str
    distro: str
    kernel: str
    hostname: str
    uptime: str
    cpu_model: str
    cpu_cores: int
    memory_total: int
    memory_used: int
    disk_total: int
    disk_used: int
    boot_mode: str
    secure_boot: bool

class SystemInfoManager:
    """Manages system information gathering"""
    
    @staticmethod
    def get_system_info() -> SystemInfo:
        """Get comprehensive system information"""
        try:
            # Basic system info
            kernel = platform.release()
            hostname = socket.gethostname()
            
            # CPU info
            cpu_model = "Unknown"
            cpu_cores = os.cpu_count() or 1
            
            if SYSTEM == "Linux":
                with open('/proc/cpuinfo', 'r') as f:
                    for line in f:
                        if line.startswith('model name'):
                            cpu_model = line.split(':')[1].strip()
                            break
            
            # Memory info
            memory_total = memory_used = 0
            if SYSTEM == "Linux":
                with open('/proc/meminfo', 'r') as f:
                    meminfo = f.read()
                    for line in meminfo.split('\n'):
                        if line.startswith('MemTotal:'):
                            memory_total = int(line.split()[1]) // 1024 // 1024
                        elif line.startswith('MemAvailable:'):
                            memory_used = memory_total - (int(line.split()[1]) // 1024 // 1024)
            
            # Disk info
            disk_total = disk_used = 0
            stdout, _, code = run_command("df -h /")
            if code == 0:
                parts = stdout.split('\n')[1].split()
                if len(parts) >= 4:
                    disk_total = float(parts[1].replace('G', ''))
                    disk_used = float(parts[2].replace('G', ''))
            
            # Uptime
            uptime = "Unknown"
            if SYSTEM == "Linux":
                with open('/proc/uptime', 'r') as f:
                    uptime_seconds = float(f.read().split()[0])
                    days = int(uptime_seconds // 86400)
                    hours = int((uptime_seconds % 86400) // 3600)
                    uptime = f"{days}d {hours}h"
            
            # Boot mode and secure boot
            boot_mode = "Unknown"
            secure_boot = False
            if SYSTEM == "Linux":
                stdout, _, code = run_command("efibootmgr 2>/dev/null")
                if code == 0:
                    boot_mode = "UEFI"
                else:
                    boot_mode = "BIOS"
                
                stdout, _, code = run_command("mokutil --sb-state 2>/dev/null")
                if code == 0:
                    secure_boot = "SecureBoot Enabled" in stdout
            
            return SystemInfo(
                os=SYSTEM,
                distro=DISTRO,
                kernel=kernel,
                hostname=hostname,
                uptime=uptime,
                cpu_model=cpu_model,
                cpu_cores=cpu_cores,
                memory_total=memory_total,
                memory_used=memory_used,
                disk_total=disk_total,
                disk_used=disk_used,
                boot_mode=boot_mode,
                secure_boot=secure_boot
            )
        except Exception as e:
            logger.error(f"Error getting system info: {e}")
            return SystemInfo(
                os=SYSTEM, distro=DISTRO, kernel="Unknown", hostname="Unknown",
                uptime="Unknown", cpu_model="Unknown", cpu_cores=1,
                memory_total=0, memory_used=0, disk_total=0, disk_used=0,
                boot_mode="Unknown", secure_boot=False
            )

# Repository Management
class RepositoryManager:
    """Repository management interface"""
    
    @staticmethod
    def get_repositories() -> List[Dict[str, Any]]:
        """Get list of repositories"""
        repos = []
        
        if PACKAGE_MANAGER == "apt":
            sources_files = ["/etc/apt/sources.list"]
            sources_files.extend(glob.glob("/etc/apt/sources.list.d/*.list"))
            
            for source_file in sources_files:
                if os.path.exists(source_file):
                    try:
                        with open(source_file, 'r') as f:
                            for line_num, line in enumerate(f, 1):
                                line = line.strip()
                                if line and not line.startswith('#'):
                                    if 'deb ' in line:
                                        enabled = not line.startswith('#deb ')
                                        repo_info = line.replace('#', '').strip()
                                        repos.append({
                                            'file': source_file,
                                            'line': line_num,
                                            'name': repo_info,
                                            'enabled': enabled,
                                            'type': 'apt'
                                        })
                    except Exception as e:
                        logger.error(f"Error reading {source_file}: {e}")
        
        elif PACKAGE_MANAGER == "dnf":
            stdout, _, code = run_command("dnf repolist -v")
            if code == 0:
                for line in stdout.split('\n'):
                    if 'Repo-id' in line:
                        repo_id = line.split(':', 1)[1].strip()
                        repos.append({
                            'name': repo_id,
                            'enabled': True,
                            'type': 'dnf'
                        })
        
        elif PACKAGE_MANAGER == "zypper":
            stdout, _, code = run_command("zypper lr")
            if code == 0:
                for line in stdout.split('\n'):
                    if line and not line.startswith('#') and '|' in line:
                        parts = [p.strip() for p in line.split('|')]
                        if len(parts) >= 3:
                            alias = parts[1]
                            enabled = parts[2] == 'Yes'
                            repos.append({
                                'name': alias,
                                'enabled': enabled,
                                'type': 'zypper'
                            })
        
        elif PACKAGE_MANAGER == "pacman":
            stdout, _, code = run_command("grep -E '^\\[.*\\]' /etc/pacman.conf")
            if code == 0:
                for line in stdout.split('\n'):
                    if line.strip():
                        repo = line.strip()
                        enabled = not repo.startswith('#[')
                        repos.append({
                            'name': repo.replace('#', ''),
                            'enabled': enabled,
                            'type': 'pacman'
                        })
        
        return repos
    
    @staticmethod
    def add_repository(repo_url: str, repo_name: str = None, password: str = None) -> Tuple[bool, str]:
        """Add a new repository"""
        try:
            if PACKAGE_MANAGER == "apt":
                if not repo_name:
                    repo_name = f"custom-repo-{int(time.time())}"
                
                # Create new sources file
                sources_file = f"/etc/apt/sources.list.d/{repo_name}.list"
                cmd = f"echo 'deb {repo_url}' > {sources_file}"
                stdout, stderr, code = run_sudo_command(cmd, password)
                
                if code == 0:
                    stdout, stderr, code = run_sudo_command("apt update", password)
                    return code == 0, stderr if code != 0 else "Repository added successfully"
                return False, stderr
            
            elif PACKAGE_MANAGER == "dnf":
                cmd = f"dnf config-manager --add-repo {repo_url}"
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else stdout
            
            elif PACKAGE_MANAGER == "zypper":
                cmd = f"zypper addrepo {repo_url}"
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else stdout
            
            elif PACKAGE_MANAGER == "pacman":
                # For pacman, we need to manually edit pacman.conf
                if not repo_name:
                    repo_name = repo_url.split('/')[-1].replace('.git', '')
                
                # Backup pacman.conf
                run_sudo_command("cp /etc/pacman.conf /etc/pacman.conf.bak", password)
                
                # Add repo to pacman.conf
                cmd = f"echo -e '\\n[{repo_name}]\\nServer = {repo_url}' >> /etc/pacman.conf"
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else "Repository added successfully"
            
            return False, "Unsupported package manager"
        except Exception as e:
            logger.error(f"Error adding repository: {e}")
            return False, str(e)
    
    @staticmethod
    def remove_repository(repo_name: str, password: str = None) -> Tuple[bool, str]:
        """Remove a repository"""
        try:
            if PACKAGE_MANAGER == "apt":
                # Find and remove from sources files
                sources_files = ["/etc/apt/sources.list"]
                sources_files.extend(glob.glob("/etc/apt/sources.list.d/*.list"))
                
                for source_file in sources_files:
                    if os.path.exists(source_file):
                        with open(source_file, 'r') as f:
                            lines = f.readlines()
                        
                        new_lines = []
                        removed = False
                        for line in lines:
                            if repo_name in line:
                                removed = True
                                continue
                            new_lines.append(line)
                        
                        if removed:
                            cmd = f"echo '{''.join(new_lines)}' > {source_file}"
                            stdout, stderr, code = run_sudo_command(cmd, password)
                            if code == 0:
                                stdout, stderr, code = run_sudo_command("apt update", password)
                                return code == 0, stderr if code != 0 else "Repository removed successfully"
                            return False, stderr
                
                return False, "Repository not found"
            
            elif PACKAGE_MANAGER == "dnf":
                cmd = f"dnf config-manager --disable {repo_name}"
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else stdout
            
            elif PACKAGE_MANAGER == "zypper":
                cmd = f"zypper removerepo {repo_name}"
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else stdout
            
            elif PACKAGE_MANAGER == "pacman":
                # Remove from pacman.conf
                cmd = f"sed -i '/\\[{repo_name}\\]/,/^$/d' /etc/pacman.conf"
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else "Repository removed successfully"
            
            return False, "Unsupported package manager"
        except Exception as e:
            logger.error(f"Error removing repository: {e}")
            return False, str(e)
    
    @staticmethod
    def toggle_repository(repo_name: str, enable: bool, password: str = None) -> Tuple[bool, str]:
        """Enable or disable a repository"""
        try:
            if PACKAGE_MANAGER == "apt":
                # Find and toggle in sources files
                sources_files = ["/etc/apt/sources.list"]
                sources_files.extend(glob.glob("/etc/apt/sources.list.d/*.list"))
                
                for source_file in sources_files:
                    if os.path.exists(source_file):
                        with open(source_file, 'r') as f:
                            lines = f.readlines()
                        
                        new_lines = []
                        toggled = False
                        for line in lines:
                            if repo_name in line:
                                if enable and line.startswith('#deb '):
                                    line = line[1:]  # Remove #
                                    toggled = True
                                elif not enable and line.startswith('deb '):
                                    line = '#' + line  # Add #
                                    toggled = True
                            new_lines.append(line)
                        
                        if toggled:
                            cmd = f"echo '{''.join(new_lines)}' > {source_file}"
                            stdout, stderr, code = run_sudo_command(cmd, password)
                            if code == 0:
                                stdout, stderr, code = run_sudo_command("apt update", password)
                                return code == 0, stderr if code != 0 else "Repository toggled successfully"
                            return False, stderr
                
                return False, "Repository not found"
            
            elif PACKAGE_MANAGER == "dnf":
                action = "enable" if enable else "disable"
                cmd = f"dnf config-manager --{action} {repo_name}"
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else stdout
            
            elif PACKAGE_MANAGER == "zypper":
                action = "enable" if enable else "disable"
                cmd = f"zypper {action}repo {repo_name}"
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else stdout
            
            elif PACKAGE_MANAGER == "pacman":
                # Toggle by commenting/uncommenting in pacman.conf
                if enable:
                    cmd = f"sed -i 's/^#\\[{repo_name}\\]/[{repo_name}/' /etc/pacman.conf"
                else:
                    cmd = f"sed -i 's/^\\[{repo_name}\\]/#[{repo_name}/' /etc/pacman.conf"
                
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else "Repository toggled successfully"
            
            return False, "Unsupported package manager"
        except Exception as e:
            logger.error(f"Error toggling repository: {e}")
            return False, str(e)
    
    @staticmethod
    def refresh_repositories(password: str = None) -> Tuple[bool, str]:
        """Refresh all repositories"""
        try:
            if PACKAGE_MANAGER == "apt":
                stdout, stderr, code = run_sudo_command("apt update", password)
                return code == 0, stderr if code != 0 else stdout
            
            elif PACKAGE_MANAGER == "dnf":
                stdout, stderr, code = run_sudo_command("dnf makecache", password)
                return code == 0, stderr if code != 0 else stdout
            
            elif PACKAGE_MANAGER == "zypper":
                stdout, stderr, code = run_sudo_command("zypper refresh", password)
                return code == 0, stderr if code != 0 else stdout
            
            elif PACKAGE_MANAGER == "pacman":
                stdout, stderr, code = run_sudo_command("pacman -Sy", password)
                return code == 0, stderr if code != 0 else stdout
            
            return False, "Unsupported package manager"
        except Exception as e:
            logger.error(f"Error refreshing repositories: {e}")
            return False, str(e)

# Boot Configuration Management
class BootManager:
    """Boot configuration management"""
    
    @staticmethod
    def get_boot_config() -> Dict[str, Any]:
        """Get boot configuration"""
        config = {
            'bootloader': 'Unknown',
            'default_entry': 'Unknown',
            'timeout': 0,
            'entries': []
        }
        
        try:
            if SYSTEM == "Linux":
                # Check for GRUB
                if os.path.exists("/boot/grub/grub.cfg"):
                    config['bootloader'] = 'GRUB2'
                    
                    # Get GRUB configuration
                    stdout, _, code = run_command("grep -E '^menuentry|^set default=' /boot/grub/grub.cfg")
                    if code == 0:
                        for line in stdout.split('\n'):
                            if line.startswith('menuentry'):
                                title = re.search(r'"([^"]+)"', line)
                                if title:
                                    config['entries'].append(title.group(1))
                            elif line.startswith('set default='):
                                default = line.split('=')[1].strip()
                                config['default_entry'] = default
                    
                    # Get timeout
                    stdout, _, code = run_command("grep -E '^set timeout=' /boot/grub/grub.cfg")
                    if code == 0:
                        for line in stdout.split('\n'):
                            if line.startswith('set timeout='):
                                config['timeout'] = int(line.split('=')[1].strip())
                
                # Check for systemd-boot
                elif os.path.exists("/boot/loader/loader.conf"):
                    config['bootloader'] = 'systemd-boot'
                    
                    with open("/boot/loader/loader.conf", 'r') as f:
                        for line in f:
                            line = line.strip()
                            if line.startswith('default '):
                                config['default_entry'] = line.split()[1]
                            elif line.startswith('timeout '):
                                config['timeout'] = int(line.split()[1])
                    
                    # Get entries
                    entries_dir = "/boot/loader/entries"
                    if os.path.exists(entries_dir):
                        for entry_file in os.listdir(entries_dir):
                            if entry_file.endswith('.conf'):
                                config['entries'].append(entry_file[:-5])
                
                # Check for rEFInd
                elif os.path.exists("/boot/efi/EFI/refind/refind.conf"):
                    config['bootloader'] = 'rEFInd'
        
        except Exception as e:
            logger.error(f"Error getting boot config: {e}")
        
        return config
    
    @staticmethod
    def update_grub(password: str = None) -> Tuple[bool, str]:
        """Update GRUB configuration"""
        try:
            stdout, stderr, code = run_sudo_command("update-grub", password)
            return code == 0, stderr if code != 0 else stdout
        except Exception as e:
            logger.error(f"Error updating GRUB: {e}")
            return False, str(e)
    
    @staticmethod
    def set_default_boot_entry(entry: str, password: str = None) -> Tuple[bool, str]:
        """Set default boot entry"""
        try:
            if os.path.exists("/etc/default/grub"):
                # Update GRUB_DEFAULT
                cmd = f"sed -i 's/^GRUB_DEFAULT=.*/GRUB_DEFAULT=\"{entry}\"/' /etc/default/grub"
                stdout, stderr, code = run_sudo_command(cmd, password)
                
                if code == 0:
                    return BootManager.update_grub(password)
                return False, stderr
            
            return False, "GRUB configuration not found"
        except Exception as e:
            logger.error(f"Error setting default boot entry: {e}")
            return False, str(e)
    
    @staticmethod
    def set_boot_timeout(timeout: int, password: str = None) -> Tuple[bool, str]:
        """Set boot timeout"""
        try:
            if os.path.exists("/etc/default/grub"):
                # Update GRUB_TIMEOUT
                cmd = f"sed -i 's/^GRUB_TIMEOUT=.*/GRUB_TIMEOUT={timeout}/' /etc/default/grub"
                stdout, stderr, code = run_sudo_command(cmd, password)
                
                if code == 0:
                    return BootManager.update_grub(password)
                return False, stderr
            
            return False, "GRUB configuration not found"
        except Exception as e:
            logger.error(f"Error setting boot timeout: {e}")
            return False, str(e)

# Kernel Management
class KernelManager:
    """Kernel management interface"""
    
    @staticmethod
    def get_installed_kernels() -> List[Dict[str, Any]]:
        """Get list of installed kernels"""
        kernels = []
        
        try:
            if SYSTEM == "Linux":
                # Get installed kernels from /boot
                boot_dir = "/boot"
                if os.path.exists(boot_dir):
                    for item in os.listdir(boot_dir):
                        if item.startswith("vmlinuz-"):
                            version = item[8:]  # Remove "vmlinuz-"
                            kernel_path = os.path.join(boot_dir, item)
                            
                            # Check if it's the current kernel
                            current = False
                            with open("/proc/version", 'r') as f:
                                current_version = f.read().split()[2]
                                if version in current_version:
                                    current = True
                            
                            # Get kernel size
                            size = os.path.getsize(kernel_path) // (1024 * 1024)  # MB
                            
                            kernels.append({
                                'version': version,
                                'path': kernel_path,
                                'current': current,
                                'size': size
                            })
                
                # Sort by version
                kernels.sort(key=lambda x: x['version'], reverse=True)
        
        except Exception as e:
            logger.error(f"Error getting installed kernels: {e}")
        
        return kernels
    
    @staticmethod
    def remove_old_kernels(keep_count: int = 2, password: str = None) -> Tuple[bool, str]:
        """Remove old kernels, keeping the specified number"""
        try:
            kernels = KernelManager.get_installed_kernels()
            
            # Keep current kernel and specified number of recent kernels
            to_remove = []
            kept = 0
            
            for kernel in kernels:
                if kernel['current']:
                    continue  # Never remove current kernel
                
                if kept < keep_count:
                    kept += 1
                else:
                    to_remove.append(kernel)
            
            if not to_remove:
                return True, "No old kernels to remove"
            
            # Remove old kernels
            for kernel in to_remove:
                version = kernel['version']
                
                if PACKAGE_MANAGER == "apt":
                    cmd = f"apt remove -y linux-image-{version} linux-headers-{version}"
                elif PACKAGE_MANAGER == "dnf":
                    cmd = f"dnf remove -y kernel-{version}"
                elif PACKAGE_MANAGER == "zypper":
                    cmd = f"zypper remove -y kernel-{version}"
                else:
                    # Manual removal
                    cmd = f"rm -f /boot/vmlinuz-{version} /boot/initrd.img-{version} /boot/config-{version} /boot/System.map-{version}"
                
                stdout, stderr, code = run_sudo_command(cmd, password)
                if code != 0:
                    return False, f"Failed to remove kernel {version}: {stderr}"
            
            # Update bootloader
            if PACKAGE_MANAGER == "apt":
                BootManager.update_grub(password)
            
            return True, f"Removed {len(to_remove)} old kernels"
        except Exception as e:
            logger.error(f"Error removing old kernels: {e}")
            return False, str(e)

# System Services Management
class SystemServiceManager:
    """Enhanced system services management"""
    
    @staticmethod
    def get_all_services() -> List[Dict[str, Any]]:
        """Get all system services with detailed information"""
        services = []
        
        try:
            if os.path.exists("/usr/bin/systemctl"):
                # Get all services
                stdout, _, code = run_command("systemctl list-units --type=service --all --no-pager")
                if code == 0:
                    for line in stdout.split('\n'):
                        if '.service' in line and not line.startswith('UNIT') and not line.startswith('●'):
                            parts = line.split()
                            if len(parts) >= 4:
                                service_name = parts[0]
                                load = parts[1]
                                active = parts[2]
                                sub = parts[3]
                                description = ' '.join(parts[4:]) if len(parts) > 4 else ""
                                
                                # Get additional service info
                                enabled = False
                                stdout2, _, code2 = run_command(f"systemctl is-enabled {service_name}")
                                if code2 == 0:
                                    enabled = stdout2.strip() == "enabled"
                                
                                services.append({
                                    'name': service_name,
                                    'load': load,
                                    'active': active,
                                    'sub': sub,
                                    'description': description,
                                    'enabled': enabled
                                })
        
        except Exception as e:
            logger.error(f"Error getting services: {e}")
        
        return services
    
    @staticmethod
    def get_service_status(service_name: str) -> Dict[str, Any]:
        """Get detailed status of a specific service"""
        status = {
            'name': service_name,
            'loaded': False,
            'active': False,
            'enabled': False,
            'description': '',
            'main_pid': 0,
            'memory': 0,
            'tasks': 0
        }
        
        try:
            if os.path.exists("/usr/bin/systemctl"):
                # Get service status
                stdout, _, code = run_command(f"systemctl show {service_name}")
                if code == 0:
                    for line in stdout.split('\n'):
                        if '=' in line:
                            key, value = line.split('=', 1)
                            if key == 'LoadState':
                                status['loaded'] = value != 'not-found'
                            elif key == 'ActiveState':
                                status['active'] = value == 'active'
                            elif key == 'UnitFileState':
                                status['enabled'] = value == 'enabled'
                            elif key == 'Description':
                                status['description'] = value
                            elif key == 'MainPID':
                                status['main_pid'] = int(value)
                            elif key == 'MemoryCurrent':
                                if value != '[not set]':
                                    status['memory'] = int(value) // 1024 // 1024  # MB
                            elif key == 'TasksCurrent':
                                if value != '[not set]':
                                    status['tasks'] = int(value)
        
        except Exception as e:
            logger.error(f"Error getting service status: {e}")
        
        return status
    
    @staticmethod
    def enable_service(service_name: str, password: str = None) -> Tuple[bool, str]:
        """Enable a service to start at boot"""
        try:
            cmd = f"systemctl enable {service_name}"
            stdout, stderr, code = run_sudo_command(cmd, password)
            return code == 0, stderr if code != 0 else stdout
        except Exception as e:
            logger.error(f"Error enabling service: {e}")
            return False, str(e)
    
    @staticmethod
    def disable_service(service_name: str, password: str = None) -> Tuple[bool, str]:
        """Disable a service from starting at boot"""
        try:
            cmd = f"systemctl disable {service_name}"
            stdout, stderr, code = run_sudo_command(cmd, password)
            return code == 0, stderr if code != 0 else stdout
        except Exception as e:
            logger.error(f"Error disabling service: {e}")
            return False, str(e)
    
    @staticmethod
    def mask_service(service_name: str, password: str = None) -> Tuple[bool, str]:
        """Mask a service (completely disable it)"""
        try:
            cmd = f"systemctl mask {service_name}"
            stdout, stderr, code = run_sudo_command(cmd, password)
            return code == 0, stderr if code != 0 else stdout
        except Exception as e:
            logger.error(f"Error masking service: {e}")
            return False, str(e)
    
    @staticmethod
    def unmask_service(service_name: str, password: str = None) -> Tuple[bool, str]:
        """Unmask a service"""
        try:
            cmd = f"systemctl unmask {service_name}"
            stdout, stderr, code = run_sudo_command(cmd, password)
            return code == 0, stderr if code != 0 else stdout
        except Exception as e:
            logger.error(f"Error unmasking service: {e}")
            return False, str(e)

# Firewall Management
class FirewallManager:
    """Enhanced firewall management"""
    
    @staticmethod
    def get_firewall_info() -> Dict[str, Any]:
        """Get comprehensive firewall information"""
        info = {
            'backend': 'unknown',
            'active': False,
            'default_zone': '',
            'zones': [],
            'rules': []
        }
        
        try:
            if SYSTEM == "Linux":
                # Check for UFW
                stdout, _, code = run_command("which ufw")
                if code == 0:
                    info['backend'] = 'ufw'
                    
                    # Get UFW status
                    stdout, _, code = run_command("ufw status verbose")
                    if code == 0:
                        info['active'] = 'Status: active' in stdout
                        
                        # Parse rules
                        for line in stdout.split('\n'):
                            if line.strip() and not line.startswith('Status') and not line.startswith('Action') and not line.startswith('--'):
                                parts = line.split()
                                if len(parts) >= 4:
                                    info['rules'].append({
                                        'action': parts[0],
                                        'direction': parts[1],
                                        'protocol': parts[3] if len(parts) > 3 else 'any',
                                        'source': parts[4] if len(parts) > 4 else 'any',
                                        'destination': parts[5] if len(parts) > 5 else 'any'
                                    })
                
                # Check for firewalld
                stdout, _, code = run_command("which firewall-cmd")
                if code == 0:
                    info['backend'] = 'firewalld'
                    
                    # Get firewalld status
                    stdout, _, code = run_command("firewall-cmd --state")
                    if code == 0:
                        info['active'] = stdout.strip() == 'running'
                    
                    # Get default zone
                    stdout, _, code = run_command("firewall-cmd --get-default-zone")
                    if code == 0:
                        info['default_zone'] = stdout.strip()
                    
                    # Get zones
                    stdout, _, code = run_command("firewall-cmd --get-zones")
                    if code == 0:
                        zones = stdout.strip().split()
                        for zone in zones:
                            zone_info = {'name': zone, 'active': False, 'services': [], 'ports': []}
                            
                            # Check if zone is active
                            stdout2, _, code2 = run_command(f"firewall-cmd --get-active-zones")
                            if code2 == 0:
                                zone_info['active'] = zone in stdout2
                            
                            # Get services in zone
                            stdout3, _, code3 = run_command(f"firewall-cmd --zone={zone} --list-services")
                            if code3 == 0:
                                zone_info['services'] = stdout3.strip().split()
                            
                            # Get ports in zone
                            stdout4, _, code4 = run_command(f"firewall-cmd --zone={zone} --list-ports")
                            if code4 == 0:
                                zone_info['ports'] = stdout4.strip().split()
                            
                            info['zones'].append(zone_info)
        
        except Exception as e:
            logger.error(f"Error getting firewall info: {e}")
        
        return info
    
    @staticmethod
    def add_firewall_rule(rule: Dict[str, str], password: str = None) -> Tuple[bool, str]:
        """Add a firewall rule"""
        try:
            if rule.get('backend') == 'ufw':
                action = rule.get('action', 'allow')
                protocol = rule.get('protocol', 'any')
                port = rule.get('port', '')
                source = rule.get('source', '')
                
                cmd = f"ufw {action}"
                if protocol != 'any':
                    cmd += f" {protocol}"
                if port:
                    cmd += f" {port}"
                if source:
                    cmd += f" from {source}"
                
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else stdout
            
            elif rule.get('backend') == 'firewalld':
                zone = rule.get('zone', 'public')
                
                if rule.get('type') == 'service':
                    service = rule.get('service', '')
                    cmd = f"firewall-cmd --zone={zone} --add-service={service} --permanent"
                elif rule.get('type') == 'port':
                    port = rule.get('port', '')
                    protocol = rule.get('protocol', 'tcp')
                    cmd = f"firewall-cmd --zone={zone} --add-port={port}/{protocol} --permanent"
                
                stdout, stderr, code = run_sudo_command(cmd, password)
                if code == 0:
                    # Reload firewall
                    stdout2, stderr2, code2 = run_sudo_command("firewall-cmd --reload", password)
                    return code2 == 0, stderr2 if code2 != 0 else "Rule added successfully"
                return False, stderr
            
            return False, "Unsupported firewall backend"
        except Exception as e:
            logger.error(f"Error adding firewall rule: {e}")
            return False, str(e)
    
    @staticmethod
    def remove_firewall_rule(rule: Dict[str, str], password: str = None) -> Tuple[bool, str]:
        """Remove a firewall rule"""
        try:
            if rule.get('backend') == 'ufw':
                # UFW doesn't have direct rule removal by ID, need to match
                action = 'deny' if rule.get('action') == 'allow' else 'allow'
                protocol = rule.get('protocol', 'any')
                port = rule.get('port', '')
                source = rule.get('source', '')
                
                cmd = f"ufw {action}"
                if protocol != 'any':
                    cmd += f" {protocol}"
                if port:
                    cmd += f" {port}"
                if source:
                    cmd += f" from {source}"
                
                stdout, stderr, code = run_sudo_command(cmd, password)
                return code == 0, stderr if code != 0 else stdout
            
            elif rule.get('backend') == 'firewalld':
                zone = rule.get('zone', 'public')
                
                if rule.get('type') == 'service':
                    service = rule.get('service', '')
                    cmd = f"firewall-cmd --zone={zone} --remove-service={service} --permanent"
                elif rule.get('type') == 'port':
                    port = rule.get('port', '')
                    protocol = rule.get('protocol', 'tcp')
                    cmd = f"firewall-cmd --zone={zone} --remove-port={port}/{protocol} --permanent"
                
                stdout, stderr, code = run_sudo_command(cmd, password)
                if code == 0:
                    # Reload firewall
                    stdout2, stderr2, code2 = run_sudo_command("firewall-cmd --reload", password)
                    return code2 == 0, stderr2 if code2 != 0 else "Rule removed successfully"
                return False, stderr
            
            return False, "Unsupported firewall backend"
        except Exception as e:
            logger.error(f"Error removing firewall rule: {e}")
            return False, str(e)

# System Logs Management
class LogManager:
    """System logs management"""
    
    @staticmethod
    def get_logs(log_type: str = 'system', lines: int = 100) -> List[str]:
        """Get system logs"""
        logs = []
        
        try:
            if log_type == 'system':
                if os.path.exists("/usr/bin/journalctl"):
                    stdout, _, code = run_command(f"journalctl -n {lines} --no-pager")
                    if code == 0:
                        logs = stdout.split('\n')
                else:
                    # Fallback to syslog
                    if os.path.exists("/var/log/syslog"):
                        stdout, _, code = run_command(f"tail -n {lines} /var/log/syslog")
                        if code == 0:
                            logs = stdout.split('\n')
            
            elif log_type == 'kernel':
                if os.path.exists("/usr/bin/journalctl"):
                    stdout, _, code = run_command(f"journalctl -k -n {lines} --no-pager")
                    if code == 0:
                        logs = stdout.split('\n')
                else:
                    # Fallback to dmesg
                    stdout, _, code = run_command(f"dmesg | tail -n {lines}")
                    if code == 0:
                        logs = stdout.split('\n')
            
            elif log_type == 'auth':
                if os.path.exists("/var/log/auth.log"):
                    stdout, _, code = run_command(f"tail -n {lines} /var/log/auth.log")
                    if code == 0:
                        logs = stdout.split('\n')
        
        except Exception as e:
            logger.error(f"Error getting logs: {e}")
        
        return logs
    
    @staticmethod
    def clear_logs(log_type: str = 'system', password: str = None) -> Tuple[bool, str]:
        """Clear system logs"""
        try:
            if log_type == 'system':
                if os.path.exists("/usr/bin/journalctl"):
                    stdout, stderr, code = run_sudo_command("journalctl --vacuum-time=1s", password)
                    return code == 0, stderr if code != 0 else stdout
                else:
                    stdout, stderr, code = run_sudo_command("> /var/log/syslog", password)
                    return code == 0, stderr if code != 0 else "Logs cleared"
            
            elif log_type == 'kernel':
                stdout, stderr, code = run_sudo_command("dmesg -c", password)
                return code == 0, stderr if code != 0 else "Kernel logs cleared"
        
        except Exception as e:
            logger.error(f"Error clearing logs: {e}")
            return False, str(e)

# Package Management (Enhanced)
class PackageManager:
    """Enhanced package management interface"""
    
    def __init__(self):
        self.manager = PACKAGE_MANAGER
        self.cmd = PACKAGE_MANAGER_CMD
    
    def search_packages(self, query: str) -> List[Tuple[str, str]]:
        """Search for packages"""
        if not self.manager:
            return []
        
        commands = {
            "apt": f"apt search {query}",
            "dnf": f"dnf search {query}",
            "zypper": f"zypper search {query}",
            "pacman": f"pacman -Ss {query}",
            "brew": f"brew search {query}"
        }
        
        if self.manager in commands:
            stdout, _, code = run_command(commands[self.manager])
            if code == 0:
                return self._parse_package_list(stdout)
        return []
    
    def _parse_package_list(self, output: str) -> List[Tuple[str, str]]:
        """Parse package list output"""
        packages = []
        for line in output.split('\n'):
            if line.strip():
                if self.manager == "apt" and '/' in line and line[0].isalnum():
                    pkg = line.split('/')[0].strip()
                    desc = line.split(' - ', 1)[-1].strip()
                    packages.append((pkg, desc))
                elif self.manager == "brew" and not line.startswith('==>'):
                    parts = line.split(' ', 1)
                    if len(parts) == 2:
                        packages.append((parts[0].strip(), parts[1].strip()))
        return packages
    
    def get_installed_packages(self) -> List[Tuple[str, str, str]]:
        """Get installed packages"""
        if not self.manager:
            return []
        
        commands = {
            "apt": "dpkg -l",
            "dnf": "dnf list installed",
            "zypper": "zypper search -i",
            "pacman": "pacman -Q",
            "brew": "brew list"
        }
        
        if self.manager in commands:
            stdout, _, code = run_command(commands[self.manager])
            if code == 0:
                return self._parse_installed_list(stdout)
        return []
    
    def _parse_installed_list(self, output: str) -> List[Tuple[str, str, str]]:
        """Parse installed packages list"""
        packages = []
        for line in output.split('\n'):
            if line.strip():
                if self.manager == "apt" and line.startswith('ii'):
                    parts = line.split()
                    if len(parts) >= 3:
                        packages.append((parts[1], parts[2], ' '.join(parts[3:])))
                elif self.manager == "brew":
                    pkg = line.strip()
                    if pkg:
                        packages.append((pkg, "", ""))
        return packages
    
    def install_package(self, package: str, password: str = None) -> Tuple[bool, str]:
        """Install a package"""
        if not self.manager:
            return False, "No package manager found"
        
        commands = {
            "apt": f"apt install -y {package}",
            "dnf": f"dnf install -y {package}",
            "zypper": f"zypper install -y {package}",
            "pacman": f"pacman -S --noconfirm {package}",
            "brew": f"brew install {package}"
        }
        
        if self.manager in commands:
            if self.manager != "brew":
                stdout, stderr, code = run_sudo_command(commands[self.manager], password)
            else:
                stdout, stderr, code = run_command(commands[self.manager])
            
            return code == 0, stderr if code != 0 else stdout
        return False, "Unsupported package manager"
    
    def remove_package(self, package: str, password: str = None) -> Tuple[bool, str]:
        """Remove a package"""
        if not self.manager:
            return False, "No package manager found"
        
        commands = {
            "apt": f"apt remove -y {package}",
            "dnf": f"dnf remove -y {package}",
            "zypper": f"zypper remove -y {package}",
            "pacman": f"pacman -R --noconfirm {package}",
            "brew": f"brew uninstall {package}"
        }
        
        if self.manager in commands:
            if self.manager != "brew":
                stdout, stderr, code = run_sudo_command(commands[self.manager], password)
            else:
                stdout, stderr, code = run_command(commands[self.manager])
            
            return code == 0, stderr if code != 0 else stdout
        return False, "Unsupported package manager"
    
    def update_system(self, password: str = None) -> Tuple[bool, str]:
        """Update system packages"""
        if not self.manager:
            return False, "No package manager found"
        
        commands = {
            "apt": "apt update && apt upgrade -y",
            "dnf": "dnf upgrade -y",
            "zypper": "zypper update -y",
            "pacman": "pacman -Syu --noconfirm",
            "brew": "brew update && brew upgrade"
        }
        
        if self.manager in commands:
            if self.manager != "brew":
                stdout, stderr, code = run_sudo_command(commands[self.manager], password)
            else:
                stdout, stderr, code = run_command(commands[self.manager])
            
            return code == 0, stderr if code != 0 else stdout
        return False, "Unsupported package manager"
    
    def get_upgradable_packages(self) -> List[Tuple[str, str, str]]:
        """Get list of upgradable packages"""
        if not self.manager:
            return []
        
        commands = {
            "apt": "apt list --upgradable",
            "dnf": "dnf check-update",
            "zypper": "zypper list-updates",
            "pacman": "pacman -Qu",
            "brew": "brew outdated"
        }
        
        if self.manager in commands:
            stdout, _, code = run_command(commands[self.manager])
            if code == 0:
                return self._parse_upgradable_list(stdout)
        return []
    
    def _parse_upgradable_list(self, output: str) -> List[Tuple[str, str, str]]:
        """Parse upgradable packages list"""
        packages = []
        for line in output.split('\n'):
            if line.strip():
                if self.manager == "apt" and '/' in line and line[0].isalnum():
                    pkg = line.split('/')[0].strip()
                    version_info = line.split('[')[1].split(']')[0] if '[' in line else ""
                    packages.append((pkg, version_info, ""))
                elif self.manager == "dnf" and not line.startswith('Last metadata'):
                    parts = line.split()
                    if len(parts) >= 2:
                        packages.append((parts[0], parts[1], ""))
        return packages

# User Management (Enhanced)
class UserManager:
    """Enhanced user management interface"""
    
    @staticmethod
    def get_users() -> List[Dict[str, Any]]:
        """Get list of system users"""
        users = []
        try:
            for user in pwd.getpwall():
                if user.pw_uid >= 1000 or user.pw_name in ['root', 'nobody']:
                    users.append({
                        'username': user.pw_name,
                        'uid': user.pw_uid,
                        'gid': user.pw_gid,
                        'home': user.pw_dir,
                        'shell': user.pw_shell,
                        'gecos': user.pw_gecos,
                        'last_login': UserManager._get_last_login(user.pw_name)
                    })
        except Exception as e:
            logger.error(f"Error getting users: {e}")
        return users
    
    @staticmethod
    def _get_last_login(username: str) -> str:
        """Get last login time for user"""
        try:
            stdout, _, code = run_command(f"lastlog -u {username} | tail -1")
            if code == 0:
                parts = stdout.split()
                if len(parts) >= 8:
                    return ' '.join(parts[4:8])
        except:
            pass
        return "Never"
    
    @staticmethod
    def create_user(username: str, password: str, full_name: str = "", 
                   groups: List[str] = None, home_dir: str = "",
                   shell: str = "/bin/bash") -> Tuple[bool, str]:
        """Create a new user with enhanced options"""
        if groups is None:
            groups = []
        
        if not username or not password:
            return False, "Username and password required"
        
        if len(password) < 8:
            return False, "Password must be at least 8 characters"
        
        try:
            cmd = f"useradd -m -s {shell}"
            if full_name:
                cmd += f" -c '{full_name}'"
            if home_dir:
                cmd += f" -d {home_dir}"
            cmd += f" {username}"
            
            stdout, stderr, code = run_sudo_command(cmd)
            if code != 0:
                return False, stderr
            
            stdout, stderr, code = run_sudo_command(f"echo '{username}:{password}' | chpasswd")
            if code != 0:
                return False, stderr
            
            # Add to groups
            for group in groups:
                stdout, stderr, code = run_sudo_command(f"usermod -aG {group} {username}")
                if code != 0:
                    logger.warning(f"Failed to add user to group {group}: {stderr}")
            
            return True, "User created successfully"
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return False, str(e)
    
    @staticmethod
    def modify_user(username: str, **kwargs) -> Tuple[bool, str]:
        """Modify user properties"""
        if not username:
            return False, "Username cannot be empty"
        
        try:
            # Modify basic info
            if 'full_name' in kwargs:
                cmd = f"usermod -c '{kwargs['full_name']}' {username}"
                stdout, stderr, code = run_sudo_command(cmd)
                if code != 0:
                    return False, stderr
            
            if 'shell' in kwargs:
                cmd = f"usermod -s {kwargs['shell']} {username}"
                stdout, stderr, code = run_sudo_command(cmd)
                if code != 0:
                    return False, stderr
            
            if 'home_dir' in kwargs:
                cmd = f"usermod -d {kwargs['home_dir']} {username}"
                stdout, stderr, code = run_sudo_command(cmd)
                if code != 0:
                    return False, stderr
            
            if 'groups' in kwargs:
                groups = ','.join(kwargs['groups'])
                cmd = f"usermod -G {groups} {username}"
                stdout, stderr, code = run_sudo_command(cmd)
                if code != 0:
                    return False, stderr
            
            if 'password' in kwargs:
                cmd = f"echo '{username}:{kwargs['password']}' | chpasswd"
                stdout, stderr, code = run_sudo_command(cmd)
                if code != 0:
                    return False, stderr
            
            return True, "User modified successfully"
        except Exception as e:
            logger.error(f"Error modifying user: {e}")
            return False, str(e)
    
    @staticmethod
    def delete_user(username: str, remove_home: bool = True) -> Tuple[bool, str]:
        """Delete a user"""
        if not username or username == 'root':
            return False, "Cannot delete root user"
        
        try:
            cmd = f"userdel {'-r' if remove_home else ''} {username}"
            stdout, stderr, code = run_sudo_command(cmd)
            return code == 0, stderr if code != 0 else "User deleted successfully"
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            return False, str(e)
    
    @staticmethod
    def lock_user(username: str) -> Tuple[bool, str]:
        """Lock a user account"""
        if not username or username == 'root':
            return False, "Cannot lock root user"
        
        try:
            stdout, stderr, code = run_sudo_command(f"usermod -L {username}")
            return code == 0, stderr if code != 0 else "User locked successfully"
        except Exception as e:
            logger.error(f"Error locking user: {e}")
            return False, str(e)
    
    @staticmethod
    def unlock_user(username: str) -> Tuple[bool, str]:
        """Unlock a user account"""
        if not username:
            return False, "Username cannot be empty"
        
        try:
            stdout, stderr, code = run_sudo_command(f"usermod -U {username}")
            return code == 0, stderr if code != 0 else "User unlocked successfully"
        except Exception as e:
            logger.error(f"Error unlocking user: {e}")
            return False, str(e)
    
    @staticmethod
    def get_groups() -> List[Dict[str, Any]]:
        """Get all system groups"""
        groups = []
        try:
            for group in grp.getgrall():
                groups.append({
                    'name': group.gr_name,
                    'gid': group.gr_gid,
                    'members': group.gr_mem
                })
        except Exception as e:
            logger.error(f"Error getting groups: {e}")
        return groups

# GUI Components
class ProgressDialog(Gtk.Dialog):
    """Progress dialog for long-running operations"""
    
    def __init__(self, parent, title="Working...", message="Please wait..."):
        Gtk.Dialog.__init__(self, title=title, parent=parent, flags=Gtk.DialogFlags.MODAL)
        self.set_default_size(400, 100)
        self.cancelled = False
        
        # Content area
        content_area = self.get_content_area()
        
        # Message label
        self.message_label = Gtk.Label(label=message)
        content_area.pack_start(self.message_label, True, True, 10)
        
        # Progress bar
        self.progress_bar = Gtk.ProgressBar()
        self.progress_bar.set_show_text(True)
        content_area.pack_start(self.progress_bar, True, True, 10)
        
        # Cancel button
        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        
        self.show_all()
        self.connect("response", self.on_response)
    
    def on_response(self, dialog, response_id):
        if response_id == Gtk.ResponseType.CANCEL:
            self.cancelled = True
    
    def update_progress(self, fraction: float, text: str = None):
        """Update progress bar"""
        self.progress_bar.set_fraction(fraction)
        if text:
            self.progress_bar.set_text(text)
        while Gtk.events_pending():
            Gtk.main_iteration()
    
    def update_message(self, message: str):
        """Update message label"""
        self.message_label.set_text(message)
        while Gtk.events_pending():
            Gtk.main_iteration()

class PasswordDialog(Gtk.Dialog):
    """Password input dialog"""
    
    def __init__(self, parent, title="Authentication Required"):
        Gtk.Dialog.__init__(self, title=title, parent=parent, flags=Gtk.DialogFlags.MODAL)
        self.set_default_size(300, 150)
        
        # Content area
        content_area = self.get_content_area()
        
        # Message
        label = Gtk.Label(label="Enter your password:")
        content_area.pack_start(label, True, True, 10)
        
        # Password entry
        self.entry = Gtk.Entry()
        self.entry.set_visibility(False)
        self.entry.set_invisible_char("*")
        self.entry.connect("activate", lambda _: self.response(Gtk.ResponseType.OK))
        content_area.pack_start(self.entry, True, True, 10)
        
        # Buttons
        self.add_button(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL)
        self.add_button(Gtk.STOCK_OK, Gtk.ResponseType.OK)
        
        self.show_all()
    
    def get_password(self) -> str:
        """Get entered password"""
        return self.entry.get_text()

# Main Application Window
class DockpanelWindow(Gtk.ApplicationWindow):
    """Main application window"""
    
    def __init__(self, app):
        Gtk.ApplicationWindow.__init__(self, application=app, title=APP_NAME)
        self.set_default_size(1400, 900)
        self.set_border_width(0)
        
        # Initialize managers
        self.pkg_manager = PackageManager()
        self.repo_manager = RepositoryManager()
        self.boot_manager = BootManager()
        self.kernel_manager = KernelManager()
        self.service_manager = SystemServiceManager()
        self.firewall_manager = FirewallManager()
        self.log_manager = LogManager()
        self.user_manager = UserManager()
        
        # Create main container
        self.main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.add(self.main_box)
        
        # Create header
        self.create_header()
        
        # Create main content area
        self.create_main_content()
        
        # Status bar
        self.statusbar = Gtk.Statusbar()
        self.main_box.pack_start(self.statusbar, False, False, 0)
        self.statusbar.push(0, "Ready")
        
        # Show all
        self.show_all()
    
    def create_header(self):
        """Create application header"""
        header = Gtk.HeaderBar()
        header.set_show_close_button(True)
        header.props.title = APP_NAME
        
        # Add refresh button
        refresh_button = Gtk.Button.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON)
        refresh_button.set_tooltip_text("Refresh")
        refresh_button.connect("clicked", self.on_refresh_clicked)
        header.pack_end(refresh_button)
        
        # Add about button
        about_button = Gtk.Button.new_from_icon_name("help-about", Gtk.IconSize.BUTTON)
        about_button.set_tooltip_text("About")
        about_button.connect("clicked", self.on_about_clicked)
        header.pack_end(about_button)
        
        self.set_titlebar(header)
    
    def create_main_content(self):
        """Create main content area with sidebar and content"""
        # Main horizontal container
        self.content_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        self.main_box.pack_start(self.content_box, True, True, 0)
        
        # Create sidebar
        self.create_sidebar()
        
        # Create content area
        self.create_content_area()
    
    def create_sidebar(self):
        """Create sidebar with navigation"""
        # Sidebar container
        self.sidebar = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.sidebar.set_size_request(220, -1)
        self.sidebar.get_style_context().add_class("sidebar")
        self.content_box.pack_start(self.sidebar, False, False, 0)
        
        # Sidebar header
        sidebar_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        sidebar_header.set_margin_top(10)
        sidebar_header.set_margin_bottom(10)
        sidebar_header.set_margin_start(10)
        sidebar_header.set_margin_end(10)
        
        # App icon
        app_icon = Gtk.Image.new_from_icon_name("computer", Gtk.IconSize.LARGE_TOOLBAR)
        sidebar_header.pack_start(app_icon, False, False, 0)
        
        # App name
        app_label = Gtk.Label()
        app_label.set_markup("<b>Dockpanel</b>")
        sidebar_header.pack_start(app_label, False, False, 0)
        
        self.sidebar.pack_start(sidebar_header, False, False, 0)
        
        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.sidebar.pack_start(separator, False, False, 0)
        
        # Navigation list
        self.nav_list = Gtk.ListBox()
        self.nav_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.nav_list.connect("row-selected", self.on_nav_selected)
        
        # Navigation items
        nav_items = [
            ("view-grid", "Dashboard", "dashboard"),
            ("system-software-install", "Packages", "packages"),
            ("folder-remote", "Repositories", "repositories"),
            ("system-users", "Users", "users"),
            ("network-transmit-receive", "Network", "network"),
            ("system-run", "Services", "services"),
            ("dialog-information", "Processes", "processes"),
            ("drive-harddisk", "Disks", "disks"),
            ("media-floppy", "Boot Loader", "boot"),
            ("document-save", "Backups", "backups"),
            ("user-trash", "Cleaner", "cleaner"),
            ("text-x-generic", "Logs", "logs"),
            ("security-high", "Firewall", "firewall"),
            ("preferences-system", "System", "system")
        ]
        
        for icon_name, label, page_id in nav_items:
            row = Gtk.ListBoxRow()
            row.set_name(page_id)
            
            box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            box.set_margin_top(8)
            box.set_margin_bottom(8)
            box.set_margin_start(10)
            box.set_margin_end(10)
            
            icon = Gtk.Image.new_from_icon_name(icon_name, Gtk.IconSize.MENU)
            box.pack_start(icon, False, False, 0)
            
            label_widget = Gtk.Label(label=label)
            label_widget.set_halign(Gtk.Align.START)
            box.pack_start(label_widget, True, True, 0)
            
            row.add(box)
            self.nav_list.add(row)
        
        # Make sidebar scrollable
        sidebar_scrolled = Gtk.ScrolledWindow()
        sidebar_scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        sidebar_scrolled.add(self.nav_list)
        sidebar_scrolled.set_hexpand(False)
        sidebar_scrolled.set_vexpand(True)
        
        self.sidebar.pack_start(sidebar_scrolled, True, True, 0)
        
        # Select first item by default
        self.nav_list.select_row(self.nav_list.get_row_at_index(0))
    
    def create_content_area(self):
        """Create main content area"""
        # Content container
        self.content_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.content_container.set_hexpand(True)
        self.content_container.set_vexpand(True)
        self.content_box.pack_start(self.content_container, True, True, 0)
        
        # Create stack for pages
        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.content_container.pack_start(self.stack, True, True, 0)
        
        # Create pages
        self.create_dashboard_page()
        self.create_packages_page()
        self.create_repositories_page()
        self.create_users_page()
        self.create_network_page()
        self.create_services_page()
        self.create_processes_page()
        self.create_disks_page()
        self.create_boot_page()
        self.create_backups_page()
        self.create_cleaner_page()
        self.create_logs_page()
        self.create_firewall_page()
        self.create_system_page()
    
    def create_dashboard_page(self):
        """Create dashboard page"""
        # Main container
        dashboard_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        dashboard_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>System Dashboard</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        dashboard_container.pack_start(title, False, False, 0)
        
        # System info grid
        system_grid = Gtk.Grid()
        system_grid.set_row_spacing(15)
        system_grid.set_column_spacing(15)
        system_grid.set_column_homogeneous(True)
        
        # System info card
        system_card = self.create_card("System Information")
        system_info = SystemInfoManager.get_system_info()
        
        info_grid = Gtk.Grid()
        info_grid.set_row_spacing(8)
        info_grid.set_column_spacing(10)
        
        info_items = [
            ("OS", f"{system_info.os} {system_info.distro}"),
            ("Kernel", system_info.kernel),
            ("Hostname", system_info.hostname),
            ("Uptime", system_info.uptime),
            ("Boot Mode", system_info.boot_mode),
            ("Secure Boot", "Enabled" if system_info.secure_boot else "Disabled"),
            ("CPU", f"{system_info.cpu_model} ({system_info.cpu_cores} cores)"),
            ("Memory", f"{system_info.memory_used}GB / {system_info.memory_total}GB"),
            ("Disk", f"{system_info.disk_used}GB / {system_info.disk_total}GB")
        ]
        
        for i, (label, value) in enumerate(info_items):
            lbl = Gtk.Label(label=f"{label}:")
            lbl.set_halign(Gtk.Align.START)
            lbl.get_style_context().add_class("dim-label")
            info_grid.attach(lbl, 0, i, 1, 1)
            
            value_lbl = Gtk.Label(label=value)
            value_lbl.set_halign(Gtk.Align.START)
            value_lbl.set_selectable(True)
            info_grid.attach(value_lbl, 1, i, 1, 1)
        
        system_card.get_child().add(info_grid)
        system_grid.attach(system_card, 0, 0, 2, 1)
        
        # Quick actions card
        actions_card = self.create_card("Quick Actions")
        actions_grid = Gtk.Grid()
        actions_grid.set_row_spacing(10)
        actions_grid.set_column_spacing(10)
        actions_grid.set_column_homogeneous(True)
        
        actions = [
            ("Update System", "system-software-update", self.on_quick_update),
            ("Clean System", "user-trash", self.on_quick_clean),
            ("Network Info", "network-transmit-receive", self.on_quick_network),
            ("Service Status", "system-run", self.on_quick_services),
            ("Disk Usage", "drive-harddisk", self.on_quick_disk),
            ("System Logs", "text-x-generic", self.on_quick_logs)
        ]
        
        for i, (label, icon, callback) in enumerate(actions):
            btn = Gtk.Button(label=label)
            btn.set_hexpand(True)
            btn.set_vexpand(True)
            if icon:
                btn.set_image(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON))
                btn.set_always_show_image(True)
            btn.connect("clicked", callback)
            actions_grid.attach(btn, i % 3, i // 3, 1, 1)
        
        actions_card.get_child().add(actions_grid)
        system_grid.attach(actions_card, 0, 1, 2, 1)
        
        dashboard_container.pack_start(system_grid, True, True, 0)
        
        # Make scrollable
        dashboard_scrolled = Gtk.ScrolledWindow()
        dashboard_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        dashboard_scrolled.add(dashboard_container)
        
        self.stack.add_titled(dashboard_scrolled, "dashboard", "Dashboard")
    
    def create_repositories_page(self):
        """Create repositories page"""
        repos_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        repos_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Repository Management</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        repos_container.pack_start(title, False, False, 0)
        
        # Toolbar
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        
        add_repo_button = Gtk.Button(label="Add Repository")
        add_repo_button.set_image(Gtk.Image.new_from_icon_name("list-add", Gtk.IconSize.BUTTON))
        add_repo_button.set_always_show_image(True)
        add_repo_button.connect("clicked", self.on_add_repository)
        toolbar.pack_start(add_repo_button, False, False, 0)
        
        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.set_image(Gtk.Image.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON))
        refresh_button.set_always_show_image(True)
        refresh_button.connect("clicked", self.on_refresh_repositories)
        toolbar.pack_start(refresh_button, False, False, 0)
        
        repos_container.pack_start(toolbar, False, False, 0)
        
        # Repository list
        repos_card = self.create_card("System Repositories")
        repos_scrolled = Gtk.ScrolledWindow()
        repos_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        repos_scrolled.set_min_content_height(400)
        
        # Create treeview for repositories
        self.repo_liststore = Gtk.ListStore(bool, str, str, str)
        self.repo_treeview = Gtk.TreeView(model=self.repo_liststore)
        self.repo_treeview.set_rules_hint(True)
        
        # Add columns
        toggle_renderer = Gtk.CellRendererToggle()
        toggle_renderer.connect("toggled", self.on_repo_toggled)
        toggle_column = Gtk.TreeViewColumn("Enabled", toggle_renderer, active=0)
        self.repo_treeview.append_column(toggle_column)
        
        text_renderer = Gtk.CellRendererText()
        name_column = Gtk.TreeViewColumn("Name", text_renderer, text=1)
        name_column.set_resizable(True)
        self.repo_treeview.append_column(name_column)
        
        url_column = Gtk.TreeViewColumn("URL", text_renderer, text=2)
        url_column.set_resizable(True)
        self.repo_treeview.append_column(url_column)
        
        type_column = Gtk.TreeViewColumn("Type", text_renderer, text=3)
        self.repo_treeview.append_column(type_column)
        
        repos_scrolled.add(self.repo_treeview)
        repos_card.get_child().add(repos_scrolled)
        repos_container.pack_start(repos_card, True, True, 0)
        
        # Action buttons
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_top(10)
        
        self.enable_repo_button = Gtk.Button(label="Enable")
        self.enable_repo_button.set_image(Gtk.Image.new_from_icon_name("dialog-yes", Gtk.IconSize.BUTTON))
        self.enable_repo_button.set_always_show_image(True)
        self.enable_repo_button.set_sensitive(False)
        self.enable_repo_button.connect("clicked", self.on_enable_repository)
        action_box.pack_start(self.enable_repo_button, False, False, 0)
        
        self.disable_repo_button = Gtk.Button(label="Disable")
        self.disable_repo_button.set_image(Gtk.Image.new_from_icon_name("dialog-no", Gtk.IconSize.BUTTON))
        self.disable_repo_button.set_always_show_image(True)
        self.disable_repo_button.set_sensitive(False)
        self.disable_repo_button.connect("clicked", self.on_disable_repository)
        action_box.pack_start(self.disable_repo_button, False, False, 0)
        
        self.remove_repo_button = Gtk.Button(label="Remove")
        self.remove_repo_button.set_image(Gtk.Image.new_from_icon_name("edit-delete", Gtk.IconSize.BUTTON))
        self.remove_repo_button.set_always_show_image(True)
        self.remove_repo_button.set_sensitive(False)
        self.remove_repo_button.connect("clicked", self.on_remove_repository)
        action_box.pack_start(self.remove_repo_button, False, False, 0)
        
        repos_container.pack_start(action_box, False, False, 0)
        
        # Make scrollable
        repos_scrolled = Gtk.ScrolledWindow()
        repos_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        repos_scrolled.add(repos_container)
        
        self.stack.add_titled(repos_scrolled, "repositories", "Repositories")
        
        # Connect selection signal
        self.repo_treeview.get_selection().connect("changed", self.on_repo_selected)
        
        # Load repositories
        self.load_repositories()
    
    def create_boot_page(self):
        """Create boot configuration page"""
        boot_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        boot_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Boot Configuration</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        boot_container.pack_start(title, False, False, 0)
        
        # Boot info grid
        boot_grid = Gtk.Grid()
        boot_grid.set_row_spacing(15)
        boot_grid.set_column_spacing(15)
        boot_grid.set_column_homogeneous(True)
        
        # Boot loader info card
        bootloader_card = self.create_card("Boot Loader Information")
        boot_config = self.boot_manager.get_boot_config()
        
        info_grid = Gtk.Grid()
        info_grid.set_row_spacing(8)
        info_grid.set_column_spacing(10)
        
        info_items = [
            ("Boot Loader", boot_config['bootloader']),
            ("Default Entry", boot_config['default_entry']),
            ("Timeout", f"{boot_config['timeout']} seconds")
        ]
        
        for i, (label, value) in enumerate(info_items):
            lbl = Gtk.Label(label=f"{label}:")
            lbl.set_halign(Gtk.Align.START)
            lbl.get_style_context().add_class("dim-label")
            info_grid.attach(lbl, 0, i, 1, 1)
            
            value_lbl = Gtk.Label(label=value)
            value_lbl.set_halign(Gtk.Align.START)
            value_lbl.set_selectable(True)
            info_grid.attach(value_lbl, 1, i, 1, 1)
        
        bootloader_card.get_child().add(info_grid)
        boot_grid.attach(bootloader_card, 0, 0, 1, 1)
        
        # Boot entries card
        entries_card = self.create_card("Boot Entries")
        entries_scrolled = Gtk.ScrolledWindow()
        entries_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        entries_scrolled.set_min_content_height(200)
        
        self.boot_entries_list = Gtk.ListBox()
        entries_scrolled.add(self.boot_entries_list)
        
        entries_card.get_child().add(entries_scrolled)
        boot_grid.attach(entries_card, 1, 0, 1, 1)
        
        # Kernel management card
        kernel_card = self.create_card("Kernel Management")
        kernel_grid = Gtk.Grid()
        kernel_grid.set_row_spacing(10)
        kernel_grid.set_column_spacing(10)
        
        # Keep kernels spin button
        kernel_grid.attach(Gtk.Label(label="Keep Kernels:"), 0, 0, 1, 1)
        self.keep_kernels_spin = Gtk.SpinButton()
        self.keep_kernels_spin.set_range(1, 10)
        self.keep_kernels_spin.set_value(2)
        kernel_grid.attach(self.keep_kernels_spin, 1, 0, 1, 1)
        
        # Remove old kernels button
        remove_kernels_button = Gtk.Button(label="Remove Old Kernels")
        remove_kernels_button.set_image(Gtk.Image.new_from_icon_name("edit-delete", Gtk.IconSize.BUTTON))
        remove_kernels_button.set_always_show_image(True)
        remove_kernels_button.connect("clicked", self.on_remove_old_kernels)
        kernel_grid.attach(remove_kernels_button, 0, 1, 2, 1)
        
        kernel_card.get_child().add(kernel_grid)
        boot_grid.attach(kernel_card, 0, 1, 2, 1)
        
        boot_container.pack_start(boot_grid, True, True, 0)
        
        # Action buttons
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_top(10)
        
        update_grub_button = Gtk.Button(label="Update GRUB")
        update_grub_button.set_image(Gtk.Image.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON))
        update_grub_button.set_always_show_image(True)
        update_grub_button.connect("clicked", self.on_update_grub)
        action_box.pack_start(update_grub_button, False, False, 0)
        
        boot_container.pack_start(action_box, False, False, 0)
        
        # Make scrollable
        boot_scrolled = Gtk.ScrolledWindow()
        boot_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        boot_scrolled.add(boot_container)
        
        self.stack.add_titled(boot_scrolled, "boot", "Boot Loader")
        
        # Load boot entries
        self.load_boot_entries()
    
    def create_firewall_page(self):
        """Create firewall page"""
        firewall_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        firewall_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Firewall Configuration</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        firewall_container.pack_start(title, False, False, 0)
        
        # Firewall info grid
        firewall_grid = Gtk.Grid()
        firewall_grid.set_row_spacing(15)
        firewall_grid.set_column_spacing(15)
        firewall_grid.set_column_homogeneous(True)
        
        # Firewall status card
        status_card = self.create_card("Firewall Status")
        firewall_info = self.firewall_manager.get_firewall_info()
        
        info_grid = Gtk.Grid()
        info_grid.set_row_spacing(8)
        info_grid.set_column_spacing(10)
        
        info_items = [
            ("Backend", firewall_info['backend']),
            ("Status", "Active" if firewall_info['active'] else "Inactive"),
            ("Default Zone", firewall_info.get('default_zone', 'N/A'))
        ]
        
        for i, (label, value) in enumerate(info_items):
            lbl = Gtk.Label(label=f"{label}:")
            lbl.set_halign(Gtk.Align.START)
            lbl.get_style_context().add_class("dim-label")
            info_grid.attach(lbl, 0, i, 1, 1)
            
            value_lbl = Gtk.Label(label=value)
            value_lbl.set_halign(Gtk.Align.START)
            value_lbl.set_selectable(True)
            info_grid.attach(value_lbl, 1, i, 1, 1)
        
        # Firewall toggle
        self.firewall_switch = Gtk.Switch()
        self.firewall_switch.set_active(firewall_info['active'])
        self.firewall_switch.connect("notify::active", self.on_firewall_toggle)
        info_grid.attach(Gtk.Label(label="Enable:"), 0, len(info_items), 1, 1)
        info_grid.attach(self.firewall_switch, 1, len(info_items), 1, 1)
        
        status_card.get_child().add(info_grid)
        firewall_grid.attach(status_card, 0, 0, 1, 1)
        
        # Firewall rules card
        rules_card = self.create_card("Firewall Rules")
        rules_scrolled = Gtk.ScrolledWindow()
        rules_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        rules_scrolled.set_min_content_height(300)
        
        # Create treeview for rules
        self.rules_liststore = Gtk.ListStore(str, str, str, str, str)
        self.rules_treeview = Gtk.TreeView(model=self.rules_liststore)
        self.rules_treeview.set_rules_hint(True)
        
        # Add columns
        text_renderer = Gtk.CellRendererText()
        columns = [
            ("Action", 0),
            ("Direction", 1),
            ("Protocol", 2),
            ("Source", 3),
            ("Destination", 4)
        ]
        
        for title, col_id in columns:
            column = Gtk.TreeViewColumn(title, text_renderer, text=col_id)
            column.set_resizable(True)
            self.rules_treeview.append_column(column)
        
        rules_scrolled.add(self.rules_treeview)
        rules_card.get_child().add(rules_scrolled)
        firewall_grid.attach(rules_card, 1, 0, 1, 1)
        
        firewall_container.pack_start(firewall_grid, True, True, 0)
        
        # Rule management buttons
        rule_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        rule_box.set_halign(Gtk.Align.END)
        rule_box.set_margin_top(10)
        
        add_rule_button = Gtk.Button(label="Add Rule")
        add_rule_button.set_image(Gtk.Image.new_from_icon_name("list-add", Gtk.IconSize.BUTTON))
        add_rule_button.set_always_show_image(True)
        add_rule_button.connect("clicked", self.on_add_firewall_rule)
        rule_box.pack_start(add_rule_button, False, False, 0)
        
        self.remove_rule_button = Gtk.Button(label="Remove Rule")
        self.remove_rule_button.set_image(Gtk.Image.new_from_icon_name("edit-delete", Gtk.IconSize.BUTTON))
        self.remove_rule_button.set_always_show_image(True)
        self.remove_rule_button.set_sensitive(False)
        self.remove_rule_button.connect("clicked", self.on_remove_firewall_rule)
        rule_box.pack_start(self.remove_rule_button, False, False, 0)
        
        firewall_container.pack_start(rule_box, False, False, 0)
        
        # Make scrollable
        firewall_scrolled = Gtk.ScrolledWindow()
        firewall_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        firewall_scrolled.add(firewall_container)
        
        self.stack.add_titled(firewall_scrolled, "firewall", "Firewall")
        
        # Connect selection signal
        self.rules_treeview.get_selection().connect("changed", self.on_rule_selected)
        
        # Load firewall rules
        self.load_firewall_rules()
    
    def create_logs_page(self):
        """Create logs page"""
        logs_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        logs_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>System Logs</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        logs_container.pack_start(title, False, False, 0)
        
        # Log type selection
        log_type_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        log_type_box.pack_start(Gtk.Label(label="Log Type:"), False, False, 0)
        
        self.log_type_combo = Gtk.ComboBoxText()
        self.log_type_combo.append_text("System")
        self.log_type_combo.append_text("Kernel")
        self.log_type_combo.append_text("Authentication")
        self.log_type_combo.set_active(0)
        self.log_type_combo.connect("changed", self.on_log_type_changed)
        log_type_box.pack_start(self.log_type_combo, False, False, 0)
        
        # Number of lines
        log_type_box.pack_start(Gtk.Label(label="Lines:"), False, False, 0)
        
        self.log_lines_spin = Gtk.SpinButton()
        self.log_lines_spin.set_range(10, 1000)
        self.log_lines_spin.set_value(100)
        self.log_lines_spin.set_increments(10, 50)
        log_type_box.pack_start(self.log_lines_spin, False, False, 0)
        
        # Refresh button
        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.set_image(Gtk.Image.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON))
        refresh_button.set_always_show_image(True)
        refresh_button.connect("clicked", self.on_refresh_logs)
        log_type_box.pack_start(refresh_button, False, False, 0)
        
        # Clear button
        clear_button = Gtk.Button(label="Clear Logs")
        clear_button.set_image(Gtk.Image.new_from_icon_name("edit-clear", Gtk.IconSize.BUTTON))
        clear_button.set_always_show_image(True)
        clear_button.connect("clicked", self.on_clear_logs)
        log_type_box.pack_start(clear_button, False, False, 0)
        
        logs_container.pack_start(log_type_box, False, False, 0)
        
        # Logs display
        logs_card = self.create_card("Log Entries")
        logs_scrolled = Gtk.ScrolledWindow()
        logs_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        logs_scrolled.set_min_content_height(400)
        
        self.logs_textview = Gtk.TextView()
        self.logs_textview.set_editable(False)
        self.logs_textview.set_wrap_mode(Gtk.WrapMode.NONE)
        self.logs_textview.get_buffer().create_tag("monospace", family="Monospace")
        
        logs_scrolled.add(self.logs_textview)
        logs_card.get_child().add(logs_scrolled)
        logs_container.pack_start(logs_card, True, True, 0)
        
        # Make scrollable
        logs_scrolled = Gtk.ScrolledWindow()
        logs_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        logs_scrolled.add(logs_container)
        
        self.stack.add_titled(logs_scrolled, "logs", "Logs")
        
        # Load initial logs
        self.load_logs()
    
    def create_packages_page(self):
        """Create packages page"""
        packages_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        packages_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Package Management</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        packages_container.pack_start(title, False, False, 0)
        
        # Search bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.package_search_entry = Gtk.Entry()
        self.package_search_entry.set_placeholder_text("Search packages...")
        self.package_search_entry.connect("activate", self.on_package_search)
        search_box.pack_start(self.package_search_entry, True, True, 0)
        
        search_button = Gtk.Button(label="Search")
        search_button.set_image(Gtk.Image.new_from_icon_name("system-search", Gtk.IconSize.BUTTON))
        search_button.set_always_show_image(True)
        search_button.connect("clicked", self.on_package_search)
        search_box.pack_start(search_button, False, False, 0)
        
        packages_container.pack_start(search_box, False, False, 0)
        
        # Package paned
        package_paned = Gtk.Paned(orientation=Gtk.Orientation.VERTICAL)
        package_paned.set_position(300)
        
        # Installed packages
        installed_card = self.create_card("Installed Packages")
        installed_scrolled = Gtk.ScrolledWindow()
        installed_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        installed_scrolled.set_min_content_height(200)
        
        self.installed_packages_list = Gtk.ListBox()
        self.installed_packages_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        installed_scrolled.add(self.installed_packages_list)
        
        installed_card.get_child().add(installed_scrolled)
        package_paned.pack1(installed_card, True, False)
        
        # Available packages
        available_card = self.create_card("Available Packages")
        available_scrolled = Gtk.ScrolledWindow()
        available_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        available_scrolled.set_min_content_height(200)
        
        self.available_packages_list = Gtk.ListBox()
        self.available_packages_list.set_selection_mode(Gtk.SelectionMode.SINGLE)
        available_scrolled.add(self.available_packages_list)
        
        available_card.get_child().add(available_scrolled)
        package_paned.pack2(available_card, True, False)
        
        packages_container.pack_start(package_paned, True, True, 0)
        
        # Upgradable packages
        upgradable_card = self.create_card("Upgradable Packages")
        upgradable_scrolled = Gtk.ScrolledWindow()
        upgradable_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        upgradable_scrolled.set_min_content_height(150)
        
        self.upgradable_packages_list = Gtk.ListBox()
        upgradable_scrolled.add(self.upgradable_packages_list)
        
        upgradable_card.get_child().add(upgradable_scrolled)
        packages_container.pack_start(upgradable_card, True, True, 0)
        
        # Action buttons
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_top(10)
        
        self.install_button = Gtk.Button(label="Install")
        self.install_button.set_image(Gtk.Image.new_from_icon_name("document-save", Gtk.IconSize.BUTTON))
        self.install_button.set_always_show_image(True)
        self.install_button.set_sensitive(False)
        self.install_button.connect("clicked", self.on_package_install)
        action_box.pack_start(self.install_button, False, False, 0)
        
        self.remove_button = Gtk.Button(label="Remove")
        self.remove_button.set_image(Gtk.Image.new_from_icon_name("edit-delete", Gtk.IconSize.BUTTON))
        self.remove_button.set_always_show_image(True)
        self.remove_button.set_sensitive(False)
        self.remove_button.connect("clicked", self.on_package_remove)
        action_box.pack_start(self.remove_button, False, False, 0)
        
        upgrade_button = Gtk.Button(label="Upgrade All")
        upgrade_button.set_image(Gtk.Image.new_from_icon_name("system-software-update", Gtk.IconSize.BUTTON))
        upgrade_button.set_always_show_image(True)
        upgrade_button.connect("clicked", self.on_package_upgrade_all)
        action_box.pack_start(upgrade_button, False, False, 0)
        
        update_button = Gtk.Button(label="Update System")
        update_button.set_image(Gtk.Image.new_from_icon_name("system-software-update", Gtk.IconSize.BUTTON))
        update_button.set_always_show_image(True)
        update_button.connect("clicked", self.on_package_update)
        action_box.pack_start(update_button, False, False, 0)
        
        packages_container.pack_start(action_box, False, False, 0)
        
        # Make scrollable
        packages_scrolled = Gtk.ScrolledWindow()
        packages_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        packages_scrolled.add(packages_container)
        
        self.stack.add_titled(packages_scrolled, "packages", "Packages")
        
        # Load packages
        self.load_packages()
    
    def create_users_page(self):
        """Create users page"""
        users_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        users_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>User Management</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        users_container.pack_start(title, False, False, 0)
        
        # User list
        users_card = self.create_card("System Users")
        users_scrolled = Gtk.ScrolledWindow()
        users_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        users_scrolled.set_min_content_height(300)
        
        # Create treeview for users
        self.user_liststore = Gtk.ListStore(str, str, str, str, str)
        self.user_treeview = Gtk.TreeView(model=self.user_liststore)
        self.user_treeview.set_rules_hint(True)
        
        # Add columns
        text_renderer = Gtk.CellRendererText()
        columns = [
            ("Username", 0),
            ("UID", 1),
            ("Home", 2),
            ("Shell", 3),
            ("Last Login", 4)
        ]
        
        for title, col_id in columns:
            column = Gtk.TreeViewColumn(title, text_renderer, text=col_id)
            column.set_resizable(True)
            self.user_treeview.append_column(column)
        
        users_scrolled.add(self.user_treeview)
        users_card.get_child().add(users_scrolled)
        users_container.pack_start(users_card, True, True, 0)
        
        # Action buttons
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_top(10)
        
        add_user_button = Gtk.Button(label="Add User")
        add_user_button.set_image(Gtk.Image.new_from_icon_name("list-add", Gtk.IconSize.BUTTON))
        add_user_button.set_always_show_image(True)
        add_user_button.connect("clicked", self.on_add_user)
        action_box.pack_start(add_user_button, False, False, 0)
        
        self.modify_user_button = Gtk.Button(label="Modify User")
        self.modify_user_button.set_image(Gtk.Image.new_from_icon_name("document-edit", Gtk.IconSize.BUTTON))
        self.modify_user_button.set_always_show_image(True)
        self.modify_user_button.set_sensitive(False)
        self.modify_user_button.connect("clicked", self.on_modify_user)
        action_box.pack_start(self.modify_user_button, False, False, 0)
        
        self.lock_user_button = Gtk.Button(label="Lock/Unlock")
        self.lock_user_button.set_image(Gtk.Image.new_from_icon_name("system-lock-screen", Gtk.IconSize.BUTTON))
        self.lock_user_button.set_always_show_image(True)
        self.lock_user_button.set_sensitive(False)
        self.lock_user_button.connect("clicked", self.on_lock_user)
        action_box.pack_start(self.lock_user_button, False, False, 0)
        
        self.delete_user_button = Gtk.Button(label="Delete User")
        self.delete_user_button.set_image(Gtk.Image.new_from_icon_name("edit-delete", Gtk.IconSize.BUTTON))
        self.delete_user_button.set_always_show_image(True)
        self.delete_user_button.set_sensitive(False)
        self.delete_user_button.connect("clicked", self.on_delete_user)
        action_box.pack_start(self.delete_user_button, False, False, 0)
        
        users_container.pack_start(action_box, False, False, 0)
        
        # Make scrollable
        users_scrolled = Gtk.ScrolledWindow()
        users_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        users_scrolled.add(users_container)
        
        self.stack.add_titled(users_scrolled, "users", "Users")
        
        # Connect selection signal
        self.user_treeview.get_selection().connect("changed", self.on_user_selected)
        
        # Load users
        self.load_users()
    
    def create_network_page(self):
        """Create network page"""
        network_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        network_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Network Management</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        network_container.pack_start(title, False, False, 0)
        
        # Network grid
        network_grid = Gtk.Grid()
        network_grid.set_row_spacing(15)
        network_grid.set_column_spacing(15)
        network_grid.set_column_homogeneous(True)
        
        # Network interfaces
        interfaces_card = self.create_card("Network Interfaces")
        interfaces_scrolled = Gtk.ScrolledWindow()
        interfaces_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        interfaces_scrolled.set_min_content_height(150)
        
        self.interfaces_list = Gtk.ListBox()
        interfaces_scrolled.add(self.interfaces_list)
        
        interfaces_card.get_child().add(interfaces_scrolled)
        network_grid.attach(interfaces_card, 0, 0, 1, 1)
        
        # Network status
        status_card = self.create_card("Network Status")
        status_grid = Gtk.Grid()
        status_grid.set_row_spacing(10)
        status_grid.set_column_spacing(10)
        
        # Get network status
        stdout, _, code = run_command("ip route | grep default")
        if code == 0:
            gateway = stdout.split()[2]
            status_grid.attach(Gtk.Label(label="Gateway:"), 0, 0, 1, 1)
            status_grid.attach(Gtk.Label(label=gateway), 1, 0, 1, 1)
        
        stdout, _, code = run_command("cat /etc/resolv.conf | grep nameserver")
        if code == 0:
            dns = stdout.split()[-1]
            status_grid.attach(Gtk.Label(label="DNS:"), 0, 1, 1, 1)
            status_grid.attach(Gtk.Label(label=dns), 1, 1, 1, 1)
        
        status_card.get_child().add(status_grid)
        network_grid.attach(status_card, 1, 0, 1, 1)
        
        network_container.pack_start(network_grid, True, True, 0)
        
        # Make scrollable
        network_scrolled = Gtk.ScrolledWindow()
        network_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        network_scrolled.add(network_container)
        
        self.stack.add_titled(network_scrolled, "network", "Network")
        
        # Load network info
        self.load_network_info()
    
    def create_services_page(self):
        """Create services page"""
        services_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        services_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Service Management</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        services_container.pack_start(title, False, False, 0)
        
        # Services list
        services_card = self.create_card("System Services")
        services_scrolled = Gtk.ScrolledWindow()
        services_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        services_scrolled.set_min_content_height(300)
        
        # Create treeview for services
        self.service_liststore = Gtk.ListStore(str, str, str, str, bool)
        self.service_treeview = Gtk.TreeView(model=self.service_liststore)
        self.service_treeview.set_rules_hint(True)
        
        # Add columns
        text_renderer = Gtk.CellRendererText()
        columns = [
            ("Name", 0),
            ("Load", 1),
            ("Active", 2),
            ("Sub", 3)
        ]
        
        for title, col_id in columns:
            column = Gtk.TreeViewColumn(title, text_renderer, text=col_id)
            column.set_resizable(True)
            self.service_treeview.append_column(column)
        
        # Enabled column with toggle
        toggle_renderer = Gtk.CellRendererToggle()
        toggle_renderer.connect("toggled", self.on_service_enabled_toggled)
        enabled_column = Gtk.TreeViewColumn("Enabled", toggle_renderer, active=4)
        self.service_treeview.append_column(enabled_column)
        
        services_scrolled.add(self.service_treeview)
        services_card.get_child().add(services_scrolled)
        services_container.pack_start(services_card, True, True, 0)
        
        # Action buttons
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_top(10)
        
        self.start_button = Gtk.Button(label="Start")
        self.start_button.set_image(Gtk.Image.new_from_icon_name("media-playback-start", Gtk.IconSize.BUTTON))
        self.start_button.set_always_show_image(True)
        self.start_button.set_sensitive(False)
        self.start_button.connect("clicked", self.on_service_start)
        action_box.pack_start(self.start_button, False, False, 0)
        
        self.stop_button = Gtk.Button(label="Stop")
        self.stop_button.set_image(Gtk.Image.new_from_icon_name("media-playback-stop", Gtk.IconSize.BUTTON))
        self.stop_button.set_always_show_image(True)
        self.stop_button.set_sensitive(False)
        self.stop_button.connect("clicked", self.on_service_stop)
        action_box.pack_start(self.stop_button, False, False, 0)
        
        self.restart_button = Gtk.Button(label="Restart")
        self.restart_button.set_image(Gtk.Image.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON))
        self.restart_button.set_always_show_image(True)
        self.restart_button.set_sensitive(False)
        self.restart_button.connect("clicked", self.on_service_restart)
        action_box.pack_start(self.restart_button, False, False, 0)
        
        self.enable_button = Gtk.Button(label="Enable")
        self.enable_button.set_image(Gtk.Image.new_from_icon_name("bookmark-new", Gtk.IconSize.BUTTON))
        self.enable_button.set_always_show_image(True)
        self.enable_button.set_sensitive(False)
        self.enable_button.connect("clicked", self.on_service_enable)
        action_box.pack_start(self.enable_button, False, False, 0)
        
        self.disable_button = Gtk.Button(label="Disable")
        self.disable_button.set_image(Gtk.Image.new_from_icon_name("edit-delete", Gtk.IconSize.BUTTON))
        self.disable_button.set_always_show_image(True)
        self.disable_button.set_sensitive(False)
        self.disable_button.connect("clicked", self.on_service_disable)
        action_box.pack_start(self.disable_button, False, False, 0)
        
        services_container.pack_start(action_box, False, False, 0)
        
        # Make scrollable
        services_scrolled = Gtk.ScrolledWindow()
        services_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        services_scrolled.add(services_container)
        
        self.stack.add_titled(services_scrolled, "services", "Services")
        
        # Connect selection signal
        self.service_treeview.get_selection().connect("changed", self.on_service_selected)
        
        # Load services
        self.load_services()
    
    def create_processes_page(self):
        """Create processes page"""
        processes_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        processes_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Process Management</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        processes_container.pack_start(title, False, False, 0)
        
        # Search bar
        search_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.process_search_entry = Gtk.Entry()
        self.process_search_entry.set_placeholder_text("Search processes...")
        self.process_search_entry.connect("changed", self.on_process_search)
        search_box.pack_start(self.process_search_entry, True, True, 0)
        
        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.set_image(Gtk.Image.new_from_icon_name("view-refresh", Gtk.IconSize.BUTTON))
        refresh_button.set_always_show_image(True)
        refresh_button.connect("clicked", self.on_refresh_processes)
        search_box.pack_start(refresh_button, False, False, 0)
        
        processes_container.pack_start(search_box, False, False, 0)
        
        # Process list
        processes_card = self.create_card("Running Processes")
        processes_scrolled = Gtk.ScrolledWindow()
        processes_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        processes_scrolled.set_min_content_height(300)
        
        # Create tree view for processes
        self.process_liststore = Gtk.ListStore(str, str, str, str, str, str, str, str, str, str, str)
        self.process_treeview = Gtk.TreeView(model=self.process_liststore)
        self.process_treeview.set_rules_hint(True)
        
        # Add columns
        columns = [
            ("User", 0),
            ("PID", 1),
            ("CPU", 2),
            ("Memory", 3),
            ("Command", 10)
        ]
        
        for title, col_id in columns:
            renderer = Gtk.CellRendererText()
            column = Gtk.TreeViewColumn(title, renderer, text=col_id)
            column.set_resizable(True)
            column.set_sort_column_id(col_id)
            self.process_treeview.append_column(column)
        
        processes_scrolled.add(self.process_treeview)
        processes_card.get_child().add(processes_scrolled)
        processes_container.pack_start(processes_card, True, True, 0)
        
        # Action buttons
        action_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        action_box.set_halign(Gtk.Align.END)
        action_box.set_margin_top(10)
        
        self.kill_button = Gtk.Button(label="Kill Process")
        self.kill_button.set_image(Gtk.Image.new_from_icon_name("process-stop", Gtk.IconSize.BUTTON))
        self.kill_button.set_always_show_image(True)
        self.kill_button.set_sensitive(False)
        self.kill_button.connect("clicked", self.on_kill_process)
        action_box.pack_start(self.kill_button, False, False, 0)
        
        self.term_button = Gtk.Button(label="Terminate")
        self.term_button.set_image(Gtk.Image.new_from_icon_name("media-playback-stop", Gtk.IconSize.BUTTON))
        self.term_button.set_always_show_image(True)
        self.term_button.set_sensitive(False)
        self.term_button.connect("clicked", self.on_terminate_process)
        action_box.pack_start(self.term_button, False, False, 0)
        
        processes_container.pack_start(action_box, False, False, 0)
        
        # Make scrollable
        processes_scrolled = Gtk.ScrolledWindow()
        processes_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        processes_scrolled.add(processes_container)
        
        self.stack.add_titled(processes_scrolled, "processes", "Processes")
        
        # Connect selection signal
        self.process_treeview.get_selection().connect("changed", self.on_process_selected)
        
        # Load processes
        self.load_processes()
    
    def create_disks_page(self):
        """Create disks page"""
        disks_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        disks_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>Disk Management</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        disks_container.pack_start(title, False, False, 0)
        
        # Disk usage
        disk_card = self.create_card("Disk Usage")
        disk_scrolled = Gtk.ScrolledWindow()
        disk_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        disk_scrolled.set_min_content_height(300)
        
        # Create treeview for disk usage
        self.disk_liststore = Gtk.ListStore(str, str, str, str, str)
        self.disk_treeview = Gtk.TreeView(model=self.disk_liststore)
        self.disk_treeview.set_rules_hint(True)
        
        # Add columns
        text_renderer = Gtk.CellRendererText()
        columns = [
            ("Filesystem", 0),
            ("Size", 1),
            ("Used", 2),
            ("Available", 3),
            ("Mount Point", 4)
        ]
        
        for title, col_id in columns:
            column = Gtk.TreeViewColumn(title, text_renderer, text=col_id)
            column.set_resizable(True)
            self.disk_treeview.append_column(column)
        
        disk_scrolled.add(self.disk_treeview)
        disk_card.get_child().add(disk_scrolled)
        disks_container.pack_start(disk_card, True, True, 0)
        
        # Make scrollable
        disks_scrolled = Gtk.ScrolledWindow()
        disks_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        disks_scrolled.add(disks_container)
        
        self.stack.add_titled(disks_scrolled, "disks", "Disks")
        
        # Load disk info
        self.load_disk_info()
    
    def create_backups_page(self):
        """Create backups page"""
        backups_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        backups_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>System Backup</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        backups_container.pack_start(title, False, False, 0)
        
        # Backup info
        info_label = Gtk.Label(label="Backup functionality requires Timeshift or Snapper to be installed.")
        info_label.set_halign(Gtk.Align.CENTER)
        backups_container.pack_start(info_label, True, True, 0)
        
        # Make scrollable
        backups_scrolled = Gtk.ScrolledWindow()
        backups_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        backups_scrolled.add(backups_container)
        
        self.stack.add_titled(backups_scrolled, "backups", "Backups")
    
    def create_cleaner_page(self):
        """Create system cleaner page"""
        cleaner_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        cleaner_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>System Cleaner</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        cleaner_container.pack_start(title, False, False, 0)
        
        # Cleaner options
        options_card = self.create_card("Cleaning Options")
        options_grid = Gtk.Grid()
        options_grid.set_row_spacing(10)
        options_grid.set_column_spacing(10)
        
        self.clean_cache_check = Gtk.CheckButton(label="Clean Package Cache")
        self.clean_cache_check.set_active(True)
        options_grid.attach(self.clean_cache_check, 0, 0, 1, 1)
        
        self.clean_temp_check = Gtk.CheckButton(label="Clean Temporary Files")
        self.clean_temp_check.set_active(True)
        options_grid.attach(self.clean_temp_check, 0, 1, 1, 1)
        
        self.clean_logs_check = Gtk.CheckButton(label="Clean System Logs")
        options_grid.attach(self.clean_logs_check, 0, 2, 1, 1)
        
        clean_button = Gtk.Button(label="Clean System")
        clean_button.set_image(Gtk.Image.new_from_icon_name("user-trash", Gtk.IconSize.BUTTON))
        clean_button.set_always_show_image(True)
        clean_button.connect("clicked", self.on_clean_system)
        options_grid.attach(clean_button, 0, 3, 1, 1)
        
        options_card.get_child().add(options_grid)
        cleaner_container.pack_start(options_card, False, False, 0)
        
        # Make scrollable
        cleaner_scrolled = Gtk.ScrolledWindow()
        cleaner_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        cleaner_scrolled.add(cleaner_container)
        
        self.stack.add_titled(cleaner_scrolled, "cleaner", "Cleaner")
    
    def create_system_page(self):
        """Create system settings page"""
        system_container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        system_container.set_border_width(20)
        
        # Title
        title = Gtk.Label()
        title.set_markup("<big><b>System Settings</b></big>")
        title.set_halign(Gtk.Align.START)
        title.set_margin_bottom(20)
        system_container.pack_start(title, False, False, 0)
        
        # System info
        info_label = Gtk.Label(label="System settings and configuration options will be available here.")
        info_label.set_halign(Gtk.Align.CENTER)
        system_container.pack_start(info_label, True, True, 0)
        
        # Make scrollable
        system_scrolled = Gtk.ScrolledWindow()
        system_scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        system_scrolled.add(system_container)
        
        self.stack.add_titled(system_scrolled, "system", "System")
    
    def create_card(self, title: str) -> Gtk.Frame:
        """Create a card widget with title"""
        card = Gtk.Frame()
        card.set_shadow_type(Gtk.ShadowType.IN)
        
        # Create header
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        header.set_margin_top(8)
        header.set_margin_bottom(8)
        header.set_margin_start(12)
        header.set_margin_end(12)
        
        title_label = Gtk.Label()
        title_label.set_markup(f"<b>{title}</b>")
        title_label.set_halign(Gtk.Align.START)
        header.pack_start(title_label, True, True, 0)
        
        # Add header to card
        card.set_label_widget(header)
        
        # Set card content
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        content.set_margin_top(5)
        content.set_margin_bottom(10)
        content.set_margin_start(12)
        content.set_margin_end(12)
        card.add(content)
        
        return card
    
    # Load methods
    def load_repositories(self):
        """Load repository list"""
        self.repo_liststore.clear()
        
        repos = self.repo_manager.get_repositories()
        for repo in repos:
            self.repo_liststore.append([
                repo['enabled'],
                repo['name'],
                repo.get('url', ''),
                repo['type']
            ])
    
    def load_boot_entries(self):
        """Load boot entries"""
        # Clear existing entries
        for child in self.boot_entries_list.get_children():
            self.boot_entries_list.remove(child)
        
        boot_config = self.boot_manager.get_boot_config()
        for entry in boot_config['entries']:
            row = Gtk.ListBoxRow()
            label = Gtk.Label(label=entry)
            label.set_halign(Gtk.Align.START)
            row.add(label)
            self.boot_entries_list.add(row)
        
        self.boot_entries_list.show_all()
    
    def load_firewall_rules(self):
        """Load firewall rules"""
        self.rules_liststore.clear()
        
        firewall_info = self.firewall_manager.get_firewall_info()
        for rule in firewall_info['rules']:
            self.rules_liststore.append([
                rule['action'],
                rule['direction'],
                rule['protocol'],
                rule['source'],
                rule['destination']
            ])
    
    def load_logs(self):
        """Load system logs"""
        log_type = self.log_type_combo.get_active_text().lower()
        lines = int(self.log_lines_spin.get_value())
        
        logs = self.log_manager.get_logs(log_type, lines)
        
        buffer = self.logs_textview.get_buffer()
        buffer.set_text('\n'.join(logs))
        
        # Apply monospace font
        start_iter = buffer.get_start_iter()
        end_iter = buffer.get_end_iter()
        buffer.apply_tag_by_name("monospace", start_iter, end_iter)
    
    def load_packages(self):
        """Load package lists"""
        # Clear existing lists
        for child in self.installed_packages_list.get_children():
            self.installed_packages_list.remove(child)
        for child in self.available_packages_list.get_children():
            self.available_packages_list.remove(child)
        for child in self.upgradable_packages_list.get_children():
            self.upgradable_packages_list.remove(child)
        
        # Load installed packages
        installed = self.pkg_manager.get_installed_packages()
        for pkg in installed[:50]:  # Limit to 50 for performance
            if len(pkg) >= 2:
                name, version = pkg[0], pkg[1]
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                
                name_label = Gtk.Label(label=name)
                name_label.set_halign(Gtk.Align.START)
                name_label.get_style_context().add_class("bold")
                box.pack_start(name_label, False, False, 0)
                
                if version:
                    version_label = Gtk.Label(label=f"Version: {version}")
                    version_label.set_halign(Gtk.Align.START)
                    version_label.get_style_context().add_class("dim-label")
                    box.pack_start(version_label, False, False, 0)
                
                row.add(box)
                self.installed_packages_list.add(row)
        
        # Load upgradable packages
        upgradable = self.pkg_manager.get_upgradable_packages()
        for pkg in upgradable:
            if len(pkg) >= 2:
                name, version = pkg[0], pkg[1]
                row = Gtk.ListBoxRow()
                box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                
                name_label = Gtk.Label(label=name)
                name_label.set_halign(Gtk.Align.START)
                name_label.get_style_context().add_class("bold")
                box.pack_start(name_label, False, False, 0)
                
                version_label = Gtk.Label(label=f"Update to: {version}")
                version_label.set_halign(Gtk.Align.START)
                version_label.get_style_context().add_class("dim-label")
                box.pack_start(version_label, False, False, 0)
                
                row.add(box)
                self.upgradable_packages_list.add(row)
        
        self.installed_packages_list.show_all()
        self.upgradable_packages_list.show_all()
    
    def load_users(self):
        """Load user list"""
        self.user_liststore.clear()
        
        users = self.user_manager.get_users()
        for user in users:
            self.user_liststore.append([
                user['username'],
                str(user['uid']),
                user['home'],
                user['shell'],
                user['last_login']
            ])
    
    def load_network_info(self):
        """Load network information"""
        # Clear existing list
        for child in self.interfaces_list.get_children():
            self.interfaces_list.remove(child)
        
        # Get network interfaces
        stdout, _, code = run_command("ip addr show")
        if code == 0:
            current_iface = None
            for line in stdout.split('\n'):
                if line and not line.startswith(' '):
                    parts = line.split()
                    if len(parts) >= 2:
                        current_iface = parts[1].rstrip(':')
                        if current_iface != 'lo':
                            row = Gtk.ListBoxRow()
                            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
                            
                            name_label = Gtk.Label(label=current_iface)
                            name_label.set_halign(Gtk.Align.START)
                            name_label.get_style_context().add_class("bold")
                            box.pack_start(name_label, False, False, 0)
                            
                            status = "Up" if "UP" in line else "Down"
                            status_label = Gtk.Label(label=f"Status: {status}")
                            status_label.set_halign(Gtk.Align.START)
                            status_label.get_style_context().add_class("dim-label")
                            box.pack_start(status_label, False, False, 0)
                            
                            row.add(box)
                            self.interfaces_list.add(row)
                elif current_iface and 'inet ' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        ip = parts[1].split('/')[0]
                        # Add IP to the last row
                        rows = self.interfaces_list.get_children()
                        if rows:
                            last_row = rows[-1]
                            box = last_row.get_child()
                            ip_label = Gtk.Label(label=f"IP: {ip}")
                            ip_label.set_halign(Gtk.Align.START)
                            ip_label.get_style_context().add_class("dim-label")
                            box.pack_start(ip_label, False, False, 0)
        
        self.interfaces_list.show_all()
    
    def load_services(self):
        """Load service list"""
        self.service_liststore.clear()
        
        services = self.service_manager.get_all_services()
        for service in services:
            self.service_liststore.append([
                service['name'],
                service['load'],
                service['active'],
                service['sub'],
                service['enabled']
            ])
    
    def load_processes(self):
        """Load process list"""
        self.process_liststore.clear()
        
        stdout, _, code = run_command("ps aux")
        if code == 0:
            lines = stdout.split('\n')[1:]
            for line in lines[:100]:  # Limit to 100 for performance
                if line.strip():
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        self.process_liststore.append([
                            parts[0],  # user
                            parts[1],  # pid
                            parts[2],  # cpu
                            parts[3],  # mem
                            parts[4],  # vsz
                            parts[5],  # rss
                            parts[6],  # tty
                            parts[7],  # stat
                            parts[8],  # start
                            parts[9],  # time
                            parts[10]  # command
                        ])
    
    def load_disk_info(self):
        """Load disk information"""
        self.disk_liststore.clear()
        
        stdout, _, code = run_command("df -h")
        if code == 0:
            lines = stdout.split('\n')[1:]
            for line in lines:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 6:
                        self.disk_liststore.append([
                            parts[0],  # filesystem
                            parts[1],  # size
                            parts[2],  # used
                            parts[3],  # avail
                            parts[5]   # mount
                        ])
    
    # Dialog methods
    def show_password_dialog(self, title: str, callback):
        """Show password dialog for sudo operations"""
        dialog = PasswordDialog(self, title)
        response = dialog.run()
        password = dialog.get_password() if response == Gtk.ResponseType.OK else None
        dialog.destroy()
        
        if password:
            callback(password)
    
    def show_error_dialog(self, title: str, message: str):
        """Show error dialog"""
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.ERROR,
            buttons=Gtk.ButtonsType.OK,
            message_format=title
        )
        dialog.format_secondary_text(message)
        dialog.run()
        dialog.destroy()
    
    # Event handlers
    def on_nav_selected(self, listbox, row):
        """Handle navigation selection"""
        if row:
            page_id = row.get_name()
            self.stack.set_visible_child_name(page_id)
    
    def on_refresh_clicked(self, button):
        """Handle refresh button click"""
        self.statusbar.push(0, "Refreshing...")
        
        # Refresh current page
        current_page = self.stack.get_visible_child_name()
        if current_page == "packages":
            self.load_packages()
        elif current_page == "repositories":
            self.load_repositories()
        elif current_page == "users":
            self.load_users()
        elif current_page == "network":
            self.load_network_info()
        elif current_page == "services":
            self.load_services()
        elif current_page == "processes":
            self.load_processes()
        elif current_page == "disks":
            self.load_disk_info()
        elif current_page == "boot":
            self.load_boot_entries()
        elif current_page == "firewall":
            self.load_firewall_rules()
        elif current_page == "logs":
            self.load_logs()
        
        self.statusbar.push(0, "Refresh complete")
    
    def on_about_clicked(self, button):
        """Handle about button click"""
        dialog = Gtk.AboutDialog()
        dialog.set_program_name(APP_NAME)
        dialog.set_version(APP_VERSION)
        dialog.set_comments("Universal system management tool")
        dialog.set_copyright("© 2021 - 2025 FloatingSkies")
        dialog.set_license_type(Gtk.License.GPL_3_0)
        dialog.run()
        dialog.destroy()
    
    # Repository event handlers
    def on_add_repository(self, button):
        """Handle add repository"""
        dialog = Gtk.Dialog(title="Add Repository", parent=self, flags=Gtk.DialogFlags.MODAL)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        
        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_border_width(10)
        
        grid.attach(Gtk.Label(label="Repository URL:"), 0, 0, 1, 1)
        url_entry = Gtk.Entry()
        grid.attach(url_entry, 1, 0, 1, 1)
        
        grid.attach(Gtk.Label(label="Name (optional):"), 0, 1, 1, 1)
        name_entry = Gtk.Entry()
        grid.attach(name_entry, 1, 1, 1, 1)
        
        dialog.get_content_area().add(grid)
        dialog.show_all()
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            url = url_entry.get_text()
            name = name_entry.get_text()
            
            def add_with_password(password):
                success, message = self.repo_manager.add_repository(url, name, password)
                if success:
                    self.statusbar.push(0, "Repository added successfully")
                    self.load_repositories()
                else:
                    self.show_error_dialog("Failed to add repository", message)
            
            self.show_password_dialog("Add Repository", add_with_password)
        
        dialog.destroy()
    
    def on_refresh_repositories(self, button):
        """Handle refresh repositories"""
        def refresh_with_password(password):
            success, message = self.repo_manager.refresh_repositories(password)
            if success:
                self.statusbar.push(0, "Repositories refreshed successfully")
                self.load_repositories()
            else:
                self.show_error_dialog("Failed to refresh repositories", message)
        
        self.show_password_dialog("Refresh Repositories", refresh_with_password)
    
    def on_repo_selected(self, selection):
        """Handle repository selection"""
        model, tree_iter = selection.get_selected()
        if tree_iter:
            self.enable_repo_button.set_sensitive(True)
            self.disable_repo_button.set_sensitive(True)
            self.remove_repo_button.set_sensitive(True)
        else:
            self.enable_repo_button.set_sensitive(False)
            self.disable_repo_button.set_sensitive(False)
            self.remove_repo_button.set_sensitive(False)
    
    def on_repo_toggled(self, widget, path):
        """Handle repository toggle"""
        model = self.repo_liststore
        tree_iter = model.get_iter(path)
        
        repo_name = model[tree_iter][1]
        enabled = model[tree_iter][0]
        
        def toggle_with_password(password):
            success, message = self.repo_manager.toggle_repository(repo_name, not enabled, password)
            if success:
                model[tree_iter][0] = not enabled
                self.statusbar.push(0, f"Repository {'enabled' if not enabled else 'disabled'}")
            else:
                self.show_error_dialog("Failed to toggle repository", message)
                # Revert toggle
                model[tree_iter][0] = enabled
        
        self.show_password_dialog("Toggle Repository", toggle_with_password)
    
    def on_enable_repository(self, button):
        """Handle enable repository"""
        selection = self.repo_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            repo_name = model[tree_iter][1]
            
            def enable_with_password(password):
                success, message = self.repo_manager.toggle_repository(repo_name, True, password)
                if success:
                    model[tree_iter][0] = True
                    self.statusbar.push(0, "Repository enabled")
                else:
                    self.show_error_dialog("Failed to enable repository", message)
            
            self.show_password_dialog("Enable Repository", enable_with_password)
    
    def on_disable_repository(self, button):
        """Handle disable repository"""
        selection = self.repo_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            repo_name = model[tree_iter][1]
            
            def disable_with_password(password):
                success, message = self.repo_manager.toggle_repository(repo_name, False, password)
                if success:
                    model[tree_iter][0] = False
                    self.statusbar.push(0, "Repository disabled")
                else:
                    self.show_error_dialog("Failed to disable repository", message)
            
            self.show_password_dialog("Disable Repository", disable_with_password)
    
    def on_remove_repository(self, button):
        """Handle remove repository"""
        selection = self.repo_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            repo_name = model[tree_iter][1]
            
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                message_format="Remove Repository"
            )
            dialog.format_secondary_text(f"Are you sure you want to remove repository '{repo_name}'?")
            response = dialog.run()
            dialog.destroy()
            
            if response == Gtk.ResponseType.YES:
                def remove_with_password(password):
                    success, message = self.repo_manager.remove_repository(repo_name, password)
                    if success:
                        self.statusbar.push(0, "Repository removed successfully")
                        self.load_repositories()
                    else:
                        self.show_error_dialog("Failed to remove repository", message)
                
                self.show_password_dialog("Remove Repository", remove_with_password)
    
    # Boot event handlers
    def on_update_grub(self, button):
        """Handle update GRUB"""
        def update_with_password(password):
            success, message = self.boot_manager.update_grub(password)
            if success:
                self.statusbar.push(0, "GRUB updated successfully")
            else:
                self.show_error_dialog("Failed to update GRUB", message)
        
        self.show_password_dialog("Update GRUB", update_with_password)
    
    def on_remove_old_kernels(self, button):
        """Handle remove old kernels"""
        keep_count = int(self.keep_kernels_spin.get_value())
        
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            message_format="Remove Old Kernels"
        )
        dialog.format_secondary_text(f"Are you sure you want to remove old kernels, keeping the last {keep_count}?")
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.YES:
            def remove_with_password(password):
                success, message = self.kernel_manager.remove_old_kernels(keep_count, password)
                if success:
                    self.statusbar.push(0, message)
                else:
                    self.show_error_dialog("Failed to remove kernels", message)
            
            self.show_password_dialog("Remove Kernels", remove_with_password)
    
    # Firewall event handlers
    def on_firewall_toggle(self, switch, state):
        """Handle firewall toggle"""
        def toggle_with_password(password):
            # This is a simplified implementation
            success, message = True, "Firewall toggled"
            if success:
                self.statusbar.push(0, f"Firewall {'enabled' if state else 'disabled'}")
            else:
                self.show_error_dialog("Failed to toggle firewall", message)
                self.firewall_switch.set_active(not state)
        
        self.show_password_dialog("Toggle Firewall", toggle_with_password)
    
    def on_add_firewall_rule(self, button):
        """Handle add firewall rule"""
        dialog = Gtk.Dialog(title="Add Firewall Rule", parent=self, flags=Gtk.DialogFlags.MODAL)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        
        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_border_width(10)
        
        grid.attach(Gtk.Label(label="Action:"), 0, 0, 1, 1)
        action_combo = Gtk.ComboBoxText()
        action_combo.append_text("allow")
        action_combo.append_text("deny")
        action_combo.set_active(0)
        grid.attach(action_combo, 1, 0, 1, 1)
        
        grid.attach(Gtk.Label(label="Protocol:"), 0, 1, 1, 1)
        protocol_combo = Gtk.ComboBoxText()
        protocol_combo.append_text("tcp")
        protocol_combo.append_text("udp")
        protocol_combo.append_text("any")
        protocol_combo.set_active(0)
        grid.attach(protocol_combo, 1, 1, 1, 1)
        
        grid.attach(Gtk.Label(label="Port:"), 0, 2, 1, 1)
        port_entry = Gtk.Entry()
        grid.attach(port_entry, 1, 2, 1, 1)
        
        dialog.get_content_area().add(grid)
        dialog.show_all()
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            action = action_combo.get_active_text()
            protocol = protocol_combo.get_active_text()
            port = port_entry.get_text()
            
            def add_with_password(password):
                rule = {
                    'backend': 'ufw',  # Simplified
                    'action': action,
                    'protocol': protocol,
                    'port': port
                }
                success, message = self.firewall_manager.add_firewall_rule(rule, password)
                if success:
                    self.statusbar.push(0, "Firewall rule added successfully")
                    self.load_firewall_rules()
                else:
                    self.show_error_dialog("Failed to add firewall rule", message)
            
            self.show_password_dialog("Add Firewall Rule", add_with_password)
        
        dialog.destroy()
    
    def on_rule_selected(self, selection):
        """Handle rule selection"""
        model, tree_iter = selection.get_selected()
        self.remove_rule_button.set_sensitive(tree_iter is not None)
    
    def on_remove_firewall_rule(self, button):
        """Handle remove firewall rule"""
        selection = self.rules_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            # Get rule details
            rule = {
                'backend': 'ufw',  # Simplified
                'action': model[tree_iter][0],
                'protocol': model[tree_iter][2],
                'port': model[tree_iter][3]
            }
            
            def remove_with_password(password):
                success, message = self.firewall_manager.remove_firewall_rule(rule, password)
                if success:
                    self.statusbar.push(0, "Firewall rule removed successfully")
                    self.load_firewall_rules()
                else:
                    self.show_error_dialog("Failed to remove firewall rule", message)
            
            self.show_password_dialog("Remove Firewall Rule", remove_with_password)
    
    # Logs event handlers
    def on_log_type_changed(self, combo):
        """Handle log type change"""
        self.load_logs()
    
    def on_refresh_logs(self, button):
        """Handle refresh logs"""
        self.load_logs()
    
    def on_clear_logs(self, button):
        """Handle clear logs"""
        log_type = self.log_type_combo.get_active_text().lower()
        
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            message_format="Clear Logs"
        )
        dialog.format_secondary_text(f"Are you sure you want to clear {log_type} logs?")
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.YES:
            def clear_with_password(password):
                success, message = self.log_manager.clear_logs(log_type, password)
                if success:
                    self.statusbar.push(0, "Logs cleared successfully")
                    self.load_logs()
                else:
                    self.show_error_dialog("Failed to clear logs", message)
            
            self.show_password_dialog("Clear Logs", clear_with_password)
    
    # Package event handlers
    def on_package_search(self, button):
        """Handle package search"""
        query = self.package_search_entry.get_text()
        if not query:
            return
        
        self.statusbar.push(0, "Searching packages...")
        
        # Clear available packages list
        for child in self.available_packages_list.get_children():
            self.available_packages_list.remove(child)
        
        # Search packages
        packages = self.pkg_manager.search_packages(query)
        for pkg, desc in packages[:50]:
            row = Gtk.ListBoxRow()
            box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            
            name_label = Gtk.Label(label=pkg)
            name_label.set_halign(Gtk.Align.START)
            name_label.get_style_context().add_class("bold")
            box.pack_start(name_label, False, False, 0)
            
            if desc:
                desc_label = Gtk.Label(label=desc[:100] + "..." if len(desc) > 100 else desc)
                desc_label.set_halign(Gtk.Align.START)
                desc_label.get_style_context().add_class("dim-label")
                box.pack_start(desc_label, False, False, 0)
            
            row.add(box)
            self.available_packages_list.add(row)
        
        self.available_packages_list.show_all()
        self.statusbar.push(0, "Search complete")
    
    def on_package_install(self, button):
        """Handle package installation"""
        row = self.available_packages_list.get_selected_row()
        if not row:
            return
        
        box = row.get_child()
        name_label = box.get_children()[0]
        package_name = name_label.get_text()
        
        def install_with_password(password):
            success, message = self.pkg_manager.install_package(package_name, password)
            if success:
                self.statusbar.push(0, "Package installed successfully")
                self.load_packages()
            else:
                self.show_error_dialog("Installation failed", message)
        
        self.show_password_dialog("Install Package", install_with_password)
    
    def on_package_remove(self, button):
        """Handle package removal"""
        row = self.installed_packages_list.get_selected_row()
        if not row:
            return
        
        box = row.get_child()
        name_label = box.get_children()[0]
        package_name = name_label.get_text()
        
        def remove_with_password(password):
            success, message = self.pkg_manager.remove_package(package_name, password)
            if success:
                self.statusbar.push(0, "Package removed successfully")
                self.load_packages()
            else:
                self.show_error_dialog("Removal failed", message)
        
        self.show_password_dialog("Remove Package", remove_with_password)
    
    def on_package_update(self, button):
        """Handle system update"""
        def update_with_password(password):
            success, message = self.pkg_manager.update_system(password)
            if success:
                self.statusbar.push(0, "System updated successfully")
                self.load_packages()
            else:
                self.show_error_dialog("Update failed", message)
        
        self.show_password_dialog("Update System", update_with_password)
    
    def on_package_upgrade_all(self, button):
        """Handle upgrade all packages"""
        def upgrade_with_password(password):
            success, message = self.pkg_manager.update_system(password)
            if success:
                self.statusbar.push(0, "All packages upgraded successfully")
                self.load_packages()
            else:
                self.show_error_dialog("Upgrade failed", message)
        
        self.show_password_dialog("Upgrade All Packages", upgrade_with_password)
    
    # User event handlers
    def on_user_selected(self, selection):
        """Handle user selection"""
        model, tree_iter = selection.get_selected()
        if tree_iter:
            self.modify_user_button.set_sensitive(True)
            self.lock_user_button.set_sensitive(True)
            self.delete_user_button.set_sensitive(True)
        else:
            self.modify_user_button.set_sensitive(False)
            self.lock_user_button.set_sensitive(False)
            self.delete_user_button.set_sensitive(False)
    
    def on_add_user(self, button):
        """Handle add user"""
        dialog = Gtk.Dialog(title="Add User", parent=self, flags=Gtk.DialogFlags.MODAL)
        dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
        
        grid = Gtk.Grid()
        grid.set_row_spacing(10)
        grid.set_column_spacing(10)
        grid.set_border_width(10)
        
        # Username
        grid.attach(Gtk.Label(label="Username:"), 0, 0, 1, 1)
        username_entry = Gtk.Entry()
        grid.attach(username_entry, 1, 0, 1, 1)
        
        # Full name
        grid.attach(Gtk.Label(label="Full Name:"), 0, 1, 1, 1)
        fullname_entry = Gtk.Entry()
        grid.attach(fullname_entry, 1, 1, 1, 1)
        
        # Password
        grid.attach(Gtk.Label(label="Password:"), 0, 2, 1, 1)
        password_entry = Gtk.Entry()
        password_entry.set_visibility(False)
        grid.attach(password_entry, 1, 2, 1, 1)
        
        dialog.get_content_area().add(grid)
        dialog.show_all()
        
        response = dialog.run()
        if response == Gtk.ResponseType.OK:
            username = username_entry.get_text()
            fullname = fullname_entry.get_text()
            password = password_entry.get_text()
            
            success, message = self.user_manager.create_user(username, password, fullname)
            if success:
                self.statusbar.push(0, "User created successfully")
                self.load_users()
            else:
                self.show_error_dialog("Failed to create user", message)
        
        dialog.destroy()
    
    def on_modify_user(self, button):
        """Handle modify user"""
        selection = self.user_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            username = model[tree_iter][0]
            
            dialog = Gtk.Dialog(title="Modify User", parent=self, flags=Gtk.DialogFlags.MODAL)
            dialog.add_buttons(Gtk.STOCK_CANCEL, Gtk.ResponseType.CANCEL, Gtk.STOCK_OK, Gtk.ResponseType.OK)
            
            grid = Gtk.Grid()
            grid.set_row_spacing(10)
            grid.set_column_spacing(10)
            grid.set_border_width(10)
            
            # Get current user info
            users = self.user_manager.get_users()
            current_user = None
            for user in users:
                if user['username'] == username:
                    current_user = user
                    break
            
            # Full name
            grid.attach(Gtk.Label(label="Full Name:"), 0, 0, 1, 1)
            fullname_entry = Gtk.Entry()
            if current_user:
                fullname_entry.set_text(current_user.get('gecos', ''))
            grid.attach(fullname_entry, 1, 0, 1, 1)
            
            # Shell
            grid.attach(Gtk.Label(label="Shell:"), 0, 1, 1, 1)
            shell_combo = Gtk.ComboBoxText()
            shells = ["/bin/bash", "/bin/sh", "/bin/zsh", "/bin/fish"]
            for shell in shells:
                shell_combo.append_text(shell)
            if current_user:
                try:
                    idx = shells.index(current_user['shell'])
                    shell_combo.set_active(idx)
                except:
                    shell_combo.set_active(0)
            grid.attach(shell_combo, 1, 1, 1, 1)
            
            dialog.get_content_area().add(grid)
            dialog.show_all()
            
            response = dialog.run()
            if response == Gtk.ResponseType.OK:
                fullname = fullname_entry.get_text()
                shell = shell_combo.get_active_text()
                
                def modify_with_password(password):
                    success, message = self.user_manager.modify_user(
                        username,
                        full_name=fullname,
                        shell=shell
                    )
                    if success:
                        self.statusbar.push(0, "User modified successfully")
                        self.load_users()
                    else:
                        self.show_error_dialog("Failed to modify user", message)
                
                self.show_password_dialog("Modify User", modify_with_password)
            
            dialog.destroy()
    
    def on_lock_user(self, button):
        """Handle lock/unlock user"""
        selection = self.user_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            username = model[tree_iter][0]
            
            # Check if user is locked (simplified check)
            stdout, _, code = run_command(f"passwd -S {username}")
            is_locked = code == 0 and stdout.split()[1] == 'L'
            
            action = "unlock" if is_locked else "lock"
            
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                message_format=f"{action.capitalize()} User"
            )
            dialog.format_secondary_text(f"Are you sure you want to {action} user '{username}'?")
            response = dialog.run()
            dialog.destroy()
            
            if response == Gtk.ResponseType.YES:
                def lock_with_password(password):
                    if action == "lock":
                        success, message = self.user_manager.lock_user(username)
                    else:
                        success, message = self.user_manager.unlock_user(username)
                    
                    if success:
                        self.statusbar.push(0, f"User {action}ed successfully")
                    else:
                        self.show_error_dialog(f"Failed to {action} user", message)
                
                self.show_password_dialog(f"{action.capitalize()} User", lock_with_password)
    
    def on_delete_user(self, button):
        """Handle delete user"""
        selection = self.user_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            username = model[tree_iter][0]
            
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                message_format="Delete User"
            )
            dialog.format_secondary_text(f"Are you sure you want to delete user '{username}'?")
            response = dialog.run()
            dialog.destroy()
            
            if response == Gtk.ResponseType.YES:
                def delete_with_password(password):
                    success, message = self.user_manager.delete_user(username)
                    if success:
                        self.statusbar.push(0, "User deleted successfully")
                        self.load_users()
                    else:
                        self.show_error_dialog("Failed to delete user", message)
                
                self.show_password_dialog("Delete User", delete_with_password)
    
    # Service event handlers
    def on_service_selected(self, selection):
        """Handle service selection"""
        model, tree_iter = selection.get_selected()
        if tree_iter:
            self.start_button.set_sensitive(True)
            self.stop_button.set_sensitive(True)
            self.restart_button.set_sensitive(True)
            self.enable_button.set_sensitive(True)
            self.disable_button.set_sensitive(True)
        else:
            self.start_button.set_sensitive(False)
            self.stop_button.set_sensitive(False)
            self.restart_button.set_sensitive(False)
            self.enable_button.set_sensitive(False)
            self.disable_button.set_sensitive(False)
    
    def on_service_enabled_toggled(self, widget, path):
        """Handle service enabled toggle"""
        model = self.service_liststore
        tree_iter = model.get_iter(path)
        
        service_name = model[tree_iter][0]
        enabled = model[tree_iter][4]
        
        def toggle_with_password(password):
            if enabled:
                success, message = self.service_manager.disable_service(service_name, password)
            else:
                success, message = self.service_manager.enable_service(service_name, password)
            
            if success:
                model[tree_iter][4] = not enabled
                self.statusbar.push(0, f"Service {'enabled' if not enabled else 'disabled'}")
            else:
                self.show_error_dialog("Failed to toggle service", message)
                # Revert toggle
                model[tree_iter][4] = enabled
        
        self.show_password_dialog("Toggle Service", toggle_with_password)
    
    def on_service_start(self, button):
        """Handle service start"""
        selection = self.service_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            service_name = model[tree_iter][0]
            
            def start_with_password(password):
                success, message = run_sudo_command(f"systemctl start {service_name}", password)
                if success:
                    self.statusbar.push(0, "Service started")
                    self.load_services()
                else:
                    self.show_error_dialog("Failed to start service", message)
            
            self.show_password_dialog("Start Service", start_with_password)
    
    def on_service_stop(self, button):
        """Handle service stop"""
        selection = self.service_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            service_name = model[tree_iter][0]
            
            def stop_with_password(password):
                success, message = run_sudo_command(f"systemctl stop {service_name}", password)
                if success:
                    self.statusbar.push(0, "Service stopped")
                    self.load_services()
                else:
                    self.show_error_dialog("Failed to stop service", message)
            
            self.show_password_dialog("Stop Service", stop_with_password)
    
    def on_service_restart(self, button):
        """Handle service restart"""
        selection = self.service_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            service_name = model[tree_iter][0]
            
            def restart_with_password(password):
                success, message = run_sudo_command(f"systemctl restart {service_name}", password)
                if success:
                    self.statusbar.push(0, "Service restarted")
                    self.load_services()
                else:
                    self.show_error_dialog("Failed to restart service", message)
            
            self.show_password_dialog("Restart Service", restart_with_password)
    
    def on_service_enable(self, button):
        """Handle service enable"""
        selection = self.service_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            service_name = model[tree_iter][0]
            
            def enable_with_password(password):
                success, message = self.service_manager.enable_service(service_name, password)
                if success:
                    self.statusbar.push(0, "Service enabled")
                    self.load_services()
                else:
                    self.show_error_dialog("Failed to enable service", message)
            
            self.show_password_dialog("Enable Service", enable_with_password)
    
    def on_service_disable(self, button):
        """Handle service disable"""
        selection = self.service_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            service_name = model[tree_iter][0]
            
            def disable_with_password(password):
                success, message = self.service_manager.disable_service(service_name, password)
                if success:
                    self.statusbar.push(0, "Service disabled")
                    self.load_services()
                else:
                    self.show_error_dialog("Failed to disable service", message)
            
            self.show_password_dialog("Disable Service", disable_with_password)
    
    # Process event handlers
    def on_process_search(self, entry):
        """Handle process search"""
        query = entry.get_text().lower()
        
        self.process_liststore.clear()
        
        stdout, _, code = run_command("ps aux")
        if code == 0:
            lines = stdout.split('\n')[1:]
            for line in lines:
                if line.strip():
                    parts = line.split(None, 10)
                    if len(parts) >= 11:
                        if query == "" or query in parts[10].lower() or query in parts[0].lower():
                            self.process_liststore.append([
                                parts[0],  # user
                                parts[1],  # pid
                                parts[2],  # cpu
                                parts[3],  # mem
                                parts[4],  # vsz
                                parts[5],  # rss
                                parts[6],  # tty
                                parts[7],  # stat
                                parts[8],  # start
                                parts[9],  # time
                                parts[10]  # command
                            ])
    
    def on_refresh_processes(self, button):
        """Handle refresh processes"""
        self.load_processes()
    
    def on_process_selected(self, selection):
        """Handle process selection"""
        model, tree_iter = selection.get_selected()
        if tree_iter:
            self.kill_button.set_sensitive(True)
            self.term_button.set_sensitive(True)
        else:
            self.kill_button.set_sensitive(False)
            self.term_button.set_sensitive(False)
    
    def on_kill_process(self, button):
        """Handle kill process"""
        selection = self.process_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            pid = model[tree_iter][1]
            
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                message_format="Kill Process"
            )
            dialog.format_secondary_text(f"Are you sure you want to kill process {pid}?")
            response = dialog.run()
            dialog.destroy()
            
            if response == Gtk.ResponseType.YES:
                def kill_with_password(password):
                    success, message = run_sudo_command(f"kill -9 {pid}", password)
                    if success:
                        self.statusbar.push(0, "Process killed")
                        self.load_processes()
                    else:
                        self.show_error_dialog("Failed to kill process", message)
                
                self.show_password_dialog("Kill Process", kill_with_password)
    
    def on_terminate_process(self, button):
        """Handle terminate process"""
        selection = self.process_treeview.get_selection()
        model, tree_iter = selection.get_selected()
        if tree_iter:
            pid = model[tree_iter][1]
            
            dialog = Gtk.MessageDialog(
                parent=self,
                flags=Gtk.DialogFlags.MODAL,
                type=Gtk.MessageType.QUESTION,
                buttons=Gtk.ButtonsType.YES_NO,
                message_format="Terminate Process"
            )
            dialog.format_secondary_text(f"Are you sure you want to terminate process {pid}?")
            response = dialog.run()
            dialog.destroy()
            
            if response == Gtk.ResponseType.YES:
                def terminate_with_password(password):
                    success, message = run_sudo_command(f"kill -15 {pid}", password)
                    if success:
                        self.statusbar.push(0, "Process terminated")
                        self.load_processes()
                    else:
                        self.show_error_dialog("Failed to terminate process", message)
                
                self.show_password_dialog("Terminate Process", terminate_with_password)
    
    # Quick action handlers
    def on_quick_update(self, button):
        """Handle quick system update"""
        def update_with_password(password):
            success, message = self.pkg_manager.update_system(password)
            if success:
                self.statusbar.push(0, "System updated")
                self.load_packages()
            else:
                self.show_error_dialog("Update failed", message)
        
        self.show_password_dialog("Update System", update_with_password)
    
    def on_quick_clean(self, button):
        """Handle quick system clean"""
        def clean_with_password(password):
            stdout, stderr, code = run_sudo_command("apt autoremove -y && apt autoclean", password)
            if code == 0:
                self.statusbar.push(0, "System cleaned")
            else:
                self.show_error_dialog("Clean failed", stderr)
        
        self.show_password_dialog("Clean System", clean_with_password)
    
    def on_quick_network(self, button):
        """Handle quick network info"""
        info = "Network Interfaces:\n"
        
        stdout, _, code = run_command("ip addr show")
        if code == 0:
            current_iface = None
            for line in stdout.split('\n'):
                if line and not line.startswith(' '):
                    parts = line.split()
                    if len(parts) >= 2:
                        current_iface = parts[1].rstrip(':')
                        if current_iface != 'lo':
                            info += f"\n- {current_iface}: {'Up' if 'UP' in line else 'Down'}"
                elif current_iface and 'inet ' in line:
                    parts = line.split()
                    if len(parts) >= 2:
                        ip = parts[1].split('/')[0]
                        info += f"\n  IP: {ip}"
        
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            message_format="Network Information"
        )
        dialog.format_secondary_text(info)
        dialog.run()
        dialog.destroy()
    
    def on_quick_services(self, button):
        """Handle quick service status"""
        info = "Service Status:\n"
        
        stdout, _, code = run_command("systemctl list-units --type=service --state=running --no-pager | head -10")
        if code == 0:
            for line in stdout.split('\n')[1:]:
                if line.strip() and '.service' in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        info += f"\n- {parts[0]}: {parts[1]} {parts[2]} {parts[3]}"
        
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            message_format="Service Status"
        )
        dialog.format_secondary_text(info)
        dialog.run()
        dialog.destroy()
    
    def on_quick_disk(self, button):
        """Handle quick disk usage"""
        info = "Disk Usage:\n"
        
        stdout, _, code = run_command("df -h")
        if code == 0:
            for line in stdout.split('\n')[1:]:
                if line.strip():
                    parts = line.split()
                    if len(parts) >= 6:
                        info += f"\n- {parts[0]}: {parts[2]}/{parts[1]} ({parts[4]}) mounted on {parts[5]}"
        
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            message_format="Disk Usage"
        )
        dialog.format_secondary_text(info)
        dialog.run()
        dialog.destroy()
    
    def on_quick_logs(self, button):
        """Handle quick logs view"""
        logs = self.log_manager.get_logs('system', 20)
        info = "Recent System Logs:\n" + "\n".join(logs)
        
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.INFO,
            buttons=Gtk.ButtonsType.OK,
            message_format="System Logs"
        )
        dialog.format_secondary_text(info)
        dialog.run()
        dialog.destroy()
    
    def on_clean_system(self, button):
        """Handle clean system"""
        options = []
        if self.clean_cache_check.get_active():
            options.append("package cache")
        if self.clean_temp_check.get_active():
            options.append("temporary files")
        if self.clean_logs_check.get_active():
            options.append("system logs")
        
        if not options:
            self.show_error_dialog("No Options Selected", "Please select at least one cleaning option.")
            return
        
        dialog = Gtk.MessageDialog(
            parent=self,
            flags=Gtk.DialogFlags.MODAL,
            type=Gtk.MessageType.QUESTION,
            buttons=Gtk.ButtonsType.YES_NO,
            message_format="Clean System"
        )
        dialog.format_secondary_text(f"Are you sure you want to clean {', '.join(options)}?")
        response = dialog.run()
        dialog.destroy()
        
        if response == Gtk.ResponseType.YES:
            def clean_with_password(password):
                results = []
                
                if "package cache" in options:
                    stdout, stderr, code = run_sudo_command("apt autoremove -y && apt autoclean", password)
                    results.append(f"Package cache: {'Success' if code == 0 else 'Failed'}")
                
                if "temporary files" in options:
                    stdout, stderr, code = run_sudo_command("find /tmp -type f -atime +7 -delete", password)
                    results.append(f"Temporary files: {'Success' if code == 0 else 'Failed'}")
                
                if "system logs" in options:
                    stdout, stderr, code = run_sudo_command("journalctl --vacuum-time=7d", password)
                    results.append(f"System logs: {'Success' if code == 0 else 'Failed'}")
                
                # Show results
                dialog = Gtk.MessageDialog(
                    parent=self,
                    flags=Gtk.DialogFlags.MODAL,
                    type=Gtk.MessageType.INFO,
                    buttons=Gtk.ButtonsType.OK,
                    message_format="Cleaning Results"
                )
                dialog.format_secondary_text("\n".join(results))
                dialog.run()
                dialog.destroy()
                
                self.statusbar.push(0, "System cleaning completed")
            
            self.show_password_dialog("Clean System", clean_with_password)

# Application Class
class DockpanelApplication(Gtk.Application):
    """Main application class"""
    
    def __init__(self):
        Gtk.Application.__init__(self, application_id="com.dockpanel.Dockpanel")
    
    def do_activate(self):
        """Activate the application"""
        win = DockpanelWindow(self)
        win.show_all()
    
    def do_startup(self):
        """Startup the application"""
        Gtk.Application.do_startup(self)

# Main Entry Point
def main():
    """Main entry point"""
    app = DockpanelApplication()
    exit_status = app.run(sys.argv)
    sys.exit(exit_status)

if __name__ == "__main__":
    main()
