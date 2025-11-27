"""Event handler classes for processing different event types."""

import logging
import time
import copy
import chess
import gc
from typing import Optional
from abc import ABC, abstractmethod

from dgt.api import Message, Event
from dgt.util import Mode, PlayMode, GameResult, TimeMode
from core.managers import EngineManager, ClockManager, MoveProcessor, BookManager
from core.game_state import GameState
from core.mode_handlers import ModeHandler, ModeHandlerFactory
from timecontrol import TimeControl
from utilities import DisplayMsg, Observable, write_picochess_ini, hms_time


class EventHandler(ABC):
    """Base class for event handlers."""

    def __init__(self, game_controller):
        """Initialize event handler with reference to game controller."""
        self.game_controller = game_controller

    @abstractmethod
    def handle(self, event):
        """Handle the event."""
        pass


class FenEventHandler(EventHandler):
    """Handles FEN events from the board."""

    def handle(self, event: Event.FEN):
        """Process FEN string from board."""
        self.game_controller.process_fen(event.fen)


class KeyboardMoveEventHandler(EventHandler):
    """Handles keyboard move events."""

    def handle(self, event: Event.KEYBOARD_MOVE):
        """Handle keyboard move."""
        move = event.move
        logging.debug('keyboard move [%s]', move)
        game_state = self.game_controller.game_state
        if move not in game_state.game.legal_moves:
            logging.warning('illegal move. fen: [%s]', game_state.fen())
        else:
            game_copy = game_state.game.copy()
            game_copy.push(move)
            fen = game_copy.board_fen()
            DisplayMsg.show(Message.DGT_FEN(fen=fen, raw=False))


class LevelEventHandler(EventHandler):
    """Handles engine level changes."""

    def handle(self, event: Event.LEVEL):
        """Handle level change."""
        if event.options:
            self.game_controller.engine_manager.startup(event.options, False)
        DisplayMsg.show(Message.LEVEL(level_text=event.level_text, level_name=event.level_name,
                                      do_speak=bool(event.options)))
        self.game_controller.stop_fen_timer()


class NewEngineEventHandler(EventHandler):
    """Handles new engine selection."""

    def handle(self, event: Event.NEW_ENGINE):
        """Handle new engine."""
        old_file = self.game_controller.engine_manager.get_file()
        old_options = {}
        raw_options = self.game_controller.engine_manager.get_options()
        for name, value in raw_options.items():
            old_options[name] = str(value.default)

        engine_fallback = False
        self.game_controller.stop_search()
        
        if self.game_controller.engine_manager.quit():
            from uci.engine import UciEngine
            uci_shell = self.game_controller.engine_manager.get_uci_shell()
            new_engine = UciEngine(file=event.eng['file'], uci_shell=uci_shell)
            try:
                engine_name = new_engine.get_name()
            except AttributeError:
                logging.error('new engine failed to start, reverting to %s', old_file)
                engine_fallback = True
                event.options = old_options
                new_engine = UciEngine(file=old_file, uci_shell=uci_shell)
                try:
                    engine_name = new_engine.get_name()
                except AttributeError:
                    logging.error('no engines started')
                    DisplayMsg.show(Message.ENGINE_FAIL())
                    time.sleep(3)
                    import sys
                    sys.exit(-1)
            
            new_engine.startup(event.options)
            new_engine.newgame(self.game_controller.game_state.game.copy())
            
            if (self.game_controller.interaction_mode == Mode.BRAIN and 
                not new_engine.has_ponder()):
                logging.debug('new engine doesnt support brain mode, reverting to %s', old_file)
                engine_fallback = True
                if new_engine.quit():
                    new_engine = UciEngine(file=old_file, uci_shell=uci_shell)
                    new_engine.startup(old_options)
                    new_engine.newgame(self.game_controller.game_state.game.copy())
                else:
                    logging.error('engine shutdown failure')
            
            # Update the engine manager with the new engine
            self.game_controller.engine_manager.engine = new_engine
            self.game_controller.engine_manager.engine_name = new_engine.get_name()
            
            self.game_controller.set_engine_mode()
            if engine_fallback:
                msg = Message.ENGINE_FAIL()
            else:
                self.game_controller.move_processor.reset()
                engine_name = self.game_controller.engine_manager.get_name()
                msg = Message.ENGINE_READY(eng=event.eng, engine_name=engine_name,
                                           eng_text=event.eng_text, 
                                           has_levels=self.game_controller.engine_manager.has_levels(),
                                           has_960=self.game_controller.engine_manager.has_chess960(), 
                                           has_ponder=self.game_controller.engine_manager.has_ponder(),
                                           show_ok=event.show_ok)
            gc.collect()
            self.game_controller.set_wait_state(msg, not engine_fallback)
            if self.game_controller.interaction_mode in (Mode.NORMAL, Mode.BRAIN):
                self.game_controller.clock_manager.stop()
        else:
            logging.error('engine shutdown failure')
            DisplayMsg.show(Message.ENGINE_FAIL())
        
        if not engine_fallback and not self.game_controller.args.engine_remote_server:
            write_picochess_ini('engine', event.eng['file'])


class SetupPositionEventHandler(EventHandler):
    """Handles setup position events."""

    def handle(self, event: Event.SETUP_POSITION):
        """Handle setup position."""
        logging.debug('setting up custom fen: %s', event.fen)
        game_state = self.game_controller.game_state
        
        if game_state.game.move_stack:
            if not (game_state.game.is_game_over() or game_state.game_declared):
                result = GameResult.ABORT
                DisplayMsg.show(Message.GAME_ENDS(result=result, play_mode=game_state.play_mode, 
                                                  game=game_state.game.copy()))
        
        game_state.reset(fen=event.fen)
        if self.game_controller.engine_manager.has_chess960():
            self.game_controller.engine_manager.option('UCI_Chess960', event.uci960)
            self.game_controller.engine_manager.send()
        self.game_controller.engine_manager.newgame(game_state.game.copy())
        self.game_controller.clock_manager.reset()
        self.game_controller.move_processor.reset()
        game_state.game_declared = False
        self.game_controller.set_wait_state(Message.START_NEW_GAME(game=game_state.game.copy(), newgame=True))


class NewGameEventHandler(EventHandler):
    """Handles new game events."""

    def handle(self, event: Event.NEW_GAME):
        """Handle new game."""
        game_state = self.game_controller.game_state
        newgame = game_state.game.move_stack or (game_state.game.chess960_pos() != event.pos960)
        
        if newgame:
            logging.debug('starting a new game with code: %s', event.pos960)
            uci960 = event.pos960 != 518

            if not (game_state.game.is_game_over() or game_state.game_declared):
                result = GameResult.ABORT
                DisplayMsg.show(Message.GAME_ENDS(result=result, play_mode=game_state.play_mode, 
                                                  game=game_state.game.copy()))

            game_state.reset(chess960_pos=event.pos960)
            self.game_controller.stop_search_and_clock()
            if self.game_controller.engine_manager.has_chess960():
                self.game_controller.engine_manager.option('UCI_Chess960', uci960)
                self.game_controller.engine_manager.send()
            self.game_controller.engine_manager.newgame(game_state.game.copy())
            self.game_controller.clock_manager.reset()
            self.game_controller.move_processor.reset()
            game_state.game_declared = False
            self.game_controller.set_wait_state(Message.START_NEW_GAME(game=game_state.game.copy(), newgame=newgame))
        else:
            logging.debug('no need to start a new game')
            DisplayMsg.show(Message.START_NEW_GAME(game=game_state.game.copy(), newgame=newgame))


class PauseResumeEventHandler(EventHandler):
    """Handles pause/resume events."""

    def handle(self, event: Event.PAUSE_RESUME):
        """Handle pause/resume."""
        if self.game_controller.engine_manager.is_thinking():
            self.game_controller.clock_manager.stop()
            self.game_controller.engine_manager.stop(show_best=True)
        elif not self.game_controller.game_state.done_computer_fen:
            if self.game_controller.clock_manager.is_running():
                self.game_controller.clock_manager.stop()
            else:
                self.game_controller.clock_manager.start(self.game_controller.game_state.turn())
        else:
            logging.debug('best move displayed, dont start/stop clock')


class AlternativeMoveEventHandler(EventHandler):
    """Handles alternative move requests."""

    def handle(self, event: Event.ALTERNATIVE_MOVE):
        """Handle alternative move."""
        game_state = self.game_controller.game_state
        if game_state.done_computer_fen:
            game_state.done_computer_fen = None
            game_state.done_move = chess.Move.null()
            if self.game_controller.interaction_mode in (Mode.NORMAL, Mode.BRAIN):
                if self.game_controller.clock_manager.get_time_control().mode == TimeMode.FIXED:
                    self.game_controller.clock_manager.reset()
                play_mode = PlayMode.USER_WHITE if game_state.turn() == chess.BLACK else PlayMode.USER_BLACK
                game_state.play_mode = play_mode
                if not self.game_controller.mode_handler.check_game_state(game_state, play_mode):
                    self.game_controller.mode_handler.start_search(
                        game_state, self.game_controller.clock_manager.get_time_control(),
                        Message.ALTERNATIVE_MOVE(game=game_state.game.copy(), play_mode=play_mode))
            else:
                logging.warning('wrong function call [alternative]! mode: %s', self.game_controller.interaction_mode)


class SwitchSidesEventHandler(EventHandler):
    """Handles switch sides events."""

    def handle(self, event: Event.SWITCH_SIDES):
        """Handle switch sides."""
        if self.game_controller.interaction_mode in (Mode.NORMAL, Mode.BRAIN):
            if not self.game_controller.engine_manager.is_waiting():
                self.game_controller.stop_search_and_clock()

            game_state = self.game_controller.game_state
            last_legal_fens = game_state.last_legal_fens
            best_move_displayed = game_state.done_computer_fen
            if best_move_displayed:
                move = game_state.done_move
                game_state.done_computer_fen = None
                game_state.done_move = game_state.pb_move = chess.Move.null()
            else:
                move = chess.Move.null()

            game_state.play_mode = PlayMode.USER_WHITE if game_state.play_mode == PlayMode.USER_BLACK else PlayMode.USER_BLACK
            text = game_state.play_mode.value
            dgttranslate = self.game_controller.dgttranslate
            msg = Message.PLAY_MODE(play_mode=game_state.play_mode, 
                                    play_mode_text=dgttranslate.text(text))

            if self.game_controller.clock_manager.get_time_control().mode == TimeMode.FIXED:
                self.game_controller.clock_manager.reset()

            game_state.legal_fens = []
            game_end = self.game_controller.mode_handler.check_game_state(game_state, game_state.play_mode)
            if game_end:
                DisplayMsg.show(msg)
            else:
                cond1 = game_state.turn() == chess.WHITE and game_state.play_mode == PlayMode.USER_BLACK
                cond2 = game_state.turn() == chess.BLACK and game_state.play_mode == PlayMode.USER_WHITE
                if cond1 or cond2:
                    self.game_controller.clock_manager.reset_start_time()
                    self.game_controller.mode_handler.start_search(
                        game_state, self.game_controller.clock_manager.get_time_control(), msg)
                else:
                    DisplayMsg.show(msg)
                    self.game_controller.clock_manager.start(game_state.turn())
                    game_state.legal_fens = self.game_controller.compute_legal_fens(game_state.game.copy())

            if best_move_displayed:
                DisplayMsg.show(Message.SWITCH_SIDES(game=game_state.game.copy(), move=move))


class DrawResignEventHandler(EventHandler):
    """Handles draw/resign events."""

    def handle(self, event: Event.DRAWRESIGN):
        """Handle draw/resign."""
        game_state = self.game_controller.game_state
        if not game_state.game_declared:
            self.game_controller.stop_search_and_clock()
            DisplayMsg.show(Message.GAME_ENDS(result=event.result, play_mode=game_state.play_mode, 
                                              game=game_state.game.copy()))
            game_state.game_declared = True
            self.game_controller.stop_fen_timer()


class RemoteMoveEventHandler(EventHandler):
    """Handles remote move events."""

    def handle(self, event: Event.REMOTE_MOVE):
        """Handle remote move."""
        game_state = self.game_controller.game_state
        if (self.game_controller.interaction_mode == Mode.REMOTE and 
            self.game_controller.is_not_user_turn(game_state.turn())):
            self.game_controller.stop_search_and_clock()
            DisplayMsg.show(Message.COMPUTER_MOVE(move=event.move, ponder=chess.Move.null(), 
                                                  game=game_state.game.copy(), wait=False))
            game_copy = game_state.game.copy()
            game_copy.push(event.move)
            game_state.done_computer_fen = game_copy.board_fen()
            game_state.done_move = event.move
            game_state.pb_move = chess.Move.null()
        else:
            logging.warning('wrong function call [remote]! mode: %s turn: %s', 
                          self.game_controller.interaction_mode, game_state.turn())


class BestMoveEventHandler(EventHandler):
    """Handles best move events from engine."""

    def handle(self, event: Event.BEST_MOVE):
        """Handle best move from engine."""
        game_state = self.game_controller.game_state
        if (self.game_controller.interaction_mode in (Mode.NORMAL, Mode.BRAIN) and 
            self.game_controller.is_not_user_turn(game_state.turn())):
            self.game_controller.clock_manager.stop()
            DisplayMsg.show(Message.CLOCK_STOP(devs={'ser', 'i2c', 'web'}))
            time.sleep(0.4)
            
            if game_state.game.is_game_over():
                logging.warning('illegal move on game_end - sliding? move: %s fen: %s', 
                              event.move, game_state.fen())
            else:
                if event.inbook:
                    DisplayMsg.show(Message.BOOK_MOVE())
                self.game_controller.move_processor.add_excluded(event.move)
                DisplayMsg.show(Message.COMPUTER_MOVE(move=event.move, ponder=event.ponder, 
                                                      game=game_state.game.copy(), wait=event.inbook))
                game_copy = game_state.game.copy()
                game_copy.push(event.move)
                game_state.done_computer_fen = game_copy.board_fen()
                game_state.done_move = event.move
                brain_book = self.game_controller.interaction_mode == Mode.BRAIN and event.inbook
                game_state.pb_move = event.ponder if event.ponder and not brain_book else chess.Move.null()
        else:
            logging.warning('wrong function call [best]! mode: %s turn: %s', 
                          self.game_controller.interaction_mode, game_state.turn())


class NewPvEventHandler(EventHandler):
    """Handles new principal variation events."""

    def handle(self, event: Event.NEW_PV):
        """Handle new PV."""
        game_state = self.game_controller.game_state
        if (self.game_controller.interaction_mode == Mode.BRAIN and 
            self.game_controller.engine_manager.is_pondering()):
            logging.debug('in brain mode and pondering ignore pv %s', event.pv[:3])
        else:
            if game_state.game.is_legal(event.pv[0]):
                DisplayMsg.show(Message.NEW_PV(pv=event.pv, mode=self.game_controller.interaction_mode, 
                                              game=game_state.game.copy()))
            else:
                logging.info('illegal move can not be displayed. move: %s fen: %s', 
                            event.pv[0], game_state.fen())
                logging.info('engine status: t:%s p:%s', 
                           self.game_controller.engine_manager.is_thinking(),
                           self.game_controller.engine_manager.is_pondering())


class NewScoreEventHandler(EventHandler):
    """Handles new score events."""

    def handle(self, event: Event.NEW_SCORE):
        """Handle new score."""
        game_state = self.game_controller.game_state
        if (self.game_controller.interaction_mode == Mode.BRAIN and 
            self.game_controller.engine_manager.is_pondering()):
            logging.debug('in brain mode and pondering, ignore score %s', event.score)
        else:
            DisplayMsg.show(Message.NEW_SCORE(score=event.score, mate=event.mate, 
                                             mode=self.game_controller.interaction_mode,
                                             turn=game_state.turn()))


class NewDepthEventHandler(EventHandler):
    """Handles new depth events."""

    def handle(self, event: Event.NEW_DEPTH):
        """Handle new depth."""
        if (self.game_controller.interaction_mode == Mode.BRAIN and 
            self.game_controller.engine_manager.is_pondering()):
            logging.debug('in brain mode and pondering, ignore depth %s', event.depth)
        else:
            DisplayMsg.show(Message.NEW_DEPTH(depth=event.depth))


class StartSearchEventHandler(EventHandler):
    """Handles search start events."""

    def handle(self, event: Event.START_SEARCH):
        """Handle search start."""
        DisplayMsg.show(Message.SEARCH_STARTED())


class StopSearchEventHandler(EventHandler):
    """Handles search stop events."""

    def handle(self, event: Event.STOP_SEARCH):
        """Handle search stop."""
        DisplayMsg.show(Message.SEARCH_STOPPED())


class SetInteractionModeEventHandler(EventHandler):
    """Handles interaction mode changes."""

    def handle(self, event: Event.SET_INTERACTION_MODE):
        """Handle interaction mode change."""
        game_state = self.game_controller.game_state
        if event.mode not in (Mode.NORMAL, Mode.REMOTE) and game_state.done_computer_fen:
            dgtmenu = self.game_controller.dgtmenu
            dgtmenu.set_mode(self.game_controller.interaction_mode)
            logging.warning('mode cant be changed to a pondering mode as long as a move is displayed')
            mode_text = self.game_controller.dgttranslate.text('Y10_errormode')
            msg = Message.INTERACTION_MODE(mode=self.game_controller.interaction_mode, 
                                          mode_text=mode_text, show_ok=False)
            DisplayMsg.show(msg)
        else:
            self.game_controller.stop_search_and_clock()
            self.game_controller.interaction_mode = event.mode
            self.game_controller.set_engine_mode()
            from core.mode_handlers import ModeHandlerFactory
            self.game_controller.mode_handler = ModeHandlerFactory.create(
                event.mode, self.game_controller.engine_manager, 
                self.game_controller.clock_manager, self.game_controller.move_processor,
                self.game_controller.book_manager)
            msg = Message.INTERACTION_MODE(mode=event.mode, mode_text=event.mode_text, 
                                          show_ok=event.show_ok)
            self.game_controller.set_wait_state(msg)


class SetOpeningBookEventHandler(EventHandler):
    """Handles opening book changes."""

    def handle(self, event: Event.SET_OPENING_BOOK):
        """Handle opening book change."""
        write_picochess_ini('book', event.book['file'])
        logging.debug('changing opening book [%s]', event.book['file'])
        self.game_controller.book_manager.change_book(event.book['file'])
        DisplayMsg.show(Message.OPENING_BOOK(book_text=event.book_text, show_ok=event.show_ok))
        self.game_controller.stop_fen_timer()


class SetTimeControlEventHandler(EventHandler):
    """Handles time control changes."""

    def handle(self, event: Event.SET_TIME_CONTROL):
        """Handle time control change."""
        tc_init = event.tc_init
        new_time_control = TimeControl(**tc_init)
        self.game_controller.clock_manager.change_time_control(new_time_control)
        if new_time_control.mode == TimeMode.BLITZ:
            write_picochess_ini('time', '{:d} 0'.format(tc_init['blitz']))
        elif new_time_control.mode == TimeMode.FISCHER:
            write_picochess_ini('time', '{:d} {:d}'.format(tc_init['blitz'], tc_init['fischer']))
        elif new_time_control.mode == TimeMode.FIXED:
            write_picochess_ini('time', '{:d}'.format(tc_init['fixed']))
        text = Message.TIME_CONTROL(time_text=event.time_text, show_ok=event.show_ok, tc_init=tc_init)
        DisplayMsg.show(text)
        self.game_controller.stop_fen_timer()


class ClockTimeEventHandler(EventHandler):
    """Handles clock time updates."""

    def handle(self, event: Event.CLOCK_TIME):
        """Handle clock time."""
        dgtdispatcher = self.game_controller.dgtdispatcher
        if dgtdispatcher.is_prio_device(event.dev, event.connect):
            logging.debug('setting tc clock time - prio: %s w:%s b:%s', event.dev,
                          hms_time(event.time_white), hms_time(event.time_black))
            self.game_controller.clock_manager.set_clock_times(event.time_white, event.time_black)
            time_u = event.time_white
            time_c = event.time_black
            if self.game_controller.interaction_mode in (Mode.NORMAL, Mode.BRAIN):
                if self.game_controller.game_state.play_mode == PlayMode.USER_BLACK:
                    time_u, time_c = time_c, time_u
            else:
                if time_c < time_u:
                    time_u, time_c = time_c, time_u
            low_time = (time_u <= 60 and not 
                       (self.game_controller.clock_manager.get_time_control().mode == TimeMode.FIXED and 
                        self.game_controller.clock_manager.get_time_control().move_time > 2))
            self.game_controller.dgtboard.low_time = low_time
            DisplayMsg.show(Message.CLOCK_TIME(time_white=event.time_white, time_black=event.time_black,
                                               low_time=low_time))
        else:
            logging.debug('ignore clock time - too low prio: %s', event.dev)


class OutOfTimeEventHandler(EventHandler):
    """Handles out of time events."""

    def handle(self, event: Event.OUT_OF_TIME):
        """Handle out of time."""
        self.game_controller.stop_search_and_clock()
        result = GameResult.OUT_OF_TIME
        DisplayMsg.show(Message.GAME_ENDS(result=result, play_mode=self.game_controller.game_state.play_mode, 
                                          game=self.game_controller.game_state.game.copy()))


class ShutdownEventHandler(EventHandler):
    """Handles shutdown events."""

    def handle(self, event: Event.SHUTDOWN):
        """Handle shutdown."""
        uci_shell = self.game_controller.engine_manager.get_uci_shell()
        if uci_shell.get():
            uci_shell.get().__exit__(None, None, None)
        result = GameResult.ABORT
        DisplayMsg.show(Message.GAME_ENDS(result=result, play_mode=self.game_controller.game_state.play_mode, 
                                          game=self.game_controller.game_state.game.copy()))
        DisplayMsg.show(Message.SYSTEM_SHUTDOWN())
        from utilities import shutdown
        shutdown(self.game_controller.args.dgtpi and uci_shell.get() is None, dev=event.dev)


class RebootEventHandler(EventHandler):
    """Handles reboot events."""

    def handle(self, event: Event.REBOOT):
        """Handle reboot."""
        result = GameResult.ABORT
        DisplayMsg.show(Message.GAME_ENDS(result=result, play_mode=self.game_controller.game_state.play_mode, 
                                          game=self.game_controller.game_state.game.copy()))
        DisplayMsg.show(Message.SYSTEM_REBOOT())
        from utilities import reboot
        uci_shell = self.game_controller.engine_manager.get_uci_shell()
        reboot(self.game_controller.args.dgtpi and uci_shell.get() is None, dev=event.dev)


class EmailLogEventHandler(EventHandler):
    """Handles email log events."""

    def handle(self, event: Event.EMAIL_LOG):
        """Handle email log."""
        from pgn import Emailer
        email_logger = Emailer(email=self.game_controller.args.email, 
                              mailgun_key=self.game_controller.args.mailgun_key)
        email_logger.set_smtp(sserver=self.game_controller.args.smtp_server, 
                             suser=self.game_controller.args.smtp_user, 
                             spass=self.game_controller.args.smtp_pass,
                             sencryption=self.game_controller.args.smtp_encryption, 
                             sfrom=self.game_controller.args.smtp_from)
        body = 'You probably want to forward this file to a picochess developer ;-)'
        import os
        email_logger.send('Picochess LOG', body, '/opt/picochess/logs/{}'.format(self.game_controller.args.log_file))


class SetVoiceEventHandler(EventHandler):
    """Handles voice setting events."""

    def handle(self, event: Event.SET_VOICE):
        """Handle voice setting."""
        DisplayMsg.show(Message.SET_VOICE(type=event.type, lang=event.lang, speaker=event.speaker,
                                          speed=event.speed))


class KeyboardButtonEventHandler(EventHandler):
    """Handles keyboard button events."""

    def handle(self, event: Event.KEYBOARD_BUTTON):
        """Handle keyboard button."""
        DisplayMsg.show(Message.DGT_BUTTON(button=event.button, dev=event.dev))


class KeyboardFenEventHandler(EventHandler):
    """Handles keyboard FEN events."""

    def handle(self, event: Event.KEYBOARD_FEN):
        """Handle keyboard FEN."""
        DisplayMsg.show(Message.DGT_FEN(fen=event.fen, raw=False))


class ExitMenuEventHandler(EventHandler):
    """Handles exit menu events."""

    def handle(self, event: Event.EXIT_MENU):
        """Handle exit menu."""
        DisplayMsg.show(Message.EXIT_MENU())


class UpdatePicoEventHandler(EventHandler):
    """Handles update pico events."""

    def handle(self, event: Event.UPDATE_PICO):
        """Handle update pico."""
        DisplayMsg.show(Message.UPDATE_PICO())
        from utilities import checkout_tag
        checkout_tag(event.tag)
        DisplayMsg.show(Message.EXIT_MENU())


class RemoteRoomEventHandler(EventHandler):
    """Handles remote room events."""

    def handle(self, event: Event.REMOTE_ROOM):
        """Handle remote room."""
        DisplayMsg.show(Message.REMOTE_ROOM(inside=event.inside))


class EventHandlerFactory:
    """Factory for creating event handlers."""

    _handler_map = {
        Event.FEN: FenEventHandler,
        Event.KEYBOARD_MOVE: KeyboardMoveEventHandler,
        Event.LEVEL: LevelEventHandler,
        Event.NEW_ENGINE: NewEngineEventHandler,
        Event.SETUP_POSITION: SetupPositionEventHandler,
        Event.NEW_GAME: NewGameEventHandler,
        Event.PAUSE_RESUME: PauseResumeEventHandler,
        Event.ALTERNATIVE_MOVE: AlternativeMoveEventHandler,
        Event.SWITCH_SIDES: SwitchSidesEventHandler,
        Event.DRAWRESIGN: DrawResignEventHandler,
        Event.REMOTE_MOVE: RemoteMoveEventHandler,
        Event.BEST_MOVE: BestMoveEventHandler,
        Event.NEW_PV: NewPvEventHandler,
        Event.NEW_SCORE: NewScoreEventHandler,
        Event.NEW_DEPTH: NewDepthEventHandler,
        Event.START_SEARCH: StartSearchEventHandler,
        Event.STOP_SEARCH: StopSearchEventHandler,
        Event.SET_INTERACTION_MODE: SetInteractionModeEventHandler,
        Event.SET_OPENING_BOOK: SetOpeningBookEventHandler,
        Event.SET_TIME_CONTROL: SetTimeControlEventHandler,
        Event.CLOCK_TIME: ClockTimeEventHandler,
        Event.OUT_OF_TIME: OutOfTimeEventHandler,
        Event.SHUTDOWN: ShutdownEventHandler,
        Event.REBOOT: RebootEventHandler,
        Event.EMAIL_LOG: EmailLogEventHandler,
        Event.SET_VOICE: SetVoiceEventHandler,
        Event.KEYBOARD_BUTTON: KeyboardButtonEventHandler,
        Event.KEYBOARD_FEN: KeyboardFenEventHandler,
        Event.EXIT_MENU: ExitMenuEventHandler,
        Event.UPDATE_PICO: UpdatePicoEventHandler,
        Event.REMOTE_ROOM: RemoteRoomEventHandler,
    }

    @classmethod
    def create_handler(cls, event, game_controller):
        """Create appropriate event handler for the event."""
        event_type = type(event)
        handler_class = cls._handler_map.get(event_type)
        if handler_class:
            return handler_class(game_controller)
        return None
