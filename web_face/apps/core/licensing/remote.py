import json
import ssl
import urllib.parse
import urllib.request
from datetime import datetime


def _get_ssl_context():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx

def fetch_remote_license_status(remote_url: str, machine_id: str, client_name: str = "") -> tuple[bool, dict, str]:
    """
    Connects to the Developer Online Control Center with a strict 3-second timeout.
    Returns: (is_successful_fetch, client_config_dict, error_message)
    """
    if not remote_url or not remote_url.strip():
        return False, {}, "لم يتم ضبط رابط مركز التحكم السحابي للمطور."

    clean_url = remote_url.strip()
    
    # Append query params if it's an API endpoint
    try:
        parsed = urllib.parse.urlparse(clean_url)
        params = {"hwid": machine_id, "name": client_name}
        query = urllib.parse.urlencode(params)
        sep = "&" if parsed.query else "?"
        target_url = f"{clean_url}{sep}{query}" if not clean_url.endswith(".json") else clean_url

        req = urllib.request.Request(
            target_url,
            headers={
                "User-Agent": "HulkGym-LicenseEngine/2.1",
                "Accept": "application/json",
            },
        )

        with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=3.5) as response:
            if response.status != 200:
                return False, {}, f"Server returned status {response.status}"
            raw_text = response.read().decode("utf-8")
            data = json.loads(raw_text)

        # 1. Check if the response is a multi-client dict (e.g. GitHub Gist or central JSON)
        clients_map = data.get("clients", data)
        client_mid = machine_id.strip()

        if isinstance(clients_map, dict) and client_mid in clients_map:
            client_data = clients_map[client_mid]
            return True, client_data, "تم جلب بيانات الترخيص من مركز التحكم بنجاح."

        # Check default fallback if present
        if isinstance(clients_map, dict) and "DEFAULT" in clients_map:
            return True, clients_map["DEFAULT"], "تم تطبيق الإعدادات الافتراضية من مركز التحكم."

        # If data itself is a single client's object
        if "status" in data:
            return True, data, "تم جلب بيانات الترخيص بنجاح."

        return False, {}, "معرّف الجهاز (HWID) غير مدرج في قاعدة بيانات مركز التحكم."

    except urllib.error.URLError as e:
        return False, {}, f"تعذر الاتصال بمركز التحكم (انقطاع الإنترنت أو السيرفر غير متاح): {e.reason}"
    except TimeoutError:
        return False, {}, "انتهت مهلة الاتصال بمركز التحكم (Timeout)."
    except Exception as e:
        return False, {}, f"خطأ في قراءة رد مركز التحكم: {str(e)}"
