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

# цены OpenAI за 1К токенов (в $) — задай в Secrets
OPENAI_IN_PRICE = float(st.secrets.get("OPENAI_IN_PRICE", 0))       # например: 0.002
OPENAI_OUT_PRICE = float(st.secrets.get("OPENAI_OUT_PRICE", 0))     # например: 0.006

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
    if "SELECT" in up:   notes.append("-- SELECT: какие колонки выводим")
    if "FROM" in up:     notes.append("-- FROM: из какой таблицы берём данные")
    if "JOIN" in up:     notes.append("-- JOIN: объединяем таблицы (LEFT JOIN — берём всех слева)")
    if "WHERE" in up:    notes.append("-- WHERE: фильтрация строк по условию")
    if "GROUP BY" in up: notes.append("-- GROUP BY: группируем строки")
    if "HAVING" in up:   notes.append("-- HAVING: фильтр по агрегатам после GROUP BY")
    if "ORDER BY" in up: notes.append("-- ORDER BY: сортировка результата")
    if "COALESCE(" in up:notes.append("-- COALESCE: подставляет значение по умолчанию, если NULL")
    if "EXTRACT(" in up: notes.append("-- EXTRACT: достаёт часть даты/времени (YEAR, MONTH и т.д.)")
    if "COUNT(" in up:   notes.append("-- COUNT: COUNT(*) считает строки; COUNT(col) пропускает NULL")
    header = "/* Краткие пояснения к запросу:\n" + "\n".join(notes) + "\n*/\n" if notes else ""
    return header + sql

st.title("🧠 AI SQL Advisor")
st.caption("Генерируем корректный SQL из естественного языка. Только SELECT. Без выполнения.")

if not SUPABASE_ANON_KEY:
    st.warning("⚠️ В секрете Streamlit отсутствует SUPABASE_ANON_KEY. Добавьте его в Settings → Secrets.")

tab_scan, tab_saved = st.tabs(["🔎 Сканировать/Генерировать", "💾 Сохранённые базы"])

# ——————— TAB 1: Сканирование + Генерация ———————
with tab_scan:
    with st.form("conn_form", clear_on_submit=False):
        db_url = st.text_input(
            "Строка подключения к БД (Postgres, read-only)",
            placeholder="postgresql://user:pass@host:5432/dbname?sslmode=require",
        )
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

                        # === Friendly handling for catalog-only gate ===
                        try:
                            data = r.json()
                        except Exception:
                            data = {}

                        if r.status_code == 403 and isinstance(data, dict) and data.get("code") == "ROLE_NOT_CATALOG_ONLY":
                            st.error(
                                "🔒 Подключённый пользователь **имеет доступ к данным**.\n\n"
                                "Для безопасности генератор разрешает только **catalog-only** роли (без `SELECT` на пользовательские таблицы).\n\n"
                                "Что можно сделать:\n"
                                "• использовать в своей БД отдельного пользователя без прав `SELECT`;\n"
                                "• или переключиться на режим **Offline JSON Schema** (загрузка схемы без подключения к БД — скоро добавим).\n",
                                icon="lock",
                            )
                            st.stop()
                        # === /Friendly handling ===

                        if r.status_code in (401,403):
                            _err_box("Нет доступа к функции (401/403).", r.text[:2000])
                        elif r.status_code >= 500:
                            _err_box("Серверная ошибка функций (5xx).", r.text[:2000])
                        else:
                            if not isinstance(data, dict) or "tables" not in data:
                                _err_box("Неожиданный ответ от /fetch_schema.", json.dumps(data, ensure_ascii=False, indent=2))
                            else:
                                st.session_state["schema_json"] = data
                                st.session_state["dialect"] = data.get("dialect", dialect) or dialect
                                st.success("Схема успешно загружена.")
                    except Exception as e:
                        _err_box("Ошибка при обращении к /fetch_schema.", str(e))

    schema_json = st.session_state.get("schema_json")
    if schema_json:
        count = schema_json.get("countTables") or (len(schema_json.get("tables", {})) if isinstance(schema_json.get("tables"), dict) else None)
        _badge(f"Схема загружена • таблиц: {count if count is not None else '?'}")
        with st.expander("Показать JSON-схему"):
            st.code(json.dumps(schema_json, ensure_ascii=False, indent=2), language="json")

        # сохранение схемы в Storage через /schemas
        with st.form("save_schema_form", clear_on_submit=True):
            save_name = st.text_input("Сохранить схему под именем", placeholder="например: neon_demo")
            save_btn = st.form_submit_button("💾 Сохранить схему")
            if save_btn:
                if not save_name.strip():
                    _err_box("Имя не задано", "Укажи короткое имя (латиница/цифры/нижнее подчёркивание).")
                else:
                    try:
                        r = _post_json("schemas", {"op": "save", "name": save_name.strip(), "schema": schema_json, "dialect": st.session_state.get("dialect","postgres")})
                        if r.status_code >= 400:
                            _err_box("Не удалось сохранить схему", r.text[:2000])
                        else:
                            st.success(f"Схема сохранена как «{save_name}».")
                    except Exception as e:
                        _err_box("Ошибка при сохранении схемы", str(e))

    st.markdown("---")
    st.subheader("Сформулируй задачу")
    nl = st.text_area("Например: «Покажи имена и email клиентов, сделавших заказ за последние 7 дней»", height=90)
    c1, c2 = st.columns([1, 1])
    with c1:
        gen = st.button("🤖 Сгенерировать SQL", use_container_width=True)
    with c2:
        clear = st.button("🧹 Очистить", use_container_width=True)

    if clear:
        st.session_state.pop("generated_sql", None)
        st.session_state.pop("usage", None)
        st.toast("Очищено.", icon="✅")

    if gen:
        if not schema_json:
            _err_box("Сначала загрузите схему.", "Нажми «Загрузить схему» и убедись, что она подтянулась.")
        elif not nl.strip():
            _err_box("Пустой запрос.", "Заполни текстовое поле с задачей.")
        else:
            payload = {
                "nl": nl.strip(),
                "schema": schema_json,
                "dialect": st.session_state.get("dialect", "postgres"),
            }
            with st.spinner("Генерируем SQL…"):
                try:
                    r = _post_json("generate_sql", payload)
                    data = r.json()
                    if r.status_code >= 500:
                        _err_box("Серверная ошибка функций (5xx).", json.dumps(data, ensure_ascii=False, indent=2))
                    else:
                        if data.get("blocked"):
                            st.warning("🚫 Запрос заблокирован политикой/валидацией.")
                            st.caption(str(data.get("reason", "")))
                            st.session_state["generated_sql"] = None
                        else:
                            st.session_state["generated_sql"] = data.get("sql")
                        st.session_state["usage"] = data.get("usage")
                except Exception as e:
                    _err_box("Ошибка при обращении к /generate_sql.", str(e))

    sql_text = st.session_state.get("generated_sql")
    usage = st.session_state.get("usage") or {}
    explain = st.checkbox("Пояснить SQL (добавить комментарии)", value=False)

    if sql_text:
        final_sql = _annotate_sql(sql_text) if explain else sql_text
        st.subheader("Результат")
        st.code(final_sql, language="sql")
        copy_to_clipboard("📋 Скопировать SQL", final_sql, key=f"copybtn-{int(time.time())}")

    # блок стоимости/usage
    if usage and (usage.get("prompt_tokens") is not None or usage.get("completion_tokens") is not None):
        pt = usage.get("prompt_tokens") or 0
        ct = usage.get("completion_tokens") or 0
        total = (usage.get("total_tokens") or (pt + ct))
        cost = 0.0
        if OPENAI_IN_PRICE > 0 or OPENAI_OUT_PRICE > 0:
            cost = (pt/1000.0)*OPENAI_IN_PRICE + (ct/1000.0)*OPENAI_OUT_PRICE
        st.info(f"Токены: prompt={pt}, completion={ct}, total={total} • Стоимость: ${cost:.2f}")
    elif OPENAI_IN_PRICE == 0 and OPENAI_OUT_PRICE == 0:
        st.caption("ℹ️ Укажи OPENAI_IN_PRICE и OPENAI_OUT_PRICE в Secrets, чтобы видеть стоимость в $.")

# ——————— TAB 2: Сохранённые базы ———————
with tab_saved:
    st.caption("Список ранее сохранённых «сканов» схем (Storage bucket: schemas).")
    if st.button("🔄 Обновить список"):
        st.session_state.pop("schemas_list", None)

    if "schemas_list" not in st.session_state:
        try:
            rr = _get("schemas")
            if rr.status_code >= 400:
                _err_box("Не удалось загрузить список схем", rr.text[:2000])
            else:
                st.session_state["schemas_list"] = rr.json().get("items", [])
        except Exception as e:
            _err_box("Ошибка при загрузке списка", str(e))

    items = st.session_state.get("schemas_list", [])
    names = [it.get("name") for it in items] if items else []
    selected = st.selectbox("Выбери схему", options=["—"] + names, index=0)

    if selected and selected != "—":
        st.write(f"Выбрана схема: **{selected}**")
        st.caption("Сейчас держим только список имён. Для подгрузки JSON можно сделать /schemas/get (при необходимости).")
        st.info("Пока используем схему из текущей сессии (вкладка «Сканировать/Генерировать»). Чтобы обновить, перезагрузи схему и сохрани заново под тем же именем — в Storage произойдёт upsert.")
