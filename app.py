# -*- coding: utf-8 -*-
import json
import time
import requests
import streamlit as st

st.set_page_config(page_title="AI SQL Advisor", page_icon="🧠", layout="centered")

# === Secrets / Config ===
SUPABASE_URL = st.secrets.get("SUPABASE_URL", "https://zpppzzwaoplfeoiynkam.supabase.co")
SUPABASE_ANON_KEY = st.secrets.get("SUPABASE_ANON_KEY", "")
FUNC_BASE = f"{SUPABASE_URL}/functions/v1"

OPENAI_IN_PRICE = float(st.secrets.get("OPENAI_IN_PRICE", 0))
OPENAI_OUT_PRICE = float(st.secrets.get("OPENAI_OUT_PRICE", 0))

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {SUPABASE_ANON_KEY}" if SUPABASE_ANON_KEY else "",
}

# — Работа с функцией /schemas (CRUD сохранённых схем)
SCHEMAS_FUNC = f"{SUPABASE_URL}/functions/v1/schemas"

def _schemas_get():
    return requests.get(SCHEMAS_FUNC, headers=HEADERS, timeout=40)

def _schemas_post(payload: dict):
    return requests.post(SCHEMAS_FUNC, headers=HEADERS, data=json.dumps(payload), timeout=60)


# === helpers ===
def _err_box(msg, details=None):
    st.error(msg)
    if details:
        with st.expander("Подробнее"):
            st.code(details, language="text")

def _post_json(path: str, payload: dict, timeout=40):
    url = f"{FUNC_BASE}/{path.lstrip('/')}"
    return requests.post(url, headers=HEADERS, data=json.dumps(payload), timeout=timeout)

def _get(path: str, timeout=40):
    url = f"{FUNC_BASE}/{path.lstrip('/')}"
    return requests.get(url, headers=HEADERS, timeout=timeout)

def _validate_url(db_url: str):
    if not db_url:
        return "Введите строку подключения к БД."
    if not db_url.startswith(("postgresql://", "postgres://")):
        return "Поддерживается только Postgres."
    if "@" not in db_url or ":" not in db_url:
        return "Нет логина/пароля или хоста."
    if "sslmode=" not in db_url:
        return "Добавьте ?sslmode=require."
    return None

def _badge(text: str):
    st.markdown(
        f"<span style='background:#10b98120;color:#065f46;padding:4px 10px;border-radius:999px;font-size:12px;border:1px solid #10b98150;'>{text}</span>",
        unsafe_allow_html=True,
    )

def copy_to_clipboard(label, text_to_copy, key):
    st.components.v1.html(f"""
        <button id="{key}" style="padding:6px 10px;border-radius:8px;border:1px solid #e5e7eb;cursor:pointer;">
            {label}
        </button>
        <script>
            const b=document.getElementById("{key}");
            b&&b.addEventListener("click",async()=>{{
                try{{await navigator.clipboard.writeText({json.dumps(text_to_copy)});b.innerText="Скопировано ✓";
                setTimeout(()=>b.innerText={json.dumps(label)},1500);}}
                catch(e){{b.innerText="Ошибка";setTimeout(()=>b.innerText={json.dumps(label)},1500);}}
            }});
        </script>
    """, height=45)

def _annotate_sql(sql: str):
    notes = []
    up = sql.upper()
    if "SELECT" in up: notes.append("-- SELECT: какие колонки выводим")
    if "FROM" in up: notes.append("-- FROM: из какой таблицы берём")
    if "JOIN" in up: notes.append("-- JOIN: соединяем таблицы")
    if "WHERE" in up: notes.append("-- WHERE: фильтрация строк")
    if "GROUP BY" in up: notes.append("-- GROUP BY: группировка")
    if "ORDER BY" in up: notes.append("-- ORDER BY: сортировка")
    if "COALESCE(" in up: notes.append("-- COALESCE: замена NULL на значение")
    if "COUNT(" in up: notes.append("-- COUNT: COUNT(*) считает все строки")
    header = "/* Пояснения:\n" + "\n".join(notes) + "\n*/\n" if notes else ""
    return header + sql


st.title("🧠 AI SQL Advisor")
st.caption("Генерация корректного SQL из естественного языка. Только SELECT, без выполнения.")

if not SUPABASE_ANON_KEY:
    st.warning("⚠️ Нет SUPABASE_ANON_KEY в Secrets.")

tab_scan, tab_saved = st.tabs(["🔎 Сканировать/Генерировать", "💾 Сохранённые базы"])

# ========== TAB 1: Scan/Generate ==========
with tab_scan:
    with st.form("conn_form", clear_on_submit=False):
        db_url = st.text_input("Строка подключения к БД", placeholder="postgresql://user:pass@host/db?sslmode=require")
        schema_name = st.text_input("Схема", value="public")
        submitted = st.form_submit_button("🔎 Загрузить схему")

        if submitted:
            err = _validate_url(db_url)
            if err:
                _err_box("Некорректный URL", err)
            else:
                with st.spinner("Читаем структуру БД..."):
                    try:
                        r = _post_json("fetch_schema", {"db_url": db_url, "schema": schema_name})
                        data = r.json()
                        if r.status_code >= 400:
                            _err_box("Ошибка загрузки схемы", json.dumps(data, ensure_ascii=False, indent=2))
                        else:
                            st.session_state["schema_json"] = data
                            st.session_state["schema_warning"] = data.get("warning")
                            st.success("Схема успешно загружена.")
                    except Exception as e:
                        _err_box("Ошибка обращения к /fetch_schema", str(e))

    w = st.session_state.get("schema_warning")
    if isinstance(w, dict) and w.get("code") == "ROLE_NOT_CATALOG_ONLY":
        st.warning("⚠️ Компромиссный режим: роль имеет доступ к данным. Работаем в read-only режиме.")

    schema_json = st.session_state.get("schema_json")
    if schema_json:
        count = schema_json.get("countTables") or len(schema_json.get("tables", {}))
        _badge(f"Схема загружена • таблиц: {count}")
        with st.expander("Показать JSON-схему"):
            st.code(json.dumps(schema_json, ensure_ascii=False, indent=2), language="json")

        with st.form("save_schema_form"):
            save_name = st.text_input("Сохранить под именем", placeholder="например: neon_demo")
            if st.form_submit_button("💾 Сохранить"):
                if not save_name.strip():
                    _err_box("Имя не задано")
                else:
                    r = _schemas_post({"op": "save", "name": save_name.strip(), "schema": schema_json})
                    if r.status_code >= 400:
                        _err_box("Ошибка сохранения", r.text)
                    else:
                        st.success(f"Схема сохранена как {save_name.strip()}")

    st.markdown("---")
    nl = st.text_area("Опиши задачу", placeholder="Например: 'Покажи имена и email клиентов...'")
    col1, col2 = st.columns(2)
    with col1:
        gen = st.button("🤖 Сгенерировать SQL", use_container_width=True)
    with col2:
        clear = st.button("🧹 Очистить", use_container_width=True)
    if clear:
        st.session_state.pop("generated_sql", None)
        st.session_state.pop("usage", None)
        st.toast("Очищено.", icon="✅")

    if gen:
        if not schema_json:
            _err_box("Сначала загрузите схему.")
        elif not nl.strip():
            _err_box("Введите текст задачи.")
        else:
            payload = {"nl": nl.strip(), "schema": schema_json, "dialect": "postgres"}
            with st.spinner("Генерируем SQL..."):
                r = _post_json("generate_sql", payload)
                data = r.json()
                if data.get("blocked"):
                    st.warning("🚫 Запрос заблокирован политикой.")
                    st.caption(data.get("reason", ""))
                else:
                    st.session_state["generated_sql"] = data.get("sql")
                st.session_state["usage"] = data.get("usage")

    sql_text = st.session_state.get("generated_sql")
    usage = st.session_state.get("usage") or {}
    explain = st.checkbox("Пояснить SQL", value=False)
    if sql_text:
        final_sql = _annotate_sql(sql_text) if explain else sql_text
        st.subheader("Результат")
        st.code(final_sql, language="sql")
        copy_to_clipboard("📋 Скопировать SQL", final_sql, f"copy-{int(time.time())}")

# === ODOMETER ===
usage = st.session_state.get("usage") or {}
reset_odometer = st.button("🧮 Обнулить счётчик токенов", use_container_width=True)
if reset_odometer:
    st.components.v1.html("<script>localStorage.removeItem('ai_sql_total_usd');localStorage.removeItem('ai_sql_total_tokens');</script>", height=0)
    st.toast("Счётчик обнулён.", icon="✅")

if (usage.get("prompt_tokens") or usage.get("completion_tokens")):
    pt = int(usage.get("prompt_tokens") or 0)
    ct = int(usage.get("completion_tokens") or 0)
    total_now = pt + ct
    cost_now = (pt / 1000.0) * OPENAI_IN_PRICE + (ct / 1000.0) * OPENAI_OUT_PRICE

    st.info(f"Текущий запрос → {total_now} токенов • ${cost_now:.2f}")

    st.components.v1.html(f"""
        <script>
        let u = parseFloat(localStorage.getItem('ai_sql_total_usd') || '0');
        let t = parseInt(localStorage.getItem('ai_sql_total_tokens') || '0');
        u += {cost_now:.6f}; t += {total_now};
        localStorage.setItem('ai_sql_total_usd', u.toFixed(6));
        localStorage.setItem('ai_sql_total_tokens', t);
        </script>
    """, height=0)

# --- UI оформление счётчика ---
st.components.v1.html("""
<div style="
    margin-top: 10px;
    padding: 10px 20px;
    border: 1px solid #4B8BFF;
    border-radius: 12px;
    background-color: #1E1E1E;
    box-shadow: 0 0 12px rgba(75, 139, 255, 0.35);
    color: #E0E6FF;
    font-family: 'Inter', sans-serif;
    font-size: 16px;
    text-align: left;
">
  <b style="color:#A0BFFF;">Всего за всё время:</b><br>
  <span id="odo_line" style="color:#8AB4FF;">читаем…</span>
</div>

<script>
const usd = parseFloat(localStorage.getItem('ai_sql_total_usd') || '0');
const tok = parseInt(localStorage.getItem('ai_sql_total_tokens') || '0');
document.getElementById('odo_line').innerHTML = `${tok.toLocaleString('ru-RU')} токенов • <span style="color:#6BFFA6;">$${usd.toFixed(2)}</span>`;
</script>
""", height=70)
# === /ODOMETER ===



# ========== TAB 2: Saved Schemas ==========
with tab_saved:
    st.caption("💾 Список сохранённых схем (Storage bucket: schemas).")
    if st.button("🔄 Обновить список", use_container_width=True):
        st.session_state.pop("schemas_list", None)

    if "schemas_list" not in st.session_state:
        rr = _schemas_get()
        if rr.status_code < 400:
            st.session_state["schemas_list"] = rr.json().get("items", [])
        else:
            _err_box("Не удалось загрузить список", rr.text)

    items = st.session_state.get("schemas_list", []) or []
    names = ["—"] + [x.get("name") for x in items]
    selected = st.selectbox("Выбери схему", options=names, index=0)

    if "schema_json" not in st.session_state:
        st.info("ℹ️ Чтобы использовать Diff/Обновить, сначала загрузите схему во вкладке «Сканировать».")
    elif selected and selected != "—":
        col1, col2, col3 = st.columns(3)
        do_diff = col1.button("⚙️ Diff с текущей", use_container_width=True)
        do_update = col2.button("♻️ Обновить", use_container_width=True)
        do_delete = col3.button("🗑 Удалить", use_container_width=True)

        if do_diff:
            r = _schemas_post({"op": "diff", "name": selected, "new_schema": st.session_state["schema_json"]})
            data = r.json()
            if r.status_code >= 400:
                _err_box("Ошибка diff", json.dumps(data, ensure_ascii=False, indent=2))
            else:
                st.code(json.dumps(data.get("diff"), ensure_ascii=False, indent=2), language="json")

        if do_update:
            r = _schemas_post({"op": "update", "name": selected, "new_schema": st.session_state["schema_json"]})
            data = r.json()
            if r.status_code >= 400:
                _err_box("Ошибка обновления", json.dumps(data, ensure_ascii=False, indent=2))
            else:
                st.success(data.get("reason", "Обновлено."))

        if do_delete:
            r = _schemas_post({"op": "delete", "name": selected})
            if r.status_code < 400:
                st.success(f"Удалено: {selected}")
                st.session_state.pop("schemas_list", None)
            else:
                _err_box("Ошибка удаления", r.text)
