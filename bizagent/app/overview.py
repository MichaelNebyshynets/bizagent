"""Сводка для дашборда и аналитики. Использует те же обработчики, что и агент, поэтому цифры совпадают с ответами в чате.
Здесь нет FastAPI: функция принимает ToolContext (company_id и роль берутся из токена, как везде)."""
from __future__ import annotations

import calendar
from datetime import date

from .agent import tools as T
from .context import ToolContext


def _shift_month(d: date, months: int) -> date:
    """Первое число месяца, смещённого на months от месяца даты d."""
    idx = d.year * 12 + (d.month - 1) + months
    return date(idx // 12, idx % 12 + 1, 1)


def _pct(cur: float, prev: float) -> float | None:
    return round((cur - prev) / prev * 100, 1) if prev else None


def build_overview(ctx: ToolContext) -> dict:
    today = ctx.today
    m_start = today.replace(day=1)
    p_start = _shift_month(m_start, -1)
    # сравниваем то же число дней: с 1 по сегодняшнее число (но не дальше конца прошлого месяца)
    p_end = p_start.replace(day=min(today.day, calendar.monthrange(p_start.year, p_start.month)[1]))

    cur = T.get_sales_summary(ctx, T.SalesSummaryArgs(date_from=m_start, date_to=today))
    prev = T.get_sales_summary(ctx, T.SalesSummaryArgs(date_from=p_start, date_to=p_end))
    months = T.get_sales_summary(ctx, T.SalesSummaryArgs(date_from=_shift_month(m_start, -11), date_to=today, group_by="month"))

    out = {
        "today": today.isoformat(),
        "currency": "BYN",
        "month": {
            "revenue": cur["revenue"], "orders": cur["orders"], "avg_check": cur["avg_check"],
            "revenue_prev": prev["revenue"], "avg_check_prev": prev["avg_check"],
            "revenue_change_pct": _pct(cur["revenue"], prev["revenue"]),
            "avg_check_change_pct": _pct(cur["avg_check"], prev["avg_check"]),
        },
        "months": months.get("groups", []),
        "top_products": T.get_top_products(
            ctx, T.TopProductsArgs(date_from=_shift_month(m_start, -2), date_to=today, limit=5))["items"],
        "low_stock": T.list_low_stock(ctx, T.LowStockArgs(threshold=5))["products"][:5],
        "slow_movers": T.list_slow_movers(ctx, T.SlowMoversArgs(days=30))["products"][:5],
        "profit": None,
    }
    if ctx.role in ("owner", "accountant"):  # маржа только финансовым ролям, как в get_profit_summary
        p = T.get_profit_summary(ctx, T.Period(date_from=m_start, date_to=today))
        out["profit"] = {
            "gross_profit": p["gross_profit"], "operating_profit": p["operating_profit"],
            "margin_pct": round(p["gross_profit"] / p["revenue"] * 100, 1) if p["revenue"] else None,
        }
    return out
