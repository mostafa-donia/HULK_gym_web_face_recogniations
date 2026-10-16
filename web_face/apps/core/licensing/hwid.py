import hashlib
import os
import platform
import subprocess
import uuid

def _get_registry_machine_guid() -> str:
    """Retrieves Windows Cryptography MachineGuid from registry."""
    if platform.system().lower() != "windows":
        return ""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(guid).strip()
    except Exception:
        return ""

def _run_ps_cmd(command: str) -> str:
    """Executes a fast powershell command with strict timeout."""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", command],
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        return (proc.stdout or "").strip()
    except Exception:
        return ""

def _get_wmic_val(wmic_args: list) -> str:
    """Executes a wmic command fallback."""
    try:
        proc = subprocess.run(
            ["wmic"] + wmic_args,
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
        )
        lines = [line.strip() for line in (proc.stdout or "").splitlines() if line.strip()]
        if len(lines) >= 2:
            return lines[1]
        return ""
    except Exception:
        return ""

def get_hardware_fingerprint() -> str:
    """
    Computes a deterministic, tamper-resistant Hardware Machine ID (HWID).
    Combines:
    1. Motherboard UUID
    2. CPU Processor ID
    3. Primary Disk Serial Number
    4. Windows MachineGuid
    """
    is_win = platform.system().lower() == "windows"
    
    mb_uuid = ""
    cpu_id = ""
    disk_serial = ""
    guid = ""

    if is_win:
        guid = _get_registry_machine_guid()
        
        # 1. Motherboard UUID
        mb_uuid = _run_ps_cmd("(Get-CimInstance Win32_ComputerSystemProduct).UUID")
        if not mb_uuid:
            mb_uuid = _get_wmic_val(["csproduct", "get", "uuid"])

        # 2. CPU ID
        cpu_id = _run_ps_cmd("(Get-CimInstance Win32_Processor).ProcessorId")
        if not cpu_id:
            cpu_id = _get_wmic_val(["cpu", "get", "processorid"])

        # 3. Disk Serial
        disk_serial = _run_ps_cmd("(Get-CimInstance Win32_DiskDrive | Select-Object -First 1).SerialNumber")
        if not disk_serial:
            disk_serial = _get_wmic_val(["diskdrive", "get", "serialnumber"])

    # Fallbacks if running on non-windows or restricted environments
    mac_node = str(uuid.getnode())
    node_name = platform.node()

    raw_components = [
        mb_uuid or "MB-DEFAULT",
        cpu_id or "CPU-DEFAULT",
        disk_serial or "DISK-DEFAULT",
        guid or "GUID-DEFAULT",
        mac_node,
        node_name,
    ]
    raw_signature = "::".join(raw_components)

    # Generate 16-character hex hash formatted as HWID-XXXX-XXXX-XXXX-XXXX
    h = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()
    parts = [h[i : i + 4].upper() for i in range(0, 16, 4)]
    return f"HWID-{'-'.join(parts)}"


if __name__ == "__main__":
    print("Machine HWID:", get_hardware_fingerprint())
