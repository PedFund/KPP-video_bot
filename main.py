import telebot
import config
import io
import os
import subprocess
import logging
import subprocess
from voice import get_all_voices, generate_audio

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота
API_TOKEN = config.bot_token
bot = telebot.TeleBot(API_TOKEN)

# Удаление вебхука
bot.delete_webhook()
logging.info("Webhook deleted.")

# Папка с роликами
VIDEO_FOLDER = "gifs/"  # MP4-файлы хранятся здесь

# Получаем все голоса из модуля voice.py
voices = get_all_voices()

# Создание клавиатуры для выбора голоса
voice_buttons = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
for voice in voices.voices:
    voice_name = voice.name  # Получаем имя голоса
    button = telebot.types.KeyboardButton(voice_name)
    voice_buttons.add(button)

# Словари для хранения выбора пользователя
selected_voice = {}
selected_video = {}

@bot.message_handler(commands=['start'])
def send_welcome(message):
    logging.info(f"User {message.from_user.id} started the bot.")
    bot.reply_to(message,
                 "Привет! Я бот для создания озвучки! Выбери голос, который будет использоваться при создании озвучки:",
                 reply_markup=voice_buttons)

@bot.message_handler(func=lambda message: message.text in [voice.name for voice in voices.voices])
def voice_selected(message):
    user_id = message.from_user.id
    selected_voice[user_id] = message.text
    logging.info(f"User {user_id} selected voice: {message.text}")

    # Предложим выбрать ролик
    video_buttons = telebot.types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    videos = [f for f in os.listdir(VIDEO_FOLDER) if f.endswith('.mp4')]

    for video in videos:
        button = telebot.types.KeyboardButton(video)
        video_buttons.add(button)

    bot.reply_to(message, f"Вы выбрали голос: {message.text}. Теперь выберите видео:", reply_markup=video_buttons)

@bot.message_handler(func=lambda message: message.text in os.listdir(VIDEO_FOLDER))
def video_selected(message):
    user_id = message.from_user.id
    selected_video[user_id] = message.text
    logging.info(f"User {user_id} selected video: {message.text}")
    bot.reply_to(message, f"Вы выбрали видео: {message.text}. Теперь введите текст для озвучки:")

@bot.message_handler(func=lambda message: True)
def generate_voice_and_video(message):
    user_id = message.from_user.id

    if user_id in selected_voice and user_id in selected_video:
        voice_name = selected_voice[user_id]
        voice = next(voice for voice in voices.voices if voice.name == voice_name)
        voice_id = voice.voice_id
        video_file = os.path.join(VIDEO_FOLDER, selected_video[user_id])

        # Генерация аудио
        audio_generator = generate_audio(message.text, voice_id)
        audio_path = f"temp_{user_id}.mp3"
        with open(audio_path, "wb") as audio_file:
            for chunk in audio_generator:
                audio_file.write(chunk)

        # Создание итогового видео с озвучкой
        output_video = f"output_{user_id}.mp4"
        # 1️⃣ Получаем длительность аудиофайла
        audio_duration_cmd = f'ffprobe -i "{audio_path}" -show_entries format=duration -v quiet -of csv="p=0"'
        audio_duration = subprocess.check_output(audio_duration_cmd, shell=True).decode().strip()

        # 2️⃣ Файл для обрезанного видео
        trimmed_video_file = f"trimmed_{user_id}.mp4"

        # 3️⃣ Обрезаем видео по длительности аудио
        trim_video_cmd = f'ffmpeg -y -stream_loop -1 -i "{video_file}" -t {audio_duration} -c:v libx264 -preset slow -crf 23 -an "{trimmed_video_file}"'
        subprocess.run(trim_video_cmd, shell=True, check=True)

        # 4️⃣ Объединяем обрезанное видео с аудио
        command = f'ffmpeg -y -i "{trimmed_video_file}" -i "{audio_path}" -map 0:v -map 1:a -c:v copy -c:a aac -b:a 192k -movflags +faststart "{output_video}"'
        subprocess.run(command, shell=True, check=True)

        # 5️⃣ Удаляем временный обрезанный файл
        os.remove(trimmed_video_file)
        subprocess.run(command, shell=True)

        # Отправка видео пользователю
        with open(output_video, "rb") as video:
            bot.send_video(user_id, video)

        logging.info(f"Video sent to user {user_id}")

        # Отправляем сообщение о завершении работы
        bot.send_message(user_id, "✅ Видео готово! Чтобы создать новое, выберите голос командой /start")

        # Очистка временных файлов
        os.remove(audio_path)
        os.remove(output_video)
    else:
        logging.info(f"User {user_id} tried to generate voice without selecting one.")
        bot.reply_to(message, "Сначала выберите голос и видео командой /start")

if __name__ == '__main__':
    bot.polling(non_stop=True)
    logging.info("Bot polling started.")