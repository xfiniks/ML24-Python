import asyncio
import aiohttp
import matplotlib.pyplot as plt
import io
from datetime import datetime
import uuid
import os
from dotenv import load_dotenv

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.types import BotCommand
from rapidfuzz import process
from aiogram.utils.keyboard import InlineKeyboardBuilder


users = {}

class ProfileStates(StatesGroup):
    weight = State()
    height = State()
    age = State()
    activity = State()
    city = State()
    calorie_goal = State()

class FoodLogStates(StatesGroup):
    waiting_for_product_choice = State()
    waiting_for_manual_cal = State()
    waiting_for_grams = State()    

load_dotenv()

API_TOKEN = os.getenv("BOT_TOKEN")
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

async def get_temperature(city: str) -> float:
    openweather_api_key = os.getenv("OPENWEATHER_API_KEY")
    url = "http://api.openweathermap.org/data/2.5/weather"
    async with aiohttp.ClientSession() as session:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
                "Accept": "application/json",
            }

            params = {
                'q': city,
                'appid': openweather_api_key,
                'units': 'metric'
            }

            async with session.get(url, params=params, headers=headers) as response:
                if response.status != 200:
                    error_text = await response.text()
                    print(f"Ошибка получения погоды: {response.status}, {error_text}, url='{url}'")
                    return 15.0

                data = await response.json(content_type=None)
                if data.get("main"):
                    return data["main"]["temp"]
                else:
                    return 15.0
        except Exception as e:
            print(f"Ошибка получения погоды: {e}")
            return 20.0

async def get_food_candidates(food_name: str, limit: int = 5):
    url = "https://world.openfoodfacts.org/cgi/search.pl"
    params = {
        "search_terms": food_name,
        "search_simple": 1,
        "action": "process",
        "json": 1,
        "page_size": 20
    }
    results = []

    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, params=params) as response:
                data = await response.json()
                products = data.get("products", [])
                for prod in products:
                    if not isinstance(prod, dict):
                        continue
                    nutriments = prod.get("nutriments", {})
                    cal = nutriments.get("energy-kcal_100g")
                    if cal is None:
                        cal = nutriments.get("energy-kcal")
                    if cal is not None:
                        product_name = prod.get("product_name", "").strip()
                        if product_name:
                            results.append({
                                "name": product_name,
                                "calories": float(cal)
                            })
        except Exception as e:
            print(f"Ошибка при получении данных о продукте: {e}")

    if not results:
        return []

    cleaned_results = []
    for i, item in enumerate(results):
        if isinstance(item, dict) and "name" in item and isinstance(item["name"], str):
            cleaned_results.append(item)

    def safe_processor(x):
        if isinstance(x, dict) and "name" in x and isinstance(x["name"], str):
            return x["name"]
        return ""

    fuzzy_matches = process.extract(
        food_name,
        cleaned_results,
        processor=safe_processor,
        limit=limit
    )

    final_list = []
    for match_data, score, _ in fuzzy_matches:
        if isinstance(match_data, dict):
            final_list.append({
                "name": match_data["name"],
                "calories": match_data["calories"],
                "score": score
            })

    final_list.sort(key=lambda x: x["score"], reverse=True)
    return final_list

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет!\nЯ бот для расчёта дневной норм воды и калорий.\n"
        "Начните с команды /set_profile для настройки вашего профиля."
    )

@dp.message(Command("set_profile"))
async def set_profile(message: types.Message, state: FSMContext):
    await message.answer("Введите ваш вес (в кг):")
    await state.set_state(ProfileStates.weight)

@dp.message(ProfileStates.weight)
async def process_weight(message: types.Message, state: FSMContext):
    try:
        weight = float(message.text)
        await state.update_data(weight=weight)
        await message.answer("Введите ваш рост (в см):")
        await state.set_state(ProfileStates.height)
    except ValueError:
        await message.answer("Пожалуйста, введите число для веса.")

@dp.message(ProfileStates.height)
async def process_height(message: types.Message, state: FSMContext):
    try:
        height = float(message.text)
        await state.update_data(height=height)
        await message.answer("Введите ваш возраст:")
        await state.set_state(ProfileStates.age)
    except ValueError:
        await message.answer("Пожалуйста, введите число для роста.")

@dp.message(ProfileStates.age)
async def process_age(message: types.Message, state: FSMContext):
    try:
        age = int(message.text)
        await state.update_data(age=age)
        await message.answer("Сколько минут активности у вас в день?")
        await state.set_state(ProfileStates.activity)
    except ValueError:
        await message.answer("Пожалуйста, введите число для возраста.")

@dp.message(ProfileStates.activity)
async def process_activity(message: types.Message, state: FSMContext):
    try:
        activity = int(message.text)
        await state.update_data(activity=activity)
        await message.answer("В каком городе вы находитесь?")
        await state.set_state(ProfileStates.city)
    except ValueError:
        await message.answer("Пожалуйста, введите число для минут активности.")

@dp.message(ProfileStates.city)
async def process_city(message: types.Message, state: FSMContext):
    city = message.text
    await state.update_data(city=city)
    await message.answer("Введите вашу цель по калориям или слово 'авто' для автоматического расчёта:")
    await state.set_state(ProfileStates.calorie_goal)

@dp.message(ProfileStates.calorie_goal)
async def process_calorie_goal(message: types.Message, state: FSMContext):
    data = await state.get_data()
    calorie_goal_input = message.text.strip()
    if calorie_goal_input == "авто":
        manual_goal = False
    else:
        try:
            calorie_goal_value = float(calorie_goal_input)
            manual_goal = True
        except ValueError:
            await message.answer("Пожалуйста, введите число для цели по калориям или отправьте слово 'авто'.")
            return
    weight = data.get("weight")
    height = data.get("height")
    age = data.get("age")
    activity = data.get("activity")
    city = data.get("city")
    
    temp = await get_temperature(city)
    
    # Расчет нормы воды:
    # Базовая норма = вес * 30 мл + 500 мл за каждые 30 мин активности + (500 мл, если температура >25°C)
    water_goal = weight * 30
    water_goal += (activity // 30) * 500
    if temp > 25:
        water_goal += 500
    
    # Расчет нормы калорий, если не задан вручную
    if not manual_goal:
        base_calories = 10 * weight + 6.25 * height - 5 * age
        activity_bonus = (activity // 30) * 200
        calorie_goal_value = base_calories + activity_bonus
    
    user_id = message.from_user.id
    users[user_id] = {
        "weight": weight,
        "height": height,
        "age": age,
        "activity": activity,
        "city": city,
        "temp": temp,
        "water_goal": water_goal,
        "calorie_goal": calorie_goal_value,
        "logged_water": 0,
        "logged_calories": 0,
        "burned_calories": 0,
        "water_logs": [],
        "food_logs": [],
        "workout_logs": [],
    }
    
    await message.answer(
        f"Профиль сохранён!\n"
        f"Ваша дневная норма воды: {int(water_goal)} мл\n"
        f"Ваша дневная норма калорий: {int(calorie_goal_value)} ккал\n"
        f"Текущая температура в {city}: {temp}°C"
    )
    await state.clear()

@dp.message(Command("log_water"))
async def log_water(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью /set_profile.")
        return

    parts = message.text.split()

    if len(parts) < 2:
        await message.answer("Используйте команду: /log_water <количество_мл>")
        return
    try:
        amount = float(parts[1])
    except ValueError:
        await message.answer("Пожалуйста, введите число для количества воды.")
        return

    users[user_id]["logged_water"] += amount
    users[user_id]["water_logs"].append((datetime.now(), amount))
    remaining = users[user_id]["water_goal"] - users[user_id]["logged_water"]
    if remaining < 0:
        remaining = 0
    await message.answer(f"Записано: {amount} мл воды.\nОсталось: {remaining:.0f} мл.")


@dp.message(Command("log_food"))
async def log_food_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью /set_profile.")
        return

    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Используйте команду: /log_food <название продукта>")
        return

    food_name = parts[1].strip()

    candidates = await get_food_candidates(food_name)

    if not candidates:
        await message.answer("Информация о продукте не найдена. Введите калорийность на 100 г вручную:")
        await state.set_state(FoodLogStates.waiting_for_manual_cal)
        await state.update_data(food_name=food_name)
        return

    builder = InlineKeyboardBuilder()

    candidates_dict = {}
    for candidate in candidates:
        candidate_id = str(uuid.uuid4())[:8]
        candidates_dict[candidate_id] = candidate

        name_short = candidate["name"][:20]
        btn_text = f"{name_short} ({candidate['calories']:.1f} ккал/100г)"

        callback_data = f"choose_food_{candidate_id}"

        builder.button(text=btn_text, callback_data=callback_data)

    builder.button(text="Ввести калорийность вручную", callback_data="choose_food_manual")

    builder.adjust(1)
    keyboard = builder.as_markup()

    data = await state.get_data()
    data["candidates_dict"] = candidates_dict
    await state.update_data(data)

    await message.answer("Найдены похожие продукты", reply_markup=keyboard)
    await state.set_state(FoodLogStates.waiting_for_product_choice)

@dp.callback_query(FoodLogStates.waiting_for_product_choice)
async def choose_food_callback(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "choose_food_manual":
        await callback.message.edit_text("Введите калорийность на 100г вручную:")
        await state.set_state(FoodLogStates.waiting_for_manual_cal)
        return

    if not callback.data.startswith("choose_food_"):
        await callback.answer("Некорректный выбор.")
        return

    candidate_id = callback.data.replace("choose_food_", "")

    data = await state.get_data()
    candidates_dict = data.get("candidates_dict", {})

    chosen_candidate = candidates_dict.get(candidate_id)
    if not chosen_candidate:
        await callback.answer("Некорректный выбор.")
        return

    cal_per_100g = chosen_candidate["calories"]
    food_name = chosen_candidate["name"]

    await callback.message.edit_text(
        f"Вы выбрали: {food_name} ({cal_per_100g:.1f} ккал на 100 г).\nСколько грамм вы съели?"
    )

    await state.update_data(food_cal_per_100g=cal_per_100g, food_name=food_name)
    await state.set_state(FoodLogStates.waiting_for_grams)

@dp.message(FoodLogStates.waiting_for_manual_cal)
async def set_manual_calories(message: types.Message, state: FSMContext):
    try:
        custom_cal = float(message.text)
        if custom_cal <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите положительное число для калорийности.")
        return

    await state.update_data(food_cal_per_100g=custom_cal)
    await message.answer("Калорийность записана. Сколько грамм вы съели?")
    await state.set_state(FoodLogStates.waiting_for_grams)

@dp.message(FoodLogStates.waiting_for_grams)
async def log_food_grams(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью /set_profile.")
        await state.clear()
        return

    try:
        grams = float(message.text)
        if grams <= 0:
            raise ValueError
    except ValueError:
        await message.answer("Пожалуйста, введите положительное число для граммов.")
        return

    data = await state.get_data()
    cal_per_100g = data.get("food_cal_per_100g")
    food_name = data.get("food_name", "Продукт")

    if cal_per_100g is None or cal_per_100g <= 0:
        await message.answer("К сожалению, не удалось определить калорийность продукта.")
        await state.clear()
        return

    calories_consumed = cal_per_100g * grams / 100.0
    users[user_id]["logged_calories"] += calories_consumed
    users[user_id]["food_logs"].append((datetime.now(), calories_consumed))

    await message.answer(f"Записано: {calories_consumed:.1f} ккал (продукт: {food_name}).")
    await state.clear()

@dp.message(Command("log_workout"))
async def log_workout(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью /set_profile.")
        return
    args = message.text.split()
    if len(args) <= 2:
        await message.answer(
            "Используйте команду: /log_workout <тип тренировки> <время (мин)>\n"
            "Поддерживаемые типы тренировки: бег, ходьба, силовая, велосипед"
            )
        return
    
    factors = {
        "бег": 10,
        "ходьба": 4,
        "силовая": 8,
        "велосипед": 7,
    }
    
    workout_type = args[1]

    if workout_type not in factors:
        await message.answer("Пожалуйста, введите поддерживаемый тип тренировки.")
        return

    try:
        minutes = float(args[2])

    except ValueError:
        await message.answer("Пожалуйста, введите число для времени тренировки.")
        return


    factor = factors.get(workout_type.lower(), 6)
    burned = factor * minutes
    users[user_id]["burned_calories"] += burned
    users[user_id]["workout_logs"].append((datetime.now(), burned))

    extra_water = (minutes // 30) * 200
    users[user_id]["water_goal"] += extra_water
    await message.answer(
        f"🏃‍♂️ {workout_type} {minutes:.0f} минут — {burned:.0f} ккал сожжено.\n"
        f"Дополнительно: выпейте {int(extra_water)} мл воды."
    )

@dp.message(Command("check_progress"))
async def check_progress(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью /set_profile.")
        return
    
    data = users[user_id]
    water_goal = data["water_goal"]
    logged_water = data["logged_water"]
    remaining_water = water_goal - logged_water if water_goal > logged_water else 0
    calorie_goal = data["calorie_goal"]
    logged_calories = data["logged_calories"]
    burned_calories = data["burned_calories"]
    net_calories = logged_calories - burned_calories
    msg = (
        f"📊 Прогресс:\n\n"
        f"Вода:\n"
        f"- Выпито: {logged_water:.0f} мл из {water_goal:.0f} мл.\n"
        f"- Осталось: {remaining_water:.0f} мл.\n\n"
        f"Калории:\n"
        f"- Потреблено: {logged_calories:.0f} ккал из {calorie_goal:.0f} ккал.\n"
        f"- Сожжено: {burned_calories:.0f} ккал.\n"
        f"- Баланс: {net_calories:.0f} ккал."
    )
    recommendations = ""
    if logged_water < water_goal * 0.5:
        recommendations += "\nРекомендация: Вам стоит выпить больше воды!"
    if net_calories > calorie_goal:
        recommendations += "\nРекомендация: Попробуйте увеличить физическую активность или снизить калорийность пищи."
    await message.answer(msg + recommendations)


@dp.message(Command("show_graph"))
async def show_graph(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        await message.answer("Сначала настройте профиль с помощью /set_profile.")
        return

    data = users[user_id]
    water_logs = data.get("water_logs", [])
    food_logs = data.get("food_logs", [])
    workout_logs = data.get("workout_logs", [])

    if water_logs:
        times_water = [log[0] for log in water_logs]
        amounts = [log[1] for log in water_logs]
        cum_water = []
        total = 0
        for amt in amounts:
            total += amt
            cum_water.append(total)

        plt.figure(figsize=(10, 5))
        plt.plot(times_water, cum_water, marker="o", label="Выпито")
        plt.axhline(y=data["water_goal"], color="r", linestyle="--", label="Норма воды")
        plt.xlabel("Время")
        plt.ylabel("Выпито воды (мл)")
        plt.title("Прогресс по воде")
        plt.legend()

        buf_water = io.BytesIO()
        plt.savefig(buf_water, format="png")
        buf_water.seek(0)
        plt.close()

        file_water = types.BufferedInputFile(buf_water.getvalue(), filename="water_progress.png")
        await message.answer_photo(photo=file_water, caption="График прогресса по воде")
    else:
        await message.answer("Нет данных для построения графика выпитой воды.")

    if food_logs or workout_logs:
        events = []
        for t, cal in food_logs:
            events.append((t, cal))
        for t, cal in workout_logs:
            events.append((t, -cal))
        events.sort(key=lambda x: x[0])

        times = []
        net_values = []
        net = 0
        for t, delta in events:
            net += delta
            times.append(t)
            net_values.append(net)

        plt.figure(figsize=(10, 5))
        plt.plot(times, net_values, marker="o", label="Нетто калории")
        plt.axhline(y=data["calorie_goal"], color="r", linestyle="--", label="Норма калорий")
        plt.xlabel("Время")
        plt.ylabel("Калории")
        plt.title("Прогресс по калориям")
        plt.legend()

        buf_calories = io.BytesIO()
        plt.savefig(buf_calories, format="png")
        buf_calories.seek(0)
        plt.close()

        file_calories = types.BufferedInputFile(buf_calories.getvalue(), filename="calorie_progress.png")
        await message.answer_photo(photo=file_calories, caption="График прогресса по калориям")
    else:
        await message.answer("Нет данных для построения графика сожженых калорий.")

async def set_bot_commands(bot: Bot):
    commands = [
        BotCommand(command="set_profile", description="Настроить профиль"),
        BotCommand(command="log_water", description="Записать воду (мл)"),
        BotCommand(command="log_food", description="Записать еду"),
        BotCommand(command="log_workout", description="Записать тренировку"),
        BotCommand(command="check_progress", description="Проверить прогресс"),
        BotCommand(command="show_graph", description="Показать график"),
        BotCommand(command="help", description="Показать доступные команды"),
    ]
    await bot.set_my_commands(commands)

async def main():
    print("Бот запущен!")
    await set_bot_commands(bot)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
