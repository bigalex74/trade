#!/usr/bin/env python3
from __future__ import annotations

import math
import os
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

def _decimal(value: Any, default: str = "0.0") -> Decimal:
    if value is None:
        return Decimal(default)
    try:
        # Чистим строку от возможных запятых и лишних пробелов
        s = str(value).replace(',', '.').strip()
        return Decimal(s)
    except (ValueError, TypeError, InvalidOperation):
        return Decimal(default)

def _int(value: Any, default: int = 0) -> int:
    if value is None:
        return default
    try:
        return int(float(value))
    except Exception:
        return default

def _env_decimal(name: str, default: str) -> Decimal:
    return _decimal(os.getenv(name), default)

def _env_int(name: str, default: int) -> int:
    return _int(os.getenv(name), default)

@dataclass(frozen=True)
class RiskSettings:
    default_trade_fraction: Decimal = Decimal("0.10")
    default_sell_fraction: Decimal = Decimal("0.25")
    max_symbol_exposure_pct: Decimal = Decimal("0.25")
    max_gross_exposure_pct: Decimal = Decimal("0.80")
    atr_risk_pct: Decimal = Decimal("0.01")
    commission_bps: Decimal = Decimal("5.0")
    limit_buffer_bps: Decimal = Decimal("8.0")
    min_order_value: Decimal = Decimal("100.0")
    max_actions_per_decision: int = 3
    max_actions_per_trader_day: int = 8
    max_pending_orders_per_trader: int = 6
    cooldown_losses: int = 3
    cooldown_minutes: int = 120

    @classmethod
    def from_env(cls) -> "RiskSettings":
        return cls(
            default_trade_fraction=_env_decimal("RISK_DEFAULT_TRADE_FRACTION", str(cls.default_trade_fraction)),
            default_sell_fraction=_env_decimal("RISK_DEFAULT_SELL_FRACTION", str(cls.default_sell_fraction)),
            max_symbol_exposure_pct=_env_decimal("RISK_MAX_SYMBOL_EXPOSURE_PCT", str(cls.max_symbol_exposure_pct)),
            max_gross_exposure_pct=_env_decimal("RISK_MAX_GROSS_EXPOSURE_PCT", str(cls.max_gross_exposure_pct)),
            atr_risk_pct=_env_decimal("RISK_ATR_RISK_PCT", str(cls.atr_risk_pct)),
            commission_bps=_env_decimal("RISK_COMMISSION_BPS", str(cls.commission_bps)),
            limit_buffer_bps=_env_decimal("RISK_LIMIT_BUFFER_BPS", str(cls.limit_buffer_bps)),
            min_order_value=_env_decimal("RISK_MIN_ORDER_VALUE", str(cls.min_order_value)),
            max_actions_per_decision=_env_int("RISK_MAX_ACTIONS_PER_DECISION", cls.max_actions_per_decision),
            max_actions_per_trader_day=_env_int("RISK_MAX_ACTIONS_PER_TRADER_DAY", cls.max_actions_per_trader_day),
            max_pending_orders_per_trader=_env_int("RISK_MAX_PENDING_ORDERS_PER_TRADER", cls.max_pending_orders_per_trader),
            cooldown_losses=_env_int("RISK_COOLDOWN_LOSSES", cls.cooldown_losses),
            cooldown_minutes=_env_int("RISK_COOLDOWN_MINUTES", cls.cooldown_minutes),
        )

def normalize_prices(snaps: dict[str, Any], market_features: dict[str, dict[str, Any]] | None = None) -> dict[str, Decimal]:
    prices: dict[str, Decimal] = {}
    for secid, value in (snaps or {}).items():
        if isinstance(value, dict):
            price = _decimal(value.get("price") or value.get("p"))
        else:
            price = _decimal(value)
        if price > 0:
            prices[str(secid).upper()] = price
    for secid, value in (market_features or {}).items():
        price = _decimal((value or {}).get("p"))
        if price > 0 and str(secid).upper() not in prices:
            prices[str(secid).upper()] = price
    return prices

def _loss_streak(cur, trader_name: str, settings: RiskSettings) -> tuple[int, datetime | None]:
    if settings.cooldown_losses <= 0:
        return 0, None
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

def load_risk_state(conn, trader_name: str, prices: dict[str, Decimal], settings: RiskSettings) -> dict[str, Any]:
    cur = conn.cursor()
    
    cur.execute("SELECT cash_balance FROM trading.portfolio WHERE trader_name = %s", (trader_name,))
    row = cur.fetchone()
    cash = _decimal(row[0]) if row else Decimal("0.0")

    cur.execute("SELECT secid, quantity, avg_entry_price FROM trading.position WHERE trader_name = %s", (trader_name,))
    positions = {}
    for r in cur.fetchall():
        positions[r[0]] = {"quantity": _int(r[1]), "avg_entry_price": _decimal(r[2])}

    cur.execute("""
        SELECT order_type, quantity, target_price, secid
        FROM trading.orders
        WHERE trader_name = %s AND status = 'PENDING'
    """, (trader_name,))
    pending_orders = []
    pending_buy_value = Decimal("0.0")
    pending_sell_qty = {}
    for r in cur.fetchall():
        otype, qty, price, secid = r[0], _int(r[1]), _decimal(r[2]), r[3]
        pending_orders.append({"type": otype, "qty": qty, "price": price, "secid": secid})
        if "buy" in otype.lower():
            pending_buy_value += qty * price
        elif "sell" in otype.lower():
            pending_sell_qty[secid] = pending_sell_qty.get(secid, 0) + qty

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
    day_action_count = filled_today + pending_count

    streak, last_at = _loss_streak(cur, trader_name, settings)
    cur.close()

    position_values = {
        sid: data["quantity"] * (prices.get(sid) or data["avg_entry_price"])
        for sid, data in positions.items()
    }
    positions_total = sum(position_values.values(), Decimal("0.0"))
    equity = cash + positions_total
    gross_exposure = sum((abs(v) for v in position_values.values()), Decimal("0.0")) + pending_buy_value
    available_cash = max(Decimal("0.0"), cash - pending_buy_value)

    cooldown_active = False
    if last_at and streak >= settings.cooldown_losses:
        if last_at.tzinfo is None:
            last_at = last_at.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - last_at).total_seconds() / 60
        cooldown_active = age <= settings.cooldown_minutes

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
        "loss_streak": streak,
        "cooldown_active": cooldown_active,
    }

def _base_candidate(action: dict, state: dict, prices: dict, features: dict, settings: RiskSettings, risk_mult: Decimal) -> tuple[dict | None, str | None]:
    secid = str(action.get("secid", "")).upper()
    act_type = str(action.get("action", "")).lower()
    price = prices.get(secid)
    if not price: return None, "missing_market_price"

    m_feat = features.get(secid, {})
    # ATR Risk Check
    atr_pct = _decimal(m_feat.get("atr_pct", "2.0"))
    if atr_pct > 0 and act_type == "buy":
        if atr_pct > settings.atr_risk_pct * 500: # 5% hard limit
            return None, "volatility_too_high"
            
    # Sentiment Risk
    sent = _decimal(m_feat.get("sent_score", "0.0"))
    if act_type == "buy" and sent < Decimal("-0.5"):
        return None, "negative_sentiment_risk"

    equity = state["equity"]
    # Лимит на 1 символ
    current_sym_val = state["position_values"].get(secid, Decimal("0.0"))
    max_sym_val = equity * settings.max_symbol_exposure_pct
    
    # Лимит на общее плечо
    max_gross = equity * settings.max_gross_exposure_pct
    room_gross = max_gross - state["gross_exposure"]
    
    if act_type == "buy":
        if state["day_action_count"] >= settings.max_actions_per_trader_day:
            return None, "max_actions_per_trader_day"
            
        room_sym = max_sym_val - current_sym_val
        budget = min(room_sym, room_gross, state["available_cash"], equity * settings.default_trade_fraction * risk_mult)
        
        if budget < settings.min_order_value:
            return None, "order_value_below_min_or_no_risk_room"
            
        qty = int(budget / (price * (Decimal("1.0") + settings.limit_buffer_bps / Decimal("10000.0"))))
        if qty < 1: return None, "quantity_below_one"
        
        return {
            "secid": secid, "order_type": "buy", "quantity": qty, 
            "target_price": (price * (Decimal("1.0") + settings.limit_buffer_bps / Decimal("10000.0"))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
            "reason": action.get("reason", "AI Signal")
        }, None

    if act_type in ["sell", "close", "reduce"]:
        pos = state["positions"].get(secid)
        if not pos or pos["quantity"] <= 0:
            return None, "no_available_position_to_sell"
            
        pending_sell = state["pending_sell_qty"].get(secid, 0)
        avail_qty = pos["quantity"] - pending_sell
        if avail_qty <= 0: return None, "all_position_already_in_pending_sell"
        
        qty = avail_qty if act_type in ["sell", "close"] else max(1, int(Decimal(str(avail_qty)) * settings.default_sell_fraction))
        
        return {
            "secid": secid, "order_type": "sell", "quantity": qty,
            "target_price": (price * (Decimal("1.0") - settings.limit_buffer_bps / Decimal("10000.0"))).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP),
            "reason": action.get("reason", "AI Signal")
        }, None

    return None, "unsupported_action_type"

def review_actions(conn, trader_name: str, actions: list[dict], snaps: dict, features: dict, settings: RiskSettings = None) -> dict:
    if settings is None: settings = RiskSettings.from_env()
    prices = normalize_prices(snaps, features)
    state = load_risk_state(conn, trader_name, prices, settings)
    
    if state["cooldown_active"]:
        return {"accepted": [], "rejected": [{"action": a, "reason": "trader_cooldown_active"} for a in actions], "state": state}

    # Множитель риска от режима рынка (упрощенно)
    risk_mult = Decimal("1.0")
    
    accepted = []
    rejected = []
    
    for act in actions[:settings.max_actions_per_decision]:
        cand, reason = _base_candidate(act, state, prices, features, settings, risk_mult)
        if cand:
            accepted.append(cand)
            # Обновляем временное состояние для следующего действия в пачке
            qty = cand["quantity"]
            px = cand["target_price"]
            if cand["order_type"] == "buy":
                val = qty * px
                state["available_cash"] -= val
                state["gross_exposure"] += val
                state["position_values"][cand["secid"]] = state["position_values"].get(cand["secid"], Decimal("0.0")) + val
                state["day_action_count"] += 1
            else:
                state["day_action_count"] += 1
        else:
            rejected.append({"action": act, "reason": reason})
            
    return {"accepted": accepted, "rejected": rejected, "state": state}
