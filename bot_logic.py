import signal
from threading import Thread, current_thread
from threading import Event
from time import sleep
import telebot
from telebot.types import InlineKeyboardButton,\
    InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
import tcping
import sys
import os
import re

from subprocess import Popen, PIPE, STDOUT

"""         ┌────────────────────────────┐
            │ Watch Dog workflow scheme  │
┌──────────────────────────────────────────────────────┐
│┌────────┐                                            │
││ Daemon │          (Waiting 4 Response)              │
│├────────┴──────────────┐        ┌───────────────┐    │
││Python TCPing Instances├<──────>│  Remote Host  │    │
│└──────────────┬────────┘        └───────────────┘    │
│         (Got response)                               │
│               ↓                                      │
│              ┌─────────────┐                         │
│       ┌─────>│ state_files │                         │
│       │      └─────────────┘                         │
│ ┌─────┴──┐                                           │
│ │ Daemon │                                           │
│ ├────────┴───┐        ┌───────────────────┐          │
│ │ Watcher    │ ──────>│   Telegram User   │          │
│ └────────────┘        └───────────────────┘          │
└──────────────────────────────────────────────────────┘
"""


class StoppableThread(Thread):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_event = Event()

    def stop(self):
        self._stop_event.set()

    def stopped(self):
        return self._stop_event.is_set()


class WatchDog:
    def __init__(self) -> None:
        self.wd_online = False
        self.survey_time = 1

        self.hosts = []
        self.TCPing_daemons = []
        self.WDaemon = None

        self.tcping_timeout = 1
        self.tcping_interval = 1

    def start_watcher(self) -> None:
        self.wd_online = True
        self.WDaemon = StoppableThread(target=self.watcher, args=(self.hosts,))
        self.WDaemon.start()

    def stop_watcher(self) -> None:
        if self.WDaemon is not None:
            self.WDaemon.stop()

    def watcher(self, hosts) -> None:
        cur_state = {}
        prev_state = {}
        while (True):
            if current_thread().stopped():
                print('Watcher was stopped')
                break

            for host in hosts:
                dst_ip = tcping.get_dst_ip(host)

                if prev_state.get(dst_ip) is None:
                    with open(f'{dst_ip}.txt', 'r') as fh:
                        state = fh.read()
                        prev_state[dst_ip] = state
                    if prev_state[dst_ip] == "1":
                        msg = f'Host {dst_ip} is online already'
                        bot.send_message(bot_conf.chat_id, msg)

                else:

                    if os.path.isfile(f'{dst_ip}.txt'):
                        with open(f'{dst_ip}.txt', 'r') as fh:
                            state = fh.read()
                            cur_state[dst_ip] = state

                    if cur_state[dst_ip] == "1" and prev_state[dst_ip] == "0":
                        prev_state[dst_ip] = '1'
                        bot.send_message(
                            bot_conf.chat_id, f'Host: {dst_ip} is online now')

                    elif prev_state[dst_ip] == "1" and \
                            cur_state[dst_ip] == '0':
                        prev_state[dst_ip] = '0'
                        bot.send_message(
                            bot_conf.chat_id, f'Host: {dst_ip} is offline now')
            sleep(self.survey_time)

    def add_tcping_daemon(self, host, port) -> None:
        dst_ip = tcping.get_dst_ip(host)
        with open(f'{dst_ip}.txt', 'w') as fh:
            fh.write('0')

        self.hosts.append(bot_conf.host)
        interval = self.tcping_interval
        timeout = self.tcping_timeout

        thread = StoppableThread(
            target=tcping.start_tcping_session,
            args=(host, port, sys.maxsize, timeout, interval, True))
        self.TCPing_daemons.append(thread)

        thread.start()

    def remove_stat_files(self) -> None:
        files = os.listdir('.')
        for file in files:
            if re.search(r'\d{1,3}.\d{1,3}.\d{1,3}.\d{1,3}', file):
                os.remove(file)

    def stop_daemons(self) -> None:
        for daemon in self.TCPing_daemons:
            daemon.stop()


class BotConfig:
    def __init__(self) -> None:
        self.bot_token = '5372606727:AAE_2d8Rv2AGlLj0rmXg65VHIyqrzmS_Wuo'
        self.usr_token = 'gp1uAlBWl-q5wtBd7wqoHfhiUBsUsub1R86jm63ASUg'

        self.host = 'habr.ru'
        self.port = 80
        self.count = 3

        self.timeout = 0.5
        self.interval = 0.5

        self.chat_id = None


reject_msg = 'I can\'t recognize you. You\'re not my master!'

bot_conf = BotConfig()
authorized = False
watch_dog_started = False

bot = telebot.TeleBot(bot_conf.bot_token)
watch_dog = WatchDog()


def generate_inline_keys():
    keyboard = InlineKeyboardMarkup()
    keyboard.add(InlineKeyboardButton('Start WatchDog', callback_data='actWD'))
    keyboard.add(
        InlineKeyboardButton(
            'Start session',
            callback_data='startSession'))
    keyboard.add(InlineKeyboardButton('Update', callback_data='upd'))
    keyboard.add(InlineKeyboardButton('Help me!', callback_data='help'))
    return keyboard


def sigint_handler(signal, frame):
    print('Started graceful shutdown')

    watch_dog.stop_daemons()
    sleep(watch_dog.tcping_interval + watch_dog.tcping_timeout)

    watch_dog.remove_stat_files()
    watch_dog.stop_watcher()

    print('Done!')
    sys.exit(0)


signal.signal(signal.SIGINT, sigint_handler)


@bot.message_handler(commands=['start'])
def start_command(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=3)
    markup.add(KeyboardButton('/auth'), KeyboardButton('/update'),
               KeyboardButton('/help'), KeyboardButton('/tcping'),
               KeyboardButton('/watchdog'))

    bot.send_message(
        message.chat.id,
        'Hello there, I\'m tcping Telegram bot!\nPlease, authorize yourself ' +
        'first. \n\nIf you have your User Token as environmental variable ' +
        '(TCPING_AUTH), you can easily do this with /auth command',
        reply_markup=markup)


@bot.message_handler(commands=['help'])
def help_command(message):
    if authorized:
        keyboard = generate_inline_keys()
        bot.send_message(
            message.chat.id,
            'I have two commands.\n\n' +
            '"Start session" or "/tcping" pings selected host on ' +
            'selected port (default habr.ru, port 80, 3 times)\n\n' +
            '"Start WatchDog" or "/watchdog" starts thread which monitors ' +
            'selected host on selected port using TCPing\n\n' +
            'Use this commands to change settings:\n' +
            '/server $new_val\n' +
            '/count $new_val\n' +
            '/interval $new_val\n' +
            '/port $new_val\n' +
            '/update - Updates list of hosts for Watch Dog',
            reply_markup=keyboard
        )
    else:
        send_reject_msg(message)


@bot.message_handler(commands=['tcping'])
def start_tcping(message):
    if authorized:
        send_results(message)
    else:
        send_reject_msg(message)


@bot.message_handler(commands=['watchdog'])
def act_wd(message):
    global watch_dog_started
    if authorized:
        watch_dog_started = True
        if watch_dog.wd_online:
            bot.send_message(
                message.chat.id,
                'You have already started WatchDog.\n\n' +
                'To add new observed host:\n' +
                '/server $ip_of_new_host\n' +
                '/port $port_of_desired_host\n' +
                '/update')
        else:
            bot_conf.chat_id = message.chat.id

            watch_dog.start_watcher()
            watch_dog.add_tcping_daemon(bot_conf.host, bot_conf.port)
            bot.send_message(
                message.chat.id,
                'Watch Dog was successfully started ' +
                f'and now looking for {bot_conf.host}')
    else:
        send_reject_msg(message)


@bot.message_handler(commands=['auth'])
def quick_auth(message):
    global authorized
    if not authorized:
        auth_token = os.environ.get('TCPING_AUTH')
        if auth_token is None:
            bot.send_message(
                message.chat.id,
                'Sorry, but you don\'t have token as env. variable')
        elif auth_token == bot_conf.usr_token:
            authorized = True
            bot.send_message(message.chat.id, 'Successfully authorized!')

            keyboard = generate_inline_keys()

            bot.send_message(
                message.chat.id,
                'Greetings, sir. How may I serve you?',
                reply_markup=keyboard)

        else:
            bot.send_message(
                message.chat.id,
                'Sorry, this doesn\'t look like authorization token.')
    else:
        bot.send_message(message.chat.id, 'Already authorized!')


@bot.message_handler(commands=['server'])
def set_host(message):
    if authorized:
        host = validate_and_get(message)
        if host is not None:
            bot_conf.host = host
            bot.send_message(message.chat.id, f'Changed host to: {host}')
    else:
        send_reject_msg(message)


@bot.message_handler(commands=['port'])
def set_port(message):
    if authorized:
        port = validate_and_get(message)
        if port is not None:
            bot_conf.port = int(port)

            bot.send_message(message.chat.id, f'Changed port to: {port} ')
    else:
        send_reject_msg(message)


@bot.message_handler(commands=['count'])
def set_count(message):
    if authorized:
        count = validate_and_get(message)
        if count is not None:
            count = int(count)
            if count < 0:
                bot.send_message(
                    message.chat.id,
                    'You can only use positive integer as ping counter!')
            elif count <= 50:
                bot_conf.count = int(count)
                bot.send_message(message.chat.id, f'Changed count to: {count}')
            else:
                bot.send_message(
                    message.chat.id,
                    'You can\'t use tcping in telegram version for long ping' +
                    ' sessions\n (which are longer than 50 pings)')
    else:
        send_reject_msg(message)


@bot.message_handler(commands=['interval'])
def set_interval(message):
    if authorized:
        interval = validate_and_get(message)
        if interval is not None:
            interval = float(interval)
            if interval <= 0:
                bot.send_message(
                    message.chat.id,
                    'You can only use positive integer as interval')
            else:
                bot_conf.interval = float(interval)
                bot.send_message(
                    message.chat.id,
                    f'Changed interval to: {interval} ')
    else:
        send_reject_msg(message)


@bot.message_handler(commands=['update'])
def update(message):
    global watch_dog_started
    if authorized:
        if not watch_dog_started:
            bot.send_message(message.chat.id,
                             'You have to start Watch Dog before using Update')
        else:
            if bot_conf.host not in watch_dog.hosts:
                watch_dog.add_tcping_daemon(bot_conf.host, bot_conf.port)
                bot.send_message(
                    message.chat.id,
                    f'Watch Dog is now looking for {bot_conf.host}')
            else:
                bot.send_message(
                    message.chat.id,
                    'You have already added this host to Watch Dog')
    else:
        send_reject_msg(message)


@bot.message_handler(func=lambda message: True)
def handle_noncommand(message):
    global authorized
    if message.text == bot_conf.usr_token:
        if authorized:
            bot.send_message(
                message.chat.id,
                'You have authorized already, enjoy your session!')
        else:
            authorized = True
        bot.send_message(message.chat.id, 'Successfully authorized!')

        keyboard = generate_inline_keys()

        bot.send_message(
            message.chat.id,
            'Greetings, sir. How may I serve you?',
            reply_markup=keyboard)
    else:
        bot.send_message(
            message.chat.id,
            'Sorry, this doesn\'t look like authorization token.\n' +
            'And I don\'t understand plain text or emoji :(')


def start_session(query):
    if authorized:
        bot.answer_callback_query(query.id)
        send_results(query.message)
    else:
        send_reject_query(query)


def send_results(message):
    init_stdout = sys.stdout

    sys.stdout = open('tcping.log', 'w')
    tcping.start_tcping_session(
        bot_conf.host,
        bot_conf.port,
        bot_conf.count,
        bot_conf.timeout,
        bot_conf.interval,
        False)
    sys.stdout.close()

    sys.stdout = init_stdout

    bot.send_chat_action(message.chat.id, 'upload_document')
    with open('tcping.log', 'rb') as file:
        bot.send_document(chat_id=message.chat.id, document=file)
    os.remove('tcping.log')


def start_watch_dog(query):
    global watch_dog_started
    if authorized:
        watch_dog_started = True
        if watch_dog.wd_online:
            bot.answer_callback_query(query.id)
            bot.send_message(
                query.message.chat.id,
                'You have already started WatchDog.\n\n' +
                'To add new observed host:\n' +
                '/server $ip_of_new_host\n' +
                '/port $port_of_desired_host\n' +
                '/update')
        else:
            bot_conf.chat_id = query.message.chat.id

            watch_dog.start_watcher()
            watch_dog.add_tcping_daemon(bot_conf.host, bot_conf.port)

            bot.send_message(
                query.message.chat.id,
                'Watch Dog was successfully started ' +
                f'and now looking for {bot_conf.host}')
    else:
        send_reject_query(query)


@bot.callback_query_handler(func=lambda call: True)
def iq_callback(query):
    data = query.data
    if data == 'startSession':
        start_session(query)
    elif data == 'actWD':
        start_watch_dog(query)
    elif data == 'help':
        help_command(query.message)
    elif data == 'upd':
        update(query.message)


def send_reject_query(query):
    bot.send_message(query.message.chat.id, reject_msg)


def send_reject_msg(message):
    bot.send_message(message.chat.id, reject_msg)


def validate_and_get(message):
    inp = message.text.split(" ")
    if len(inp) == 2:
        return inp[1]
    else:
        bot.send_message(
            message.chat.id,
            'Incorrect input type! Please, try again')
        return None


if __name__ == '__main__':
    bot.polling(none_stop=True)
