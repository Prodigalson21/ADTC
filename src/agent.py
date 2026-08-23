"""
agent.py -- routes an incoming message (English or Swahili) to a tool
call, via two layers:

  Fast-path: swahili_agreement.is_covered() -- deterministic lookup
    table + regex, zero LLM involvement.

  LLM fallback: only reached when the fast-path doesn't match.
    Requires an inference_backend + a GBNF grammar. If the LLM
    produces something invalid, or isn't available, falls through to
    an honest degradation response rather than crashing.

The precondition check itself lives in business_logic.py / database.py
-- agent.py never touches the database directly.
"""

from typing import Optional, Dict, Any, Callable

import src.business_logic as business_logic


def _dispatch_record_sale(db, params: Dict[str, str]) -> Dict[str, Any]:
    return business_logic.record_sale(
        db,
        product_name=params["product"],
        quantity=float(params["quantity"]),
        unit=params["unit"],
    )


def _dispatch_resolve_refund_by_product(db, params: Dict[str, str]) -> Dict[str, Any]:
    return business_logic.process_refund(db, product_name=params["product"])


def _dispatch_apply_discount(db, params: Dict[str, str]) -> Dict[str, Any]:
    return business_logic.apply_discount(
        db,
        product_name=params["product"],
        percent=float(params["percent"]),
    )


def _dispatch_check_inventory(db, params: Dict[str, str]) -> Dict[str, Any]:
    return business_logic.check_inventory(db, product_name=params["product"])


def _dispatch_restock_alert(db, params: Dict[str, str]) -> Dict[str, Any]:
    return business_logic.restock_alert(db, product_name=params["product"])


ACTION_DISPATCH: Dict[str, Callable] = {
    "record_sale": _dispatch_record_sale,
    "resolve_refund_by_product": _dispatch_resolve_refund_by_product,
    "apply_discount": _dispatch_apply_discount,
    "check_inventory": _dispatch_check_inventory,
    "restock_alert": _dispatch_restock_alert,
}


class Agent:
    """Ties the fast-path, the LLM fallback, and business_logic
    together. inference_backend is optional -- pass None to run with
    the fast-path only."""

    def __init__(self, db, is_covered_fn=None, inference_backend=None,
                 grammar_path: Optional[str] = None, system_prompt: str = ""):
        from src.swahili_agreement import is_covered as default_is_covered
        self._is_covered = is_covered_fn or default_is_covered
        self.db = db
        self.inference_backend = inference_backend
        self.grammar_path = grammar_path
        self.system_prompt = system_prompt

    def process_message(self, text: str) -> Dict[str, Any]:
        """Always returns a structured dict, never raises."""
        handled, match = self._is_covered(text)

        if handled:
            return self._dispatch(match["action"], match["parameters"], layer="fast-path")

        return self._llm_fallback(text)

    def _dispatch(self, action: str, raw_params: Dict[str, str], layer: str) -> Dict[str, Any]:
        handler = ACTION_DISPATCH.get(action)
        if handler is None:
            return {
                "success": False,
                "layer": layer,
                "error": f"No handler registered for action '{action}'",
            }

        try:
            result = handler(self.db, raw_params)
        except (KeyError, ValueError) as e:
            return {
                "success": False,
                "layer": layer,
                "error": f"Malformed parameters for action '{action}': {e}",
            }

        result["layer"] = layer
        result["action"] = action
        return result

    def _llm_fallback(self, text: str) -> Dict[str, Any]:
        """Layer 3. Never crashes, never fabricates an action."""
        if self.inference_backend is None:
            return {
                "success": False,
                "layer": "llm-fallback",
                "error": "No LLM configured and fast-path did not cover this input",
                "degraded": True,
            }

        try:
            prompt = f"{self.system_prompt}\n\nUser: {text}"
            tool_call = self.inference_backend.generate_json(prompt, self.grammar_path)
        except Exception as e:
            return {
                "success": False,
                "layer": "llm-fallback",
                "error": f"LLM generation failed: {e}",
                "degraded": True,
            }

        action = tool_call.get("action")
        params = tool_call.get("parameters", {})
        if action is None:
            return {
                "success": False,
                "layer": "llm-fallback",
                "error": "LLM output missing 'action' field",
                "degraded": True,
            }

        return self._dispatch(action, params, layer="llm-fallback")
