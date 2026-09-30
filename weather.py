# -*- coding: utf-8 -*-

"""طقس كركوك - Open-Meteo."""

import httpx


KIRKUK_LAT = 35.4681
KIRKUK_LON = 44.3922

KIRKUK_NAME = "كركوك"


WEATHER_CODES = {
    0: "☀️ صافٍ",
    1: "🌤️ غالباً صافٍ",
    2: "⛅ غائم جزئياً",
    3: "☁️ غائم",
    45: "🌫️ ضباب",
    48: "🌫️ ضباب كثيف",
    51: "🌦️ رذاذ خفيف",
    53: "🌦️ رذاذ",
    55: "🌧️ رذاذ كثيف",
    61: "🌦️ أمطار خفيفة",
    63: "🌧️ أمطار",
    65: "🌧️ أمطار غزيرة",
    71: "🌨️ ثلوج خفيفة",
    73: "🌨️ ثلوج",
    75: "❄️ ثلوج غزيرة",
    77: "🌨️ حبيبات ثلجية",
    80: "🌦️ زخات مطر خفيفة",
    81: "🌧️ زخات مطر",
    82: "⛈️ زخات مطر غزيرة",
    85: "🌨️ زخات ثلجية",
    86: "❄️ زخات ثلجية غزيرة",
    95: "⛈️ عاصفة رعدية",
    96: "⛈️ عاصفة رعدية مع برد",
    99: "⛈️ عاصفة رعدية قوية مع برد",
}


def weather_description(code):
    return WEATHER_CODES.get(
        int(code),
        "🌡️ حالة جوية غير معروفة",
    )


async def get_weather():
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": KIRKUK_LAT,
        "longitude": KIRKUK_LON,

        "current": (
            "temperature_2m,"
            "relative_humidity_2m,"
            "apparent_temperature,"
            "weather_code,"
            "wind_speed_10m"
        ),

        "daily": (
            "weather_code,"
            "temperature_2m_max,"
            "temperature_2m_min"
        ),

        "timezone": "Asia/Baghdad",
        "forecast_days": 4,
    }

    async with httpx.AsyncClient(
        timeout=15.0
    ) as client:

        response = await client.get(
            url,
            params=params,
        )

        response.raise_for_status()

        return response.json()


def format_weather(data):
    current = data.get("current", {})
    daily = data.get("daily", {})

    temperature = current.get(
        "temperature_2m"
    )

    feels = current.get(
        "apparent_temperature"
    )

    humidity = current.get(
        "relative_humidity_2m"
    )

    wind = current.get(
        "wind_speed_10m"
    )

    code = current.get(
        "weather_code",
        0,
    )

    text = (
        "🌤️ **طقس كركوك**\n\n"

        f"🌡️ الحرارة: **{temperature}°C**\n"
        f"🤚 المحسوسة: **{feels}°C**\n"
        f"💧 الرطوبة: **{humidity}%**\n"
        f"💨 سرعة الرياح: **{wind} كم/س**\n"
        f"☁️ الحالة: **{weather_description(code)}**\n\n"

        "━━━━━━━━━━━━━━\n\n"
        "📅 **التوقعات القادمة:**\n"
    )

    dates = daily.get(
        "time",
        []
    )

    max_temps = daily.get(
        "temperature_2m_max",
        []
    )

    min_temps = daily.get(
        "temperature_2m_min",
        []
    )

    codes = daily.get(
        "weather_code",
        []
    )

    days = [
        "اليوم",
        "غداً",
        "بعد غد",
        "اليوم الرابع",
    ]

    for i in range(
        min(
            len(dates),
            4,
        )
    ):

        day_name = days[i]

        maximum = (
            max_temps[i]
            if i < len(max_temps)
            else "-"
        )

        minimum = (
            min_temps[i]
            if i < len(min_temps)
            else "-"
        )

        day_code = (
            codes[i]
            if i < len(codes)
            else 0
        )

        text += (
            f"\n📆 **{day_name}**\n"
            f"☁️ {weather_description(day_code)}\n"
            f"🔺 العظمى: {maximum}°C\n"
            f"🔻 الصغرى: {minimum}°C\n"
        )

    text += (
        "\n━━━━━━━━━━━━━━\n"
        "📍 الموقع: كركوك"
    )

    return text
