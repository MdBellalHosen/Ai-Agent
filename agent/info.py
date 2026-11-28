"""Free information from the web without API keys: weather, news, Wikipedia."""
import json
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import config

WEATHER = {0: "clear sky", 1: "mostly clear", 2: "partly cloudy", 3: "cloudy", 45: "fog", 48: "fog",
           51: "light drizzle", 53: "drizzle", 55: "heavy drizzle", 61: "light rain", 63: "rain",
           65: "heavy rain", 66: "freezing rain", 67: "freezing rain", 71: "light snow", 73: "snow",
           75: "heavy snow", 80: "rain showers", 81: "rain showers", 82: "heavy rain showers",
           95: "thunderstorm", 96: "thunderstorm with hail", 99: "thunderstorm with hail"}


def fetch(url, timeout=15):
    request = urllib.request.Request(url, headers={"User-Agent": "Mira-assistant/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def get_json(url, **params):
    return json.loads(fetch(url + "?" + urllib.parse.urlencode(params)))


def weather(city=""):
    """Now and the next two days (Open-Meteo, free)."""
    city = (city or config.env("CITY", "Dhaka")).strip()
    found = get_json("https://geocoding-api.open-meteo.com/v1/search", name=city, count=1, language="en")
    if not found.get("results"):
        return f"City '{city}' not found"
    place = found["results"][0]
    data = get_json("https://api.open-meteo.com/v1/forecast", latitude=place["latitude"],
                    longitude=place["longitude"], timezone="auto", forecast_days=3,
                    current="temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m",
                    daily="temperature_2m_max,temperature_2m_min,precipitation_probability_max,weather_code")
    now, day = data["current"], data["daily"]
    lines = [f"{place['name']}, {place.get('country', '')}: now {now['temperature_2m']}°C "
             f"(feels {now['apparent_temperature']}°C), {WEATHER.get(now['weather_code'], 'unknown')}, "
             f"humidity {now['relative_humidity_2m']}%, wind {now['wind_speed_10m']} km/h"]
    for i, date in enumerate(day["time"]):
        lines.append(f"{date}: {day['temperature_2m_min'][i]}-{day['temperature_2m_max'][i]}°C, "
                     f"{WEATHER.get(day['weather_code'][i], 'unknown')}, "
                     f"rain chance {day['precipitation_probability_max'][i]}%")
    return "\n".join(lines)


def news(topic="", language="bn", count=6):
    """Latest headlines from Google News (Bangladesh edition)."""
    lang = "bn" if language != "en" else "en"
    edition = {"hl": lang, "gl": "BD", "ceid": f"BD:{lang}"}
    if topic:
        url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": topic, **edition})
    else:
        url = "https://news.google.com/rss?" + urllib.parse.urlencode(edition)
    root = ET.fromstring(fetch(url))
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        when = (item.findtext("pubDate") or "")[:16]
        if title:
            items.append(f"- {title} ({when})")
        if len(items) >= max(1, min(int(count or 6), 10)):
            break
    return "\n".join(items) or "No news found"


def wikipedia(query, language="bn"):
    """Short summary of a topic from Wikipedia."""
    lang = "bn" if language != "en" else "en"
    base = f"https://{lang}.wikipedia.org"
    hits = get_json(f"{base}/w/api.php", action="query", list="search", srsearch=query,
                    format="json", srlimit=1)["query"]["search"]
    if not hits:
        if lang == "bn":
            return wikipedia(query, "en")
        return f"Nothing found on Wikipedia for '{query}'"
    title = hits[0]["title"]
    page = json.loads(fetch(f"{base}/api/rest_v1/page/summary/" + urllib.parse.quote(title.replace(" ", "_"))))
    return f"{page.get('title', title)}: {page.get('extract', '')[:2500]}\nSource: {base}/wiki/{urllib.parse.quote(title)}"
