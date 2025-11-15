"""
Streamlit dashboard for monitoring comment sentiment.

This module provides data-loading helpers and aggregation utilities that the
Streamlit UI layer can reuse.  The UI components will be defined below these
helpers so that tests (or CLI experiments) can import the functions without
initialising Streamlit.
"""
from __future__ import annotations

import os
import requests
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import streamlit as st
import altair as alt
from sqlalchemy import create_engine, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from config.settings import Settings
from database.models import Comment


# -----------------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------------


def check_password() -> bool:
    """
    Проверка пароля для доступа к dashboard
    Возвращает True если пользователь авторизован
    """
    # Получаем пароль из переменной окружения
    correct_password = os.getenv("DASHBOARD_PASSWORD", "admin123")
    
    # Если уже авторизован
    if st.session_state.get("authenticated", False):
        return True
    
    # Форма входа
    st.title("🔐 Вход в систему")
    st.markdown("Введите пароль для доступа к dashboard")
    
    with st.form("login_form"):
        password = st.text_input("Пароль", type="password")
        submit = st.form_submit_button("Войти")
        
        if submit:
            if password == correct_password:
                st.session_state["authenticated"] = True
                st.success("✅ Авторизация успешна!")
                st.rerun()
            else:
                st.error("❌ Неверный пароль")
    
    return False


# -----------------------------------------------------------------------------
# Data access helpers
# -----------------------------------------------------------------------------


def _resolve_db_path(db_path: Optional[str] = None) -> Path:
    """
    Resolve the SQLite database path.

    If the caller does not provide a path we fall back to the application
    settings (env var `DB_PATH`, default `comments.db`).
    """
    if db_path:
        return Path(db_path).expanduser().resolve()

    Settings.load()
    return Path(Settings.DB_PATH).expanduser().resolve()


def create_sqlite_engine(db_path: Optional[str] = None) -> Engine:
    """Create a SQLAlchemy engine for the SQLite comments database."""
    resolved = _resolve_db_path(db_path)
    return create_engine(
        f"sqlite:///{resolved}",
        connect_args={"check_same_thread": False},
    )


def get_session(engine: Engine) -> Session:
    """Get a SQLAlchemy session bound to the provided engine."""
    from sqlalchemy.orm import sessionmaker

    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


# -----------------------------------------------------------------------------
# Data loading & aggregation layer
# -----------------------------------------------------------------------------


def fetch_comments_dataframe(
    engine: Engine,
    date_range: Optional[Tuple[datetime, datetime]] = None,
    source: Optional[str] = None,
) -> pd.DataFrame:
    """
    Load comments into a pandas DataFrame applying optional filters.

    Parameters
    ----------
    engine:
        SQLAlchemy engine pointing to the comments database.
    date_range:
        Optional tuple (start_datetime, end_datetime).  Boundaries are inclusive.
    source:
        Optional platform filter. Accepts `'vk'`, `'telegram'`, or `None` for all.
    """
    with engine.connect() as conn:
        stmt = select(Comment)
        if source and source != "all":
            stmt = stmt.filter(Comment.source == source)

        if date_range:
            start, end = date_range
            if start:
                stmt = stmt.filter(Comment.comment_published_at >= start)
            if end:
                stmt = stmt.filter(Comment.comment_published_at <= end)

        df = pd.read_sql(stmt, conn)

    if not df.empty:
        datetime_columns = [
            "post_published_at",
            "comment_published_at",
            "parsed_at",
        ]
        for column in datetime_columns:
            if column in df.columns:
                df[column] = pd.to_datetime(df[column])

    return df


def sentiment_breakdown(df: pd.DataFrame) -> pd.Series:
    """
    Return sentiment distribution including 'undefined' bucket.

    The database stores `None` for unprocessed comments; they are reported as
    `'undefined'` so the frontend can display them explicitly.
    """
    if df.empty:
        return pd.Series(dtype=int)

    sentiments = df["sentiment"].fillna("undefined")
    return sentiments.value_counts().reindex(
        ["positive", "negative", "neutral", "undefined"], fill_value=0
    )


def daily_sentiment_percentages(df: pd.DataFrame) -> pd.DataFrame:
    """
    Aggregate sentiment percentages by day.

    The resulting frame has columns:
        - `date` (datetime) – the date
        - `positive_pct` (percentage of positive)
        - `negative_pct` (percentage of negative)
        - `neutral_pct` (percentage of neutral)
    """
    if df.empty:
        return pd.DataFrame(columns=["date", "positive_pct", "negative_pct", "neutral_pct"])

    # Filter only comments with sentiment defined
    filtered = df[df["sentiment"].isin(["positive", "negative", "neutral"])].copy()
    if filtered.empty:
        return pd.DataFrame(columns=["date", "positive_pct", "negative_pct", "neutral_pct"])

    # Extract date only (without time)
    filtered["date"] = filtered["comment_published_at"].dt.date

    # Count sentiments per day
    grouped = filtered.groupby("date")["sentiment"].value_counts().unstack(fill_value=0)
    grouped = grouped.reindex(columns=["positive", "negative", "neutral"], fill_value=0)
    
    # Calculate total per day and percentages (keep raw counts for tooltip)
    grouped["total"] = grouped.sum(axis=1)
    grouped["positive_pct"] = (grouped["positive"] / grouped["total"] * 100)
    grouped["negative_pct"] = (grouped["negative"] / grouped["total"] * 100)
    grouped["neutral_pct"] = (grouped["neutral"] / grouped["total"] * 100)
    
    # Keep counts for tooltip
    grouped["positive_count"] = grouped["positive"]
    grouped["negative_count"] = grouped["negative"]
    grouped["neutral_count"] = grouped["neutral"]
    
    # Reset index and convert date back to datetime for plotting
    grouped = grouped.reset_index()
    grouped["date"] = pd.to_datetime(grouped["date"])
    
    return grouped[["date", "positive_pct", "negative_pct", "neutral_pct", 
                    "positive_count", "negative_count", "neutral_count"]].sort_values("date")


def get_comment_date_bounds(engine: Engine) -> Tuple[Optional[datetime], Optional[datetime]]:
    """Return min/max `comment_published_at` timestamps."""
    with engine.connect() as conn:
        result = conn.execute(
            select(
                func.min(Comment.comment_published_at),
                func.max(Comment.comment_published_at),
            )
        ).first()

    if not result:
        return None, None

    return result[0], result[1]


def get_available_sources(engine: Engine) -> list[str]:
    """Fetch distinct sources from the comments table."""
    with engine.connect() as conn:
        rows = conn.execute(select(Comment.source).distinct()).fetchall()
    return sorted({row[0] for row in rows if row[0]})


@dataclass
class PostSummary:
    post_url: str
    group_channel_name: str
    comment_count: int
    negative_count: int


def post_highlights(df: pd.DataFrame) -> Tuple[Optional[PostSummary], Optional[PostSummary]]:
    """
    Determine posts with most comments and most negative comments.

    Returns
    -------
    tuple(PostSummary | None, PostSummary | None)
        First item is the post with the highest total comment count.
        Second item is the post with the highest negative comment count.
    """
    if df.empty:
        return None, None

    grouped = (
        df.groupby(["post_url", "group_channel_name"])
        .agg(
            comment_count=("id", "count"),
            negative_count=(
                "sentiment",
                lambda s: (s == "negative").sum(),
            ),
        )
        .reset_index()
    )

    if grouped.empty:
        return None, None

    top_comment_row = grouped.sort_values("comment_count", ascending=False).iloc[0]
    top_negative_row = grouped.sort_values("negative_count", ascending=False).iloc[0]

    top_comment = PostSummary(
        post_url=top_comment_row["post_url"],
        group_channel_name=top_comment_row["group_channel_name"],
        comment_count=int(top_comment_row["comment_count"]),
        negative_count=int(top_comment_row["negative_count"]),
    )

    top_negative = PostSummary(
        post_url=top_negative_row["post_url"],
        group_channel_name=top_negative_row["group_channel_name"],
        comment_count=int(top_negative_row["comment_count"]),
        negative_count=int(top_negative_row["negative_count"]),
    )

    return top_comment, top_negative


def prepare_raw_table(df: pd.DataFrame) -> pd.DataFrame:
    """
    Return a cleaned dataframe for the raw data table.

    Applies basic sorting and ensures datetime columns are formatted.
    """
    if df.empty:
        return df

    columns_order = [
        "id",
        "source",
        "group_channel_name",
        "post_url",
        "comment_url",
        "author_name",
        "comment_text",
        "sentiment",
        "sentiment_score",
        "comment_published_at",
        "parsed_at",
    ]

    available_columns = [col for col in columns_order if col in df.columns]
    remainder = [col for col in df.columns if col not in available_columns]

    table = df[available_columns + remainder].copy()
    table = table.sort_values("comment_published_at", ascending=False)
    return table.reset_index(drop=True)


def render_header(db_path: Path) -> None:
    st.set_page_config(
        page_title="Unified Monitor Dashboard",
        layout="wide",
        page_icon="📊",
    )
    st.title("Unified Monitor — дашборд комментариев")
    st.caption(
        f"Источник данных: `{db_path}`. "
        "Настройте путь и фильтры в левом сайдбаре."
    )


def sidebar_controls(default_db_path: Path) -> tuple[Path, tuple[datetime, datetime], str]:
    st.sidebar.header("⚙️ Настройки")

    db_path_str = st.sidebar.text_input(
        "Путь к базе SQLite",
        value=str(default_db_path),
    )
    db_path = Path(db_path_str).expanduser()

    try:
        engine = create_sqlite_engine(str(db_path))
        min_date, max_date = get_comment_date_bounds(engine)
    except Exception as exc:  # pragma: no cover - Streamlit feedback
        st.sidebar.error(f"Не удалось подключиться к базе: {exc}")
        raise

    if not db_path.exists():
        st.sidebar.warning("Файл базы данных не найден — проверьте путь.")

    if not min_date or not max_date:
        default_start = datetime.utcnow() - timedelta(days=7)
        default_end = datetime.utcnow()
    else:
        default_start = min_date
        default_end = max_date

    period = st.sidebar.date_input(
        "Период комментариев",
        value=(default_start.date(), default_end.date()),
        min_value=(min_date.date() if min_date else None),
        max_value=(max_date.date() if max_date else None),
    )

    if isinstance(period, tuple):
        if len(period) == 2:
            start_date, end_date = period
        elif len(period) == 1:
            start_date = end_date = period[0]
        else:
            # Fallback
            start_date = end_date = default_start.date()
    else:
        # Single date selected
        start_date = end_date = period

    # Convert to datetime boundaries inclusive
    start_dt = datetime.combine(start_date, datetime.min.time())
    end_dt = datetime.combine(end_date, datetime.max.time())

    sources = get_available_sources(engine)
    source_option = st.sidebar.selectbox(
        "Площадка",
        options=["all"] + sources,
        format_func=lambda value: {
            "all": "Все площадки",
            "vk": "ВКонтакте",
            "telegram": "Telegram",
        }.get(value, value),
    )

    return db_path, (start_dt, end_dt), source_option


def kpi_section(df: pd.DataFrame) -> None:
    total_comments = int(len(df))
    sentiments = sentiment_breakdown(df)

    positive = int(sentiments.get("positive", 0))
    negative = int(sentiments.get("negative", 0))
    neutral = int(sentiments.get("neutral", 0))
    undefined = int(sentiments.get("undefined", 0))

    st.subheader("Сводка по тональностям")
    col_total, col_pos, col_neg, col_neu, col_undef = st.columns(5)
    col_total.metric("Всего комментариев", f"{total_comments:,}".replace(",", " "))
    col_pos.metric("Позитивных", positive, help="Количество комментариев с тональностью 'positive'")
    col_neg.metric("Негативных", negative, help="Количество комментариев с тональностью 'negative'")
    col_neu.metric("Нейтральных", neutral, help="Количество комментариев с тональностью 'neutral'")
    col_undef.metric("Неопределено", undefined, help="Комментарии без рассчитанной тональности")


def daily_histogram_section(df: pd.DataFrame) -> None:
    st.subheader("Распределение тональности по дням (в %)")
    daily_df = daily_sentiment_percentages(df)

    if daily_df.empty:
        st.info("Недостаточно данных для построения гистограммы.")
        return

    # Преобразуем в long-формат для stacked bar chart, добавляем counts
    chart_data = daily_df.melt(
        id_vars=["date", "positive_count", "negative_count", "neutral_count"],
        value_vars=["positive_pct", "negative_pct", "neutral_pct"],
        var_name="sentiment",
        value_name="percentage",
    )
    
    # Добавляем соответствующие counts для каждого sentiment
    def get_count(row):
        if row["sentiment"] == "positive_pct":
            return row["positive_count"]
        elif row["sentiment"] == "negative_pct":
            return row["negative_count"]
        else:
            return row["neutral_count"]
    
    chart_data["count"] = chart_data.apply(get_count, axis=1)
    
    # Переименуем для удобства
    sentiment_map = {
        "positive_pct": "Позитивные",
        "negative_pct": "Негативные",
        "neutral_pct": "Нейтральные"
    }
    chart_data["sentiment"] = chart_data["sentiment"].map(sentiment_map)

    chart = (
        alt.Chart(chart_data)
        .mark_bar()
        .encode(
            x=alt.X(
                "date:T", 
                title="Дата",
                axis=alt.Axis(
                    format="%d.%m.%Y",
                    formatType="time",
                    labelAngle=-45,
                    tickCount="day"
                )
            ),
            y=alt.Y("percentage:Q", title="Процент от комментариев за день (%)", stack="zero"),
            color=alt.Color(
                "sentiment:N",
                title="Тональность",
                scale=alt.Scale(
                    domain=["Позитивные", "Нейтральные", "Негативные"],
                    range=["#4CAF50", "#9E9E9E", "#F44336"],
                ),
            ),
            tooltip=[
                alt.Tooltip("date:T", title="Дата", format="%d.%m.%Y"),
                alt.Tooltip("sentiment:N", title="Тональность"),
                alt.Tooltip("count:Q", title="Количество"),
                alt.Tooltip("percentage:Q", title="Процент", format=".1f"),
            ],
        )
        .properties(height=360)
    )

    st.altair_chart(chart, use_container_width=True)


def post_summary_section(df: pd.DataFrame) -> None:
    st.subheader("Лидеры по постам")
    top_comment, top_negative = post_highlights(df)

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("**Больше всего комментариев**")
        if top_comment:
            st.metric(
                label=top_comment.group_channel_name,
                value=f"{top_comment.comment_count} комментариев",
                delta=f"{top_comment.negative_count} негативных",
                delta_color="inverse",
            )
            st.markdown(f"[Перейти к посту]({top_comment.post_url})")
        else:
            st.info("Нет данных по постам.")

    with col2:
        st.markdown("**Больше всего негатива**")
        if top_negative:
            st.metric(
                label=top_negative.group_channel_name,
                value=f"{top_negative.negative_count} негативных",
                delta=f"{top_negative.comment_count} всего",
            )
            st.markdown(f"[Перейти к посту]({top_negative.post_url})")
        else:
            st.info("Нет данных по негативным комментариям.")


def raw_data_section(df: pd.DataFrame) -> None:
    st.subheader("Raw Data")
    raw_table = prepare_raw_table(df)

    if raw_table.empty:
        st.info("Нет строк для отображения в таблице.")
        return

    st.dataframe(raw_table, use_container_width=True, hide_index=True)

    csv_data = raw_table.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Скачать CSV",
        data=csv_data,
        file_name="comments_export.csv",
        mime="text/csv",
    )


def manual_labeling_section(selected_range: Tuple[datetime, datetime]) -> None:
    """
    Секция для ручной разметки неопределенной тональности
    
    Args:
        selected_range: Выбранный период (start_datetime, end_datetime)
    """
    st.subheader("🏷️ Ручная разметка тональности")
    
    # Получаем настройки API из переменных окружения
    api_url = os.getenv("API_URL", "http://localhost:8000")
    api_username = os.getenv("API_USERNAME", "admin")
    api_password = os.getenv("API_PASSWORD", "changeme")
    
    # Проверка доступности API
    try:
        response = requests.get(f"{api_url}/api/health", timeout=2)
        if response.status_code != 200:
            st.error(f"⚠️ API недоступен. Проверьте что сервер запущен на {api_url}")
            return
    except requests.exceptions.RequestException:
        st.error(f"⚠️ Не удалось подключиться к API на {api_url}")
        st.info("Убедитесь что api_server.py запущен")
        return
    
    # Получаем неопределенные комментарии
    start_dt, end_dt = selected_range
    
    try:
        response = requests.get(
            f"{api_url}/api/comments/undefined",
            params={
                "start_date": start_dt.strftime("%Y-%m-%d"),
                "end_date": end_dt.strftime("%Y-%m-%d"),
                "limit": 50  # Показываем по 50 за раз
            },
            auth=(api_username, api_password),
            timeout=10
        )
        
        if response.status_code == 401:
            st.error("❌ Неверные учетные данные для API")
            return
        
        response.raise_for_status()
        undefined_comments = response.json()
        
    except requests.exceptions.RequestException as e:
        st.error(f"Ошибка при получении комментариев: {e}")
        return
    
    if not undefined_comments:
        st.success("✅ Все комментарии в выбранном периоде размечены!")
        return
    
    st.info(f"Найдено {len(undefined_comments)} неразмеченных комментариев")
    
    # Инициализируем индекс текущего комментария
    if "current_comment_index" not in st.session_state:
        st.session_state["current_comment_index"] = 0
    
    # Убеждаемся что индекс в пределах массива
    if st.session_state["current_comment_index"] >= len(undefined_comments):
        st.session_state["current_comment_index"] = 0
    
    if not undefined_comments:
        return
    
    current_idx = st.session_state["current_comment_index"]
    comment = undefined_comments[current_idx]
    
    # Прогресс бар
    progress = (current_idx + 1) / len(undefined_comments)
    st.progress(progress, text=f"Комментарий {current_idx + 1} из {len(undefined_comments)}")
    
    # Карточка комментария
    with st.container():
        st.markdown("---")
        
        col_info1, col_info2 = st.columns(2)
        with col_info1:
            st.markdown(f"**ID:** {comment['id']}")
            st.markdown(f"**Источник:** {comment['source']}")
            st.markdown(f"**Автор:** {comment['author_name']}")
        
        with col_info2:
            st.markdown(f"**Канал/Группа:** {comment['group_channel_name']}")
            comment_date = datetime.fromisoformat(comment['comment_published_at'].replace('Z', '+00:00'))
            st.markdown(f"**Дата:** {comment_date.strftime('%d.%m.%Y %H:%M')}")
        
        st.markdown("**Текст комментария:**")
        st.info(comment['comment_text'])
        
        # Ссылки
        col_link1, col_link2 = st.columns(2)
        with col_link1:
            st.markdown(f"[🔗 Ссылка на пост]({comment['post_url']})")
        with col_link2:
            st.markdown(f"[💬 Ссылка на комментарий]({comment['comment_url']})")
        
        st.markdown("---")
        
        # Кнопки выбора тональности
        st.markdown("**Выберите тональность:**")
        col1, col2, col3, col4 = st.columns([1, 1, 1, 1])
        
        with col1:
            if st.button("🟢 Позитивный", key=f"pos_{comment['id']}", use_container_width=True):
                if update_sentiment_via_api(
                    api_url, comment['id'], "positive", 
                    api_username, api_password
                ):
                    st.success("✅ Обновлено: Позитивный")
                    st.session_state["current_comment_index"] = min(
                        current_idx + 1, len(undefined_comments) - 1
                    )
                    st.rerun()
        
        with col2:
            if st.button("⚪ Нейтральный", key=f"neu_{comment['id']}", use_container_width=True):
                if update_sentiment_via_api(
                    api_url, comment['id'], "neutral",
                    api_username, api_password
                ):
                    st.success("✅ Обновлено: Нейтральный")
                    st.session_state["current_comment_index"] = min(
                        current_idx + 1, len(undefined_comments) - 1
                    )
                    st.rerun()
        
        with col3:
            if st.button("🔴 Негативный", key=f"neg_{comment['id']}", use_container_width=True):
                if update_sentiment_via_api(
                    api_url, comment['id'], "negative",
                    api_username, api_password
                ):
                    st.success("✅ Обновлено: Негативный")
                    st.session_state["current_comment_index"] = min(
                        current_idx + 1, len(undefined_comments) - 1
                    )
                    st.rerun()
        
        with col4:
            if st.button("⏭️ Пропустить", key=f"skip_{comment['id']}", use_container_width=True):
                st.session_state["current_comment_index"] = (current_idx + 1) % len(undefined_comments)
                st.rerun()
        
        # Навигация
        st.markdown("---")
        nav_col1, nav_col2, nav_col3 = st.columns([1, 2, 1])
        
        with nav_col1:
            if st.button("⬅️ Предыдущий", disabled=(current_idx == 0)):
                st.session_state["current_comment_index"] = current_idx - 1
                st.rerun()
        
        with nav_col3:
            if st.button("Следующий ➡️", disabled=(current_idx >= len(undefined_comments) - 1)):
                st.session_state["current_comment_index"] = current_idx + 1
                st.rerun()


def update_sentiment_via_api(
    api_url: str, 
    comment_id: int, 
    sentiment: str,
    username: str,
    password: str
) -> bool:
    """
    Обновить тональность через API
    
    Returns:
        True если успешно, False если ошибка
    """
    try:
        response = requests.put(
            f"{api_url}/api/comments/{comment_id}/sentiment",
            json={
                "sentiment": sentiment,
                "sentiment_score": 0.95  # Ручная разметка имеет высокую уверенность
            },
            auth=(username, password),
            timeout=10
        )
        
        response.raise_for_status()
        return True
        
    except requests.exceptions.RequestException as e:
        st.error(f"Ошибка при обновлении: {e}")
        return False


def main() -> None:
    """
    Запуск Streamlit дашборда.

    Команда для запуска:
        streamlit run dashboard/streamlit_app.py
    """
    # Проверка авторизации
    if not check_password():
        st.stop()
    
    default_db_path = _resolve_db_path()
    db_path, selected_range, selected_source = sidebar_controls(default_db_path)
    engine = create_sqlite_engine(str(db_path))

    render_header(db_path)

    df = fetch_comments_dataframe(engine, selected_range, None if selected_source == "all" else selected_source)

    if df.empty:
        st.warning("Не найдено комментариев для выбранных фильтров.")
        return

    with st.expander("Текущие фильтры", expanded=False):
        start_dt, end_dt = selected_range
        st.write(
            f"Период: {start_dt.strftime('%d.%m.%Y')} — {end_dt.strftime('%d.%m.%Y')}"
        )
        st.write(
            "Площадка: "
            + ("Все" if selected_source == "all" else selected_source.capitalize())
        )

    kpi_section(df)
    daily_histogram_section(df)
    post_summary_section(df)
    
    # Секция ручной разметки
    st.markdown("---")
    manual_labeling_section(selected_range)
    
    # Raw data в конце
    st.markdown("---")
    raw_data_section(df)


if __name__ == "__main__":
    main()

