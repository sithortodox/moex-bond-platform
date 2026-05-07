import os
import time
import json
import re
import logging
from datetime import datetime, timedelta

import requests
import psycopg2
import pandas as pd
from psycopg2.extras import execute_values

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("collector")

DB_URL = os.environ.get("DATABASE_URL", "postgresql://moex:moex123@localhost:5432/moex_bonds")
MOEX_API_DELAY = float(os.environ.get("MOEX_API_DELAY", "1.2"))

BOARD_GROUPS = [58, 193, 105, 77, 207, 167, 245]


def get_db_conn():
    return psycopg2.connect(DB_URL)


def _api_get(url: str, retries: int = 3, backoff: int = 60) -> dict | None:
    for attempt in range(retries):
        try:
            time.sleep(MOEX_API_DELAY)
            r = requests.get(url, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            log.warning("API error attempt %d/%d: %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                time.sleep(backoff)
    return None


def fetch_all_bonds() -> list[dict]:
    all_bonds = []
    for bg in BOARD_GROUPS:
        url = (
            f"https://iss.moex.com/iss/engines/stock/markets/bonds/boardgroups/{bg}/securities.json"
            "?iss.dp=comma&iss.meta=off&iss.only=securities,marketdata&"
            "securities.columns=SECID,SECNAME,PREVLEGALCLOSEPRICE,ISIN,FACEVALUE,COUPONVALUE,"
            "COUPONPERCENT,COUPONFREQ,COUPONDATE,MATDATE,ISSUEDATE,EMITENTNAME,LISTYLEVEL&"
            "marketdata.columns=SECID,YIELD,DURATION,VALTODAY,VOLTODAY,NUMTRADES,WAPRICE,ADMITTEDQ"
        )
        log.info("Fetching board group %s: %s", bg, url)
        data = _api_get(url)
        if not data:
            continue

        securities = data.get("securities", {}).get("data", [])
        marketdata = data.get("marketdata", {}).get("data", [])
        md_dict = {m[0]: m for m in marketdata if m}

        for sec in securities:
            secid = sec[0]
            md = md_dict.get(secid)
            if not md:
                continue

            bond = {
                "secid": secid,
                "name": sec[1].replace('"', "").replace("'", "") if sec[1] else None,
                "price_pct": sec[2],
                "isin": sec[3] if len(sec) > 3 else None,
                "current_nominal": sec[4] if len(sec) > 4 else None,
                "coupon_size": sec[5] if len(sec) > 5 else None,
                "current_coupon_pct": sec[6] if len(sec) > 6 else None,
                "coupon_freq": sec[7] if len(sec) > 7 else None,
                "coupon_date_str": str(sec[8]) if len(sec) > 8 and sec[8] else None,
                "maturity_date": str(sec[9]) if len(sec) > 9 and sec[9] else None,
                "issue_date": str(sec[10]) if len(sec) > 10 and sec[10] else None,
                "issuer": sec[11] if len(sec) > 11 else None,
                "board_group": bg,
                "moex_yield": md[1],
                "moex_duration": round(md[2] / 30, 2) if md[2] else None,
                "moex_volume_15d": md[3] if len(md) > 3 else None,
                "moex_price": md[6] if len(md) > 6 else None,
            }

            if md[1] is not None:
                all_bonds.append(bond)

        log.info("Board group %s: %d bonds with yield data", bg, len(securities))

    log.info("Total bonds fetched: %d", len(all_bonds))
    return all_bonds


def enrich_bond_details(bonds: list[dict], max_enrich: int | None = None) -> list[dict]:
    to_enrich = bonds[:max_enrich] if max_enrich else bonds
    for i, bond in enumerate(to_enrich):
        secid = bond.get("secid") or bond.get("isin")
        if not secid:
            continue

        desc_url = (
            f"https://iss.moex.com/iss/securities/{secid}.json"
            "?iss.meta=off&iss.only=description,boards&"
            "description.columns=name,title,value&"
            "boards.columns=secid,boardid,is_primary"
        )
        desc_data = _api_get(desc_url)
        if not desc_data:
            continue

        desc_items = desc_data.get("description", {}).get("data", [])
        desc_map = {item[0]: item[2] for item in desc_items if len(item) > 2}

        bond["nominal_currency"] = desc_map.get("FACEUNIT", None)
        bond["issue_volume_bln"] = None
        if desc_map.get("ISSUESIZEPLACED") and bond.get("current_nominal"):
            try:
                bond["issue_volume_bln"] = round(
                    float(desc_map["ISSUESIZEPLACED"]) * float(bond["current_nominal"]) / 1e9, 2
                )
            except (ValueError, TypeError):
                pass
        bond["is_subordinated"] = "да" if desc_map.get("SUBORDINATED") == "1" else "нет"
        bond["coupon_type"] = desc_map.get("COUPONTYPE", None)
        bond["has_guarantee"] = "да" if desc_map.get("HASGUARANTEES") == "1" else "нет"
        bond["is_qualified"] = "да" if desc_map.get("ISQUALIFIEDINVESTORS") == "1" else "нет"
        bond["borrower_country"] = desc_map.get("EMITENTCOUNTRY", None)
        bond["issuer_type"] = desc_map.get("TYPENAME", None)

        boards = desc_data.get("boards", {}).get("data", [])
        primary_board = next((b[1] for b in boards if b[2] == 1), None)
        bond["board_id"] = primary_board

        if i % 50 == 0:
            log.info("Enriched %d/%d bonds", i + 1, len(to_enrich))

    return bonds


def fetch_volume_15d(secid: str, board_id: str) -> dict:
    if not board_id:
        return {"volume_sum": None, "low_liquid": 1}
    from_date = (datetime.now() - timedelta(days=15)).strftime("%Y-%m-%d")
    url = (
        f"https://iss.moex.com/iss/history/engines/stock/markets/bonds/"
        f"boards/{board_id}/securities/{secid}.json?"
        f"iss.meta=off&iss.only=history&"
        f"history.columns=SECID,TRADEDATE,VOLUME,NUMTRADES&limit=20&from={from_date}"
    )
    data = _api_get(url)
    if not data:
        return {"volume_sum": None, "low_liquid": 1}
    hist = data.get("history", {}).get("data", [])
    volume_sum = sum(h[2] or 0 for h in hist)
    low_liquid = 1 if len(hist) < 6 else 0
    return {"volume_sum": volume_sum, "low_liquid": low_liquid}


def fetch_payments_info(secid: str) -> dict:
    url = (
        f"https://iss.moex.com/iss/statistics/engines/stock/markets/bonds/"
        f"bondization/{secid}.json?iss.meta=off&iss.only=coupons&start=0&limit=100"
    )
    data = _api_get(url)
    if not data:
        return {"payments_known": "неизвестно"}
    coupons = data.get("coupons", {}).get("data", [])
    unknown = sum(1 for c in coupons if c[3] and datetime.strptime(str(c[3]), "%Y-%m-%d") > datetime.now() and c[9] is None)
    return {"payments_known": "да" if unknown == 0 else f"нет ({unknown} неизвестных)"}


def fetch_nkd(secid: str) -> float | None:
    url = (
        f"https://iss.moex.com/iss/engines/stock/markets/bonds/boards/TQCB/"
        f"securities/{secid}.json?iss.meta=off&iss.only=securities&"
        f"securities.columns=SECID,ADMITTEDQ,ACCRUEDINT,YIELD,DURATION"
    )
    data = _api_get(url)
    if not data:
        return None
    rows = data.get("securities", {}).get("data", [])
    if rows and len(rows[0]) > 2:
        return rows[0][2]
    return None


def upsert_bonds(conn, bonds: list[dict]) -> tuple[int, int]:
    inserted = 0
    updated = 0
    cur = conn.cursor()

    for bond in bonds:
        isin = bond.get("isin")
        if not isin:
            continue

        cols = [
            "isin0", "isin", "name", "issuer", "primary_borrower", "borrower_country",
            "nominal_currency", "issue_volume_bln", "current_nominal", "min_lot",
            "price_pct", "nkd", "coupon_size", "current_coupon_pct", "coupon_freq",
            "coupon_type", "is_subordinated", "has_guarantee", "issuer_type",
            "issue_date", "maturity_date", "duration", "ytm", "current_yield",
            "board_group", "board_id", "secid", "moex_yield", "moex_duration",
            "moex_price", "moex_nkd", "moex_volume_15d", "is_qualified",
            "payments_known", "updated_at",
        ]

        vals = [
            _clean_val(bond.get("isin0") or isin, "isin0"),
            _clean_val(isin, "isin"),
            _clean_val(bond.get("name"), "name"),
            _clean_val(bond.get("issuer"), "issuer"),
            _clean_val(bond.get("primary_borrower"), "primary_borrower"),
            _clean_val(bond.get("borrower_country"), "borrower_country"),
            _clean_val(bond.get("nominal_currency"), "nominal_currency"),
            _clean_val(bond.get("issue_volume_bln"), "issue_volume_bln"),
            _clean_val(bond.get("current_nominal"), "current_nominal"),
            _clean_val(bond.get("min_lot"), "min_lot"),
            _clean_val(bond.get("price_pct"), "price_pct"),
            _clean_val(bond.get("nkd"), "nkd"),
            _clean_val(bond.get("coupon_size"), "coupon_size"),
            _clean_val(bond.get("current_coupon_pct"), "current_coupon_pct"),
            _clean_val(bond.get("coupon_freq"), "coupon_freq"),
            _clean_val(bond.get("coupon_type"), "coupon_type"),
            _clean_val(bond.get("is_subordinated"), "is_subordinated"),
            _clean_val(bond.get("has_guarantee"), "has_guarantee"),
            _clean_val(bond.get("issuer_type"), "issuer_type"),
            _clean_val(bond.get("issue_date"), "issue_date"),
            _clean_val(bond.get("maturity_date"), "maturity_date"),
            _clean_val(bond.get("moex_duration"), "moex_duration"),
            _clean_val(bond.get("moex_yield"), "moex_yield"),
            _clean_val(bond.get("current_yield"), "current_yield"),
            _clean_val(bond.get("board_group"), "board_group"),
            _clean_val(bond.get("board_id"), "board_id"),
            _clean_val(bond.get("secid"), "secid"),
            _clean_val(bond.get("moex_yield"), "moex_yield"),
            _clean_val(bond.get("moex_duration"), "moex_duration"),
            _clean_val(bond.get("moex_price"), "moex_price"),
            _clean_val(bond.get("moex_nkd"), "moex_nkd"),
            _clean_val(bond.get("moex_volume_15d"), "moex_volume_15d"),
            _clean_val(bond.get("is_qualified"), "is_qualified"),
            _clean_val(bond.get("payments_known"), "payments_known"),
            datetime.now(),
        ]

        placeholders = ", ".join(["%s"] * len(vals))
        col_str = ", ".join(cols)
        update_str = ", ".join(f"{c}=EXCLUDED.{c}" for c in cols if c not in ("isin",))

        sql = f"""
            INSERT INTO bonds ({col_str})
            VALUES ({placeholders})
            ON CONFLICT (isin) DO UPDATE SET {update_str}
        """
        try:
            cur.execute(sql, vals)
            if cur.rowcount == 1:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            log.error("DB error for ISIN %s: %s", isin, e)
            conn.rollback()

    conn.commit()
    cur.close()
    return inserted, updated


def import_excel_data(xlsx_path: str) -> int:
    log.info("Importing Excel data from %s", xlsx_path)
    df = pd.read_excel(xlsx_path, sheet_name="data", engine="openpyxl")
    df.columns = [
        "isin0", "rating", "industry", "yield_cb", "yield_dohod", "yield_avg",
        "yield_deviation", "yield_category", "liquidity_cb", "liquidity_dohod",
        "liquidity_avg", "liquidity_category", "isin", "name", "issuer",
        "primary_borrower", "borrower_country", "nominal_currency",
        "issue_volume_bln", "nearest_date_str", "years_to_date", "duration",
        "event_at_date", "ytm", "yield_no_reinvest", "reinvest_profit_pct",
        "simple_yield", "current_yield", "credit_quality_rank",
        "credit_quality_num", "issuer_quality", "inside_q", "outside_q",
        "netdebt_equity_rank", "liquidity_ratio", "median_daily_turnover",
        "complexity", "size_rank", "issue_date", "maturity_date",
        "yield_calc_date", "current_nominal", "min_lot", "price_pct", "nkd",
        "coupon_size", "current_coupon_pct", "coupon_freq", "coupon_type",
        "is_subordinated", "has_guarantee", "issuer_type", "base_index_frn",
        "frn_premium_discount",
    ] + [f"extra_{i}" for i in range(len(df.columns) - 54)]

    df = df.dropna(subset=["isin"])
    df = df.where(pd.notnull(df), None)

    conn = get_db_conn()
    inserted, updated = upsert_bonds_from_df(conn, df)
    conn.close()
    log.info("Excel import: %d inserted, %d updated", inserted, updated)
    return inserted + updated


NUMERIC_COLS = {
    "yield_cb", "yield_dohod", "yield_avg", "yield_deviation",
    "liquidity_cb", "liquidity_avg",
    "issue_volume_bln", "years_to_date", "duration",
    "ytm", "yield_no_reinvest", "reinvest_profit_pct",
    "simple_yield", "current_yield",
    "credit_quality_num", "issuer_quality", "inside_q", "outside_q",
    "netdebt_equity_rank", "liquidity_ratio", "median_daily_turnover",
    "complexity", "size_rank",
    "current_nominal", "min_lot", "price_pct", "nkd",
    "coupon_size", "current_coupon_pct", "coupon_freq",
    "frn_premium_discount",
    "board_group", "moex_yield", "moex_duration", "moex_price",
    "moex_nkd", "moex_volume_15d", "g_spread",
}


def _clean_val(val, col: str):
    if val is None or (isinstance(val, float) and str(val) == "nan"):
        return None
    if isinstance(val, str):
        val = val.strip()
        if val in ("-", "", "—", "–", "N/A", "n/a", "null", "NULL", "#N/A", "#VALUE!"):
            return None
        if col in NUMERIC_COLS:
            val = val.replace(",", ".").replace(" ", "").replace("\xa0", "")
            try:
                return float(val)
            except (ValueError, TypeError):
                return None
    return val


def upsert_bonds_from_df(conn, df: pd.DataFrame) -> tuple[int, int]:
    inserted = 0
    updated = 0
    cur = conn.cursor()

    db_cols = [
        "isin0", "rating", "industry", "yield_cb", "yield_dohod", "yield_avg",
        "yield_deviation", "yield_category", "liquidity_cb", "liquidity_dohod",
        "liquidity_avg", "liquidity_category", "isin", "name", "issuer",
        "primary_borrower", "borrower_country", "nominal_currency",
        "issue_volume_bln", "nearest_date_str", "years_to_date", "duration",
        "event_at_date", "ytm", "yield_no_reinvest", "reinvest_profit_pct",
        "simple_yield", "current_yield", "credit_quality_rank",
        "credit_quality_num", "issuer_quality", "inside_q", "outside_q",
        "netdebt_equity_rank", "liquidity_ratio", "median_daily_turnover",
        "complexity", "size_rank", "issue_date", "maturity_date",
        "yield_calc_date", "current_nominal", "min_lot", "price_pct", "nkd",
        "coupon_size", "current_coupon_pct", "coupon_freq", "coupon_type",
        "is_subordinated", "has_guarantee", "issuer_type", "base_index_frn",
        "frn_premium_discount", "updated_at",
    ]

    for _, row in df.iterrows():
        vals = [_clean_val(row.get(c), c) for c in db_cols[:-1]] + [datetime.now()]
        placeholders = ", ".join(["%s"] * len(vals))
        col_str = ", ".join(db_cols)
        update_cols = [c for c in db_cols if c != "isin"]
        update_str = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)

        sql = f"""
            INSERT INTO bonds ({col_str})
            VALUES ({placeholders})
            ON CONFLICT (isin) DO UPDATE SET {update_str}
        """
        try:
            cur.execute(sql, vals)
            if cur.rowcount == 1:
                inserted += 1
            else:
                updated += 1
        except Exception as e:
            log.error("DB error for ISIN %s: %s", row.get("isin"), e)
            conn.rollback()

    conn.commit()
    cur.close()
    return inserted, updated


def run_full_collection(xlsx_path: str | None = None):
    started = datetime.now()
    log.info("=== Starting full collection at %s ===", started)

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO collection_log (status, started_at) VALUES ('running', %s) RETURNING id", (started,))
    log_id = cur.fetchone()[0]
    conn.commit()
    cur.close()

    errors = 0
    total_inserted = 0
    total_updated = 0

    try:
        if xlsx_path and os.path.exists(xlsx_path):
            df = pd.read_excel(xlsx_path, sheet_name="data", engine="openpyxl")
            df.columns = [
                "isin0", "rating", "industry", "yield_cb", "yield_dohod", "yield_avg",
                "yield_deviation", "yield_category", "liquidity_cb", "liquidity_dohod",
                "liquidity_avg", "liquidity_category", "isin", "name", "issuer",
                "primary_borrower", "borrower_country", "nominal_currency",
                "issue_volume_bln", "nearest_date_str", "years_to_date", "duration",
                "event_at_date", "ytm", "yield_no_reinvest", "reinvest_profit_pct",
                "simple_yield", "current_yield", "credit_quality_rank",
                "credit_quality_num", "issuer_quality", "inside_q", "outside_q",
                "netdebt_equity_rank", "liquidity_ratio", "median_daily_turnover",
                "complexity", "size_rank", "issue_date", "maturity_date",
                "yield_calc_date", "current_nominal", "min_lot", "price_pct", "nkd",
                "coupon_size", "current_coupon_pct", "coupon_freq", "coupon_type",
                "is_subordinated", "has_guarantee", "issuer_type", "base_index_frn",
                "frn_premium_discount",
            ] + [f"extra_{i}" for i in range(len(df.columns) - 54)]
            df = df.dropna(subset=["isin"])
            df = df.where(pd.notnull(df), None)
            ins, upd = upsert_bonds_from_df(conn, df)
            total_inserted += ins
            total_updated += upd
            log.info("Excel import: %d inserted, %d updated", ins, upd)

        bonds = fetch_all_bonds()
        log.info("Fetched %d bonds from MOEX API", len(bonds))

        bonds = enrich_bond_details(bonds, max_enrich=500)

        for bond in bonds:
            board_id = bond.get("board_id")
            secid = bond.get("secid")
            if board_id and secid:
                vol_info = fetch_volume_15d(secid, board_id)
                bond["moex_volume_15d"] = vol_info["volume_sum"]

            if secid:
                nkd_val = fetch_nkd(secid)
                bond["moex_nkd"] = nkd_val

        ins, upd = upsert_bonds(conn, bonds)
        total_inserted += ins
        total_updated += upd
        log.info("API upsert: %d inserted, %d updated", ins, upd)

        status = "completed"
    except Exception as e:
        log.error("Collection failed: %s", e, exc_info=True)
        status = "failed"
        errors += 1

    finished = datetime.now()
    cur = conn.cursor()
    cur.execute(
        "UPDATE collection_log SET finished_at=%s, status=%s, bonds_found=%s, "
        "bonds_updated=%s, bonds_inserted=%s, errors=%s WHERE id=%s",
        (finished, status, total_inserted + total_updated, total_updated, total_inserted, errors, log_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    log.info("=== Collection %s at %s ===", status, finished)


def run_fast_collection(xlsx_path: str | None = None):
    started = datetime.now()
    log.info("=== Starting FAST collection at %s ===", started)

    conn = get_db_conn()
    cur = conn.cursor()
    cur.execute("INSERT INTO collection_log (status, started_at) VALUES ('running', %s) RETURNING id", (started,))
    log_id = cur.fetchone()[0]
    conn.commit()
    cur.close()

    errors = 0
    total_inserted = 0
    total_updated = 0

    try:
        if xlsx_path and os.path.exists(xlsx_path):
            df = pd.read_excel(xlsx_path, sheet_name="data", engine="openpyxl")
            df.columns = [
                "isin0", "rating", "industry", "yield_cb", "yield_dohod", "yield_avg",
                "yield_deviation", "yield_category", "liquidity_cb", "liquidity_dohod",
                "liquidity_avg", "liquidity_category", "isin", "name", "issuer",
                "primary_borrower", "borrower_country", "nominal_currency",
                "issue_volume_bln", "nearest_date_str", "years_to_date", "duration",
                "event_at_date", "ytm", "yield_no_reinvest", "reinvest_profit_pct",
                "simple_yield", "current_yield", "credit_quality_rank",
                "credit_quality_num", "issuer_quality", "inside_q", "outside_q",
                "netdebt_equity_rank", "liquidity_ratio", "median_daily_turnover",
                "complexity", "size_rank", "issue_date", "maturity_date",
                "yield_calc_date", "current_nominal", "min_lot", "price_pct", "nkd",
                "coupon_size", "current_coupon_pct", "coupon_freq", "coupon_type",
                "is_subordinated", "has_guarantee", "issuer_type", "base_index_frn",
                "frn_premium_discount",
            ] + [f"extra_{i}" for i in range(len(df.columns) - 54)]
            df = df.dropna(subset=["isin"])
            df = df.where(pd.notnull(df), None)
            ins, upd = upsert_bonds_from_df(conn, df)
            total_inserted += ins
            total_updated += upd
            log.info("Excel import: %d inserted, %d updated", ins, upd)

        bonds = fetch_all_bonds()
        log.info("Fetched %d bonds from MOEX API (skip enrichment)", len(bonds))

        ins, upd = upsert_bonds(conn, bonds)
        total_inserted += ins
        total_updated += upd
        log.info("API upsert: %d inserted, %d updated", ins, upd)

        status = "completed"
    except Exception as e:
        log.error("Collection failed: %s", e, exc_info=True)
        status = "failed"
        errors += 1

    finished = datetime.now()
    cur = conn.cursor()
    cur.execute(
        "UPDATE collection_log SET finished_at=%s, status=%s, bonds_found=%s, "
        "bonds_updated=%s, bonds_inserted=%s, errors=%s WHERE id=%s",
        (finished, status, total_inserted + total_updated, total_updated, total_inserted, errors, log_id),
    )
    conn.commit()
    cur.close()
    conn.close()
    log.info("=== FAST collection %s at %s ===", status, finished)


if __name__ == "__main__":
    import sys
    xlsx = None
    skip_enrich = False
    for arg in sys.argv[1:]:
        if arg == "--skip-enrich":
            skip_enrich = True
        else:
            xlsx = arg
    if skip_enrich:
        run_fast_collection(xlsx_path=xlsx)
    else:
        run_full_collection(xlsx_path=xlsx)
