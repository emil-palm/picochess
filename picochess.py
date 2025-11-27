#!/usr/bin/env python3

# Copyright (C) 2013-2018 Jean-Francois Romang (jromang@posteo.de)
#                         Shivkumar Shivaji ()
#                         Jürgen Précour (LocutusOfPenguin@posteo.de)
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import sys
import os
import threading
import copy
import gc
import logging
from logging.handlers import RotatingFileHandler
import time
import queue
import configargparse
from platform import machine

from uci.engine import UciShell, UciEngine
from uci.read import read_engine_ini
import chess
import chess.polyglot
import chess.uci

from timecontrol import TimeControl
from utilities import get_location, update_picochess, get_opening_books, shutdown, reboot, checkout_tag
from utilities import Observable, DisplayMsg, version, evt_queue, write_picochess_ini, hms_time, RepeatedTimer
from pgn import Emailer, PgnDisplay
from server import WebServer
from talker.picotalker import PicoTalkerDisplay
from dispatcher import Dispatcher

from dgt.api import Message, Event
from dgt.util import GameResult, TimeMode, Mode, PlayMode
from dgt.hw import DgtHw
from dgt.pi import DgtPi
from dgt.display import DgtDisplay
from dgt.board import DgtBoard
from dgt.translate import DgtTranslate
from dgt.menu import DgtMenu

from core.game_controller import GameController
from core.managers import EngineManager, ClockManager, MoveProcessor, BookManager
from core.game_state import GameState


def main():
    """Main function."""
    def display_ip_info():
        """Fire an IP_INFO message with the IP adr."""
        location, ext_ip, int_ip = get_location()
        info = {'location': location, 'ext_ip': ext_ip, 'int_ip': int_ip, 'version': version}
        DisplayMsg.show(Message.IP_INFO(info=info))

    def _dgt_serial_nr():
        DisplayMsg.show(Message.DGT_SERIAL_NR(number='dont_use'))

    def transfer_time(time_list: list):
        """Transfer the time list to a TimeControl Object and a Text Object."""
        def _num(time_str):
            try:
                value = int(time_str)
                if value > 99:
                    value = 99
                return value
            except ValueError:
                return 1

        if len(time_list) == 1:
            fixed = _num(time_list[0])
            timec = TimeControl(TimeMode.FIXED, fixed=fixed)
            textc = dgttranslate.text('B00_tc_fixed', timec.get_list_text())
        elif len(time_list) == 2:
            blitz = _num(time_list[0])
            fisch = _num(time_list[1])
            if fisch == 0:
                timec = TimeControl(TimeMode.BLITZ, blitz=blitz)
                textc = dgttranslate.text('B00_tc_blitz', timec.get_list_text())
            else:
                timec = TimeControl(TimeMode.FISCHER, blitz=blitz, fischer=fisch)
                textc = dgttranslate.text('B00_tc_fisch', timec.get_list_text())
        else:
            timec = TimeControl(TimeMode.BLITZ, blitz=5)
            textc = dgttranslate.text('B00_tc_blitz', timec.get_list_text())
        return timec, textc

    def get_engine_level_dict(engine_manager, engine_level):
        """Transfer an engine level to its level_dict plus an index."""
        installed_engines = engine_manager.get_installed_engines()
        for index in range(0, len(installed_engines)):
            eng = installed_engines[index]
            if eng['file'] == engine_manager.get_file():
                level_list = sorted(eng['level_dict'])
                try:
                    level_index = level_list.index(engine_level)
                    return eng['level_dict'][level_list[level_index]], level_index
                except ValueError:
                    break
        return {}, None


    # Enable garbage collection - needed for engine swapping as objects orphaned
    gc.enable()

    # Command line argument parsing
    parser = configargparse.ArgParser(default_config_files=[os.path.join(os.path.dirname(__file__), 'picochess.ini')])
    parser.add_argument('-e', '--engine', type=str, help="UCI engine filename/path such as 'engines/armv7l/a-stockf'",
                        default=None)
    parser.add_argument('-el', '--engine-level', type=str, help='UCI engine level', default=None)
    parser.add_argument('-er', '--engine-remote', type=str,
                        help="UCI engine filename/path such as 'engines/armv7l/a-stockf'", default=None)
    parser.add_argument('-ers', '--engine-remote-server', type=str, help='adress of the remote engine server',
                        default=None)
    parser.add_argument('-eru', '--engine-remote-user', type=str, help='username for the remote engine server')
    parser.add_argument('-erp', '--engine-remote-pass', type=str, help='password for the remote engine server')
    parser.add_argument('-erk', '--engine-remote-key', type=str, help='key file for the remote engine server')
    parser.add_argument('-erh', '--engine-remote-home', type=str, help='engine home path for the remote engine server',
                        default='')
    parser.add_argument('-d', '--dgt-port', type=str,
                        help="enable dgt board on the given serial port such as '/dev/ttyUSB0'")
    parser.add_argument('-b', '--book', type=str, help="path of book such as 'books/b-flank.bin'",
                        default='books/h-varied.bin')
    parser.add_argument('-t', '--time', type=str, default='5 0',
                        help="Time settings <FixSec> or <StMin IncSec> like '10'(move) or '5 0'(game) '3 2'(fischer). \
                        All values must be below 100")
    parser.add_argument('-norl', '--disable-revelation-leds', action='store_true', help='disable Revelation leds')
    parser.add_argument('-l', '--log-level', choices=['notset', 'debug', 'info', 'warning', 'error', 'critical'],
                        default='warning', help='logging level')
    parser.add_argument('-lf', '--log-file', type=str, help='log to the given file')
    parser.add_argument('-pf', '--pgn-file', type=str, help='pgn file used to store the games', default='games.pgn')
    parser.add_argument('-pu', '--pgn-user', type=str, help='user name for the pgn file', default=None)
    parser.add_argument('-pe', '--pgn-elo', type=str, help='user elo for the pgn file', default='-')
    parser.add_argument('-w', '--web-server', dest='web_server_port', nargs='?', const=80, type=int, metavar='PORT',
                        help='launch web server')
    parser.add_argument('-m', '--email', type=str, help='email used to send pgn/log files', default=None)
    parser.add_argument('-ms', '--smtp-server', type=str, help='adress of email server', default=None)
    parser.add_argument('-mu', '--smtp-user', type=str, help='username for email server', default=None)
    parser.add_argument('-mp', '--smtp-pass', type=str, help='password for email server', default=None)
    parser.add_argument('-me', '--smtp-encryption', action='store_true',
                        help='use ssl encryption connection to email server')
    parser.add_argument('-mf', '--smtp-from', type=str, help='From email', default='no-reply@picochess.org')
    parser.add_argument('-mk', '--mailgun-key', type=str, help='key used to send emails via Mailgun Webservice',
                        default=None)
    parser.add_argument('-bc', '--beep-config', choices=['none', 'some', 'all'], help='sets standard beep config',
                        default='some')
    parser.add_argument('-bs', '--beep-some-level', type=int, default=0x03,
                        help='sets (some-)beep level from 0(=no beeps) to 15(=all beeps)')
    parser.add_argument('-uv', '--user-voice', type=str, help='voice for user', default=None)
    parser.add_argument('-cv', '--computer-voice', type=str, help='voice for computer', default=None)
    parser.add_argument('-sv', '--speed-voice', type=int, help='voice speech factor from 0(=90%%) to 9(=135%%)',
                        default=2, choices=range(0, 10))
    parser.add_argument('-sp', '--enable-setpieces-voice', action='store_true',
                        help="speak last computer move again when 'set pieces' displayed")
    parser.add_argument('-u', '--enable-update', action='store_true', help='enable picochess updates')
    parser.add_argument('-ur', '--enable-update-reboot', action='store_true', help='reboot system after update')
    parser.add_argument('-nocm', '--disable-confirm-message', action='store_true', help='disable confirmation messages')
    parser.add_argument('-v', '--version', action='version', version='%(prog)s version {}'.format(version),
                        help='show current version', default=None)
    parser.add_argument('-pi', '--dgtpi', action='store_true', help='use the DGTPi hardware')
    parser.add_argument('-pt', '--ponder-interval', type=int, default=3, choices=range(1, 9),
                        help='how long each part of ponder display should be visible (default=3secs)')
    parser.add_argument('-lang', '--language', choices=['en', 'de', 'nl', 'fr', 'es', 'it'], default='en',
                        help='picochess language')
    parser.add_argument('-c', '--enable-console', action='store_true', help='use console interface')
    parser.add_argument('-cl', '--enable-capital-letters', action='store_true', help='clock messages in capital letters')
    parser.add_argument('-noet', '--disable-et', action='store_true', help='some clocks need this to work - deprecated')
    parser.add_argument('-ss', '--slow-slide', type=int, default=0, choices=range(0, 10),
                        help='extra wait time factor for a stable board position (sliding detect)')
    parser.add_argument('-nosn', '--disable-short-notation', action='store_true', help='disable short notation')

    args, unknown = parser.parse_known_args()

    # Enable logging
    if args.log_file:
        handler = RotatingFileHandler('logs' + os.sep + args.log_file, maxBytes=1.4 * 1024 * 1024, backupCount=5)
        logging.basicConfig(level=getattr(logging, args.log_level.upper()),
                            format='%(asctime)s.%(msecs)03d %(levelname)7s %(module)10s - %(funcName)s: %(message)s',
                            datefmt="%Y-%m-%d %H:%M:%S", handlers=[handler])
    logging.getLogger('chess.engine').setLevel(logging.INFO)  # don't want to get so many python-chess uci messages

    logging.debug('#' * 20 + ' PicoChess v%s ' + '#' * 20, version)
    # log the startup parameters but hide the password fields
    a_copy = copy.copy(vars(args))
    a_copy['mailgun_key'] = a_copy['smtp_pass'] = a_copy['engine_remote_key'] = a_copy['engine_remote_pass'] = '*****'
    logging.debug('startup parameters: %s', a_copy)
    if unknown:
        logging.warning('invalid parameter given %s', unknown)
    # wire some dgt classes
    dgtboard = DgtBoard(args.dgt_port, args.disable_revelation_leds, args.dgtpi, args.disable_et, args.slow_slide)
    dgttranslate = DgtTranslate(args.beep_config, args.beep_some_level, args.language, version)
    dgtmenu = DgtMenu(args.disable_confirm_message, args.ponder_interval,
                      args.user_voice, args.computer_voice, args.speed_voice, args.enable_capital_letters,
                      args.disable_short_notation, args.log_file, args.engine_remote_server, dgttranslate)
    dgtdispatcher = Dispatcher(dgtmenu)

    time_control, time_text = transfer_time(args.time.split())
    time_text.beep = False
    # The class dgtDisplay fires Event (Observable) & DispatchDgt (Dispatcher)
    DgtDisplay(dgttranslate, dgtmenu, time_control).start()

    # Create PicoTalker for speech output
    PicoTalkerDisplay(args.user_voice, args.computer_voice, args.speed_voice, args.enable_setpieces_voice).start()

    # Launch web server
    if args.web_server_port:
        WebServer(args.web_server_port, dgtboard).start()
        dgtdispatcher.register('web')

    if args.enable_console:
        logging.debug('starting PicoChess in console mode')
        RepeatedTimer(1, _dgt_serial_nr).start()  # simulate the dgtboard watchdog
    else:
        # Connect to DGT board
        logging.debug('starting PicoChess in board mode')
        if args.dgtpi:
            DgtPi(dgtboard).start()
            dgtdispatcher.register('i2c')
        else:
            logging.debug('(ser) starting the board connection')
            dgtboard.run()  # a clock can only be online together with the board, so we must start it infront
        DgtHw(dgtboard).start()
        dgtdispatcher.register('ser')
    # The class Dispatcher sends DgtApi messages at the correct (delayed) time out
    dgtdispatcher.start()
    # Save to PGN
    emailer = Emailer(email=args.email, mailgun_key=args.mailgun_key)
    emailer.set_smtp(sserver=args.smtp_server, suser=args.smtp_user, spass=args.smtp_pass,
                     sencryption=args.smtp_encryption, sfrom=args.smtp_from)

    PgnDisplay('games' + os.sep + args.pgn_file, emailer).start()
    if args.pgn_user:
        user_name = args.pgn_user
    else:
        if args.email:
            user_name = args.email.split('@')[0]
        else:
            user_name = 'Player'

    # Update
    if args.enable_update:
        update_picochess(args.dgtpi, args.enable_update_reboot, dgttranslate)

    # try the given engine first and if that fails the first/second from "engines.ini" then crush
    engine_file = args.engine if args.engine_remote_server is None else args.engine_remote
    engine_home = 'engines' + os.sep + machine() if args.engine_remote_server is None else args.engine_remote_home.rstrip(os.sep)
    engine_tries = 0
    engine = engine_name = None
    uci_shell = UciShell(hostname=args.engine_remote_server, username=args.engine_remote_user,
                         key_file=args.engine_remote_key, password=args.engine_remote_pass)
    while engine_tries < 2:
        if engine_file is None:
            eng_ini = read_engine_ini(uci_shell.get(), engine_home)
            engine_file = eng_ini[engine_tries]['file']
            engine_tries += 1
        engine_file = os.path.basename(engine_file)
        # Gentlemen, start your engines...
        engine = UciEngine(file=engine_file, uci_shell=uci_shell, home=engine_home)
        try:
            engine_name = engine.get_name()
            break
        except AttributeError:
            logging.error('engine %s not started', engine_file)
            engine_file = None

    if engine_tries == 2:
        time.sleep(3)
        DisplayMsg.show(Message.ENGINE_FAIL())
        time.sleep(2)
        sys.exit(-1)

    # Startup - internal
    # Initialize managers
    engine_manager = EngineManager(engine, uci_shell)
    clock_manager = ClockManager(time_control)
    move_processor = MoveProcessor()
    
    all_books = get_opening_books()
    try:
        book_index = [book['file'] for book in all_books].index(args.book)
    except ValueError:
        logging.warning('selected book not present, defaulting to %s', all_books[7]['file'])
        book_index = 7
    book_manager = BookManager(all_books[book_index]['file'])
    
    interaction_mode = Mode.NORMAL

    args.engine_level = None if args.engine_level == 'None' else args.engine_level
    engine_opt, level_index = get_engine_level_dict(engine_manager, args.engine_level)
    engine_manager.startup(engine_opt)
    engine_manager.newgame(chess.Board())
    
    # Initialize game controller
    game_controller = GameController(
        engine_manager, clock_manager, move_processor, book_manager,
        interaction_mode, dgtboard, dgttranslate, dgtmenu, dgtdispatcher, args)
    
    # Initialize game state legal FENs
    game_controller.game_state.legal_fens = game_controller.compute_legal_fens(
        game_controller.game_state.game.copy())

    # Startup - external
    level_name = args.engine_level
    if level_name:
        level_text = dgttranslate.text('B00_level', level_name)
        level_text.beep = False
    else:
        level_text = None
        level_name = ''
    sys_info = {'version': version, 'engine_name': engine_manager.get_name(), 
                'user_name': user_name, 'user_elo': args.pgn_elo}
    DisplayMsg.show(Message.STARTUP_INFO(info={'interaction_mode': interaction_mode, 
                                               'play_mode': game_controller.game_state.play_mode,
                                               'books': all_books, 'book_index': book_index,
                                               'level_text': level_text, 'level_name': level_name,
                                               'tc_init': time_control.get_parameters(), 'time_text': time_text}))
    DisplayMsg.show(Message.SYSTEM_INFO(info=sys_info))
    DisplayMsg.show(Message.ENGINE_STARTUP(installed_engines=engine_manager.get_installed_engines(), 
                                           file=engine_manager.get_file(),
                                           level_index=level_index,
                                           has_960=engine_manager.has_chess960(), 
                                           has_ponder=engine_manager.has_ponder()))

    ip_info_thread = threading.Timer(10, display_ip_info)  # give RaspberyPi 10sec time to startup its network devices
    ip_info_thread.start()

    # Event loop
    logging.info('evt_queue ready')
    while True:
        try:
            event = evt_queue.get()
        except queue.Empty:
            pass
        else:
            logging.debug('received event from evt_queue: %s', event)
            game_controller.process_event(event)
            evt_queue.task_done()


if __name__ == '__main__':
    main()
