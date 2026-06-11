import xml.etree.ElementTree as ET
import re
from .config import logger

def parse_ui(xml_content):
    """
    Parses the ADB uiautomator dump XML.
    Returns:
        (clickable_nodes, static_labels)
    """
    if not xml_content or not xml_content.strip():
        logger.warning("Empty XML content received for parsing.")
        return [], []

    try:
        root = ET.fromstring(xml_content)
    except ET.ParseError as e:
        logger.error(f"Error parsing UI XML: {e}")
        logger.debug(f"Raw invalid XML content: {xml_content}")
        return [], []

    clickable_nodes = []
    static_labels = []

    for n in root.iter("node"):
        is_clickable = n.attrib.get("clickable") == "true"
        is_editable = n.attrib.get("editable") == "true" or "EditText" in n.attrib.get("class", "")
        text = n.attrib.get("text", "").strip()
        desc = n.attrib.get("content-desc", "").strip()
        id_attr = n.attrib.get("resource-id", "").strip()

        # Ignore empty elements
        if not text and not desc and not id_attr and not is_editable:
            continue

        bounds = n.attrib.get("bounds", "")

        if is_clickable or is_editable:
            clickable_nodes.append({
                "text": text,
                "desc": desc,
                "id": id_attr,
                "bounds": bounds,
                "editable": is_editable,
                "focused": n.attrib.get("focused", "false") == "true"
            })
        else:
            if text or desc:
                static_labels.append({
                    "text": text,
                    "desc": desc,
                    "id": id_attr
                })

    logger.debug(f"Parsed {len(clickable_nodes)} clickable nodes and {len(static_labels)} static labels.")
    return clickable_nodes, static_labels


def bounds_center(bounds):
    """
    Calculates the center (x, y) coordinates from a bounds string, e.g., '[10,20][30,40]'
    """
    if not bounds:
        return None
    try:
        nums = re.findall(r"\d+", bounds)
        x1, y1, x2, y2 = map(int, nums)
        return (x1 + x2) // 2, (y1 + y2) // 2
    except Exception as e:
        logger.debug(f"Could not calculate center for bounds '{bounds}': {e}")
        return None
