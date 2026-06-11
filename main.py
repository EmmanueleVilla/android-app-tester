#!/usr/bin/env python3
import os
import sys
import time

# Import package submodules from src
from src import config
from src import adb
from src import parser
from src import llm
from src.config import logger

# =========================
# GOALS LOADING
# =========================

def load_steps(directory, single_goal_filename=None):
    """
    Loads exploration steps from the goals directory.
    If a specific file is requested, only steps from that file are loaded.
    """
    import yaml
    steps = []
    if not os.path.exists(directory):
        logger.warning(f"Goals directory '{directory}' does not exist.")
        return steps
    
    def process_goal_data(goal_data, source_name):
        processed_steps = []
        if isinstance(goal_data, list):
            items = goal_data
        elif isinstance(goal_data, dict):
            items = [goal_data]
        else:
            logger.warning(f"Skipping invalid goal data in '{source_name}': Must be a list or dictionary.")
            return []
            
        for item in items:
            if not isinstance(item, dict):
                logger.warning(f"Skipping invalid step in '{source_name}': Step must be a dictionary.")
                continue
            if "type" not in item:
                item["type"] = "prompting"
            
            # Map 'step' key. If missing but 'goal' exists, use 'goal'.
            if "step" not in item:
                if "goal" in item:
                    item["step"] = item["goal"]
                elif item["type"] == "manual" and "id" in item:
                    item["step"] = f"Click ID {item['id']}"
                else:
                    item["step"] = "Unnamed Step"
            processed_steps.append(item)
        return processed_steps

    if single_goal_filename:
        base_name = os.path.splitext(single_goal_filename)[0]
        goal_path = None
        for ext in [".yaml", ".yml"]:
            path = os.path.join(directory, base_name + ext)
            if os.path.exists(path):
                goal_path = path
                break
        
        if not goal_path:
            goal_path = os.path.join(directory, single_goal_filename)
        
        if os.path.exists(goal_path):
            try:
                with open(goal_path, "r", encoding="utf-8") as f:
                    goal_data = yaml.safe_load(f)
                    steps.extend(process_goal_data(goal_data, goal_path))
            except Exception as e:
                logger.critical(f"Error loading goal file '{goal_path}': {e}")
                sys.exit(1)
        else:
            logger.critical(f"Goal file not found: {goal_path}")
            sys.exit(1)
    else:
        try:
            for filename in sorted(os.listdir(directory)):
                if filename.endswith(".yaml") or filename.endswith(".yml"):
                    with open(os.path.join(directory, filename), "r", encoding="utf-8") as f:
                        try:
                            goal_data = yaml.safe_load(f)
                            steps.extend(process_goal_data(goal_data, filename))
                        except Exception as e:
                            logger.error(f"Error parsing goal file '{filename}': {e}")
        except Exception as e:
            logger.error(f"Error listing goals directory: {e}")
    return steps



# Check for single goal argument
TARGET_GOAL_FILE = sys.argv[1] if len(sys.argv) > 1 else None
STEPS = load_steps(config.GOALS_DIR, TARGET_GOAL_FILE)

# =========================
# ACTION EXECUTION
# =========================

def execute(action, nodes):
    """
    Translates agent JSON actions into ADB inputs.
    """
    if not action:
        logger.warning("No valid action parsed from model response.")
        return

    kind = action.get("action")

    if kind == "tap":
        idx = action.get("index", 0)

        if idx >= len(nodes):
            logger.error(f"Invalid index {idx} (total available elements: {len(nodes)})")
            return

        c = parser.bounds_center(nodes[idx]["bounds"])
        if not c:
            logger.error(f"Cannot compute touch center for element index {idx}")
            return

        logger.info(f"Executing: TAP [{idx}] -> {c}")
        adb.tap(*c)

    elif kind == "type_text":
        idx = action.get("index")
        if idx is not None:
            if idx >= len(nodes):
                logger.error(f"Invalid index {idx} for typing.")
                return
            c = parser.bounds_center(nodes[idx]["bounds"])
            if c:
                logger.info(f"Executing: TAP (focusing field) [{idx}] -> {c}")
                adb.tap(*c)
                time.sleep(1)
                
        text = action.get("text", "")
        logger.info(f"Executing: TYPING: '{text}'")
        adb.type_text(text)

    elif kind == "back":
        logger.info("Executing: NAVIGATING BACK")
        adb.back()

    elif kind == "swipe":
        x1 = action.get("x1", 500)
        y1 = action.get("y1", 1500)
        x2 = action.get("x2", 500)
        y2 = action.get("y2", 500)
        logger.info(f"Executing: SWIPE from ({x1}, {y1}) to ({x2}, {y2})")
        adb.swipe(x1, y1, x2, y2)
        
    else:
        logger.warning(f"Unknown action type '{kind}'")


# =========================
# MAIN LOOP
# =========================

def main():
    logger.info("=" * 50)
    logger.info(" STARTING ANDROID UI EXPLORATION AGENT")
    logger.info("=" * 50)

    # Pre-flight ADB connection check
    if not adb.check_adb_connection():
        logger.critical("ADB setup is incomplete or no device is connected. Aborting initialization.")
        sys.exit(1)
    
    logger.info("ADB status: Connected and ready.")
    logger.info(f"Target app package: {config.PACKAGE}")
    logger.info(f"Execution mode: {config.MODE} ({config.OLLAMA_MODEL if config.MODE == 'ollama' else config.OPENAI_MODEL})")
    logger.info("-" * 50)

    if not STEPS:
        logger.error("No steps found in the goals directory. Exiting.")
        return

    history = []
    step_index = 0
    consecutive_errors = 0
    max_consecutive_errors = 5

    while True:
        try:
            current_step = STEPS[step_index]
            step_text = current_step.get("step", "Unnamed Step")
            step_type = current_step.get("type", "prompting")
            
            logger.info(f"ACTIVE STEP [{step_index + 1}/{len(STEPS)}]: {step_text} (Type: {step_type})")
            logger.info("-" * 50)

            # Dump device hierarchy with retry logic on failure
            xml = None
            for attempt in range(1, 4):
                logger.info(f"Dumping UI layout (attempt {attempt}/3)...")
                xml = adb.dump_ui_xml()
                if xml and xml.strip():
                    break
                logger.warning("Dump returned empty content. Retrying in 2 seconds...")
                time.sleep(2)
            
            if not xml or not xml.strip():
                raise RuntimeError("Failed to capture a valid UI dump after 3 attempts.")

            clickable_nodes, static_labels = parser.parse_ui(xml)

            # Log list of detected clickable nodes
            ids = [f"[{i}] {n['text'] or n['id'] or 'unnamed'}" for i, n in enumerate(clickable_nodes)]
            if ids:
                logger.info(f"Detected Clickable Elements: {', '.join(ids)}")
            else:
                logger.warning("No interactive elements detected on the current screen.")

            if step_type == "manual":
                action_name = current_step.get("action")
                if action_name == "click id":
                    target_id = current_step.get("id")
                    if not target_id:
                        logger.error("Manual action 'click id' requires an 'id' field in the configuration.")
                        sys.exit(1)
                    
                    found_node = None
                    found_index = None
                    for i, node in enumerate(clickable_nodes):
                        node_id = node.get("id") or ""
                        if node_id == target_id or target_id in node_id:
                            found_node = node
                            found_index = i
                            break
                    
                    if found_node:
                        c = parser.bounds_center(found_node["bounds"])
                        if c:
                            logger.info(f"Executing Manual Action: TAP [{found_index}] (id: {found_node['id']}) -> {c}")
                            adb.tap(*c)
                            
                            # Add to history
                            history_entry = {
                                "raw": f"Manual action executed: click id '{target_id}'",
                                "action": {"action": "tap", "index": found_index},
                                "tapped_element": {
                                    "text": found_node.get("text"),
                                    "id": found_node.get("id"),
                                    "index": found_index
                                }
                            }
                            history.append(history_entry)
                            
                            logger.info("=" * 50)
                            logger.info(f"STEP COMPLETED: {step_text}")
                            logger.info("=" * 50)
                            
                            step_index += 1
                            if step_index >= len(STEPS):
                                logger.info("ALL STEPS ACHIEVED. SHUTTING DOWN.")
                                break
                            
                            logger.info(f"MOVING TO NEXT STEP: {STEPS[step_index].get('step', 'Unnamed Step')}")
                            time.sleep(2)
                            consecutive_errors = 0
                            continue
                        else:
                            logger.error(f"Cannot compute touch center for element with ID '{target_id}'")
                    
                    consecutive_errors += 1
                    logger.warning(f"Manual element with ID '{target_id}' not found on screen (attempt {consecutive_errors}/{max_consecutive_errors}).")
                    if consecutive_errors >= max_consecutive_errors:
                        raise RuntimeError(f"Failed to find manual click target ID '{target_id}' after {max_consecutive_errors} attempts.")
                    time.sleep(2)
                    continue
                else:
                    logger.error(f"Unsupported manual action '{action_name}'")
                    sys.exit(1)
            else:
                # Show last few steps of history
                if history:
                    logger.info("History (Last 5 steps):")
                    for h in history[-5:]:
                        action = h.get("action", {})
                        details = (
                            h.get("tapped_element", {}).get("text")
                            or h.get("tapped_element", {}).get("id")
                            or "no details"
                        )
                        logger.info(f"  - {action.get('action')} ({details})")

                # Call the language model
                raw = llm.ask_llm(clickable_nodes, static_labels, history, step_text)
                action = llm.extract_json(raw)

                logger.info(f"Parsed Action: {action}")

                if action and action.get("action") == "test_failed":
                    motivation = action.get("motivation", "No reason provided")
                    logger.error("=" * 50)
                    logger.error(f"STEP FAILED: {step_text}")
                    logger.error(f"MOTIVATION: {motivation}")
                    logger.error("=" * 50)
                    break

                if action and action.get("action") == "goal_completed":
                    logger.info("=" * 50)
                    logger.info(f"STEP COMPLETED: {step_text}")
                    logger.info("=" * 50)
                    
                    step_index += 1
                    if step_index >= len(STEPS):
                        logger.info("ALL STEPS ACHIEVED. SHUTTING DOWN.")
                        break
                    
                    logger.info(f"MOVING TO NEXT STEP: {STEPS[step_index].get('step', 'Unnamed Step')}")
                    time.sleep(2)
                    consecutive_errors = 0 # Reset error count on successful step transition
                    continue

                # Record history
                history_entry = {
                    "raw": raw,
                    "action": action
                }
                if action and action.get("action") == "tap":
                    idx = action.get("index")
                    if idx is not None and 0 <= idx < len(clickable_nodes):
                        node = clickable_nodes[idx]
                        history_entry["tapped_element"] = {
                            "text": node.get("text"),
                            "id": node.get("id"),
                            "index": idx
                        }

                history.append(history_entry)

                # Perform the requested action on the device
                execute(action, clickable_nodes)
                time.sleep(2)
                
                # Reset consecutive errors since we had a successful loop iteration
                consecutive_errors = 0

        except KeyboardInterrupt:
            logger.info("STOPPED BY USER")
            break

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"Exception encountered (consecutive error {consecutive_errors}/{max_consecutive_errors}): {e}")
            
            if consecutive_errors >= max_consecutive_errors:
                logger.critical("Maximum consecutive errors reached. Shutting down to prevent infinite crash loop.")
                sys.exit(1)
                
            time.sleep(3)


if __name__ == "__main__":
    main()
