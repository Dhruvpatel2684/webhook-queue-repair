"""Write merged CRDT state to output files."""
import json
import hashlib
import os


def compute_state_digest(registers, sets, conflicts):
    """Compute deterministic digest of merged state."""
    digest_parts = []
    for key in sorted(registers.keys()):
        r = registers[key]
        digest_parts.append(f"reg:{key}={r['value']}@{r['replica']}")
    for key in sorted(sets.keys()):
        values = sorted(e["value"] for e in sets[key])
        digest_parts.append(f"set:{key}=[{','.join(values)}]")
    digest_parts.append(f"conflicts:{len(conflicts)}")
    digest_input = "|".join(digest_parts)
    return hashlib.sha256(digest_input.encode()).hexdigest()[:16]


def write_state(registers, sets, conflicts, output_dir):
    """Write merged state and conflict report to output directory."""
    os.makedirs(output_dir, exist_ok=True)

    # Build register state
    reg_state = {}
    for key, op in registers.items():
        reg_state[key] = {
            "value": op["value"],
            "timestamp": op["timestamp"],
            "replica": op["replica"],
        }

    # Build set state
    set_state = {}
    for key, elements in sets.items():
        set_state[key] = [{"value": e["value"], "element_id": e["element_id"]} for e in elements]

    digest = compute_state_digest(registers, sets, conflicts)

    state_output = {
        "registers": reg_state,
        "sets": set_state,
        "state_digest": digest,
        "total_registers": len(reg_state),
        "total_sets": len(set_state),
    }

    state_path = os.path.join(output_dir, "merged_state.json")
    with open(state_path, "w") as f:
        json.dump(state_output, f, indent=2, sort_keys=True)

    conflict_output = {
        "high_conflict_entries": conflicts,
        "total_conflicts": len(conflicts),
    }

    conflict_path = os.path.join(output_dir, "conflict_report.json")
    with open(conflict_path, "w") as f:
        json.dump(conflict_output, f, indent=2)

    return state_path, conflict_path
