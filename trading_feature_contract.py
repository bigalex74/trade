#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any


DEFAULT_MAX_SYMBOLS = int(os.getenv("AI_TRADER_MAX_SYMBOLS", "12"))

FAST_MOVE_TRADERS = {
    "Scalper_Kesha",
    "PriceAction_Nikita",
    "VSA_Victor",
    "Contrarian_Ricardo",
    "Chaos_Bill",
    "Quant_Diana",
}

SLOW_LIQUIDITY_TRADERS = {
    "Passive_Palych",
    "Value_Monya",
    "Index_Tracker",
}

AGENT_FIELDS = {
    "VSA_Victor": {
        "base", "flow", "levels", "vsa",
    },
    "Chaos_Bill": {
        "base", "flow", "chaos", "volatility",
    },
    "Elliott_Alex": {
        "base", "trend", "levels", "momentum",
    },
    "Contrarian_Ricardo": {
        "base", "reversion", "levels", "volatility",
    },
    "Quant_Diana": {
        "base", "trend", "momentum", "volatility", "liquidity",
    },
    "PriceAction_Nikita": {
        "base", "price_action", "levels", "flow",
    },
    "Passive_Palych": {
        "base", "slow_trend", "liquidity",
    },
    "Scalper_Kesha": {
        "base", "flow", "price_action", "liquidity",
    },
    "Value_Monya": {
        "base", "slow_trend", "liquidity",
    },
    "Index_Tracker": {
        "base", "trend", "liquidity",
    },
    "Meta_Oracle": {
        "base", "trend", "flow", "levels", "volatility", "liquidity",
    },
}


def _round(value: Any, digits: int = 3):
    if value is None:
        return None
    try:
        return round(float(value), digits)
    except Exception:
        return value


def _number(value: Any):
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _window(item: dict[str, Any], key: str) -> dict[str, Any]:
    value = (item.get("windows") or {}).get(key) or {}
    return value if isinstance(value, dict) else {}


def _indicators(item: dict[str, Any], *window_keys: str) -> dict[str, Any]:
    for key in window_keys:
        indicators = _window(item, key).get("indicators")
        if isinstance(indicators, dict) and indicators:
            return indicators
    return {}


def _indicator(indicators: dict[str, Any], prefixes: tuple[str, ...]):
    for key, value in indicators.items():
        if any(str(key).startswith(prefix) for prefix in prefixes):
            return _number(value)
    return None


def _pct_change(last: Any, first: Any):
    last_n = _number(last)
    first_n = _number(first)
    if first_n in (None, 0) or last_n is None:
        return None
    return ((last_n / first_n) - 1) * 100


def _age_seconds(updated_at: str | None):
    if not updated_at:
        return None
    try:
        value = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return max(0, int((datetime.now(timezone.utc) - value.astimezone(timezone.utc)).total_seconds()))
    except Exception:
        return None


def _close_location(window: dict[str, Any]):
    high = _number(window.get("high"))
    low = _number(window.get("low"))
    close = _number(window.get("close"))
    if high is None or low is None or close is None or high == low:
        return None
    return ((close - low) / (high - low)) * 100


def _range_pct(window: dict[str, Any]):
    high = _number(window.get("high"))
    low = _number(window.get("low"))
    close = _number(window.get("close"))
    if high is None or low is None or close in (None, 0):
        return None
    return ((high - low) / close) * 100


def _body_pct(window: dict[str, Any]):
    open_ = _number(window.get("open"))
    close = _number(window.get("close"))
    if open_ in (None, 0) or close is None:
        return None
    return ((close - open_) / open_) * 100


def _volume_ratio(current: dict[str, Any], previous: dict[str, Any]):
    current_volume = _number(current.get("volume"))
    previous_volume = _number(previous.get("volume"))
    if current_volume is None or previous_volume in (None, 0):
        return None
    return current_volume / previous_volume


def _trend_state(item: dict[str, Any], indicators: dict[str, Any]):
    price = _number(item.get("price"))
    sma20 = _indicator(indicators, ("SMA_20",))
    sma50 = _indicator(indicators, ("SMA_50",))
    adx = _indicator(indicators, ("ADX",))
    chop = _indicator(indicators, ("CHOP",))
    day_change = _number(item.get("day_change"))

    if day_change is not None and day_change <= -3:
        return "panic"
    if chop is not None and chop >= 60:
        return "range"
    if price is not None and sma20 is not None and sma50 is not None:
        if price > sma20 > sma50 and (adx is None or adx >= 18):
            return "trend_up"
        if price < sma20 < sma50 and (adx is None or adx >= 18):
            return "trend_down"
    return "mixed"


def _liquidity_bucket(day_window: dict[str, Any]):
    value = _number(day_window.get("value"))
    if value is None:
        return "unknown"
    if value >= 1_000_000_000:
        return "high"
    if value >= 200_000_000:
        return "medium"
    return "low"


def _vwap_distance_pct(price: Any, indicators: dict[str, Any]):
    price_n = _number(price)
    vwap = _indicator(indicators, ("VWAP",))
    if price_n in (None, 0) or vwap is None:
        return None
    return ((price_n / vwap) - 1) * 100


def _atr_pct(price: Any, indicators: dict[str, Any]):
    price_n = _number(price)
    atr = _indicator(indicators, ("ATR", "ATRr"))
    if price_n in (None, 0) or atr is None:
        return None
    return (atr / price_n) * 100


def build_symbol_features(secid: str, item: dict[str, Any], trader_name: str | None = None) -> dict[str, Any]:
    current_5m = _window(item, "current_5m")
    previous_5m = _window(item, "previous_5m")
    current_hour = _window(item, "current_hour")
    previous_hour = _window(item, "previous_hour")
    current_day = _window(item, "current_day")
    previous_day = _window(item, "previous_day")
    year_window = _window(item, "year")
    indicators = _indicators(item, "current_5m", "current_hour", "current_day", "year")
    field_groups = AGENT_FIELDS.get(trader_name or "", AGENT_FIELDS["Meta_Oracle"])
    price = item.get("price")

    features: dict[str, Any] = {
        "p": _round(price, 4),
        "ch5": _round(item.get("five_min_change"), 3),
        "ch1h": _round(item.get("hour_change"), 3),
        "ch1d": _round(item.get("day_change"), 3),
        "age_s": _age_seconds(item.get("updated_at")),
    }

    if "base" in field_groups:
        features.update({
            "trend": _trend_state(item, indicators),
            "issuer": item.get("issuer_name"),
        })

    if "flow" in field_groups:
        features.update({
            "vol5r": _round(_volume_ratio(current_5m, previous_5m), 3),
            "vol1hr": _round(_volume_ratio(current_hour, previous_hour), 3),
            "vwap_dist": _round(_vwap_distance_pct(price, indicators), 3),
        })

    if "vsa" in field_groups:
        features.update({
            "spread5": _round(_range_pct(current_5m), 3),
            "close_loc5": _round(_close_location(current_5m), 2),
            "body5": _round(_body_pct(current_5m), 3),
        })

    if "trend" in field_groups or "momentum" in field_groups:
        features.update({
            "rsi": _round(_indicator(indicators, ("RSI",)), 2),
            "macdh": _round(_indicator(indicators, ("MACDh",)), 4),
            "adx": _round(_indicator(indicators, ("ADX",)), 2),
            "chop": _round(_indicator(indicators, ("CHOP",)), 2),
        })

    if "chaos" in field_groups:
        features.update({
            "jaw": _round(_indicator(indicators, ("AL_JAW",)), 4),
            "teeth": _round(_indicator(indicators, ("AL_TEETH",)), 4),
            "lips": _round(_indicator(indicators, ("AL_LIPS",)), 4),
            "fr_up": bool(indicators.get("fractal_up")) if "fractal_up" in indicators else None,
            "fr_dn": bool(indicators.get("fractal_down")) if "fractal_down" in indicators else None,
        })

    if "reversion" in field_groups:
        features.update({
            "rsi": _round(_indicator(indicators, ("RSI",)), 2),
            "bbp": _round(_indicator(indicators, ("BBP",)), 3),
            "vwap_dist": _round(_vwap_distance_pct(price, indicators), 3),
        })

    if "price_action" in field_groups:
        features.update({
            "range5": _round(_range_pct(current_5m), 3),
            "range1d": _round(_range_pct(current_day), 3),
            "body5": _round(_body_pct(current_5m), 3),
            "body1d": _round(_body_pct(current_day), 3),
            "close_loc5": _round(_close_location(current_5m), 2),
        })

    if "levels" in field_groups:
        features.update({
            "day_hi": _round(current_day.get("high"), 4),
            "day_lo": _round(current_day.get("low"), 4),
            "prev_hi": _round(previous_day.get("high"), 4),
            "prev_lo": _round(previous_day.get("low"), 4),
            "prev_close": _round(previous_day.get("close"), 4),
        })

    if "volatility" in field_groups:
        features.update({
            "atr_pct": _round(_atr_pct(price, indicators), 3),
            "range1d": _round(_range_pct(current_day), 3),
        })

    if "liquidity" in field_groups:
        features.update({
            "liq": _liquidity_bucket(current_day),
            "day_value_m": _round((_number(current_day.get("value")) or 0) / 1_000_000, 1),
        })

    if "slow_trend" in field_groups:
        features.update({
            "week_ch": _round(_window(item, "current_week").get("change_pct"), 3),
            "month_ch": _round(_window(item, "current_month").get("change_pct"), 3),
            "year_ch": _round(year_window.get("change_pct"), 3),
        })

    return {key: value for key, value in features.items() if value is not None}


def _symbol_priority(item: dict[str, Any]):
    current_day = _window(item, "current_day")
    value = _number(current_day.get("value")) or 0
    move = max(
        abs(_number(item.get("five_min_change")) or 0),
        abs(_number(item.get("hour_change")) or 0),
        abs(_number(item.get("day_change")) or 0),
    )
    return (value, move)


def _move_priority(item: dict[str, Any], trader_name: str):
    current_day = _window(item, "current_day")
    value = _number(current_day.get("value")) or 0
    five = abs(_number(item.get("five_min_change")) or 0)
    hour = abs(_number(item.get("hour_change")) or 0)
    day = abs(_number(item.get("day_change")) or 0)
    if trader_name in FAST_MOVE_TRADERS:
        move = five * 4.0 + hour * 2.0 + day * 0.5
    elif trader_name in SLOW_LIQUIDITY_TRADERS:
        move = five * 0.25 + hour * 0.5 + day * 2.0
    else:
        move = five * 2.0 + hour + day
    return (move, value)


def _selection_slots(trader_name: str, max_symbols: int):
    if trader_name in FAST_MOVE_TRADERS:
        move_slots = max(1, int(round(max_symbols * 0.67)))
    elif trader_name in SLOW_LIQUIDITY_TRADERS:
        move_slots = max(1, int(round(max_symbols * 0.34)))
    else:
        move_slots = max(1, int(round(max_symbols * 0.50)))
    return min(max_symbols, move_slots)


def _mixed_symbol_selection(candidates, trader_name: str, max_symbols: int):
    move_slots = _selection_slots(trader_name, max_symbols)
    by_move = sorted(candidates, key=lambda pair: _move_priority(pair[1], trader_name), reverse=True)
    by_liquidity = sorted(candidates, key=lambda pair: _symbol_priority(pair[1]), reverse=True)
    selected = []
    seen = set()

    def add(pair):
        secid, _ = pair
        if secid in seen or len(selected) >= max_symbols:
            return
        selected.append(pair)
        seen.add(secid)

    for pair in by_move:
        if len(selected) >= move_slots:
            break
        add(pair)
    for pair in by_liquidity:
        add(pair)
    return selected


def build_trader_market_payload(
    context: dict[str, dict[str, Any]],
    trader_name: str,
    max_symbols: int | None = None,
) -> dict[str, dict[str, Any]]:
    max_symbols = max_symbols or DEFAULT_MAX_SYMBOLS
    candidates = [
        (secid, item)
        for secid, item in context.items()
        if item.get("price") is not None
    ]
    selected = _mixed_symbol_selection(candidates, trader_name, max_symbols)
    return {
        secid: build_symbol_features(secid, item, trader_name)
        for secid, item in selected
    }


def payload_stats(payload: dict[str, Any]) -> dict[str, Any]:
    import json

    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return {
        "symbols": len(payload),
        "chars": len(text),
        "avg_chars_per_symbol": round(len(text) / max(1, len(payload)), 1),
    }
