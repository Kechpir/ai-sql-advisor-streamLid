import streamlit as st
import requests
import json

st.set_page_config(page_title="AI SQL Advisor", page_icon="🧠", layout="centered")

st.title("🧠 AI SQL Advisor")
st.caption("Подключай базу → пиши вопрос → получай SQL")

st.divider()
st.subheader("1️⃣ Подключение к базе данных")

with st.form("connect_form"):
    host = st.text_input("Host", "ep-weathered-scene-ag47iood-pooler.c-2.eu-central-1.aws.neon.tech")
    port = st.text_input("Port", "5432")
    dbname = st.text_input("Database", "neondb")
    user = st.text_input("User", "neondb_owner")
    password = st.text_input("Password", type="password")
    submitted = st.form_submit_button("📡 Считать структуру")

if submitted:
    db_url = f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=require"
    st.write("🔗 Подключение к базе...")
    try:
        res = requests.post(
            "https://zpppzzwaoplfeoiynkam.supabase.co/functions/v1/fetch_schema",
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer eyJhbGciOi..."  # вставь сюда свой anon public key
            },
            json={"db_url": db_url},
            timeout=30,
        )
        if res.status_code == 200:
            schema = res.json()
            st.success(f"✅ Считано таблиц: {schema.get('countTables', '—')}")
            st.json(schema)
            st.session_state["schema"] = schema
        else:
            st.error(f"Ошибка {res.status_code}: {res.text}")
    except Exception as e:
        st.error(f"Ошибка подключения: {e}")

st.divider()
st.subheader("2️⃣ Генерация SQL-запроса")

nl_query = st.text_area("Ваш запрос на естественном языке", "Покажи всех клиентов, сделавших заказ за последнюю неделю")

if st.button("🧠 Сгенерировать SQL"):
    schema = st.session_state.get("schema")
    if not schema:
        st.warning("Сначала подключи базу и считай структуру 👆")
    else:
        st.write("🤖 Генерация запроса...")
        try:
            res = requests.post(
                "https://zpppzzwaoplfeoiynkam.supabase.co/functions/v1/generate_sql",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer eyJhbGciOi..."  # сюда тоже твой anon key
                },
                json={"nl": nl_query, "schema": schema},
                timeout=60,
            )
            data = res.json()
            if data.get("blocked"):
                st.error(f"❌ Запрос заблокирован: {data.get('reason')}")
            else:
                st.code(data.get("sql", ""), language="sql")
                st.success("✅ SQL готов! Можно копировать в DBeaver")
        except Exception as e:
            st.error(f"Ошибка генерации: {e}")

st.caption("© 2025 Kechpir — AI SQL Advisor • powered by Supabase + OpenAI")
