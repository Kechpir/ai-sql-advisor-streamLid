# app.py — Streamlit UI для AI SQL Advisor
# Берёт SUPABASE_URL и SUPABASE_ANON_KEY из Streamlit Secrets.
# (Добавляются в Cloud: Manage app → Settings → Secrets)

import json
import requests
import streamlit as st

st.set_page_config(page_title="AI SQL Advisor", page_icon="🧠", layout="centered")
st.title("🧠 AI SQL Advisor")
st.caption("Подключай базу → пиши вопрос → получай безопасный SQL")

# === Секреты (без них ничего не поедет) ===
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"].rstrip("/")
    SUPABASE_ANON = st.secrets["SUPABASE_ANON_KEY"]
except Exception:
    st.error("❌ Не найдены секреты SUPABASE_URL / SUPABASE_ANON_KEY. "
             "Задай их в Streamlit Cloud: Manage app → Settings → Secrets.")
    st.stop()

FETCH_SCHEMA_URL = f"{SUPABASE_URL}/functions/v1/fetch_schema"
GENERATE_SQL_URL = f"{SUPABASE_URL}/functions/v1/generate_sql"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SUPABASE_ANON}",
}

st.divider()
st.subheader("1️⃣ Подключение к базе данных (read-only)")

with st.form("connect_form", clear_on_submit=False):
    col1, col2 = st.columns(2)
    with col1:
        host = st.text_input("Host", value="ep-weathered-scene-ag47iood-pooler.c-2.eu-central-1.aws.neon.tech")
        dbname = st.text_input("Database", value="neondb")
        user = st.text_input("User", value="neondb_owner")
    with col2:
        port = st.text_input("Port", value="5432")
        password = st.text_input("Password", type="password")
        schema_name = st.text_input("Schema", value="public")

    submitted = st.form_submit_button("📡 Считать структуру")

if submitted:
    db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"
    st.info("Подключаюсь и читаю структуру…")
    try:
        res = requests.post(FETCH_SCHEMA_URL, headers=HEADERS,
                            json={"db_url": db_url, "schema": schema_name}, timeout=30)
        if res.status_code == 200:
            schema = res.json()
            st.session_state["schema"] = schema
            st.success(f"✅ Схема прочитана. Таблиц: {schema.get('countTables', 0)}")
            with st.expander("Показать JSON-схему"):
                st.json(schema)
        else:
            st.error(f"Ошибка {res.status_code}: {res.text}")
    except Exception as e:
        st.error(f"Ошибка подключения: {e}")

st.divider()
st.subheader("2️⃣ Генерация SQL-запроса")

nl_query = st.text_area("Ваш запрос на естественном языке",
                        value="Покажи имена и email клиентов, сделавших заказ за последние 7 дней",
                        height=120)

if st.button("🧠 Сгенерировать SQL"):
    schema = st.session_state.get("schema")
    if not schema:
        st.warning("Сначала подключи базу и считай структуру (шаг 1).")
    else:
        st.info("Генерирую SQL…")
        try:
            res = requests.post(GENERATE_SQL_URL, headers=HEADERS,
                                json={"nl": nl_query, "schema": schema}, timeout=60)
            data = res.json()
            if res.status_code != 200:
                st.error(f"Ошибка {res.status_code}: {data}")
            elif data.get("blocked"):
                st.error(f"❌ Запрос заблокирован фильтром: {data.get('reason')}")
            else:
                sql = data.get("sql", "")
                st.code(sql, language="sql")
                st.success("✅ Готово! Копируй в DBeaver.")
        except Exception as e:
            st.error(f"Ошибка генерации: {e}")

st.caption("© 2025 Kechpir — AI SQL Advisor • Supabase + OpenAI • read-only & safe")
