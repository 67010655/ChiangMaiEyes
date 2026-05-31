from typing import Any


def repair_thai_mojibake(value: str) -> str:
    try:
        return value.encode("cp874").decode("utf-8")
    except UnicodeError:
        return value


def repair_thai_mojibake_tree(value: Any) -> Any:
    if isinstance(value, str):
        return repair_thai_mojibake(value)
    if isinstance(value, list):
        return [repair_thai_mojibake_tree(item) for item in value]
    if isinstance(value, dict):
        return {key: repair_thai_mojibake_tree(item) for key, item in value.items()}
    return value
