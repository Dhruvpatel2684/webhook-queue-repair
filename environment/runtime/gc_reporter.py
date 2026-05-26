"""
GC Reporter - Generates the final GC report output.

Combines information from the GC context, candidate analysis, and execution
plan into a structured report suitable for monitoring and auditing. The report
includes both the plan details and contextual information about the state of
the version store at the time of GC.
"""

import hashlib
import json


class GCReporter:
    """Generates structured GC reports."""

    def __init__(self, context, gc_candidates, gc_plan):
        self._context = context
        self._gc_candidates = gc_candidates
        self._gc_plan = gc_plan

    def generate(self):
        """Generate the complete GC report.

        Returns a dict containing:
          - state: current system state summary
          - gc_plan: the execution plan
          - gc_candidates: detailed candidate information
          - digest: integrity hash of the plan
        """
        state = self._build_state_section()
        candidates_detail = self._build_candidates_detail()
        digest = self._compute_digest()

        return {
            "state": state,
            "gc_plan": self._gc_plan,
            "gc_candidates": candidates_detail,
            "digest": digest,
        }

    def _build_state_section(self):
        """Build the state summary section of the report."""
        return {
            "total_keys": self._context["total_keys"],
            "total_versions": self._context["total_versions"],
            "active_transactions": self._context["transaction_count"],
            "watermark": self._context["watermark"],
        }

    def _build_candidates_detail(self):
        """Build detailed candidate information."""
        total_candidate_versions = sum(
            len(v) for v in self._gc_candidates.values()
        )
        return {
            "keys_with_candidates": len(self._gc_candidates),
            "total_candidate_versions": total_candidate_versions,
            "by_key": {
                key: {"version_ids": vids, "count": len(vids)}
                for key, vids in sorted(self._gc_candidates.items())
            },
        }

    def _compute_digest(self):
        """Compute a digest hash of the GC plan for integrity verification.

        The digest covers the key plan fields to detect any tampering or
        corruption of the plan between generation and execution.
        """
        digest_input = {
            "watermark": self._context["watermark"],
            "total_reclaimable": self._gc_plan["total_reclaimable_versions"],
            "space_savings": self._gc_plan["estimated_space_savings_bytes"],
            "keys_affected": self._gc_plan["keys_affected"],
        }
        serialized = json.dumps(digest_input, sort_keys=True)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def __repr__(self):
        return f"GCReporter(keys={len(self._gc_candidates)})"
