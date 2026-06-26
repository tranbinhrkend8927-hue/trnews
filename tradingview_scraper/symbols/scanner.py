"""Helpers for TradingView scanner responses."""

from typing import Iterable, List, Mapping


class ScannerResponseMapper:
    """Maps TradingView scanner rows into dictionaries keyed by requested fields."""

    @staticmethod
    def map_rows(rows: Iterable[Mapping], fields: List[str]):
        mapped_rows = []
        for item in rows or []:
            values = item.get("d") or []
            if not values:
                continue

            mapped_item = {"symbol": item.get("s", "")}
            for index, field in enumerate(fields):
                if index < len(values):
                    mapped_item[field] = values[index]

            mapped_rows.append(mapped_item)

        return mapped_rows
