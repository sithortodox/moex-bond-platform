import os
import hashlib
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sqlalchemy import create_engine, text
from io import BytesIO

DB_URL = os.environ.get("DATABASE_URL", "postgresql://moex:moex_bonds@localhost:5432/moex_bonds")
engine = create_engine(DB_URL)

st.set_page_config(page_title="MOEX Bond Screener", page_icon="📊", layout="wide")


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


_CREDENTIALS = {
    "admin": "4aeacba51e89303b00e830e5ec7c83aa4af978c2526aa9c534c2f4b399dc079f",
}


def check_auth():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False
    if st.session_state.authenticated:
        return True

    st.markdown("## 🔐 Вход в MOEX Bond Screener")
    with st.form("login_form"):
        username = st.text_input("Логин")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти")
        if submitted:
            if username in _CREDENTIALS and _hash(password) == _CREDENTIALS[username]:
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Неверный логин или пароль")
    return False


if not check_auth():
    st.stop()

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
    import subprocess, os, sys
    subprocess.Popen([sys.executable, "-m", "data_collector", "--skip-enrich"], cwd="/app", stdout=open("/tmp/collector.log", "a"), stderr=open("/tmp/collector.log", "a"))
    st.cache_data.clear()

if "favorites" not in st.session_state:
    st.session_state.favorites = set()

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

tabs = st.tabs(["📋 Таблица", "📊 Графики", "⚖️ Сравнение", "🧮 Калькулятор", "⭐ Избранное"])

with st.sidebar:
    st.header("⚙️ Настройки отображения")

    show_cols = st.multiselect(
        "Видимые колонки",
        options=ALL_COLS,
        default=DEFAULT_COLS,
        format_func=lambda c: DISPLAY_NAMES.get(c, c),
    )

    st.markdown("---")
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

    st.markdown("---")
    st.header("📥 Управление данными")

    if st.button("🔄 Обновить данные из MOEX API", type="secondary"):
        with st.spinner("Запуск сбора... Это может занять 20+ минут"):
            run_collector()
        st.rerun()


    st.link_button("Upload Excel (.xlsx)", "/upload-page")
    import glob, os as os_mod
    xlsx_files = sorted(glob.glob("/app/data/*.xlsx"))
    if xlsx_files:
        selected = st.selectbox("Imported files", xlsx_files, format_func=lambda x: os_mod.path.basename(x))
        if st.button("Apply to DB"):
            from data_collector import import_excel_data
            try:
                count = import_excel_data(selected)
                st.success(f"Imported {count} records")
                st.cache_data.clear()
                st.rerun()
            except Exception as e:
                st.error(f"Error: {e}")
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

with tabs[0]:
    st.subheader(f"Найдено облигаций: {len(display_df)}")

    sort_col = st.selectbox(
        "Сортировка по",
        options=show_cols,
        index=show_cols.index("moex_yield") if "moex_yield" in show_cols else 0,
        format_func=lambda c: DISPLAY_NAMES.get(c, c),
        key="sort_col",
    )
    sort_asc = st.checkbox("По возрастанию", value=False, key="sort_asc")

    if sort_col and sort_col in filtered.columns:
        display_df_sorted = filtered[show_cols].sort_values(
            by=sort_col, ascending=sort_asc, na_position="last"
        ).copy()
        display_df_sorted.rename(columns=DISPLAY_NAMES, inplace=True)
    else:
        display_df_sorted = display_df

    page_size = st.selectbox("Строк на страницу", [25, 50, 100, 200], index=1, key="page_size")
    total_rows = len(display_df_sorted)
    total_pages = max(1, (total_rows - 1) // page_size + 1)
    current_page = st.number_input("Страница", min_value=1, max_value=total_pages, value=1, key="current_page")

    start_idx = (current_page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)
    page_df = display_df_sorted.iloc[start_idx:end_idx]

    st.caption(f"Стр. {current_page}/{total_pages} | Записи {start_idx+1}–{end_idx} из {total_rows}")

    st.dataframe(
        page_df,
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

    col_csv, col_pdf = st.columns(2)
    with col_csv:
        csv = display_df_sorted.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "📥 Скачать CSV",
            data=csv,
            file_name="moex_bonds.csv",
            mime="text/csv",
        )
    with col_pdf:
        xlsx_buf = BytesIO()
        display_df_sorted.to_excel(xlsx_buf, index=False, engine="openpyxl")
        xlsx_buf.seek(0)
        st.download_button(
            "📄 Скачать Excel",
            data=xlsx_buf,
            file_name="moex_bonds.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    with st.expander("📋 Журнал сборов данных"):
        log_df = load_collection_log()
        if not log_df.empty:
            st.dataframe(log_df, use_container_width=True, hide_index=True)
        else:
            st.info("Журнал пуст")

with tabs[1]:
    st.subheader("📊 Визуализация рынка облигаций")

    chart_data = filtered.dropna(subset=[ytm_col]).copy()

    if chart_data.empty:
        st.info("Нет данных для графиков при текущих фильтрах")
    else:
        chart_type = st.selectbox(
            "Тип графика",
            ["YTM vs Дюрация", "Распределение YTM", "YTM по рейтингу", "Тепловая карта рейтинг×ликвидность"],
            key="chart_type",
        )

        if chart_type == "YTM vs Дюрация":
            dur_col = "duration" if "duration" in chart_data.columns else "years_to_date"
            hover_cols = ["isin", "name", "issuer"]
            available_hover = [c for c in hover_cols if c in chart_data.columns]
            fig = px.scatter(
                chart_data,
                x=dur_col,
                y=ytm_col,
                color="rating" if "rating" in chart_data.columns else None,
                hover_data=available_hover,
                title="YTM vs Дюрация (цвет — рейтинг)",
                labels={dur_col: "Дюрация", ytm_col: "YTM, %"},
                height=600,
            )
            st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "Распределение YTM":
            fig = px.histogram(
                chart_data,
                x=ytm_col,
                nbins=50,
                title="Распределение YTM",
                labels={ytm_col: "YTM, %"},
                height=500,
            )
            st.plotly_chart(fig, use_container_width=True)

        elif chart_type == "YTM по рейтингу":
            if "rating" in chart_data.columns:
                rating_order = sorted(chart_data["rating"].dropna().unique())
                fig = px.box(
                    chart_data,
                    x="rating",
                    y=ytm_col,
                    category_orders={"rating": rating_order},
                    title="YTM по рейтингам",
                    labels={"rating": "Рейтинг", ytm_col: "YTM, %"},
                    height=600,
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Нет данных по рейтингу")

        elif chart_type == "Тепловая карта рейтинг×ликвидность":
            if "rating" in chart_data.columns and "liquidity_category" in chart_data.columns:
                pivot = chart_data.groupby(["rating", "liquidity_category"])[ytm_col].mean().reset_index()
                pivot_map = pivot.pivot(index="rating", columns="liquidity_category", values=ytm_col)
                fig = px.imshow(
                    pivot_map,
                    title="Средний YTM: рейтинг × ликвидность",
                    labels=dict(x="Ликвидность", y="Рейтинг", color="YTM, %"),
                    height=600,
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Нет данных по рейтингу или ликвидности")

with tabs[2]:
    st.subheader("⚖️ Сравнение облигаций")

    isin_list = filtered["isin"].dropna().unique().tolist()
    compare_isins = st.multiselect(
        "Выберите облигации для сравнения (ISIN)",
        options=isin_list,
        max_selections=5,
        key="compare_isins",
    )

    if compare_isins:
        compare_df = df[df["isin"].isin(compare_isins)].copy()
        compare_cols = [c for c in ALL_COLS if c in compare_df.columns]
        compare_display = compare_df[compare_cols].copy()
        compare_display.rename(columns=DISPLAY_NAMES, inplace=True)
        st.dataframe(compare_display, use_container_width=True, hide_index=True)

        if ytm_col in compare_df.columns and "duration" in compare_df.columns:
            chart_compare = compare_df.dropna(subset=[ytm_col, "duration"])
            if not chart_compare.empty:
                hover_cols = ["isin", "name"]
                available_hover = [c for c in hover_cols if c in chart_compare.columns]
                fig = px.scatter(
                    chart_compare,
                    x="duration",
                    y=ytm_col,
                    text="isin" if "isin" in chart_compare.columns else None,
                    hover_data=available_hover,
                    title="Сравнение: YTM vs Дюрация",
                    labels={"duration": "Дюрация", ytm_col: "YTM, %"},
                    height=500,
                )
                fig.update_traces(textposition="top center", marker_size=14)
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Выберите до 5 облигаций для сравнения")

with tabs[3]:
    st.subheader("🧮 Калькулятор доходности")

    calc_isin = st.selectbox(
        "Выберите облигацию",
        options=isin_list,
        key="calc_isin",
    )

    if calc_isin:
        bond = df[df["isin"] == calc_isin].iloc[0] if len(df[df["isin"] == calc_isin]) > 0 else None
        if bond is not None:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.markdown(f"**{bond.get('name', '—')}**")
                st.write(f"ISIN: {bond.get('isin', '—')}")
                st.write(f"Эмитент: {bond.get('issuer', '—')}")
                st.write(f"Рейтинг: {bond.get('rating', '—')}")
                st.write(f"Номинал: {bond.get('current_nominal', '—')} {bond.get('nominal_currency', '')}")
            with col2:
                st.write(f"Цена: {bond.get('price_pct', '—')}%")
                st.write(f"НКД: {bond.get('nkd', '—')} ₽")
                st.write(f"Купон: {bond.get('coupon_size', '—')} ₽")
                st.write(f"Купон %: {bond.get('current_coupon_pct', '—')}")
                st.write(f"Частота: {bond.get('coupon_freq', '—')} раз/год")
            with col3:
                st.write(f"YTM: {bond.get(ytm_col, '—')}%")
                st.write(f"Дюрация: {bond.get('duration', '—')}")
                st.write(f"Дата погашения: {bond.get('maturity_date', '—')}")
                st.write(f"Тип купона: {bond.get('coupon_type', '—')}")

            st.markdown("---")
            st.markdown("#### Расчёт доходности по своей цене")

            nominal = float(bond.get("current_nominal") or 1000)
            coupon = float(bond.get("coupon_size") or 0)
            try:
                freq = int(float(bond.get("coupon_freq") or 1))
            except (ValueError, TypeError):
                freq = 1
            try:
                nkd = float(bond.get("nkd") or 0)
            except (ValueError, TypeError):
                nkd = 0

            custom_price_pct = st.number_input(
                "Цена покупки, % от номинала",
                value=float(bond.get("price_pct", 100) or 100),
                min_value=0.0,
                step=0.1,
                key="custom_price",
            )
            qty = st.number_input("Количество облигаций", value=1, min_value=1, step=1, key="calc_qty")

            investment = (custom_price_pct / 100) * nominal * qty + nkd * qty
            annual_coupon = coupon * freq * qty

            st.markdown(f"""
            | Показатель | Значение |
            |---|---|
            | Затраты на покупку | {investment:,.2f} ₽ |
            | Годовой купонный доход | {annual_coupon:,.2f} ₽ |
            | Текущая доходность (купон/цена) | {annual_coupon / investment * 100:.2f}% |
            | Доход к номиналу при погашении | {((nominal * qty - (custom_price_pct / 100) * nominal * qty) / investment * 100):.2f}% |
            """)

with tabs[4]:
    st.subheader("⭐ Избранное")

    fav_isins = st.multiselect(
        "Добавить ISIN в избранное",
        options=isin_list,
        key="add_fav",
    )
    if st.button("➕ Добавить в избранное", key="btn_add_fav"):
        st.session_state.favorites.update(fav_isins)
        st.rerun()

    if st.session_state.favorites:
        fav_df = df[df["isin"].isin(st.session_state.favorites)].copy()
        fav_cols = [c for c in ALL_COLS if c in fav_df.columns]
        fav_display = fav_df[fav_cols].copy()
        fav_display.rename(columns=DISPLAY_NAMES, inplace=True)

        st.dataframe(fav_display, use_container_width=True, hide_index=True)

        remove_isin = st.selectbox(
            "Удалить из избранного",
            options=list(st.session_state.favorites),
            key="remove_fav",
        )
        if st.button("🗑️ Удалить", key="btn_remove_fav"):
            st.session_state.favorites.discard(remove_isin)
            st.rerun()
    else:
        st.info("Список избранного пуст. Добавьте облигации через поле выше.")
