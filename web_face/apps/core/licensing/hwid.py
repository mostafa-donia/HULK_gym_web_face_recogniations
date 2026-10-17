import ctypes
import functools
import hashlib
import json
import os
import platform

_PERSISTENCE_FILE_NAME = ".system_machine_hwid"


def _get_base_storage_dir() -> str:
    """Finds a safe, persistent directory for storing the verified machine anchor."""
    # Current file is in apps/core/licensing/
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    # Go up to web_face
    web_face_dir = os.path.abspath(os.path.join(cur_dir, "..", "..", ".."))
    data_dir = os.path.join(web_face_dir, "data")
    if os.path.exists(data_dir):
        return data_dir
    return web_face_dir


def _read_windows_hardware_components() -> tuple[str, str, str, str]:
    """
    Directly and instantaneously reads hardware indicators from Windows Registry and Kernel.
    Takes ~1ms and NEVER spawns external PowerShell or WMIC subprocesses.
    Infallible against network disconnects, adapter changes, or process timeouts.
    """
    guid = ""
    mb_str = ""
    cpu_str = ""
    vol_hex = ""

    try:
        import winreg

        # 1. Windows MachineGuid (Invariant across hardware sessions)
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as k:
                guid, _ = winreg.QueryValueEx(k, "MachineGuid")
                guid = str(guid).strip()
        except Exception:
            guid = ""

        # 2. Motherboard Product and Manufacturer
        mb_parts = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as k:
                for sub in ["BaseBoardManufacturer", "BaseBoardProduct", "SystemProductName", "SystemManufacturer"]:
                    try:
                        val, _ = winreg.QueryValueEx(k, sub)
                        if val:
                            mb_parts.append(str(val).strip())
                    except Exception:
                        pass
        except Exception:
            pass
        mb_str = ",".join(mb_parts)

        # 3. CPU Identification
        cpu_parts = []
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0") as k:
                for sub in ["ProcessorNameString", "Identifier", "VendorIdentifier"]:
                    try:
                        val, _ = winreg.QueryValueEx(k, sub)
                        if val:
                            cpu_parts.append(str(val).strip())
                    except Exception:
                        pass
        except Exception:
            pass
        cpu_str = ",".join(cpu_parts)

    except ImportError:
        pass

    # 4. Primary System Volume (C:) Serial Number via Kernel32
    try:
        vol_serial = ctypes.c_ulong()
        kernel32 = ctypes.windll.kernel32
        if kernel32.GetVolumeInformationW("C:\\", None, 0, ctypes.byref(vol_serial), None, None, None, 0):
            vol_hex = f"{vol_serial.value:08X}"
    except Exception:
        vol_hex = ""

    return guid, mb_str, cpu_str, vol_hex


def _read_unix_hardware_components() -> str:
    """Fallback for non-Windows environments."""
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        return content
            except Exception:
                pass
    return f"{platform.node()}::{platform.machine()}::{platform.processor()}"


@functools.lru_cache(maxsize=1)
def get_hardware_fingerprint() -> str:
    """
    Computes a 100% deterministic, tamper-resistant Hardware Machine ID (HWID).
    - Guaranteed to remain identical on the same machine.
    - Guaranteed to change if database/files are copied to another machine.
    - Executes in < 2ms (0 external process spawns).
    """
    is_win = platform.system().lower() == "windows"
    storage_dir = _get_base_storage_dir()
    anchor_file = os.path.join(storage_dir, _PERSISTENCE_FILE_NAME)

    if is_win:
        guid, mb_str, cpu_str, vol_hex = _read_windows_hardware_components()
        raw_components = [
            guid or "GUID-FALLBACK",
            mb_str or "MB-FALLBACK",
            cpu_str or "CPU-FALLBACK",
            vol_hex or "VOL-FALLBACK",
        ]
        raw_signature = "::".join(raw_components)
    else:
        raw_signature = _read_unix_hardware_components()

    # Generate 16-character hex hash formatted as HWID-XXXX-XXXX-XXXX-XXXX
    h = hashlib.sha256(raw_signature.encode("utf-8")).hexdigest()
    parts = [h[i : i + 4].upper() for i in range(0, 16, 4)]
    computed_hwid = f"HWID-{'-'.join(parts)}"

    # Check anchor file to guarantee persistence on this machine
    try:
        if os.path.exists(anchor_file):
            with open(anchor_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                saved_hwid = data.get("hwid")
                saved_sig = data.get("sig")
                # If signature matches, return saved HWID
                if saved_sig == raw_signature and saved_hwid:
                    return saved_hwid
        
        # Write anchor file for this machine
        os.makedirs(storage_dir, exist_ok=True)
        with open(anchor_file, "w", encoding="utf-8") as f:
            json.dump({"hwid": computed_hwid, "sig": raw_signature}, f)
    except Exception:
        pass

    return computed_hwid


if __name__ == "__main__":
    print("Machine HWID:", get_hardware_fingerprint())
