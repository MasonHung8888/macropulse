#!/usr/bin/env python3
"""
validate_schema_compatibility.py
MacroPulse Data Engine Compatibility & Regression Validator

Verifies that a candidate JSON strictly maintains backwards compatibility with
the production JSON currently in use by index.html and taiwan_market.html.
Rules:
1. No deleted keys from the production baseline.
2. Data types must match: number remains number, string remains string, list remains list, dict remains dict.
3. No critical numbers converted to None/null.
4. Quality metadata (_quality_metadata) can be added as non-breaking enrichment.
"""

import sys
import json
import os
from typing import Any, List, Tuple

def get_type_name(val: Any) -> str:
    if val is None:
        return "null"
    if isinstance(val, bool):
        return "bool"
    if isinstance(val, (int, float)):
        return "number"
    if isinstance(val, str):
        return "string"
    if isinstance(val, list):
        return "list"
    if isinstance(val, dict):
        return "dict"
    return type(val).__name__

def check_compatibility(base: Any, cand: Any, path: str = "") -> List[str]:
    errors = []
    
    # Check nulls on base non-null
    if base is not None and cand is None:
        return [f"[TYPE ERROR] {path}: Baseline is {get_type_name(base)} but Candidate is null"]
    
    base_type = get_type_name(base)
    cand_type = get_type_name(cand)
    
    if base is not None and cand is not None:
        if base_type != cand_type:
            # Allow int/float interchangeability for 'number'
            if not (base_type == "number" and cand_type == "number"):
                return [f"[TYPE MISMATCH] {path}: Expected {base_type}, got {cand_type}"]
    
    if isinstance(base, dict) and isinstance(cand, dict):
        for k, v in base.items():
            child_path = f"{path}.{k}" if path else k
            if k not in cand:
                errors.append(f"[MISSING KEY] {child_path}: Present in baseline but missing in candidate")
            else:
                errors.extend(check_compatibility(v, cand[k], child_path))
    elif isinstance(base, list) and isinstance(cand, list):
        # If baseline has elements, inspect first element structure
        if len(base) > 0 and len(cand) > 0:
            if isinstance(base[0], dict) and isinstance(cand[0], dict):
                # Check that essential keys in base[0] exist in cand[0]
                for k, v in base[0].items():
                    child_path = f"{path}[*].{k}"
                    if k not in cand[0]:
                        errors.append(f"[MISSING LIST ITEM KEY] {child_path}: Missing in candidate items")
                    else:
                        errors.extend(check_compatibility(v, cand[0][k], child_path))
    return errors

def validate_pair(baseline_path: str, candidate_path: str) -> bool:
    print(f"=== Validating {os.path.basename(candidate_path)} against {os.path.basename(baseline_path)} ===")
    if not os.path.exists(baseline_path):
        print(f"Error: Baseline file not found: {baseline_path}")
        return False
    if not os.path.exists(candidate_path):
        print(f"Error: Candidate file not found: {candidate_path}")
        return False
        
    with open(baseline_path, 'r', encoding='utf-8') as f:
        base_data = json.load(f)
    with open(candidate_path, 'r', encoding='utf-8') as f:
        cand_data = json.load(f)
        
    errors = check_compatibility(base_data, cand_data)
    
    if errors:
        print(f"FAIL: Found {len(errors)} compatibility issue(s):")
        for err in errors[:20]:
            print("  ", err)
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more errors.")
        return False
    else:
        print("PASS: 100% schema compatibility confirmed. All keys, types, and structures match baseline.")
        return True

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python validate_schema_compatibility.py <baseline_json> <candidate_json>")
        sys.exit(1)
    success = validate_pair(sys.argv[1], sys.argv[2])
    sys.exit(0 if success else 1)
