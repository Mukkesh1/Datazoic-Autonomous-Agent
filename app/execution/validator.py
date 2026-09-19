from typing import Dict, Any, Tuple
import jsonschema
from jsonschema.exceptions import ValidationError
from app.tools.schemas import ToolMetadata

class SchemaValidator:
    """
    Validates LLM-generated arguments against strict JSON schemas.
    This acts as a hard guardrail preventing hallucinated parameters from reaching external APIs.
    """
    
    @staticmethod
    def validate_args(tool: ToolMetadata, extracted_args: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Validates the arguments against the tool's input_schema.
        
        Returns:
            Tuple[bool, str]: (is_valid, error_message)
        """
        try:
            # Coerce strings to numbers/booleans if the schema expects it, as 8B models often wrap everything in strings
            properties = tool.input_schema.get("properties", {})
            for key, val in list(extracted_args.items()):
                if key in properties:
                    expected_type = properties[key].get("type")
                    if isinstance(val, str):
                        if expected_type in ["number", "integer"]:
                            try:
                                extracted_args[key] = int(val) if val.isdigit() else float(val)
                            except ValueError:
                                pass
                        elif expected_type == "boolean":
                            if val.lower() == "true": extracted_args[key] = True
                            elif val.lower() == "false": extracted_args[key] = False
                    elif isinstance(val, bool) and expected_type in ["number", "integer"]:
                        # ingest_postman maps booleans to 'number', so coerce back to pass validation
                        extracted_args[key] = 1 if val else 0

            # We use jsonschema because OpenAPI specs and Postman collections 
            # natively define parameters using standard JSON Schema.
            jsonschema.validate(instance=extracted_args, schema=tool.input_schema)
            return True, ""
            
        except ValidationError as e:
            # Construct a highly specific error message. 
            # If the LLM sees this, it knows exactly which field to fix on its next attempt.
            path = ".".join([str(p) for p in e.path]) if e.path else "root"
            error_msg = f"Validation Error at '{path}': {e.message}"
            return False, error_msg
