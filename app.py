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


def _err_box(msg: str, details: str | None = None):
    st.error(msg)
    if details:
        with st.expander("Подробнее об ошибке"):
            st.code(details, language="text")


def _post_json(path: str, payload: dict, timeout=40) -> requests.Response:
    url = f"{FUNC_BASE}/{path.lstrip('/')}"
    return requests.post(url, headers=HEADERS, data=json.dumps(payload), timeout=timeout)


def _get(path: str, timeout=40) -> requests.Response:
    url = f"{FUNC_BASE}/{path.lstrip('/')}"
    return requests.get(url, headers=HEADERS, timeout=timeout)


def _validate_url(db_url: str) -> str | None:
    if not db_url:
        return "Введите строку подключения к БД (db_url)."
    if not db_url.startswith(("postgresql://", "postgres://")):
        return "Сейчас поддерживается Postgres. URL должен начинаться с postgresql:// или postgres://"
    if "@" not in db_url or ":" not in db_url:
        return "Похоже, в URL нет логина/пароля или хоста. Проверьте формат."
    if "sslmode=" not in db_url:
        return "Рекомендуется добавить ?sslmode=require к строке подключения."
    return None


def _badge(text: str):
    st.markdown(
        f"<span style='background:#10b98120;color:#065f46;padding:4px 10px;border-radius:999px;font-size:12px;border:1px solid #10b98150;'>{text}</span>",
        unsafe_allow_html=True,
    )


def copy_to_clipboard(label: str, text_to_copy: str, key: str):
    st.components.v1.html(f"""
        <div><button id="{key}" style="padding:6px 10px;border-radius:8px;border:1px solid #e5e7eb;cursor:pointer;">
            {label}
        </button></div>
        <script>
            const btn = document.getElementById("{key}");
            if (btn) {{
                btn.addEventListener("click", async () => {{
                    try {{
                        await navigator.clipboard.writeText({json.dumps(text_to_copy)});
                        btn.innerText = "Скопировано ✓";
                        setTimeout(() => btn.innerText = {json.dumps(label)}, 1500);
                    }} catch (e) {{
                        btn.innerText = "Не вышло :(";
                        setTimeout(() => btn.innerText = {json.dumps(label)}, 1500);
                    }}
                }});
            }}
        </script>
    """, height=50)


def _annotate_sql(sql: str) -> str:
    notes = []
    up = sql.upper()
    if "SELECT" in up: notes.append("-- SELECT: какие колонки выводим")
    if "FROM" in up: notes.append("-- FROM: из какой таблицы берём данные")
    if "JOIN" in up: notes.append("-- JOIN: объединяем таблицы (LEFT JOIN — берём всех слева)")
    if "WHERE" in up: notes.append("-- WHERE: фильтрация строк по условию")
    if "GROUP BY" in up: notes.append("-- GROUP BY: группируем строки")
    if "HAVING" in up: notes.append("-- HAVING: фильтр по агрегатам после GROUP BY")
    if "ORDER BY" in up: notes.append("-- ORDER BY: сортировка результата")
    if "COALESCE(" in up: notes.append("-- COALESCE: подставляет значение по умолчанию, если NULL")
    if "EXTRACT(" in up: notes.append("-- EXTRACT: достаёт часть даты/времени (YEAR, MONTH и т.д.)")
    if "COUNT(" in up: notes.append("-- COUNT: COUNT(*) считает строки; COUNT(col) пропускает NULL")
    header = "/* Краткие пояснения к запросу:\n" + "\n".join(notes) + "\n*/\n" if notes else ""
    return header + sql


st.title("🧠 AI SQL Advisor")
st.caption("Генерируем корректный SQL из естественного языка. Только SELECT. Без выполнения.")

if not SUPABASE_ANON_KEY:
    st.warning("⚠️ В секрете Streamlit отсутствует SUPABASE_ANON_KEY. Добавьте его в Settings → Secrets.")

tab_scan, tab_saved = st.tabs(["🔎 Сканировать/Генерировать", "💾 Сохранённые базы"])

# ——————— TAB 1 ———————
with tab_scan:
    with st.form("conn_form", clear_on_submit=False):
        db_url = st.text_input("Строка подключения к БД (Postgres, read-only)", placeholder="postgresql://user:pass@host:5432/dbname?sslmode=require")
        col1, col2 = st.columns([1,1])
        with col1:
            schema_name = st.text_input("Схема", value="public")
        with col2:
            dialect = st.selectbox("Диалект (пока только Postgres)", options=["postgres"], index=0)

        submitted = st.form_submit_button("🔎 Загрузить схему")
        if submitted:
            err = _validate_url(db_url)
            if err:
                _err_box("Некорректный db_url", err)
            else:
                with st.spinner("Читаем структуру БД…"):
                    try:
                        r = _post_json("fetch_schema", {"db_url": db_url, "schema": schema_name})
                        try:
                            data = r.json()
                        except Exception:
                            data = {}

                        # === Friendly handling for catalog-only gate ===
                        if r.status_code == 403 and isinstance(data, dict) and data.get("code") == "ROLE_NOT_CATALOG_ONLY":
                            st.session_state["catalog_gate"] = True
                            st.rerun()
                        # === /Friendly handling ===

                        if r.status_code in (401,403):
                            _err_box("Нет доступа к функции (401/403).", r.text[:2000])
                        elif r.status_code >= 500:
                            _err_box("Серверная ошибка функций (5xx).", r.text[:2000])
                        else:
                            data = r.json()
                            if not isinstance(data, dict) or "tables" not in data:
                                _err_box("Неожиданный ответ от /fetch_schema.", json.dumps(data, ensure_ascii=False, indent=2))
                            else:
                                st.session_state["schema_json"] = data
                                st.session_state["dialect"] = data.get("dialect", dialect) or dialect
                                st.success("Схема успешно загружена.")
                    except Exception as e:
                        _err_box("Ошибка при обращении к /fetch_schema.", str(e))

    # показываем карточку, если сработал catalog_gate
    if st.session_state.get("catalog_gate"):
        st.error(
            "🔒 Подключённый пользователь **имеет доступ к данным**.\n\n"
            "Для безопасности генератор разрешает только **catalog-only** роли (без `SELECT` на пользовательские таблицы).\n\n"
            "Что можно сделать:\n"
            "• использовать в своей БД отдельного пользователя без прав `SELECT`;\n"
            "• или переключиться на режим **Offline JSON Schema** (загрузка схемы без подключения к БД — скоро добавим).\n"
        )
        st.session_state["catalog_gate"] = False

    # остальной код UI без изменений
    schema_json = st.session_state.get("schema_json")
    if schema_json:
        count = schema_json.get("countTables") or (len(schema_json.get("tables", {})) if isinstance(schema_json.get("tables"), dict) else None)
        _badge(f"Схема загружена • таблиц: {count if count is not None else '?'}")
        with st.expander("Показать JSON-схему"):
            st.code(json.dumps(schema_json, ensure_ascii=False, indent=2), language="json")
