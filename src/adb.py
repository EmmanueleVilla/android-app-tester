import subprocess
import sys
import time
import re
from .config import logger

def run(cmd):
    """Executes a command and returns the decoded output. Raises error on failure."""
    try:
        return subprocess.check_output(cmd, stderr=subprocess.PIPE).decode("utf-8", errors="ignore")
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode("utf-8", errors="ignore").strip()
        logger.error(f"ADB command failed: {' '.join(cmd)} - Error: {stderr_msg}")
        raise


def check_adb_connection():
    """
    Checks if ADB is installed and if at least one authorized device/emulator is connected.
    Returns True if a device is ready, False otherwise.
    """
    try:
        subprocess.run(["adb", "version"], capture_output=True, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.error("'adb' executable not found. Please ensure Android SDK Platform-Tools are installed and 'adb' is in your PATH.")
        return False

    try:
        output = subprocess.check_output(["adb", "devices"]).decode("utf-8")
        lines = [line.strip() for line in output.strip().split("\n") if line.strip()]
        devices = lines[1:]
        if not devices:
            logger.warning("No ADB devices or emulators detected. Please connect a device or start an emulator.")
            return False
        
        valid_devices = [d for d in devices if "device" in d and "unauthorized" not in d]
        if not valid_devices:
            logger.warning(f"ADB devices found, but none are ready/authorized:\n{output.strip()}")
            return False
            
        return True
    except Exception as e:
        logger.error(f"Error checking connected devices: {e}")
        return False


def dump_ui_xml():
    """
    Dumps the current UI state of the device and returns the XML string.
    Returns None if the dump fails.
    """
    try:
        res = subprocess.run(["adb", "shell", "uiautomator", "dump"], capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"ADB UI dump command failed: {res.stderr.strip()}")
            return None
        return run(["adb", "shell", "cat", "/sdcard/window_dump.xml"])
    except Exception as e:
        logger.error(f"Failed to dump UI XML: {e}")
        return None


def tap(x, y):
    """Simulates a tap at (x, y)."""
    try:
        subprocess.run(["adb", "shell", "input", "tap", str(x), str(y)], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Tap command failed at ({x}, {y}): {e.stderr.decode().strip()}")


def back():
    """Simulates pressing the physical Back button."""
    try:
        subprocess.run(["adb", "shell", "input", "keyevent", "4"], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Back keyevent failed: {e.stderr.decode().strip()}")


def swipe(x1, y1, x2, y2, duration=250):
    """Simulates a swipe gesture from (x1, y1) to (x2, y2)."""
    try:
        subprocess.run([
            "adb", "shell", "input", "swipe",
            str(x1), str(y1), str(x2), str(y2), str(duration)
        ], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Swipe failed from ({x1}, {y1}) to ({x2}, {y2}): {e.stderr.decode().strip()}")


def type_text(text):
    """Types the given text on the device after sanitizing it to prevent shell injections."""
    # Sanitize: Remove critical shell injection characters and quotes
    # Allow alphanumeric, spaces, and basic safe punctuation
    sanitized = re.sub(r'[;&|$`"\\]', '', text)
    # Escape spaces for ADB input text
    escaped_text = sanitized.replace(" ", "%s")
    try:
        subprocess.run(["adb", "shell", "input", "text", escaped_text], check=True, capture_output=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Type text failed for '{text}': {e.stderr.decode().strip()}")
