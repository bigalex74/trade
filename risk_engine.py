#!/usr/bin/env python3
from __future__ import annotations

import math
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def _float(value: Any, default: float = 0.0) -> float:
    if value is None:
        return default
    try:
        return float(value)
    except Exception:
        return default


def _int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    return _float(os.getenv(name), default)


def _env_int(name: str, default: int) -> int:
    return _int(os.getenv(name), default)


@dataclass(frozen=True)
class RiskSettings:
    default_trade_fraction: float = 0.10
    default_sell_fraction: float = 0.25
    max_symbol_exposure_pct: float = 0.25
    max_gross_exposure_pct: float = 0.80
    atr_risk_pct: float = 0.01
    commission_bps: float = 5.0
    limit_buffer_bps: float = 8.0
    min_order_value: float = 100.0
    max_actions_per_decision: int = 3
    max_actions_per_trader_day: int = 8
    max_pending_orders_per_trader: int = 6
    cooldown_losses: int = 3
    cooldown_minutes: int = 120

    @classmethod
    def from_env(cls) -> "RiskSettings":
        return cls(
            default_trade_fraction=_env_float("RISK_DEFAULT_TRADE_FRACTION", cls.default_trade_fraction),
            default_sell_fraction=_env_float("RISK_DEFAULT_SELL_FRACTION", cls.default_sell_fraction),
            max_symbol_exposure_pct=_env_float("RISK_MAX_SYMBOL_EXPOSURE_PCT", cls.max_symbol_exposure_pct),
            max_gross_exposure_pct=_env_float("RISK_MAX_GROSS_EXPOSURE_PCT", cls.max_gross_exposure_pct),
            atr_risk_pct=_env_float("RISK_ATR_RISK_PCT", cls.atr_risk_pct),
            commission_bps=_env_float("RISK_COMMISSION_BPS", cls.commission_bps),
            limit_buffer_bps=_env_float("RISK_LIMIT_BUFFER_BPS", cls.limit_buffer_bps),
            min_order_value=_env_float("RISK_MIN_ORDER_VALUE", cls.min_order_value),
            max_actions_per_decision=_env_int("RISK_MAX_ACTIONS_PER_DECISION", cls.max_actions_per_decision),
            max_actions_per_trader_day=_env_int("RISK_MAX_ACTIONS_PER_TRADER_DAY", cls.max_actions_per_trader_day),
            max_pending_orders_per_trader=_env_int("RISK_MAX_PENDING_ORDERS_PER_TRADER", cls.max_pending_orders_per_trader),
            cooldown_losses=_env_int("RISK_COOLDOWN_LOSSES", cls.cooldown_losses),
            cooldown_minutes=_env_int("RISK_COOLDOWN_MINUTES", cls.cooldown_minutes),
        )


def normalize_prices(snaps: dict[str, Any], market_features: dict[str, dict[str, Any]] | None = None) -> dict[str, float]:
    prices: dict[str, float] = {}
    for secid, value in (snaps or {}).items():
        if isinstance(value, dict):
            price = _float(value.get("price") or value.get("p"))
        else:
            price = _float(value)
        if price > 0:
            prices[str(secid).upper()] = price
    for secid, value in (market_features or {}).items():
        price = _float((value or {}).get("p"))
        if price > 0 and str(secid).upper() not in prices:
            prices[str(secid).upper()] = price
    return prices


def _loss_streak(cur, trader_name: str, settings: RiskSettings) -> tuple[int, datetime | None]:
    if settings.cooldown_losses <= 0:
        return 0, None
    # Оптимизировано: используем новую колонку is_win и индекс idx_journal_is_win
    cur.execute(
        """
        SELECT is_win, created_at
        FROM trading.journal
        WHERE trader_name = %s
          AND is_win IS NOT NULL
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (trader_name, settings.cooldown_losses),
    )
    rows = cur.fetchall()
    streak = 0
    last_at = None
    for is_win, created_at in rows:
        if is_win:
            break
        streak += 1
        last_at = last_at or created_at
    return streak, last_at


def load_risk_state(conn, trader_name: str, prices: dict[str, float], settings: RiskSettings | None = None) -> dict[str, Any]:
    settings = settings or RiskSettings.from_env()
    cur = conn.cursor()
    cur.execute("SELECT cash_balance FROM trading.portfolio WHERE trader_name = %s", (trader_name,))
    row = cur.fetchone()
    cash = _float(row[0]) if row else 0.0

    cur.execute(
        "SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s AND quantity > 0",
        (trader_name,),
    )
    positions = {
        str(secid).upper(): {
            "quantity": _int(quantity),
            "avg_entry_price": _float(avg_entry_price),
        }
        for secid, quantity, avg_entry_price in cur.fetchall()
    }

    cur.execute(
        """
        SELECT secid, order_type, quantity, target_price
        FROM trading.orders
        WHERE trader_name = %s AND status = 'PENDING'
        """,
        (trader_name,),
    )
    pending_orders = cur.fetchall()
    pending_buy_value = 0.0
    pending_sell_qty: dict[str, int] = {}
    for secid, order_type, quantity, target_price in pending_orders:
        secid = str(secid).upper()
        qty = _int(quantity)
        price = _float(target_price) or prices.get(secid, 0.0)
        if order_type == "limit_buy":
            pending_buy_value += max(0, qty) * max(0.0, price) * (1 + settings.commission_bps / 10000)
        elif order_type in {"limit_sell", "stop_loss"}:
            pending_sell_qty[secid] = pending_sell_qty.get(secid, 0) + max(0, qty)

    cur.execute(
        """
        SELECT count(*)
        FROM trading.journal
        WHERE trader_name = %s
          AND created_at >= CURRENT_DATE
          AND upper(action) IN ('BUY', 'SELL', 'SHORT', 'COVER')
        """,
        (trader_name,),
    )
    filled_today = _int(cur.fetchone()[0])
    pending_count = len(pending_orders)

    # Умный расчет дневной активности:
    # Исключаем из общего лимита попытки, которые не привели к PENDING ордеру (например, отклоненные ИИ-вызовом ранее)
    # day_action_count теперь отражает только РЕАЛЬНОЕ давление на лимит (исполненные + ждущие исполнения)
    day_action_count = filled_today + pending_count

    loss_streak, last_loss_at = _loss_streak(cur, trader_name, settings)
    cur.close()

    position_values = {
        secid: data["quantity"] * (prices.get(secid) or data["avg_entry_price"])
        for secid, data in positions.items()
    }
    positions_value = sum(position_values.values())
    equity = cash + positions_value
    gross_exposure = sum(abs(value) for value in position_values.values()) + pending_buy_value
    available_cash = max(0.0, cash - pending_buy_value)

    cooldown_active = False
    if last_loss_at and loss_streak >= settings.cooldown_losses:
        if last_loss_at.tzinfo is None:
            last_loss_at = last_loss_at.replace(tzinfo=timezone.utc)
        age_minutes = (datetime.now(timezone.utc) - last_loss_at.astimezone(timezone.utc)).total_seconds() / 60
        cooldown_active = age_minutes <= settings.cooldown_minutes

    return {
        "trader_name": trader_name,
        "cash": cash,
        "available_cash": available_cash,
        "positions": positions,
        "position_values": position_values,
        "equity": equity,
        "gross_exposure": gross_exposure,
        "pending_buy_value": pending_buy_value,
        "pending_sell_qty": pending_sell_qty,
        "pending_count": pending_count,
        "filled_today": filled_today,
        "day_action_count": day_action_count,
        "loss_streak": loss_streak,
        "cooldown_active": cooldown_active,
    }


def _requested_quantity(action: dict[str, Any]) -> int | None:
    qty = action.get("quantity", action.get("qty"))
    if qty is None:
        return None
    qty_i = _int(qty)
    return qty_i if qty_i > 0 else None


def _feature(market_features: dict[str, dict[str, Any]], secid: str, name: str) -> float | None:
    value = (market_features.get(secid) or {}).get(name)
    if value is None:
        return None
    number = _float(value)
    return number if number > 0 else None


def _feature_number(market_features: dict[str, dict[str, Any]], secid: str, name: str) -> float | None:
    value = (market_features.get(secid) or {}).get(name)
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _reject(action: dict[str, Any], reason: str) -> dict[str, Any]:
    return {"action": action, "reason": reason}


def _base_candidate(
    action: dict[str, Any],
    state: dict[str, Any],
    prices: dict[str, float],
    market_features: dict[str, dict[str, Any]],
    settings: RiskSettings,
    risk_multiplier: float,
) -> tuple[dict[str, Any] | None, str | None]:
    secid = str(action.get("secid") or "").upper().strip()
    action_name = str(action.get("action") or "").lower().strip()
    if not secid:
        return None, "missing_secid"
    if action_name in {"hold", "wait", "none", "noop"}:
        return None, "hold_no_order"
    if action_name not in {"buy", "sell", "short", "cover"}:
        return None, f"unsupported_action:{action_name}"
    if action_name in {"short", "cover"}:
        return None, "short_book_not_enabled"

    price = prices.get(secid)
    if not price or price <= 0:
        return None, "missing_market_price"

    requested_qty = _requested_quantity(action)
    fee_rate = settings.commission_bps / 10000
    equity = max(_float(state.get("equity")), 1.0)
    original_reason = str(action.get("reason") or "")[:500]

    if action_name == "buy":
        if state.get("cooldown_active"):
            return None, f"cooldown_after_{state.get('loss_streak')}_losses"
        if state["pending_count"] >= settings.max_pending_orders_per_trader:
            return None, "too_many_pending_orders"

        available_cash = _float(state.get("available_cash"))
        budget = min(available_cash, equity * settings.default_trade_fraction * max(0.0, risk_multiplier))
        sent_score = _feature_number(market_features, secid, "sent_score")
        sent_age_h = _feature_number(market_features, secid, "sent_age_h")
        if sent_score is not None and (sent_age_h is None or sent_age_h <= 24):
            if sent_score <= -0.6:
                return None, "negative_sentiment_risk"
            if sent_score <= -0.3:
                budget *= 0.5
        if requested_qty:
            budget = min(budget, requested_qty * price)

        atr_pct = _feature(market_features, secid, "atr_pct")
        if atr_pct:
            risk_per_share = price * (atr_pct / 100)
            if risk_per_share > 0:
                atr_qty = math.floor((equity * settings.atr_risk_pct * max(0.0, risk_multiplier)) / risk_per_share)
                if requested_qty:
                    atr_qty = min(atr_qty, requested_qty)
                budget = min(budget, max(0, atr_qty) * price)

        current_symbol_value = _float(state["position_values"].get(secid))
        symbol_room = equity * settings.max_symbol_exposure_pct - current_symbol_value
        gross_room = equity * settings.max_gross_exposure_pct - _float(state.get("gross_exposure"))
        budget = min(budget, symbol_room, gross_room)
        if budget < settings.min_order_value:
            return None, "order_value_below_min_or_no_risk_room"

        qty = math.floor(budget / (price * (1 + fee_rate)))
        if qty < 1:
            return None, "quantity_below_one"
        notional = qty * price
        target_price = price * (1 + settings.limit_buffer_bps / 10000)
        return {
            "secid": secid,
            "action": "buy",
            "order_type": "limit_buy",
            "quantity": qty,
            "price": round(price, 6),
            "target_price": round(target_price, 6),
            "notional": round(notional, 2),
            "reason": original_reason,
            "risk": {
                "risk_multiplier": risk_multiplier,
                "atr_pct": atr_pct,
                "sent_score": sent_score,
                "commission_bps": settings.commission_bps,
                "limit_buffer_bps": settings.limit_buffer_bps,
            },
        }, None

    held_qty = _int((state["positions"].get(secid) or {}).get("quantity"))
    pending_sell_qty = _int(state["pending_sell_qty"].get(secid))
    available_qty = max(0, held_qty - pending_sell_qty)
    if available_qty < 1:
        return None, "no_available_position_to_sell"
    qty = min(requested_qty or max(1, math.floor(available_qty * settings.default_sell_fraction)), available_qty)
    if qty < 1:
        return None, "quantity_below_one"
    target_price = price * (1 - settings.limit_buffer_bps / 10000)
    return {
        "secid": secid,
        "action": "sell",
        "order_type": "limit_sell",
        "quantity": qty,
        "price": round(price, 6),
        "target_price": round(target_price, 6),
        "notional": round(qty * price, 2),
        "reason": original_reason,
        "risk": {
            "held_qty": held_qty,
            "pending_sell_qty": pending_sell_qty,
            "commission_bps": settings.commission_bps,
            "limit_buffer_bps": settings.limit_buffer_bps,
        },
    }, None


def _apply_candidate(state: dict[str, Any], candidate: dict[str, Any], settings: RiskSettings) -> None:
    secid = candidate["secid"]
    qty = _int(candidate["quantity"])
    price = _float(candidate["price"])
    fee_rate = settings.commission_bps / 10000
    notional = qty * price
    state["pending_count"] += 1
    state["day_action_count"] += 1
    if candidate["action"] == "buy":
        reserved = notional * (1 + fee_rate)
        state["available_cash"] = max(0.0, _float(state["available_cash"]) - reserved)
        state["gross_exposure"] = _float(state["gross_exposure"]) + notional
        state["pending_buy_value"] = _float(state["pending_buy_value"]) + reserved
        return
    state["pending_sell_qty"][secid] = _int(state["pending_sell_qty"].get(secid)) + qty


def review_actions(
    conn,
    trader_name: str,
    actions: list[dict[str, Any]],
    prices: dict[str, Any],
    market_features: dict[str, dict[str, Any]] | None = None,
    risk_multiplier: float = 1.0,
    settings: RiskSettings | None = None,
) -> dict[str, Any]:
    settings = settings or RiskSettings.from_env()
    market_features = market_features or {}
    normalized_prices = normalize_prices(prices, market_features)
    state = load_risk_state(conn, trader_name, normalized_prices, settings)
    working_state = deepcopy(state)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for action in actions or []:
        if len(accepted) >= settings.max_actions_per_decision:
            rejected.append(_reject(action, "max_actions_per_decision"))
            continue
        if working_state["day_action_count"] >= settings.max_actions_per_trader_day:
            rejected.append(_reject(action, "max_actions_per_trader_day"))
            continue

        candidate, reason = _base_candidate(
            action,
            working_state,
            normalized_prices,
            market_features,
            settings,
            risk_multiplier,
        )
        if reason:
            rejected.append(_reject(action, reason))
            continue
        accepted.append(candidate)
        _apply_candidate(working_state, candidate, settings)

    return {
        "accepted": accepted,
        "rejected": rejected,
        "state": {
            "cash": round(state["cash"], 2),
            "available_cash": round(state["available_cash"], 2),
            "equity": round(state["equity"], 2),
            "gross_exposure": round(state["gross_exposure"], 2),
            "pending_count": state["pending_count"],
            "day_action_count": state["day_action_count"],
            "loss_streak": state["loss_streak"],
            "cooldown_active": state["cooldown_active"],
        },
        "settings": {
            "max_actions_per_decision": settings.max_actions_per_decision,
            "max_actions_per_trader_day": settings.max_actions_per_trader_day,
            "max_symbol_exposure_pct": settings.max_symbol_exposure_pct,
            "max_gross_exposure_pct": settings.max_gross_exposure_pct,
        },
    }
