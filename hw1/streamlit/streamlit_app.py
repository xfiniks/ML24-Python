import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import requests

st.set_page_config(page_title="Weather Analysis Dashboard", layout="wide")

BASE_URL = "http://api.openweathermap.org/data/2.5/weather"
SEASONS = ['winter', 'spring', 'summer', 'autumn']


@st.cache_data
def load_and_prepare_data(uploaded_file):
    df = pd.read_csv(uploaded_file, parse_dates=['timestamp'])
    df['year'] = df['timestamp'].dt.year
    df['month'] = df['timestamp'].dt.month
    df['day'] = df['timestamp'].dt.day
    return df


def prepare_city_data(df, city, window_size):
    city_data = df[df['city'] == city].copy()

    city_data['rolling_mean'] = city_data['temperature'].rolling(
        window=window_size, center=True).mean()
    city_data['rolling_std'] = city_data['temperature'].rolling(
        window=window_size, center=True).std()

    city_data['is_anomaly'] = abs(
        city_data['temperature'] - city_data['rolling_mean']
    ) > 2 * city_data['rolling_std']

    return city_data

@st.cache_data(ttl=600)
def get_current_weather(city, api_key):
    if not api_key:
        return None

    params = {
        'q': city,
        'appid': api_key,
        'units': 'metric'
    }

    try:
        response = requests.get(BASE_URL, params=params)
        data = response.json()

        if response.status_code == 401:
            st.error("Неверный API ключ. Пожалуйста, проверьте ваш ключ.")
            return None
        elif response.status_code != 200:
            st.error(f"Ошибка получения данных: {data.get('message', 'Unknown error')}")
            return None

        return data
    except Exception as e:
        st.error(f"Ошибка при запросе к API: {str(e)}")
        return None


def plot_temperature_heatmap(df, city):
    city_data = df[df['city'] == city].copy()
    pivot_data = city_data.pivot_table(
        index='month',
        columns='year',
        values='temperature',
        aggfunc='mean'
    ).round(1)

    fig = px.imshow(pivot_data,
                    labels=dict(x="Год", y="Месяц", color="Температура"),
                    title=f"Тепловая карта температур для {city}")
    return fig


def plot_anomalies_distribution(city_data):
    monthly_anomalies = city_data.groupby(['year', 'month'])['is_anomaly'].sum().reset_index()
    monthly_anomalies['date'] = pd.to_datetime(
        monthly_anomalies[['year', 'month']].assign(day=1)
    )

    fig = px.bar(
        monthly_anomalies,
        x='date',
        y='is_anomaly',
        title='Количество аномалий по месяцам'
    )

    return fig


def main():
    st.title('📊 Анализ температурных данных')

    with st.sidebar:
        st.header("⚙️ Настройки")

        api_key = st.text_input('OpenWeatherMap API Key', type='password')

        st.subheader("Настройки визуализации")
        show_trend = st.checkbox("Показывать тренд", value=True)
        show_anomalies = st.checkbox("Показывать аномалии", value=True)
        rolling_window = st.slider("Окно скользящего среднего (дни)", 5, 60, 30)

    uploaded_file = st.file_uploader("📁 Загрузите файл с историческими данными (CSV)", type=['csv'])

    if uploaded_file is not None:
        df = load_and_prepare_data(uploaded_file)
        cities = sorted(df['city'].unique())

        col1, col2 = st.columns([2, 1])
        with col1:
            city = st.selectbox('🌆 Выберите город', cities)

        if city:
            city_data = prepare_city_data(df, city, rolling_window)

            if api_key:
                weather_data = get_current_weather(city, api_key)
                if weather_data:
                    current_temp = weather_data['main']['temp']
                    current_date = pd.Timestamp.now()

                    city_data['date_diff'] = abs(city_data['timestamp'] - current_date)
                    closest_dates = city_data.nsmallest(rolling_window, 'date_diff')

                    rolling_mean = closest_dates['temperature'].mean()
                    rolling_std = closest_dates['temperature'].std()

                    is_current_anomaly = abs(current_temp - rolling_mean) > 2 * rolling_std
                    deviation_sigma = abs(current_temp - rolling_mean) / rolling_std

                    col1, col2, col3 = st.columns(3)
                    with col1:
                        st.metric(
                            "🌡️ Текущая температура",
                            f"{current_temp:.1f}°C",
                            f"{current_temp - rolling_mean:+.1f}°C от нормы"
                        )
                    with col2:
                        st.metric("💧 Влажность", f"{weather_data['main']['humidity']}%")
                    with col3:
                        st.metric("🌪️ Давление", f"{weather_data['main']['pressure']} hPa")

                    st.subheader("Анализ текущей температуры")
                    temperature_status = (
                        "🚨 Аномальная" if is_current_anomaly else "✅ Нормальная"
                    )

                    start_date = closest_dates['timestamp'].min().strftime('%d.%m')
                    end_date = closest_dates['timestamp'].max().strftime('%d.%m')

                    st.markdown(f"""
                    **Статус:** {temperature_status}

                    Анализ основан на скользящем окне в {rolling_window} дней:
                    - Период анализа: {start_date} - {end_date}
                    - Средняя температура за период: {rolling_mean:.1f}°C
                    - Отклонение от среднего: {deviation_sigma:.1f}σ
                    - Диапазон нормы: от {rolling_mean - 2 * rolling_std:.1f}°C до {rolling_mean + 2 * rolling_std:.1f}°C
                    """)

                    if is_current_anomaly:
                        st.warning(f"""
                        ⚠️ Текущая температура отклоняется от нормы на {deviation_sigma:.1f} 
                        стандартных отклонений (рассчитано на основе {rolling_window}-дневного окна). 
                        Это считается статистически значимым отклонением.
                        """)

                        st.info(f"""
                        📊 Дополнительная статистика:
                        - Абсолютное отклонение: {abs(current_temp - rolling_mean):.1f}°C
                        - Стандартное отклонение в периоде: {rolling_std:.1f}°C
                        """)


            tab1, tab2, tab3 = st.tabs(["📈 Временной ряд", "🗺️ Тепловая карта", "📊 Аномалии"])

            with tab1:
                fig_timeline = px.scatter(
                    city_data,
                    x='timestamp',
                    y='temperature',
                    color='is_anomaly' if show_anomalies else None,
                    title=f'Температурный ряд для {city}',
                    color_discrete_map={True: 'red', False: 'blue'}
                )

                if show_trend:
                    fig_timeline.add_trace(
                        go.Scatter(
                            x=city_data['timestamp'],
                            y=city_data['rolling_mean'],
                            mode='lines',
                            name=f'{rolling_window}-дневное среднее',
                            line=dict(color='green', width=2)
                        )
                    )

                    fig_timeline.add_trace(
                        go.Scatter(
                            x=city_data['timestamp'],
                            y=city_data['rolling_mean'] + 2 * city_data['rolling_std'],
                            mode='lines',
                            name='Верхняя граница (2σ)',
                            line=dict(color='rgba(255,165,0,0.5)', width=1, dash='dash')
                        )
                    )
                    fig_timeline.add_trace(
                        go.Scatter(
                            x=city_data['timestamp'],
                            y=city_data['rolling_mean'] - 2 * city_data['rolling_std'],
                            mode='lines',
                            name='Нижняя граница (2σ)',
                            line=dict(color='rgba(255,165,0,0.5)', width=1, dash='dash'),
                            fill='tonexty',
                            fillcolor='rgba(255,165,0,0.1)'
                        )
                    )

                fig_timeline.update_layout(
                    showlegend=True,
                    legend=dict(
                        yanchor="top",
                        y=0.99,
                        xanchor="left",
                        x=0.01,
                        bgcolor='rgba(255,255,255,0.8)'
                    ),
                    hovermode='x unified'
                )

                fig_timeline.update_xaxes(title="Дата")
                fig_timeline.update_yaxes(title="Температура (°C)")

                st.plotly_chart(fig_timeline, use_container_width=True)

            with tab2:
                fig_heatmap = plot_temperature_heatmap(df, city)
                st.plotly_chart(fig_heatmap, use_container_width=True)

            with tab3:
                fig_anomalies = plot_anomalies_distribution(city_data)
                st.plotly_chart(fig_anomalies, use_container_width=True)

            st.header("📊 Статистический анализ")
            col1, col2 = st.columns(2)

            with col1:
                st.subheader("Описательная статистика")
                stats = city_data['temperature'].describe().round(2)
                st.dataframe(stats)

            with col2:
                st.subheader("Сезонная статистика")
                seasonal_stats = city_data.groupby('season')['temperature'].agg([
                    'mean', 'std', 'min', 'max'
                ]).round(2)
                st.dataframe(seasonal_stats)

            st.header("❗ Анализ аномалий")
            total_anomalies = city_data['is_anomaly'].sum()
            total_days = len(city_data)
            anomaly_percentage = (total_anomalies / total_days) * 100

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Количество аномалий", f"{int(total_anomalies)}")
            with col2:
                st.metric("Процент аномалий", f"{anomaly_percentage:.1f}%")


if __name__ == '__main__':
    main()