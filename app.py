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

# цены OpenAI за 1К токенов (в $)
OPENAI_IN_PRICE = float(st.secrets.get("OPENAI_IN_PRICE", 0))       # напр.: 0.002
OPENAI_OUT_PRICE = float(st.secrets.get("OPENAI_OUT_PRICE", 0))     # напр.: 0.006

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


# ==============================
# Helpers
# ==============================
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

# ==============================
# Pseudo-Auth (UI only)
# ==============================
with st.sidebar:
    st.subheader("🔐 Авторизация (демо)")
    if "user" not in st.session_state:
        st.session_state["user"] = None

    if st.button("Войти через Google (демо)"):
        st.session_state["user"] = {"provider": "google", "email": "demo@user.dev"}
        st.success("Вход выполнен (демо).")

    with st.form("auth_demo_form", clear_on_submit=True):
        email = st.text_input("Email")
        password = st.text_input("Пароль", type="password")
        col_a, col_b = st.columns(2)
        with col_a:
            login = st.form_submit_button("Войти (демо)")
        with col_b:
            register = st.form_submit_button("Зарегистрироваться (демо)")
        if login or register:
            if email.strip():
                st.session_state["user"] = {"provider": "password", "email": email.strip()}
                st.success("Готово. Это демо-вход без бэка.")
            else:
                st.error("Укажи email.")

    with st.expander("Забыли пароль? (демо)"):
        rp_email = st.text_input("Email для восстановления", key="rp_email")
        if st.button("Отправить ссылку (демо)"):
            if rp_email.strip():
                st.info("Ссылка на восстановление отправлена (демо).")
            else:
                st.error("Укажи email.")

    if st.session_state["user"]:
        st.caption(f"Вы вошли как: **{st.session_state['user']['email']}**")
        if st.button("Выйти"):
            st.session_state["user"] = None
            st.success("Вы вышли (демо).")
            st.rerun()

# ==============================
# Main UI
# ==============================
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

                        # пробуем распарсить ответ заранее
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
                            if not isinstance(data, dict) or "tables" not in data:
                                _err_box("Неожиданный ответ от /fetch_schema.", json.dumps(data, ensure_ascii=False, indent=2))
                            else:
                                st.session_state["schema_json"] = data
                                st.session_state["dialect"] = data.get("dialect", dialect) or dialect
                                st.success("Схема успешно загружена.")
                    except Exception as e:
                        _err_box("Ошибка при обращении к /fetch_schema.", str(e))

    # показываем карточку, если сработал catalog_gate (вне спиннера)
    if st.session_state.get("catalog_gate"):
        st.error(
            "🔒 Подключённый пользователь **имеет доступ к данным**.\n\n"
            "Для безопасности генератор разрешает только **catalog-only** роли (без `SELECT` на пользовательские таблицы).\n\n"
            "Что можно сделать:\n"
            "• использовать в своей БД отдельного пользователя без прав `SELECT`;\n"
            "• или переключиться на режим **Offline JSON Schema** (загрузка схемы без подключения к БД — скоро добавим).\n"
        )
        st.session_state["catalog_gate"] = False

    # — Генерация SQL
    schema_json = st.session_state.get("schema_json")
    st.markdown("---")
    st.subheader("Сформулируй задачу")
    nl = st.text_area("Например: «Покажи имена и email клиентов, сделавших заказ за последние 7 дней»", height=90)
    c1, c2, c3 = st.columns([1, 1, 1])

    with c1:
        gen = st.button("🤖 Сгенерировать SQL", use_container_width=True)
    with c2:
        clear = st.button("🧹 Очистить", use_container_width=True)
    with c3:
        reset_usage = st.button("🔄 Обнулить счётчик токенов", use_container_width=True)

    if clear:
        st.session_state.pop("generated_sql", None)
        st.session_state.pop("usage", None)
        st.toast("Очищено.", icon="✅")

    if reset_usage:
        st.session_state.pop("usage", None)
        st.toast("Счётчик токенов обнулён.", icon="✅")

    if gen:
        if not schema_json:
            _err_box("Сначала загрузите схему.", "Нажми «Загрузить схему» и убедись, что она подтянулась.")
        elif not nl.strip():
            _err_box("Пустой запрос.", "Заполни текстовое поле с задачей.")
        else:
            payload = {
                "nl": nl.strip(),
                "schema": schema_json,
                "dialect": (st.session_state.get("dialect") or "postgres"),
            }
            with st.spinner("Генерируем SQL…"):
                try:
                    r = _post_json("generate_sql", payload)
                    data = {}
                    try:
                        data = r.json()
                    except Exception:
                        pass

                    if r.status_code >= 500:
                        _err_box("Серверная ошибка функций (5xx).", json.dumps(data, ensure_ascii=False, indent=2))
                    else:
                        if isinstance(data, dict) and data.get("blocked"):
                            st.warning("🚫 Запрос заблокирован политикой/валидацией.")
                            st.caption(str(data.get("reason", "")))
                            st.session_state["generated_sql"] = None
                        else:
                            st.session_state["generated_sql"] = (data.get("sql") if isinstance(data, dict) else None)

                        # usage подсчёт и стоимость
                        usage = (data.get("usage") if isinstance(data, dict) else {}) or {}
                        pt = int(usage.get("prompt_tokens") or 0)
                        ct = int(usage.get("completion_tokens") or 0)
                        tt = int(usage.get("total_tokens") or (pt + ct))
                        st.session_state["usage"] = {
                            "prompt_tokens": pt,
                            "completion_tokens": ct,
                            "total_tokens": tt,
                        }
                except Exception as e:
                    _err_box("Ошибка при обращении к /generate_sql.", str(e))

    # чекбокс «Пояснить SQL»
    sql_text = st.session_state.get("generated_sql")
    explain = st.checkbox("Пояснить SQL (добавить комментарии)", value=False)

    if sql_text:
        final_sql = _annotate_sql(sql_text) if explain else sql_text
        st.subheader("Результат")
        st.code(final_sql, language="sql")
        copy_to_clipboard("📋 Скопировать SQL", final_sql, key=f"copybtn-{int(time.time())}")

    # ——————— БЛОК СТОИМОСТИ / USAGE (персистентный счётчик в браузере) ———————
usage = st.session_state.get("usage") or {}

# кнопка сброса "одометра"
reset_odometer = st.button("🧮 Обнулить счётчик токенов", use_container_width=True)

# если нажали — чистим локальный счётчик в браузере
if reset_odometer:
    st.components.v1.html("""
        <script>
          localStorage.removeItem('ai_sql_total_usd');
          localStorage.removeItem('ai_sql_total_tokens');
        </script>
    """, height=0)
    st.toast("Счётчик обнулён.", icon="✅")

# показываем разовый расход за текущий запрос (если есть)
if (usage.get("prompt_tokens") is not None) or (usage.get("completion_tokens") is not None):
    pt = int(usage.get("prompt_tokens") or 0)
    ct = int(usage.get("completion_tokens") or 0)
    total_now = int(usage.get("total_tokens") or (pt + ct))
    # стоимость за этот запрос
    cost_now = 0.0
    if OPENAI_IN_PRICE > 0 or OPENAI_OUT_PRICE > 0:
        cost_now = (pt/1000.0)*OPENAI_IN_PRICE + (ct/1000.0)*OPENAI_OUT_PRICE

    # отображаем разовый расход
    st.info(f"Текущий запрос → токены: prompt={pt}, completion={ct}, total={total_now} • Стоимость: ${cost_now:.2f}")

    # прибавляем к "одометру" в браузере
    st.components.v1.html(f"""
        <script>
          const deltaUsd = {cost_now:.6f};
          const deltaTok = {total_now};

          const K_USD = 'ai_sql_total_usd';
          const K_TOK = 'ai_sql_total_tokens';

          let usd = parseFloat(localStorage.getItem(K_USD) || '0');
          let tok = parseInt(localStorage.getItem(K_TOK) || '0');

          usd = (usd + deltaUsd);
          tok = (tok + deltaTok);

          localStorage.setItem(K_USD, usd.toFixed(6));
          localStorage.setItem(K_TOK, String(tok));
        </script>
    """, height=0)

# рисуем "одометр" (сумма за всё время в этом браузере)
st.components.v1.html("""
  <div id="ai-sql-odometer" style="margin-top:6px;padding:10px;border:1px solid #374151;border-radius:10px;">
    <b>Всего за всё время (на этом устройстве):</b>
    <div id="ai-sql-odometer-line" style="margin-top:4px;">читаем…</div>
  </div>
  <script>
    const usd = parseFloat(localStorage.getItem('ai_sql_total_usd') || '0');
    const tok = parseInt(localStorage.getItem('ai_sql_total_tokens') || '0');
    const line = document.getElementById('ai-sql-odometer-line');
    if (line) {{
      line.textContent = `${{tok}} токенов • $${{usd.toFixed(2)}}`;
    }}
  </script>
""", height=70)

# если цены не заданы — подсказываем
if OPENAI_IN_PRICE == 0 and OPENAI_OUT_PRICE == 0:
    st.caption("ℹ️ Укажи OPENAI_IN_PRICE и OPENAI_OUT_PRICE в Secrets, чтобы видеть стоимость в $.")
# ——————— /БЛОК СТОИМОСТИ ———————


    # показ загруженной схемы + сохранение
    if schema_json:
        count = schema_json.get("countTables") or (len(schema_json.get("tables", {})) if isinstance(schema_json.get("tables"), dict) else None)
        _badge(f"Схема загружена • таблиц: {count if count is not None else '?'}")
        with st.expander("Показать JSON-схему"):
            st.code(json.dumps(schema_json, ensure_ascii=False, indent=2), language="json")

        with st.form("save_schema_form", clear_on_submit=True):
            save_name = st.text_input("Сохранить схему под именем", placeholder="например: neon_demo")
            save_btn = st.form_submit_button("💾 Сохранить схему")
            if save_btn:
                if not save_name.strip():
                    _err_box("Имя не задано", "Укажи короткое имя (латиница/цифры/нижнее подчёркивание).")
                else:
                    try:
                        r = _post_json(
                            "schemas",
                            {"op": "save", "name": save_name.strip(), "schema": schema_json, "dialect": (st.session_state.get("dialect") or "postgres")}
                        )
                        if r.status_code >= 400:
                            _err_box("Не удалось сохранить схему", r.text[:2000])
                        else:
                            st.success(f"Схема сохранена как «{save_name}».")
                    except Exception as e:
                        _err_box("Ошибка при сохранении схемы", str(e))

# ——————— TAB 2: Сохранённые базы ———————
with tab_saved:
    st.caption("Список ранее сохранённых «сканов» схем (Storage bucket: schemas).")

    c_refresh, _ = st.columns([1, 3])
    with c_refresh:
        if st.button("🔄 Обновить список", use_container_width=True):
            st.session_state.pop("schemas_list", None)

    # Подгружаем список схем
    if "schemas_list" not in st.session_state:
        try:
            rr = _schemas_get()
            if rr.status_code >= 400:
                _err_box("Не удалось загрузить список схем", rr.text[:2000])
            else:
                st.session_state["schemas_list"] = rr.json().get("items", [])
        except Exception as e:
            _err_box("Ошибка при загрузке списка", str(e))

    items = st.session_state.get("schemas_list", []) or []
    names = ["—"] + [it.get("name") for it in items]

    selected = st.selectbox("Выбери схему", options=names, index=0)
    if selected and selected != "—":
        st.text_input("Имя схемы", value=selected, disabled=True)

        colA, colB, colC = st.columns([1, 1, 1])
        can_diff = "schema_json" in st.session_state
        can_update = "schema_json" in st.session_state

        do_diff = colA.button("⚙️ Diff с текущей", use_container_width=True, disabled=not can_diff)
        do_update = colB.button("♻️ Обновить сохранённую", use_container_width=True, disabled=not can_update)
        do_delete = colC.button("🗑 Удалить", use_container_width=True)

        if do_diff:
            try:
                payload = {"op": "diff", "name": selected, "new_schema": st.session_state["schema_json"]}
                r = _schemas_post(payload)
                data = r.json()
                if r.status_code >= 400:
                    _err_box("Diff не выполнился", json.dumps(data, ensure_ascii=False, indent=2))
                else:
                    diff = data.get("diff") or {}
                    with st.expander("Результат сравнения (diff)", expanded=True):
                        st.code(json.dumps(diff, ensure_ascii=False, indent=2), language="json")
                    st.toast("Diff готов.", icon="✅")
            except Exception as e:
                _err_box("Ошибка diff", str(e))

        if do_update:
            try:
                payload = {"op": "update", "name": selected, "new_schema": st.session_state["schema_json"]}
                r = _schemas_post(payload)
                data = r.json()
                if r.status_code >= 400:
                    _err_box("Не удалось обновить схему", json.dumps(data, ensure_ascii=False, indent=2))
                else:
                    if data.get("updated"):
                        st.success("Схема обновлена.")
                    else:
                        st.info(data.get("reason", "Изменений не обнаружено."))
                    st.session_state.pop("schemas_list", None)
            except Exception as e:
                _err_box("Ошибка обновления", str(e))

        if do_delete:
            try:
                r = _schemas_post({"op": "delete", "name": selected})
                data = r.json()
                if r.status_code >= 400:
                    _err_box("Не удалось удалить схему", json.dumps(data, ensure_ascii=False, indent=2))
                else:
                    st.success(f"Удалено: {selected}")
                    st.session_state.pop("schemas_list", None)
            except Exception as e:
                _err_box("Ошибка удаления", str(e))

    st.markdown("---")
    st.caption("Чтобы обновить схему, просто загрузите новую во вкладке «Сканировать/Генерировать» и сохраните под тем же именем — произойдёт upsert.")
