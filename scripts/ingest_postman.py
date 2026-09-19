import json
import os
import re
import glob

def slugify(text: str) -> str:
    text = text.lower()
    text = re.sub(r'[^a-z0-9]+', '_', text)
    return text.strip('_')

def parse_postman_directory(input_dir: str, output_path: str, default_base_url: str):
    all_tools = []
    
    files = glob.glob(os.path.join(input_dir, "*.json"))
    for file_path in files:
        with open(file_path, 'r', encoding='utf-8') as f:
            collection = json.load(f)
            
        def extract_items(items, prefix=""):
            for item in items:
                if "item" in item:
                    folder_name = slugify(item["name"])
                    extract_items(item["item"], prefix=f"{prefix}{folder_name}_")
                elif "request" in item:
                    all_tools.append(parse_request(item, prefix))

        def parse_request(item, prefix):
            req = item["request"]
            raw_name = item["name"]
            method = req.get("method", "GET").upper()
            
            if isinstance(req.get("url"), dict):
                raw_url = req["url"].get("raw", "")
            elif isinstance(req.get("url"), str):
                raw_url = req["url"]
            else:
                raw_url = ""
                
            url = re.sub(r'\{\{[a-zA-Z0-9_-]+\}\}', default_base_url, raw_url)
            url = re.sub(r':([a-zA-Z0-9_]+)', r'{\1}', url)
            
            properties = {}
            required = []
            flat_props_required_candidates = []
            
            path_vars = re.findall(r'\{([a-zA-Z0-9_]+)\}', url)
            for pv in path_vars:
                properties[pv] = {"type": "string", "description": f"URL Path variable: {pv}"}
                required.append(pv)
            
            if "query" in req.get("url", {}):
                for q in req["url"]["query"]:
                    if not q.get("disabled", False):
                        q_name = q["key"]
                        properties[q_name] = {"type": "string", "description": q.get("description", f"Query parameter: {q_name}")}
                        
            if "body" in req and req["body"].get("mode") == "raw":
                if method == "PATCH":
                    properties["request_body"] = {
                        "type": "array",
                        "description": "JSON Patch payload (RFC 6902 format). MUST be an array of operations.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string", "description": "The operation to perform (e.g. 'replace', 'add', 'remove')"},
                                "path": {"type": "string", "description": "The JSON path to the field being modified (e.g. '/description')"},
                                "value": {"type": "string", "description": "The new value to set"}
                            },
                            "required": ["op", "path"]
                        }
                    }
                    required.append("request_body")
                else:
                    raw_body_example = req["body"].get("raw", "")
                    if raw_body_example.strip().startswith("{"):
                        try:
                            def get_flat_schema(node, path=[]):
                                flat = {}
                                if isinstance(node, dict):
                                    for k, v in node.items():
                                        flat.update(get_flat_schema(v, path + [k]))
                                elif isinstance(node, list):
                                    if len(node) > 0:
                                        flat.update(get_flat_schema(node[0], path))
                                else:
                                    key = path[-1] if path else "value"
                                    # Very basic heuristic for preventing collision
                                    if len(path) > 1 and key in ["value", "id", "type", "status", "code", "name"]:
                                        key = f"{path[-2]}_{key}"
                                    if key in flat and len(path) > 1:
                                        key = f"{path[-2]}_{key}"
                                    if key in flat and len(path) > 2:
                                        key = f"{path[-3]}_{key}"
                                    flat[key] = {"type": "string" if isinstance(node, str) else "number", "description": f"Example: {node}"}
                                return flat
                                
                            parsed = json.loads(raw_body_example)
                            flat_props = get_flat_schema(parsed)
                            flat_props_required_candidates = list(flat_props.keys())
                            # We put flat_props directly at the top level!
                            properties.update(flat_props)
                        except Exception:
                            properties["json_body"] = {
                                "type": "object", 
                                "description": "The JSON payload dictionary containing the actual data for the API request."
                            }
                            required.append("json_body")

            required = list(set(required) | set(flat_props_required_candidates))
            required = [r for r in required if r != "request_body"] + (["request_body"] if "request_body" in properties and method == "PATCH" else [])
            
            tool_id = f"{prefix}{slugify(raw_name)}"
            
            description = item.get("description", f"Executes the {raw_name} API call.")
            if not isinstance(description, str):
                description = str(description)

            tool = {
                "tool_id": f"paypal.{tool_id}",
                "name": tool_id[:64], 
                "description": description[:512],
                "api_endpoint": url,
                "http_method": method,
                "auth_type": "paypal_oauth",
                "is_mutating": method in ["POST", "PUT", "DELETE", "PATCH"],
                "requires_confirmation": method in ["POST", "PUT", "DELETE"],
                "tags": ["paypal", method.lower(), tool_id],
                "input_schema": {
                    "type": "object",
                    "properties": properties,
                    "required": required
                }
            }
            if "body" in req and req["body"].get("mode") == "raw" and method != "PATCH":
                try:
                    tool["payload_template"] = json.loads(req["body"]["raw"].strip())
                except Exception as e:
                    print(f"FAILED to parse template for {tool_id}: {e}")
            return tool

        if "item" in collection:
            extract_items(collection["item"])

    # Deduplicate tools by method and endpoint (prefer 'subscriptions_' prefixes if multiple exist)
    unique_tools = {}
    for t in all_tools:
        key = f"{t['http_method']} {t['api_endpoint']}"
        if key not in unique_tools:
            unique_tools[key] = t
        else:
            # If the new one has 'subscriptions' in the ID, prefer it
            if 'subscriptions' in t['tool_id'] and 'subscriptions' not in unique_tools[key]['tool_id']:
                unique_tools[key] = t

    final_tools = list(unique_tools.values())

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(final_tools, f, indent=2)
        
    print(f"Successfully converted {len(final_tools)} unique Postman endpoints into agent tools at {output_path}")

if __name__ == "__main__":
    base_dir = os.path.dirname(os.path.dirname(__file__))
    input_dir = os.path.join(base_dir, "data", "postman_exports")
    out_file = os.path.join(base_dir, "data", "paypal_tools.json")
    
    if not os.path.exists(input_dir):
        print(f"ERROR: Directory not found: {input_dir}")
    else:
        parse_postman_directory(input_dir, out_file, "https://api-m.sandbox.paypal.com")
