"""Main game controller class."""

import logging
import time
import copy
import threading
import chess
from typing import Optional, List

from dgt.api import Message, Event
from dgt.util import Mode, PlayMode
from core.game_state import GameState
from core.managers import EngineManager, ClockManager, MoveProcessor, BookManager
from core.mode_handlers import ModeHandler, ModeHandlerFactory
from core.event_handlers import EventHandlerFactory
from timecontrol import TimeControl
from utilities import DisplayMsg, Observable


class GameController:
    """Main controller for the chess game."""

    def __init__(self, engine_manager: EngineManager, clock_manager: ClockManager,
                 move_processor: MoveProcessor, book_manager: BookManager,
                 interaction_mode: Mode, dgtboard, dgttranslate, dgtmenu, 
                 dgtdispatcher, args):
        """Initialize game controller."""
        self.engine_manager = engine_manager
        self.clock_manager = clock_manager
        self.move_processor = move_processor
        self.book_manager = book_manager
        self.interaction_mode = interaction_mode
        self.dgtboard = dgtboard
        self.dgttranslate = dgttranslate
        self.dgtmenu = dgtmenu
        self.dgtdispatcher = dgtdispatcher
        self.args = args

        # Initialize game state
        self.game_state = GameState()
        self.game_state.play_mode = PlayMode.USER_WHITE

        # Initialize mode handler
        self.mode_handler = ModeHandlerFactory.create(
            interaction_mode, engine_manager, clock_manager, move_processor, book_manager)

        # FEN timer management
        self.fen_timer = None
        self.fen_timer_running = False
        self.error_fen = None

    def compute_legal_fens(self, game_copy: chess.Board) -> List[str]:
        """Compute a list of legal FENs for the given game."""
        fens = []
        for move in game_copy.legal_moves:
            game_copy.push(move)
            fens.append(game_copy.board_fen())
            game_copy.pop()
        return fens

    def is_not_user_turn(self, turn: bool) -> bool:
        """Return if it is not user's turn."""
        assert self.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE), \
            'wrong mode: %s' % self.interaction_mode
        condition1 = (self.game_state.play_mode == PlayMode.USER_WHITE and turn == chess.BLACK)
        condition2 = (self.game_state.play_mode == PlayMode.USER_BLACK and turn == chess.WHITE)
        return condition1 or condition2

    def start_fen_timer(self):
        """Start the fen timer in case an unhandled fen string been received from board."""
        if self.fen_timer_running:
            self.stop_fen_timer()
        self.fen_timer = threading.Timer(3, self._expired_fen_timer)
        self.fen_timer.start()
        self.fen_timer_running = True

    def stop_fen_timer(self):
        """Stop the fen timer cause another fen string been send."""
        if self.fen_timer_running:
            self.fen_timer.cancel()
            self.fen_timer.join()
            self.fen_timer_running = False

    def _expired_fen_timer(self):
        """Handle times up for an unhandled fen string send from board."""
        self.fen_timer_running = False
        if self.error_fen:
            logging.info('wrong fen %s for 3secs', self.error_fen)
            DisplayMsg.show(Message.WRONG_FEN())
            DisplayMsg.show(Message.EXIT_MENU())

    def process_fen(self, fen: str):
        """Process given fen like doMove, undoMove, takebackPosition, handleSliding."""
        handled_fen = True
        game_state = self.game_state

        # Check for same position
        if fen == game_state.board_fen():
            logging.debug('Already in this fen: %s', fen)

        # Check if we have to undo a previous move (sliding)
        elif fen in game_state.last_legal_fens:
            logging.info('sliding move detected')
            if self.interaction_mode in (Mode.NORMAL, Mode.BRAIN):
                if self.is_not_user_turn(game_state.turn()):
                    self.stop_search()
                    game_state.pop()
                    logging.info('user move in computer turn, reverting to: %s', game_state.fen())
                elif game_state.done_computer_fen:
                    game_state.done_computer_fen = None
                    game_state.done_move = chess.Move.null()
                    game_state.pop()
                    logging.info('user move while computer move is displayed, reverting to: %s', game_state.fen())
                else:
                    handled_fen = False
                    logging.error('last_legal_fens not cleared: %s', game_state.fen())
            elif self.interaction_mode == Mode.REMOTE:
                if self.is_not_user_turn(game_state.turn()):
                    game_state.pop()
                    logging.info('user move in remote turn, reverting to: %s', game_state.fen())
                elif game_state.done_computer_fen:
                    game_state.done_computer_fen = None
                    game_state.done_move = chess.Move.null()
                    game_state.pop()
                    logging.info('user move while remote move is displayed, reverting to: %s', game_state.fen())
                else:
                    handled_fen = False
                    logging.error('last_legal_fens not cleared: %s', game_state.fen())
            else:
                game_state.pop()
                logging.info('wrong color move -> sliding, reverting to: %s', game_state.fen())
            legal_moves = list(game_state.legal_moves)
            move = legal_moves[game_state.last_legal_fens.index(fen)]
            self._handle_user_move(move, sliding=True)
            if self.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE):
                game_state.legal_fens = []
            else:
                game_state.legal_fens = self.compute_legal_fens(game_state.game.copy())

        # legal move
        elif fen in game_state.legal_fens:
            logging.info('standard move detected')
            legal_moves = list(game_state.legal_moves)
            move = legal_moves[game_state.legal_fens.index(fen)]
            self._handle_user_move(move, sliding=False)
            game_state.last_legal_fens = game_state.legal_fens
            if self.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE):
                game_state.legal_fens = []
            else:
                game_state.legal_fens = self.compute_legal_fens(game_state.game.copy())

        # Player had done the computer or remote move on the board
        elif fen == game_state.done_computer_fen:
            logging.info('done move detected')
            assert self.interaction_mode in (Mode.NORMAL, Mode.BRAIN, Mode.REMOTE), \
                'wrong mode: %s' % self.interaction_mode
            DisplayMsg.show(Message.COMPUTER_MOVE_DONE())
            result = self.mode_handler.handle_computer_move_done(game_state)
            if result:
                game_state.legal_fens = []
                DisplayMsg.show(result)
            else:
                self.move_processor.reset()
                self.clock_manager.add_time(not game_state.turn())
                self.clock_manager.start(game_state.turn())
                if self.interaction_mode == Mode.BRAIN:
                    if hasattr(self.mode_handler, 'start_brain'):
                        self.mode_handler.start_brain(game_state)
                game_state.legal_fens = self.compute_legal_fens(game_state.game.copy())
            game_state.last_legal_fens = []

        # Check if this is a previous legal position and allow user to restart from this position
        else:
            handled_fen = False
            game_copy = copy.deepcopy(game_state.game)
            while game_copy.move_stack:
                game_copy.pop()
                if game_copy.board_fen() == fen:
                    handled_fen = True
                    logging.info('current game fen      : %s', game_state.fen())
                    logging.info('undoing game until fen: %s', fen)
                    self.stop_search_and_clock()
                    while len(game_copy.move_stack) < len(game_state.game.move_stack):
                        game_state.pop()

                    # its a complete new pos, delete safed values
                    game_state.done_computer_fen = None
                    game_state.done_move = game_state.pb_move = chess.Move.null()
                    self.move_processor.reset()

                    self.set_wait_state(Message.TAKE_BACK(game=game_state.game.copy()))
                    break

        logging.debug('fen: %s result: %s', fen, handled_fen)
        self.stop_fen_timer()
        if handled_fen:
            self.error_fen = None
        else:
            self.error_fen = fen
            self.start_fen_timer()

    def _handle_user_move(self, move: chess.Move, sliding: bool):
        """Handle a user move."""
        msg = self.mode_handler.handle_user_move(self.game_state, move, sliding)
        if msg:
            game_end = self.mode_handler.check_game_state(self.game_state, self.game_state.play_mode)
            if game_end:
                DisplayMsg.show(msg)
                DisplayMsg.show(game_end)
            else:
                if (self.interaction_mode == Mode.NORMAL or 
                    (self.interaction_mode == Mode.BRAIN and move != self.game_state.pb_move)):
                    if not self.mode_handler.check_game_state(self.game_state, self.game_state.play_mode):
                        logging.info('starting think()')
                        self.mode_handler.start_search(
                            self.game_state, self.clock_manager.get_time_control(), msg)
                elif self.interaction_mode == Mode.BRAIN:
                    logging.info('think() not started cause ponderhit')
                    DisplayMsg.show(msg)
                    self.clock_manager.start(self.game_state.turn())
                    self.engine_manager.hit()
                elif self.interaction_mode in (Mode.REMOTE, Mode.OBSERVE):
                    self.mode_handler.start_search(
                        self.game_state, self.clock_manager.get_time_control(), msg)
                else:  # ANALYSIS, KIBITZ, PONDER
                    self.mode_handler.start_search(
                        self.game_state, self.clock_manager.get_time_control(), msg)

    def stop_search(self):
        """Stop current search."""
        self.engine_manager.stop()
        while not self.engine_manager.is_waiting():
            time.sleep(0.05)
            logging.warning('engine is still not waiting')

    def stop_search_and_clock(self, ponder_hit: bool = False):
        """Stop search and clock based on interaction mode."""
        self.mode_handler.stop_search_and_clock(ponder_hit=ponder_hit)

    def set_wait_state(self, msg: Message, start_search: bool = True):
        """Enter engine waiting (normal mode) and maybe (by parameter) start pondering."""
        game_state = self.game_state
        if not game_state.done_computer_fen:
            game_state.legal_fens = self.compute_legal_fens(game_state.game.copy())
            game_state.last_legal_fens = []

        if self.interaction_mode in (Mode.NORMAL, Mode.BRAIN):
            if game_state.done_computer_fen:
                logging.debug('best move displayed, dont search and also keep play mode: %s', 
                            game_state.play_mode)
                start_search = False
            else:
                old_mode = game_state.play_mode
                game_state.play_mode = PlayMode.USER_WHITE if game_state.turn() == chess.WHITE else PlayMode.USER_BLACK
                if old_mode != game_state.play_mode:
                    logging.debug('new play mode: %s', game_state.play_mode)
                    text = game_state.play_mode.value
                    DisplayMsg.show(Message.PLAY_MODE(play_mode=game_state.play_mode, 
                                                      play_mode_text=self.dgttranslate.text(text)))

        if start_search:
            assert self.engine_manager.is_waiting(), \
                'engine not waiting! thinking status: %s' % self.engine_manager.is_thinking()
            # Go back to analysing or observing
            if self.interaction_mode == Mode.BRAIN and not game_state.done_computer_fen:
                if hasattr(self.mode_handler, 'start_brain'):
                    self.mode_handler.start_brain(game_state)
            if self.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
                self.mode_handler.start_search(
                    game_state, self.clock_manager.get_time_control(), msg)
                return
            if self.interaction_mode in (Mode.OBSERVE, Mode.REMOTE):
                self.mode_handler.start_search(
                    game_state, self.clock_manager.get_time_control(), msg)
                return

        DisplayMsg.show(msg)
        self.stop_fen_timer()

    def set_engine_mode(self):
        """Set engine mode based on interaction mode."""
        ponder_mode = analyse_mode = False
        if self.interaction_mode in (Mode.NORMAL, Mode.REMOTE):
            pass
        elif self.interaction_mode == Mode.BRAIN:
            ponder_mode = True
        elif self.interaction_mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.OBSERVE, Mode.PONDER):
            analyse_mode = True
        self.engine_manager.mode(ponder=ponder_mode, analyse=analyse_mode)

    def process_event(self, event):
        """Process an event from the event queue."""
        handler = EventHandlerFactory.create_handler(event, self)
        if handler:
            handler.handle(event)
        else:
            logging.warning('event not handled : [%s]', event)
