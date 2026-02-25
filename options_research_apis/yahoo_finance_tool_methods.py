from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence

import yfinance as yf


@dataclass
class OptionContract:
    """Normalized option data used by the strategy helpers."""

    symbol: str
    expiration: str
    option_type: str  # "call" or "put"
    contract_symbol: str
    strike: float
    last_price: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    implied_volatility: float
    in_the_money: bool
    change: float
    percent_change: float
    last_trade_date: str
    currency: str

    @property
    def mid_price(self) -> float:
        if self.bid > 0 and self.ask > 0:
            return round((self.bid + self.ask) / 2, 4)
        return round(self.last_price, 4)

    @property
    def spread(self) -> float:
        return round(max(self.ask - self.bid, 0.0), 4)

    @property
    def spread_pct_of_mid(self) -> float:
        mid = self.mid_price
        if mid <= 0:
            return 0.0
        return round((self.spread / mid) * 100, 2)


class YahooOptionsTradingScript:
    """
    Options research utility built on yfinance.

    Note: yfinance provides market data only. This script does not place orders.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol.upper().strip()
        self.ticker = yf.Ticker(self.symbol)

    def get_spot_price(self) -> float:
        history = self.ticker.history(period="1d")
        if history.empty:
            raise RuntimeError(f"Could not load spot price for {self.symbol}.")
        return float(history["Close"].iloc[-1])

    def get_expirations(self) -> Sequence[str]:
        expirations = self.ticker.options
        if not expirations:
            raise RuntimeError(f"No listed options found for {self.symbol}.")
        return expirations

    def get_option_chain(self, expiration: str) -> Dict[str, List[OptionContract]]:
        chain = self.ticker.option_chain(expiration)
        return {
            "calls": self._normalize_chain(chain.calls, expiration, "call"),
            "puts": self._normalize_chain(chain.puts, expiration, "put"),
        }

    def get_detailed_chain(
        self,
        expiration: Optional[str] = None,
        option_type: str = "both",
        limit: Optional[int] = None,
        sort_by: str = "open_interest",
        min_open_interest: int = 0,
        min_volume: int = 0,
        min_strike: Optional[float] = None,
        max_strike: Optional[float] = None,
        moneyness: Optional[str] = None,
    ) -> Dict[str, object]:
        expiration = expiration or self.get_expirations()[0]
        spot = self.get_spot_price()
        chain = self.get_option_chain(expiration)
        calls = chain["calls"]
        puts = chain["puts"]

        calls = self._filter_contracts(calls, min_open_interest, min_volume, min_strike, max_strike, spot, moneyness)
        puts = self._filter_contracts(puts, min_open_interest, min_volume, min_strike, max_strike, spot, moneyness)

        detail = {
            "symbol": self.symbol,
            "spot_price": round(spot, 4),
            "expiration": expiration,
            "as_of_utc": datetime.now(timezone.utc).isoformat(),
            "calls": self._contracts_to_details(calls, spot),
            "puts": self._contracts_to_details(puts, spot),
        }

        detail["calls"] = self._sort_contract_details(detail["calls"], sort_by)
        detail["puts"] = self._sort_contract_details(detail["puts"], sort_by)
        if limit is not None:
            detail["calls"] = detail["calls"][:limit]
            detail["puts"] = detail["puts"][:limit]

        if option_type == "call":
            detail["puts"] = []
        elif option_type == "put":
            detail["calls"] = []
        return detail

    def build_long_call_plan(self, expiration: Optional[str] = None) -> Dict[str, float | str]:
        expiration = expiration or self.get_expirations()[0]
        spot = self.get_spot_price()
        contracts = self.get_option_chain(expiration)["calls"]
        contract = self._pick_liquid_near_strike(contracts, target_strike=spot, otm=True)
        if contract is None:
            raise RuntimeError("No liquid call contract found for long-call plan.")
        debit = contract.mid_price
        return {
            "strategy": "long_call",
            "symbol": self.symbol,
            "expiration": expiration,
            "contract_symbol": contract.contract_symbol,
            "strike": contract.strike,
            "entry_debit": round(debit, 4),
            "break_even_at_expiry": round(contract.strike + debit, 4),
            "max_loss": round(debit * 100, 2),
            "max_profit": math.inf,
        }

    def build_long_put_plan(self, expiration: Optional[str] = None) -> Dict[str, float | str]:
        expiration = expiration or self.get_expirations()[0]
        spot = self.get_spot_price()
        contracts = self.get_option_chain(expiration)["puts"]
        contract = self._pick_liquid_near_strike(contracts, target_strike=spot, otm=True)
        if contract is None:
            raise RuntimeError("No liquid put contract found for long-put plan.")
        debit = contract.mid_price
        return {
            "strategy": "long_put",
            "symbol": self.symbol,
            "expiration": expiration,
            "contract_symbol": contract.contract_symbol,
            "strike": contract.strike,
            "entry_debit": round(debit, 4),
            "break_even_at_expiry": round(contract.strike - debit, 4),
            "max_loss": round(debit * 100, 2),
            "max_profit": round((contract.strike - debit) * 100, 2),
        }

    def build_covered_call_plan(self, expiration: Optional[str] = None) -> Dict[str, float | str]:
        expiration = expiration or self.get_expirations()[0]
        spot = self.get_spot_price()
        contracts = self.get_option_chain(expiration)["calls"]
        target_strike = spot * 1.05
        contract = self._pick_liquid_near_strike(contracts, target_strike=target_strike, otm=True)
        if contract is None:
            raise RuntimeError("No liquid call contract found for covered-call plan.")
        credit = contract.mid_price
        return {
            "strategy": "covered_call",
            "symbol": self.symbol,
            "expiration": expiration,
            "contract_symbol": contract.contract_symbol,
            "strike": contract.strike,
            "entry_credit": round(credit, 4),
            "premium_received": round(credit * 100, 2),
            "if_called_away_sale_price": round(contract.strike * 100, 2),
            "downside_buffer_per_share": round(credit, 4),
        }

    @staticmethod
    def _normalize_chain(chain_df, expiration: str, option_type: str) -> List[OptionContract]:
        contracts: List[OptionContract] = []
        for _, row in chain_df.iterrows():
            contracts.append(
                OptionContract(
                    symbol=str(row.get("contractSymbol", ""))[:6] or "",
                    expiration=expiration,
                    option_type=option_type,
                    contract_symbol=str(row.get("contractSymbol", "")),
                    strike=YahooOptionsTradingScript._safe_float(row.get("strike", 0.0)),
                    last_price=YahooOptionsTradingScript._safe_float(row.get("lastPrice", 0.0)),
                    bid=YahooOptionsTradingScript._safe_float(row.get("bid", 0.0)),
                    ask=YahooOptionsTradingScript._safe_float(row.get("ask", 0.0)),
                    volume=YahooOptionsTradingScript._safe_int(row.get("volume", 0)),
                    open_interest=YahooOptionsTradingScript._safe_int(row.get("openInterest", 0)),
                    implied_volatility=YahooOptionsTradingScript._safe_float(
                        row.get("impliedVolatility", 0.0)
                    ),
                    in_the_money=bool(row.get("inTheMoney", False)),
                    change=YahooOptionsTradingScript._safe_float(row.get("change", 0.0)),
                    percent_change=YahooOptionsTradingScript._safe_float(
                        row.get("percentChange", 0.0)
                    ),
                    last_trade_date=YahooOptionsTradingScript._safe_datetime_iso(
                        row.get("lastTradeDate")
                    ),
                    currency=str(row.get("currency", "")),
                )
            )
        return contracts

    @staticmethod
    def _contracts_to_details(contracts: Sequence[OptionContract], spot: float) -> List[Dict[str, object]]:
        details: List[Dict[str, object]] = []
        for c in contracts:
            moneyness_pct = 0.0 if spot <= 0 else round(((spot - c.strike) / spot) * 100, 2)
            if c.option_type == "put":
                moneyness_pct = -moneyness_pct

            details.append(
                {
                    "contract_symbol": c.contract_symbol,
                    "type": c.option_type,
                    "strike": c.strike,
                    "last_price": c.last_price,
                    "bid": c.bid,
                    "ask": c.ask,
                    "mid_price": c.mid_price,
                    "spread": c.spread,
                    "spread_pct_mid": c.spread_pct_of_mid,
                    "volume": c.volume,
                    "open_interest": c.open_interest,
                    "oi_to_volume_ratio": round(
                        c.open_interest / c.volume, 2
                    )
                    if c.volume > 0
                    else math.inf,
                    "implied_volatility": c.implied_volatility,
                    "change": c.change,
                    "percent_change": c.percent_change,
                    "in_the_money": c.in_the_money,
                    "moneyness_pct_from_spot": moneyness_pct,
                    "days_to_expiry": YahooOptionsTradingScript._days_to_expiry(c.expiration),
                    "last_trade_date": c.last_trade_date,
                    "premium_per_share": c.mid_price,
                    "premium_per_contract": round(c.mid_price * 100, 2),
                    "contract_cost_100x_mid": round(c.mid_price * 100, 2),
                    "currency": c.currency,
                }
            )
        return details

    @staticmethod
    def _sort_contract_details(
        rows: List[Dict[str, object]], sort_by: str
    ) -> List[Dict[str, object]]:
        key_map = {
            "open_interest": "open_interest",
            "volume": "volume",
            "strike": "strike",
            "iv": "implied_volatility",
            "spread_pct": "spread_pct_mid",
        }
        selected = key_map.get(sort_by, "open_interest")
        reverse = selected in {"open_interest", "volume", "implied_volatility", "spread_pct_mid"}
        return sorted(rows, key=lambda r: r.get(selected, 0), reverse=reverse)

    @staticmethod
    def _safe_float(value: object) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return 0.0

        if math.isnan(number) or math.isinf(number):
            return 0.0
        return number

    @staticmethod
    def _safe_int(value: object) -> int:
        return int(YahooOptionsTradingScript._safe_float(value))

    @staticmethod
    def _safe_datetime_iso(value: object) -> str:
        if value is None:
            return ""
        if hasattr(value, "to_pydatetime"):
            dt = value.to_pydatetime()
        elif isinstance(value, datetime):
            dt = value
        else:
            try:
                parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
                dt = parsed
            except ValueError:
                return str(value)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    @staticmethod
    def _days_to_expiry(expiration: str) -> int:
        try:
            expiry = datetime.strptime(expiration, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return -1
        now = datetime.now(timezone.utc)
        delta = expiry - now
        return max(delta.days, 0)

    @staticmethod
    def _filter_contracts(
        contracts: Sequence[OptionContract],
        min_open_interest: int = 0,
        min_volume: int = 0,
        min_strike: Optional[float] = None,
        max_strike: Optional[float] = None,
        spot: Optional[float] = None,
        moneyness: Optional[str] = None,
    ) -> List[OptionContract]:
        filtered = []
        for c in contracts:
            if min_open_interest > 0 and c.open_interest < min_open_interest:
                continue
            if min_volume > 0 and c.volume < min_volume:
                continue
            if min_strike is not None and c.strike < min_strike:
                continue
            if max_strike is not None and c.strike > max_strike:
                continue
            if moneyness and spot is not None:
                is_itm = (c.option_type == "call" and c.strike < spot) or (c.option_type == "put" and c.strike > spot)
                if moneyness == "itm" and not is_itm:
                    continue
                if moneyness == "otm" and is_itm:
                    continue
            filtered.append(c)
        return filtered

    @staticmethod
    def _pick_liquid_near_strike(
        contracts: Sequence[OptionContract],
        target_strike: float,
        otm: bool,
    ) -> Optional[OptionContract]:
        filtered = [
            c
            for c in contracts
            if c.open_interest >= 100 and c.volume >= 1 and c.ask > 0
        ]
        if otm:
            if contracts and contracts[0].option_type == "call":
                filtered = [c for c in filtered if c.strike >= target_strike]
            else:
                filtered = [c for c in filtered if c.strike <= target_strike]

        if not filtered:
            return None

        return min(
            filtered,
            key=lambda c: (
                abs(c.strike - target_strike),
                -(c.open_interest + c.volume),
            ),
        )


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Simple options strategy helper using yfinance.")
    parser.add_argument(
        "--symbol",
        default="AAPL",
        help="Ticker symbol, e.g. AAPL (default: AAPL)",
    )
    parser.add_argument(
        "--mode",
        choices=["strategy", "chain"],
        default="chain",
        help="Use 'strategy' for single trade plan or 'chain' for detailed contracts",
    )
    parser.add_argument(
        "--strategy",
        choices=["long_call", "long_put", "covered_call"],
        default="long_call",
        help="Strategy to analyze",
    )
    parser.add_argument(
        "--expiration",
        default=None,
        help="Expiration date in YYYY-MM-DD format. Defaults to nearest expiration.",
    )
    parser.add_argument(
        "--option-type",
        choices=["call", "put", "both"],
        default="both",
        help="When mode=chain, show calls, puts, or both",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="When mode=chain, max contracts per side to print (0 = all)",
    )
    parser.add_argument(
        "--sort-by",
        choices=["open_interest", "volume", "strike", "iv", "spread_pct"],
        default="open_interest",
        help="When mode=chain, sorting field",
    )
    parser.add_argument(
        "--min-oi",
        type=int,
        default=0,
        help="Minimum open interest filter (default: 0 = no filter)",
    )
    parser.add_argument(
        "--min-volume",
        type=int,
        default=0,
        help="Minimum volume filter (default: 0 = no filter)",
    )
    parser.add_argument(
        "--min-strike",
        type=float,
        default=None,
        help="Minimum strike price filter",
    )
    parser.add_argument(
        "--max-strike",
        type=float,
        default=None,
        help="Maximum strike price filter",
    )
    parser.add_argument(
        "--moneyness",
        choices=["itm", "otm", "all"],
        default="all",
        help="Filter by moneyness: itm (in-the-money), otm (out-of-the-money), or all",
    )
    parser.add_argument(
        "--output",
        choices=["pretty", "json"],
        default="pretty",
        help="Output format (default: pretty)",
    )
    return parser.parse_args()


def _print_plan(plan: Dict[str, float | str]) -> None:
    print("=" * 68)
    print(f"Generated: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 68)
    for key, value in plan.items():
        if value == math.inf:
            value = "unlimited"
        print(f"{key:>24}: {value}")


def _print_run_configuration(args: argparse.Namespace) -> None:
    expiration_display = args.expiration if args.expiration else "nearest available"
    limit_display = "all" if args.limit <= 0 else args.limit
    print("=" * 68)
    print("Run Configuration")
    print("=" * 68)
    print(f"{'symbol':>24}: {args.symbol}")
    print(f"{'mode':>24}: {args.mode}")
    print(f"{'strategy':>24}: {args.strategy}")
    print(f"{'expiration':>24}: {expiration_display}")
    print(f"{'option_type':>24}: {args.option_type}")
    print(f"{'limit':>24}: {limit_display}")
    print(f"{'sort_by':>24}: {args.sort_by}")
    print(f"{'min_oi':>24}: {args.min_oi}")
    print(f"{'min_volume':>24}: {args.min_volume}")
    print(f"{'min_strike':>24}: {args.min_strike}")
    print(f"{'max_strike':>24}: {args.max_strike}")
    print(f"{'moneyness':>24}: {args.moneyness}")
    print(f"{'output':>24}: {args.output}")


def _print_chain_details(result: Dict[str, object], args: argparse.Namespace) -> None:
    label_width = 46

    def print_aligned(label: str, value: object) -> None:
        print(f"{label:<{label_width}}: {value}")

    print("=" * 68)
    print(f"Generated: {result.get('as_of_utc')}")
    print("=" * 68)
    print_aligned("symbol", result.get("symbol"))
    print_aligned("spot price", result.get("spot_price"))
    print_aligned("expiration", result.get("expiration"))

    for side in ("calls", "puts"):
        rows = result.get(side, [])
        if not rows:
            continue
        print("\n" + "-" * 68)
        print(f"{side.upper()} ({len(rows)} rows)")
        print("-" * 68)
        for row in rows:
            print_aligned("mode type", args.mode)
            print_aligned("strategy type", args.strategy)
            print_aligned("position type", "long_or_short")
            print_aligned("option type", row["type"])
            print_aligned("contract symbol", row["contract_symbol"])
            print_aligned("strike", row["strike"])
            print_aligned("mid price", row["mid_price"])
            print_aligned("spread", row["spread"])
            print_aligned("spread percentage of mid price", f"{row['spread_pct_mid']}%")
            print_aligned("bid", row["bid"])
            print_aligned("ask", row["ask"])
            print_aligned("last traded price", row["last_price"])
            print_aligned("open interest", row["open_interest"])
            print_aligned("volume", row["volume"])
            print_aligned("open interest to volume ratio", row["oi_to_volume_ratio"])
            print_aligned("implied volatility", row["implied_volatility"])
            print_aligned("change", row["change"])
            print_aligned("percentage change", row["percent_change"])
            print_aligned("in the money", row["in_the_money"])
            print_aligned("moneyness percentage from spot", row["moneyness_pct_from_spot"])
            print_aligned("days to expiry", row["days_to_expiry"])
            print_aligned("last traded date", row["last_trade_date"])
            print_aligned("premium per share", row["premium_per_share"])
            print_aligned("premium per contract", row["premium_per_contract"])
            print_aligned(
                "one hundred share contract cost at mid price",
                row["contract_cost_100x_mid"],
            )
            print_aligned("currency", row["currency"])
            print("-" * 68)


def main() -> None:
    args = _parse_args()
    script = YahooOptionsTradingScript(args.symbol)
    # _print_run_configuration(args)
    print()

    if args.mode == "chain":
        selected_limit = None if args.limit <= 0 else args.limit
        moneyness = None if args.moneyness == "all" else args.moneyness
        chain_details = script.get_detailed_chain(
            expiration=args.expiration,
            option_type=args.option_type,
            limit=selected_limit,
            sort_by=args.sort_by,
            min_open_interest=args.min_oi,
            min_volume=args.min_volume,
            min_strike=args.min_strike,
            max_strike=args.max_strike,
            moneyness=moneyness,
        )
        if args.output == "json":
            print(json.dumps(chain_details, indent=2, default=str))
        else:
            _print_chain_details(chain_details, args)
    else:
        if args.strategy == "long_call":
            plan = script.build_long_call_plan(args.expiration)
        elif args.strategy == "long_put":
            plan = script.build_long_put_plan(args.expiration)
        else:
            plan = script.build_covered_call_plan(args.expiration)
        if args.output == "json":
            print(json.dumps(plan, indent=2, default=str))
        else:
            _print_plan(plan)


if __name__ == "__main__":
    main()
