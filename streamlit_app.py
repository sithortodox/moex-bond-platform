import os
import streamlit as st
import pandas as pd
from sqlalchemy import create_engine, text

DB_URL = os.environ.get("DATABASE_URL", "postgresql://moex:moex123@localhost:5432/moex_bonds")
engine = create_engine(DB_URL)

st.set_page_config(page_title="MOEX Bond Screener", page_icon="📊", layout="wide")

st.title("📊 MOEX Bond Screener — Облигации Московской биржи")
st.caption("Аналог dohod.ru/analytic/bonds | Данные из API Мосбиржи + доп. источники")

@st.cache_data(ttl=300)
def load_bonds() -> pd.DataFrame:
    with engine.connect() as conn:
        df = pd.read_sql(
            "SELECT * FROM bonds ORDER BY moex_yield DESC NULLS LAST",
            conn,
        )
    return df

@st.cache_data(ttl=600)
def load_collection_log() -> pd.DataFrame:
    with engine.connect() as conn:
        return pd.read_sql(
            "SELECT * FROM collection_log ORDER BY started_at DESC LIMIT 5",
            conn,
        )

@st.cache_data(ttl=3600)
def get_distinct_values(col: str) -> list:
    with engine.connect() as conn:
        result = conn.execute(text(f"SELECT DISTINCT {col} FROM bonds WHERE {col} IS NOT NULL ORDER BY {col}"))
        return [r[0] for r in result]

def run_collector():
    from data_collector import run_full_collection
    run_full_collection()
    st.cache_data.clear()


df = load_bonds()

if df.empty:
    st.warning("База данных пуста. Запустите сбор данных.")
    if st.button("🚀 Запустить сбор данных (может занять 20+ мин)"):
        with st.spinner("Сбор данных..."):
            run_collector()
        st.rerun()
    st.stop()

COL_META = {
    "isin": ("ISIN", True),
    "name": ("Название", True),
    "issuer": ("Эмитент", True),
    "issuer_type": ("Тип эмитента", True),
    "rating": ("Рейтинг", True),
    "industry": ("Отрасль", True),
    "nominal_currency": ("Валюта", True),
    "current_nominal": ("Номинал", True),
    "min_lot": ("Мин. лот", True),
    "price_pct": ("Цена, %", True),
    "nkd": ("НКД", True),
    "moex_yield": ("YTM (MOEX), %", True),
    "ytm": ("YTM, %", True),
    "yield_no_reinvest": ("Дох. без реинвест., %", False),
    "simple_yield": ("Простая доходность, %", False),
    "current_yield": ("Текущая доходность, %", True),
    "coupon_size": ("Купон, руб.", True),
    "current_coupon_pct": ("Купон, %", True),
    "coupon_freq": ("Купон (раз/год)", True),
    "coupon_type": ("Тип купона", True),
    "duration": ("Дюрация", True),
    "years_to_date": ("Лет до даты", True),
    "maturity_date": ("Дата погашения", True),
    "nearest_date_str": ("Ближайшая дата", True),
    "event_at_date": ("Событие", False),
    "issue_date": ("Дата выпуска", False),
    "issue_volume_bln": ("Объём выпуска, млрд", False),
    "moex_volume_15d": ("Объём 15д, шт.", True),
    "median_daily_turnover": ("Медиана оборота, млн", False),
    "liquidity_category": ("Ликвидность", True),
    "credit_quality_rank": ("Кр. качество (рэнкинг)", True),
    "credit_quality_num": ("Кр. качество (число)", False),
    "is_subordinated": ("Субординир.", False),
    "has_guarantee": ("С гарантией", False),
    "is_qualified": ("Квалиф. инвестор", True),
    "borrower_country": ("Страна", False),
    "issuer_quality": ("Качество эмитента", False),
    "complexity": ("Сложность", False),
    "size_rank": ("Размер (ранг)", False),
    "g_spread": ("G-spread", False),
    "amortization": ("Амортизация", False),
    "offer_call_date": ("Оферта колл", False),
    "offer_put_date": ("Оферта пут", False),
    "payments_known": ("Выплаты известны", False),
    "yield_category": ("Катег. доходности", False),
    "board_group": ("Группа торгов", False),
    "secid": ("SECID", False),
    "board_id": ("Board ID", False),
    "updated_at": ("Обновлено", False),
}

ALL_COLS = [c for c in df.columns if c in COL_META]
DEFAULT_COLS = [c for c in ALL_COLS if COL_META.get(c, ("", False))[1]]
DISPLAY_NAMES = {c: COL_META[c][0] for c in COL_META if c in df.columns}

with st.sidebar:
    st.header("⚙️ Настройки отображения")

    show_cols = st.multiselect(
        "Видимые колонки",
        options=ALL_COLS,
        default=DEFAULT_COLS,
        format_func=lambda c: DISPLAY_NAMES.get(c, c),
    )

    st.divider()
    st.header("🔍 Фильтры")

    search_text = st.text_input("Поиск по ISIN / названию / эмитенту", "")

    rating_options = get_distinct_values("rating")
    rating_filter = st.multiselect("Рейтинг", rating_options)

    issuer_type_options = get_distinct_values("issuer_type")
    issuer_type_filter = st.multiselect("Тип эмитента", issuer_type_options)

    currency_options = get_distinct_values("nominal_currency")
    currency_filter = st.multiselect("Валюта", currency_options)

    coupon_type_options = get_distinct_values("coupon_type")
    coupon_type_filter = st.multiselect("Тип купона", coupon_type_options)

    liquidity_options = get_distinct_values("liquidity_category")
    liquidity_filter = st.multiselect("Ликвидность", liquidity_options)

    qualified_filter = st.selectbox("Квалиф. инвестор", ["Все", "Нет", "Да"], index=0)

    st.subheader("Числовые фильтры")
    ytm_range = st.slider("YTM, %", min_value=0.0, max_value=50.0, value=(0.0, 50.0), step=0.5)
    duration_range = st.slider("Дюрация", min_value=0.0, max_value=50.0, value=(0.0, 50.0), step=0.5)
    price_range = st.slider("Цена, % от ном.", min_value=0.0, max_value=200.0, value=(0.0, 200.0), step=1.0)
    coupon_range = st.slider("Купон, %", min_value=0.0, max_value=30.0, value=(0.0, 30.0), step=0.5)
    volume_min = st.number_input("Мин. объём торгов 15д, шт.", value=0, min_value=0, step=1000)

    st.divider()
    st.header("📥 Управление данными")

    if st.button("🔄 Обновить данные из MOEX API", type="secondary"):
        with st.spinner("Запуск сбора... Это может занять 20+ минут"):
            run_collector()
        st.rerun()

    uploaded = st.file_uploader("Загрузить Excel (лист 'data')", type=["xlsx"])
    if uploaded and st.button("📥 Импортировать Excel"):
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(uploaded.getvalue())
            tmp_path = tmp.name
        from data_collector import import_excel_data
        try:
            count = import_excel_data(tmp_path)
            st.success(f"Импортировано {count} записей")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Ошибка импорта: {e}")

filtered = df.copy()

if search_text:
    mask = (
        filtered["isin"].astype(str).str.contains(search_text, case=False, na=False)
        | filtered["name"].astype(str).str.contains(search_text, case=False, na=False)
        | filtered["issuer"].astype(str).str.contains(search_text, case=False, na=False)
    )
    filtered = filtered[mask]

if rating_filter:
    filtered = filtered[filtered["rating"].isin(rating_filter)]
if issuer_type_filter:
    filtered = filtered[filtered["issuer_type"].isin(issuer_type_filter)]
if currency_filter:
    filtered = filtered[filtered["nominal_currency"].isin(currency_filter)]
if coupon_type_filter:
    filtered = filtered[filtered["coupon_type"].isin(coupon_type_filter)]
if liquidity_filter:
    filtered = filtered[filtered["liquidity_category"].isin(liquidity_filter)]
if qualified_filter == "Нет":
    filtered = filtered[filtered["is_qualified"] == "нет"]
elif qualified_filter == "Да":
    filtered = filtered[filtered["is_qualified"] == "да"]

ytm_col = "ytm" if "ytm" in filtered.columns and filtered["ytm"].notna().any() else "moex_yield"
if ytm_col in filtered.columns:
    filtered = filtered[
        filtered[ytm_col].between(ytm_range[0], ytm_range[1], inclusive="both")
        | filtered[ytm_col].isna()
    ]
if "duration" in filtered.columns:
    filtered = filtered[
        filtered["duration"].between(duration_range[0], duration_range[1], inclusive="both")
        | filtered["duration"].isna()
    ]
if "price_pct" in filtered.columns:
    filtered = filtered[
        filtered["price_pct"].between(price_range[0], price_range[1], inclusive="both")
        | filtered["price_pct"].isna()
    ]
if "current_coupon_pct" in filtered.columns:
    filtered = filtered[
        filtered["current_coupon_pct"].between(coupon_range[0], coupon_range[1], inclusive="both")
        | filtered["current_coupon_pct"].isna()
    ]
if "moex_volume_15d" in filtered.columns and volume_min > 0:
    filtered = filtered[
        (filtered["moex_volume_15d"] >= volume_min) | filtered["moex_volume_15d"].isna()
    ]

if not show_cols:
    show_cols = DEFAULT_COLS

display_df = filtered[show_cols].copy()
display_df.rename(columns=DISPLAY_NAMES, inplace=True)

st.subheader(f"Найдено облигаций: {len(display_df)}")

sort_col = st.selectbox(
    "Сортировка по",
    options=show_cols,
    index=show_cols.index("moex_yield") if "moex_yield" in show_cols else 0,
    format_func=lambda c: DISPLAY_NAMES.get(c, c),
)
sort_asc = st.checkbox("По возрастанию", value=False)

if sort_col and sort_col in filtered.columns:
    display_df_sorted = filtered[show_cols].sort_values(
        by=sort_col, ascending=sort_asc, na_position="last"
    ).copy()
    display_df_sorted.rename(columns=DISPLAY_NAMES, inplace=True)
else:
    display_df_sorted = display_df

st.dataframe(
    display_df_sorted,
    use_container_width=True,
    height=700,
    hide_index=True,
    column_config={
        DISPLAY_NAMES.get("moex_yield", "moex_yield"): st.column_config.NumberColumn(format="%.2f %%"),
        DISPLAY_NAMES.get("ytm", "ytm"): st.column_config.NumberColumn(format="%.2f %%"),
        DISPLAY_NAMES.get("price_pct", "price_pct"): st.column_config.NumberColumn(format="%.2f %%"),
        DISPLAY_NAMES.get("duration", "duration"): st.column_config.NumberColumn(format="%.2f"),
        DISPLAY_NAMES.get("nkd", "nkd"): st.column_config.NumberColumn(format="%.2f ₽"),
        DISPLAY_NAMES.get("coupon_size", "coupon_size"): st.column_config.NumberColumn(format="%.2f ₽"),
        DISPLAY_NAMES.get("current_coupon_pct", "current_coupon_pct"): st.column_config.NumberColumn(format="%.2f %%"),
    },
)

csv = display_df_sorted.to_csv(index=False).encode("utf-8-sig")
st.download_button(
    "📥 Скачать CSV",
    data=csv,
    file_name="moex_bonds.csv",
    mime="text/csv",
)

with st.expander("📋 Журнал сборов данных"):
    log_df = load_collection_log()
    if not log_df.empty:
        st.dataframe(log_df, use_container_width=True, hide_index=True)
    else:
        st.info("Журнал пуст")

st.markdown("---")
st.markdown("[Deployed Sithortodox](https://t.me/sith_ortodox)")
