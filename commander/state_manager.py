import os
import yaml
import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from commander.config import LOG_DIR, resolve_path

JST = datetime.timezone(datetime.timedelta(hours=9))

def get_default_state() -> Dict[str, Any]:
    return {
        "version": 1,
        "model": "claude-opus-4-8",
        "phase": "P2",
        "loop_status": "idle",
        "last_action": {
            "type": "none",
            "timestamp": None,
            "result": None,
            "detail": None
        },
        "current_night": None,
        "turn": None,
        "pending_reviews": [],
        "pending_tasks": [],
        "error_count": 0,
        "budget": {
            "llm_calls_today": 0,
            "max_llm_calls_per_day": 24,
            "llm_calls_window": [],
            "max_llm_calls_per_window": 8,
            "wakeups_today": 0,
            "last_reset_date": None
        },
        "stop_reason": None
    }

class StateManager:
    def __init__(self, path: str = "commander/state.yml"):
        """Initialize the StateManager with a given file path."""
        self.path = Path(path)

    def load(self) -> dict:
        """Load state.yml. If it does not exist, return the default structure without creating a file."""
        if not self.path.exists():
            return get_default_state()
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
                return data if data is not None else get_default_state()
        except Exception:
            return get_default_state()

    def save(self, state: dict) -> None:
        """Save the state dictionary to the state file using atomic write."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = self.path.with_name(self.path.name + ".tmp")
        with open(temp_path, "w", encoding="utf-8") as f:
            yaml.dump(state, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
        os.replace(temp_path, self.path)

    def get(self, key: str, default: Any = None) -> Any:
        """Get a value by a dot-notation key (e.g., 'last_action.type')."""
        state = self.load()
        parts = key.split(".")
        current = state
        for part in parts:
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return default
        return current

    def update(self, updates: Dict[str, Any]) -> dict:
        """
        Partially update the state using a dictionary with dot-notation keys.
        Saves the state after updating and returns the updated state.
        Example: update({"loop_status": "reviewing", "last_action.type": "review"})
        """
        state = self.load()
        for key, value in updates.items():
            parts = key.split(".")
            current = state
            for part in parts[:-1]:
                if part not in current or not isinstance(current[part], dict):
                    current[part] = {}
                current = current[part]
            current[parts[-1]] = value
        self.save(state)
        return state

    def record_action(self, action_type: str, result: str, detail: str) -> None:
        """Update last_action with the current time (JST) and save."""
        now_jst = datetime.datetime.now(JST).isoformat()
        self.update({
            "last_action.type": action_type,
            "last_action.timestamp": now_jst,
            "last_action.result": result,
            "last_action.detail": detail
        })

    def record_wakeup(self, note: str = "") -> None:
        """Increment wakeups_today and save, including daily reset logic."""
        self.reset_daily_if_needed()
        wakeups = self.get("budget.wakeups_today", 0)
        self.update({"budget.wakeups_today": wakeups + 1})

    def record_llm_call(self) -> None:
        """Increment llm_calls_today, append current time to llm_calls_window, and save."""
        self.reset_daily_if_needed()
        calls_today = self.get("budget.llm_calls_today", 0)
        window = self.get("budget.llm_calls_window", [])
        now_jst = datetime.datetime.now(JST).isoformat()
        window.append(now_jst)
        self.update({
            "budget.llm_calls_today": calls_today + 1,
            "budget.llm_calls_window": window
        })

    def can_call_llm(self) -> Tuple[bool, Optional[str]]:
        """
        Check if LLM can be called.
        - Removes entries from llm_calls_window older than 5 hours.
        - Checks daily limit.
        - Checks window limit.
        - Checks if stop_reason is non-null.
        Returns (True, None) if allowed, else (False, reason).
        """
        self.reset_daily_if_needed()
        stop_reason = self.get("stop_reason")
        if stop_reason is not None:
            return False, f"stopped: {stop_reason}"

        calls_today = self.get("budget.llm_calls_today", 0)
        max_daily = self.get("budget.max_llm_calls_per_day", 24)
        if calls_today >= max_daily:
            return False, "daily-budget-exceeded"

        window = self.get("budget.llm_calls_window", [])
        now_jst = datetime.datetime.now(JST)
        five_hours_ago = now_jst - datetime.timedelta(hours=5)

        filtered_window = []
        for ts_str in window:
            try:
                ts = datetime.datetime.fromisoformat(ts_str)
                if ts >= five_hours_ago:
                    filtered_window.append(ts_str)
            except ValueError:
                pass

        if len(filtered_window) != len(window):
            self.update({"budget.llm_calls_window": filtered_window})

        max_window = self.get("budget.max_llm_calls_per_window", 8)
        if len(filtered_window) >= max_window:
            return False, "window-budget-exceeded"

        return True, None

    def should_stop(self) -> Tuple[bool, Optional[str]]:
        """
        Evaluate permanent stop conditions.
        - error_count >= 5 -> (True, "consecutive-errors")
        - stop_reason is not null -> (True, stop_reason)
        Returns (False, None) otherwise.
        """
        stop_reason = self.get("stop_reason")
        if stop_reason is not None:
            return True, stop_reason

        error_count = self.get("error_count", 0)
        if error_count >= 5:
            return True, "consecutive-errors"

        return False, None

    def reset_daily_if_needed(self) -> bool:
        """
        Check if the current day (JST) is different from budget.last_reset_date.
        If so, reset llm_calls_today and wakeups_today to 0, update date, and return True.
        Returns False if no reset was needed.
        """
        last_reset = self.get("budget.last_reset_date")
        today_str = datetime.datetime.now(JST).strftime("%Y-%m-%d")

        if last_reset != today_str:
            if last_reset is not None:
                try:
                    state = self.load()
                    log_dir = resolve_path(LOG_DIR)
                    log_dir.mkdir(parents=True, exist_ok=True)
                    snapshot_path = log_dir / f"state-snapshot-{last_reset}.yml"
                    with open(snapshot_path, "w", encoding="utf-8") as f:
                        yaml.dump(state, f, default_flow_style=False, sort_keys=False, allow_unicode=True)
                except Exception:
                    pass

            self.update({
                "budget.llm_calls_today": 0,
                "budget.wakeups_today": 0,
                "budget.last_reset_date": today_str
            })
            return True
        return False

if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(description="State Manager CLI")
    parser.add_argument("--can-call-llm", action="store_true", help="Check if LLM can be called")
    parser.add_argument("--should-stop", action="store_true", help="Check if loop should permanently stop")
    parser.add_argument("--record-wakeup", type=str, nargs="?", const="", help="Record a wakeup event, optionally with a note")
    parser.add_argument("--record-llm-call", action="store_true", help="Record an LLM call")
    parser.add_argument("--get", type=str, help="Get a value from state.yml by key")
    parser.add_argument("--check-turn-due", action="store_true", help="Check if turn is due (turn1 and >= 21:00 JST)")

    args = parser.parse_args()
    manager = StateManager()

    if args.can_call_llm:
        can_call, reason = manager.can_call_llm()
        if can_call:
            print("True")
        else:
            print(f"False|{reason}")

    elif args.should_stop:
        should_stop, reason = manager.should_stop()
        if should_stop:
            print(f"True|{reason}")
        else:
            print("False")

    elif args.record_wakeup is not None:
        manager.record_wakeup(args.record_wakeup)
        print("OK")

    elif args.record_llm_call:
        manager.record_llm_call()
        print("OK")

    elif args.get is not None:
        val = manager.get(args.get)
        if val is None:
            print("")
        elif isinstance(val, bool):
            print(str(val))
        else:
            print(str(val))

    elif args.check_turn_due:
        turn = manager.get("turn")
        now_jst = datetime.datetime.now(JST)
        if turn == "turn1" and now_jst.hour >= 21:
            print("True")
        else:
            print("False")
