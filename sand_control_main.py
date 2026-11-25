import base64
from datetime import datetime, timedelta, timezone
import io, os, sqlite3
import matplotlib.pyplot as plt
import pandas as pd
from PIL import Image
import seaborn as sns
import streamlit as st


def local_now():
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
DEPTS = [
    "ЦДНГ",
    "ЦЭРТ",
    "ЦППНиППД",
    "ЦЭЭ",
    "ЦЭОТВС",
    "Подрядчики OOC",
    "Подрядчики ДТИ",
    "Подрядчики УКС",
]
EXCS = [
    "НYUNDAI R180NLC-9S #7565УТ86",
    "НYUNDAI R220LC-9S #9447УС86",
    "XCMG XE225DN #7695УТ86",
    "SHANTUI SE220LC #9533УХ86",
]

if "role" not in st.session_state:
    st.session_state.role = "Гость"


def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS shipments (
            id INTEGER PRIMARY KEY AUTOINCREMENT, created_at TIMESTAMP,
            department TEXT, unloading_place TEXT, planned_volume REAL,
            actual_volume REAL DEFAULT 0, excavator_id TEXT,
            status TEXT DEFAULT 'Новая заявка', shipped_at TIMESTAMP, photo TEXT)""")
        try:
            conn.execute("ALTER TABLE shipments ADD COLUMN photo TEXT")
        except sqlite3.OperationalError:
            pass


def compress_img(file):
    if not file:
        return ""
    img = Image.open(file).convert("RGB")
    img.thumbnail((800, 800))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def get_data():
    with sqlite3.connect(DB_FILE) as conn:
        df = pd.read_sql_query("SELECT * FROM shipments", conn)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
        df["shipped_at"] = pd.to_datetime(df["shipped_at"])
    return df


def format_df(df):
    out = df.drop(columns=["photo"], errors="ignore").copy()
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
            st.download_button("💾 Скачать базу (.db)", f, "sand_backup.db")

role = st.session_state.role
st.title("🏗️ Контроль отгрузки песка")

if page == "📝 Заявки и Отгрузка":
    df_all = get_data()
    c1, c2 = st.columns(2)

    with c1:
        st.subheader("1. Заказчик: Заявки и Приемка")
        if role in ["Заказчик", "Администратор"]:
            with st.form("req_form", clear_on_submit=True):
                dept = st.selectbox("Подразделение", DEPTS)
                place = st.text_input("Место выгрузки")
                vol = st.number_input("План (м³)", min_value=1.0, value=20.0)
                if st.form_submit_button("Создать заявку") and place.strip():
                    with sqlite3.connect(DB_FILE) as conn:
                        conn.execute(
                            "INSERT INTO shipments (created_at, department, unloading_place, planned_volume, status) VALUES (?, ?, ?, ?, 'Новая заявка')",
                            (local_now(), dept, place, vol),
                        )
                    st.rerun()

            # Блок подтверждения выполнения отгруженных заявок
            shipped_reqs = (
                df_all[df_all["status"] == "Отгружено"]
                if not df_all.empty
                else pd.DataFrame()
            )
            if not shipped_reqs.empty:
                st.markdown("**Подтверждение выполнения:**")
                with st.form("confirm_form", clear_on_submit=True):
                    c_opts = {
                        f"№{r['id']} | {r['department']} -> {r['unloading_place']} (Факт: {r['actual_volume']} м³)": r[
                            "id"
                        ]
                        for _, r in shipped_reqs.iterrows()
                    }
                    c_sel = st.selectbox(
                        "Отгруженные заявки:", list(c_opts.keys())
                    )
                    if st.form_submit_button("✅ Подтвердить выполнение"):
                        with sqlite3.connect(DB_FILE) as conn:
                            conn.execute(
                                "UPDATE shipments SET status='Выполнено' WHERE id=?",
                                (c_opts[c_sel],),
                            )
                        st.rerun()
        else:
            st.warning("🔒 Доступно роли **Заказчик**")

    with c2:
        st.subheader("2. Карьер: Погрузка экскаватором")
        if role in ["Карьер", "Администратор"]:
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
                    exc = st.selectbox("Экскаватор", EXCS)
                    act = st.number_input("Факт (м³)", min_value=1.0, value=20.0)
                    photo = st.file_uploader(
                        "📸 Фото отгрузки (обязательно)",
                        type=["jpg", "jpeg", "png"],
                    )
                    if st.form_submit_button("Отгрузить"):
                        if photo:
                            with sqlite3.connect(DB_FILE) as conn:
                                conn.execute(
                                    "UPDATE shipments SET actual_volume=?, excavator_id=?, status='Отгружено', shipped_at=?, photo=? WHERE id=?",
                                    (
                                        act,
                                        exc,
                                        local_now(),
                                        compress_img(photo),
                                        opts[sel],
                                    ),
                                )
                            st.rerun()
                        else:
                            st.error("❌ Прикрепите фото отгрузки!")
            else:
                st.info("Нет активных заявок")
        else:
            st.warning("🔒 Доступно роли **Карьер**")

    st.divider()
    if not df_all.empty:
        st.dataframe(
            format_df(df_all.sort_values("id", ascending=False)),
            use_container_width=True,
        )
        photos = df_all[df_all["photo"].notna() & (df_all["photo"] != "")]
        if not photos.empty:
            st.subheader("📷 Фотоотчеты отгрузки")
            p_opts = {
                f"№{r['id']} | {r['department']} ({r['shipped_at'].strftime('%d.%m %H:%M')})": r[
                    "photo"
                ]
                for _, r in photos.sort_values("id", ascending=False).iterrows()
            }
            chosen = st.selectbox("Выберите заявку:", list(p_opts.keys()))
            st.image(base64.b64decode(p_opts[chosen]), width=450)

elif page == "📊 Графики и Отчеты":
    df = get_data()
    if df.empty:
        st.info("База пуста")
    else:
        shipped = df[df["status"].isin(["Отгружено", "Выполнено"])].copy()
        if not shipped.empty:
            m1, m2, m3 = st.columns(3)
            m1.metric("Отгружено (м³)", f"{shipped['actual_volume'].sum():,.1f}")
            m2.metric("Рейсов выполнено", len(shipped))
            m3.metric(
                "Отклонение (м³)",
                f"{shipped['actual_volume'].sum() - shipped['planned_volume'].sum():+,.1f}",
            )

            g1, g2 = st.columns(2)
            for col, g_col, title, pal in [
                (g1, "department", "По подразделениям (м³)", "Blues_d"),
                (g2, "excavator_id", "По экскаваторам (м³)", "Oranges_d"),
            ]:
                with col:
                    fig, ax = plt.subplots(figsize=(5, 3.8))
                    agg = shipped.groupby(g_col, as_index=False)[
                        "actual_volume"
                    ].sum()
                    sns.barplot(
                        data=agg, x=g_col, y="actual_volume", ax=ax, palette=pal
                    )
                    ax.set_title(title, fontweight="bold")
                    ax.set(xlabel="", ylabel="м³")
                    ax.set_ylim(0, agg["actual_volume"].max() * 1.15)
                    ax.tick_params(axis="x", rotation=45)
                    for lbl in ax.get_xticklabels():
                        lbl.set_horizontalalignment("right")
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
)