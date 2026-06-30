"""Prompt for market alert generation."""

from typing import Any, Dict, Optional


PROMPT_VERSION = "market_alert@2026-06-30"
TASK_NAME = "market_alert"
TASK_SYSTEM_PROMPT = "Tugas: buat alert pasar yang ringkas, hati-hati, dan tidak bersifat rekomendasi transaksi."


def validate_input(input_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not input_data:
        return {"type": "missing_input", "message": "input_data is required.", "retryable": False}
    return None


def build_user_payload(input_data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "task": "Buat market alert.",
        "market_data": input_data.get("market_data") or input_data,
        "output_constraints": {
            "no_buy_sell_instruction": True,
            "no_take_profit_stop_loss": True,
            "no_profit_promise": True,
        },
    }
