# modules/action.py

from typing import Dict, Any, Union
from pydantic import BaseModel
import ast

# Optional logging fallback
try:
    from agent import log
except ImportError:
    import datetime
    def log(stage: str, msg: str):
        now = datetime.datetime.now().strftime("%H:%M:%S")
        print(f"[{now}] [{stage}] {msg}")


class ToolCallResult(BaseModel):
    tool_name: str
    arguments: Dict[str, Any]
    result: Union[str, list, dict]
    raw_response: Any


def parse_function_call(response: str) -> tuple[str, Dict[str, Any]]:
    """
    Parses a FUNCTION_CALL string like:
    "FUNCTION_CALL: add|a=5|b=7"
    "FUNCTION_CALL: create_google_sheet|title=Test|data_json=[...]"
    Into a tool name and a dictionary of arguments.
    
    Handles complex nested structures by supporting JSON strings for parameters ending in _json.
    """
    import json
    import re
    
    try:
        if not response.startswith("FUNCTION_CALL:"):
            raise ValueError("Invalid function call format.")

        _, raw = response.split(":", 1)
        
        # First, extract the tool name
        tool_name_match = re.match(r'^(\w+)\|', raw)
        if not tool_name_match:
            # Try without pipe separator (single parameter or no parameters)
            if '|' not in raw and '=' not in raw:
                return raw.strip(), {}
            tool_name = raw.split('|')[0].strip()
            param_str = raw[len(tool_name):].lstrip('|')
        else:
            tool_name = tool_name_match.group(1)
            param_str = raw[len(tool_name)+1:]
        
        args = {}
        
        # Parse parameters - handle quoted values and JSON strings
        # Split on | but respect quoted strings and JSON arrays/objects
        param_parts = []
        current_part = ""
        in_quotes = False
        quote_char = None
        bracket_depth = 0
        brace_depth = 0
        
        i = 0
        while i < len(param_str):
            char = param_str[i]
            
            if char in ['"', "'"] and (i == 0 or param_str[i-1] != '\\'):
                if not in_quotes:
                    in_quotes = True
                    quote_char = char
                elif char == quote_char:
                    in_quotes = False
                    quote_char = None
                current_part += char
            elif char == '[' and not in_quotes:
                bracket_depth += 1
                current_part += char
            elif char == ']' and not in_quotes:
                bracket_depth -= 1
                current_part += char
            elif char == '{' and not in_quotes:
                brace_depth += 1
                current_part += char
            elif char == '}' and not in_quotes:
                brace_depth -= 1
                current_part += char
            elif char == '|' and not in_quotes and bracket_depth == 0 and brace_depth == 0:
                if current_part.strip():
                    param_parts.append(current_part.strip())
                current_part = ""
            else:
                current_part += char
            i += 1
        
        if current_part.strip():
            param_parts.append(current_part.strip())
        
        # Parse each parameter
        for part in param_parts:
            if "=" not in part:
                continue
            
            # Split on first = only
            key, val = part.split("=", 1)
            key = key.strip()
            val = val.strip()
            
            # Check if this is a JSON parameter
            if key.endswith("_json"):
                try:
                    parsed_val = json.loads(val)
                    key = key[:-5]  # Remove _json suffix
                except json.JSONDecodeError:
                    # Try as Python literal if JSON fails
                    try:
                        parsed_val = ast.literal_eval(val)
                        key = key[:-5]
                    except:
                        parsed_val = val
            else:
                # Try parsing as Python literal first (handles lists, dicts, etc.)
                try:
                    parsed_val = ast.literal_eval(val)
                except (ValueError, SyntaxError):
                    # If that fails, try JSON
                    try:
                        parsed_val = json.loads(val)
                    except json.JSONDecodeError:
                        # Fallback to string, removing quotes if present
                        parsed_val = val.strip().strip('"').strip("'")

            # Support nested keys (e.g., input.value)
            keys = key.split(".")
            current = args
            for k in keys[:-1]:
                current = current.setdefault(k, {})
            current[keys[-1]] = parsed_val

        log("parser", f"Parsed: {tool_name} → {args}")
        return tool_name, args

    except Exception as e:
        log("parser", f"❌ Parse failed: {e}")
        raise
