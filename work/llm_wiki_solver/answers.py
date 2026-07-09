from __future__ import annotations

from typing import Any


def normalize_answer(answer: dict[str, Any]) -> dict[str, Any]:
    if "error_msg" in answer:
        return {"error_msg": str(answer["error_msg"])}
    if "count" in answer:
        return {"count": _to_int(answer.get("count"))}
    count_like = {
        key: value
        for key, value in answer.items()
        if key not in {"datas", "source", "target"} and _looks_int(value)
    }
    if len(count_like) == 1 and len(answer) == 1:
        key, value = next(iter(count_like.items()))
        return {key: _to_int(value)}
    if {"source", "target"}.issubset(answer):
        return {
            "source": _normalize_path(str(answer["source"])),
            "target": _normalize_path(str(answer["target"])),
        }
    if "datas" in answer:
        values = answer.get("datas")
        if not isinstance(values, list):
            return {"datas": []}
        normalized = sorted(
            {
                _normalize_path(str(value))
                for value in values
                if str(value).strip()
            }
        )
        return {"datas": normalized}
    return {"datas": []}


def normalize_answers(answers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [normalize_answer(answer) for answer in answers]


def _normalize_path(value: str) -> str:
    return value.replace("\\", "/").strip()


def _looks_int(value: Any) -> bool:
    try:
        int(value)
    except (TypeError, ValueError):
        return False
    return True


def _to_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
