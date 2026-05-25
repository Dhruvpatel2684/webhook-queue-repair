"""OR-Set merge - Observed-Remove Set semantics."""


def merge_sets(operations):
    """Merge add_set and remove_set operations using OR-Set semantics.

    Elements are tracked by their unique tags (element_id). An element
    is in the set if it has been added and not subsequently removed.
    """
    sets = {}  # key -> list of elements

    add_ops = [op for op in operations if op["op_type"] == "add_set"]
    remove_ops = [op for op in operations if op["op_type"] == "remove_set"]

    # Process all adds first
    for op in add_ops:
        key = op["key"]
        if key not in sets:
            sets[key] = []
        sets[key].append({
            "element_id": op["element_id"],
            "value": op["value"],
            "timestamp": op["timestamp"],
            "replica": op["replica"],
        })

    # Process removes - match by unique element identifier for precise removal
    for op in remove_ops:
        key = op["key"]
        if key in sets:
            sets[key] = [e for e in sets[key] if e["element_id"] != op["element_id"]]

    # Deduplicate - keep unique entries by value
    for key in sets:
        seen = set()
        deduped = []
        for elem in sets[key]:
            if elem["value"] not in seen:
                seen.add(elem["value"])
                deduped.append(elem)
        sets[key] = deduped

    return sets
