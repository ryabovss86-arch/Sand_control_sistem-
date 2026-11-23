from datetime import datetime, timedelta, timezone
import os, sqlite3
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
import streamlit as st

def local_now():
    # Часовой пояс UTC+5 (Нягань / ЕКБ)
    return datetime.now(timezone(timedelta(hours=5))).replace(tzinfo=None)

st.set_page_config(page_title="Контроль отгрузки песка", layout="wide")
sns.set_theme(style="whitegrid")
DB_FILE = "sand_control.db"

PASSWORDS = {"Заказчик": "1111", "Карьер": "2222", "Администратор": "9999"}
RU_COLS = {
    "id": "№",
    "created_at": "Создано",
    "department": "Подразделение",
    "unloading_place": "Место выгрузки",
    "planned_volume": "План (м³)",
    "actual_volume": "Факт (м³)",
    "excavator_id": "Экскаватор",
    "status": "Статус",
    "shipped_at": "Отгружено",
}

if "role" not in st.session_state:
    st.session_state.role = "Гость"


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TIMESTAMP,
            department TEXT, unloading_place TEXT, planned_volume REAL,
            actual_volume REAL DEFAULT 0, excavator_id TEXT,
            status TEXT DEFAULT 'Новая заявка', shipped_at TIMESTAMP)""")


def get_data():
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("SELECT * FROM shipments", conn)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
        df["shipped_at"] = pd.to_datetime(df["shipped_at"])
    return df


def format_df(df):
    out = df.copy()
    if not out.empty:
        out["created_at"] = out["created_at"].dt.strftime("%d.%m.%Y %H:%M")
        out["shipped_at"] = (
            out["shipped_at"].dt.strftime("%d.%m.%Y %H:%M").fillna("—")
        )
        out["excavator_id"] = out["excavator_id"].fillna("—")
    return out.rename(columns=RU_COLS)


init_db()

with st.sidebar:
    page = st.radio(
        "📌 Раздел:", ["📝 Заявки и Отгрузка", "📊 Графики и Отчеты"]
    )
    st.divider()
    st.write(f"Роль: **{st.session_state.role}**")
    if st.session_state.role == "Гость":
        r = st.selectbox("Вход:", list(PASSWORDS.keys()))
        p = st.text_input("Пароль", type="password")
        if st.button("Войти"):
            if p == PASSWORDS[r]:
                st.session_state.role = r
                st.rerun()
            else:
                st.error("Неверный пароль")
    else:
        if st.button("Выйти"):
            st.session_state.role = "Гость"
            st.rerun()
    st.divider()
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as f:
            st.download_button(
                "💾 Скачать базу (.db)", f, file_name="sand_backup.db"
            )

role = st.session_state.role
st.title("🏗️ Контроль отгрузки песка")

if page == "📝 Заявки и Отгрузка":
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("1. Новая заявка")
        if role in ["Заказчик", "Администратор"]:
            with st.form("req_form", clear_on_submit=True):
                dept = st.selectbox(
                    "Подразделение",
                    ["ЦДНГ", "ЦЭРТ", "ЦППНиППД", "ЦЭЭ", "ЦЭОТВС", " Подрядчики OOC", "Подрядчики ДТИ", "Подрядчики УКС"],
                )
                place = st.text_input("Место выгрузки")
                vol = st.number_input("План (м³)", min_value=1.0, value=20.0)
                if st.form_submit_button("Создать заявку") and place.strip():
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.execute(
                            "INSERT INTO shipments (created_at, department, unloading_place, planned_volume, status) VALUES (?, ?, ?, ?,'Новая заявка')",
                            (local_now(), dept, place, vol),
                        )
                    st.rerun()
        else:
            st.warning("🔒 Доступно роли **Заказчик**")

    with c2:
        st.subheader("2. Погрузка экскаватором")
        if role in ["Карьер", "Администратор"]:
            df_all = get_data()
            reqs = (
                df_all[df_all["status"] == "Новая заявка"]
                if not df_all.empty
                else pd.DataFrame()
            )
            if not reqs.empty:
                with st.form("load_form", clear_on_submit=True):
                    opts = {
                        f"№{r['id']} | {r['department']} -> {r['unloading_place']} ({r['planned_volume']} м³)": r[
                            "id"
                        ]
                        for _, r in reqs.iterrows()
                    }
                    sel = st.selectbox("Заявка", list(opts.keys()))
                    exc = st.selectbox(
                        "Экскаватор",
                        ["НYUNDAI R180NLC-9S #7565УТ86", "НYUNDAI R220LC-9S #9447УС86", "XCMG XE225DN #7695УТ86", "SHANTUI SE220LC #9533УХ86"],
                    )
                    act = st.number_input("Факт (м³)", min_value=1.0, value=20.0)
                    if st.form_submit_button("Отгрузить"):
                        with sqlite3.connect(DB_FILE) as conn:
                            conn.execute(
                                "UPDATE shipments SET actual_volume=?, excavator_id=?, status='Отгружено', shipped_at=? WHERE id=?",
                                (act, exc, local_now(), opts[sel]),
                            )
                        st.rerun()
            else:
                st.info("Нет активных заявок")
        else:
            st.warning("🔒 Доступно роли **Карьер**")

    st.divider()
    df_disp = get_data()
    if not df_disp.empty:
        st.dataframe(
            format_df(df_disp.sort_values("id", ascending=False)),
            use_container_width=True,
        )

elif page == "📊 Графики и Отчеты":
    df = get_data()
    if df.empty:
        st.info("База пуста")
    else:
        shipped = df[df["status"] == "Отгружено"].copy()
        if not shipped.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("Отгружено (м³)", f"{shipped['actual_volume'].sum():,.1f}")
            m2.metric("Заявок выполнено", len(shipped))
            m3.metric(
                "Отклонение (м³)",
                f"{shipped['actual_volume'].sum() - shipped['planned_volume'].sum():+,.1f}",
            )

            g1, g2 = st.columns(2)
            for col, group_col, title, pal in [
                (g1, "department", "По подразделениям (м³)", "Blues_d"),
                (g2, "excavator_id", "По экскаваторам (м³)", "Oranges_d"),
            ]:
                with col:
                    fig, ax = plt.subplots(figsize=(5, 3.2))
                    agg = shipped.groupby(group_col, as_index=False)[
                        "actual_volume"
                    ].sum()
                    sns.barplot(
                        data=agg,
                        x=group_col,
                        y="actual_volume",
                        ax=ax,
                        palette=pal,
                    )
                    ax.set_title(title, fontweight="bold")
                    ax.set(xlabel="", ylabel="м³")
                    ax.tick_params(axis="x", rotation=45)
                    for label in ax.get_xticklabels():
                        label.set_horizontalalignment("right")

                    for p in ax.patches:
                        ax.annotate(
                            f"{p.get_height():.0f}",
                            (p.get_x() + p.get_width() / 2, p.get_height()),
                            ha="center",
                            va="bottom",
                        )
                    sns.despine(ax=ax)
                    plt.tight_layout()
                    st.pyplot(fig)

        st.divider()
        st.subheader("📥 Выгрузка отчета")
        period = st.radio(
            "Период:", ["Сутки", "Месяц", "Всё время"], horizontal=True
        )
        now = local_now()
        if period == "Сутки":
            rep = df[df["created_at"].dt.date == now.date()]
        elif period == "Месяц":
            rep = df[
                (df["created_at"].dt.year == now.year)
                & (df["created_at"].dt.month == now.month)
            ]
        else:
            rep = df

        exp = format_df(rep)
        st.dataframe(exp, use_container_width=True)
        st.download_button(
            "📥 Скачать отчет (CSV)",
            exp.to_csv(index=False, sep=";").encode("utf-8-sig"),
            "otchet_pesok.csv",
            "text/csv",
        )




