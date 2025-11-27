"""Mode-specific handlers for different interaction modes."""

import logging
import time
import copy
import chess
from typing import Optional
from abc import ABC, abstractmethod

from dgt.api import Message, Event
from dgt.util import Mode, PlayMode, GameResult
from core.managers import EngineManager, ClockManager, MoveProcessor, BookManager
from core.game_state import GameState
from timecontrol import TimeControl


class ModeHandler(ABC):
    """Base class for mode handlers."""

    def __init__(self, engine_manager: EngineManager, clock_manager: ClockManager,
                 move_processor: MoveProcessor, book_manager: BookManager):
        """Initialize mode handler."""
        self.engine_manager = engine_manager
        self.clock_manager = clock_manager
        self.move_processor = move_processor
        self.book_manager = book_manager

    @abstractmethod
    def handle_user_move(self, game_state: GameState, move: chess.Move, sliding: bool) -> Optional[Message]:
        """Handle a user move."""
        pass

    @abstractmethod
    def handle_computer_move_done(self, game_state: GameState) -> Optional[Message]:
        """Handle when computer move is done on board."""
        pass

    @abstractmethod
    def start_search(self, game_state: GameState, time_control: TimeControl, msg: Message):
        """Start engine search."""
        pass

    @abstractmethod
    def stop_search_and_clock(self, ponder_hit: bool = False):
        """Stop search and clock."""
        pass

    def check_game_state(self, game_state: GameState, play_mode: PlayMode) -> Optional[Message]:
        """Check if game has ended."""
        game = game_state.game
        result = None
        if game.is_stalemate():
            result = GameResult.STALEMATE
        if game.is_insufficient_material():
            result = GameResult.INSUFFICIENT_MATERIAL
        if game.is_seventyfive_moves():
            result = GameResult.SEVENTYFIVE_MOVES
        if game.is_fivefold_repetition():
            result = GameResult.FIVEFOLD_REPETITION
        if game.is_checkmate():
            result = GameResult.MATE

        if result is None:
            return None
        else:
            return Message.GAME_ENDS(result=result, play_mode=play_mode, game=game.copy())


class NormalModeHandler(ModeHandler):
    """Handler for NORMAL mode."""

    def handle_user_move(self, game_state: GameState, move: chess.Move, sliding: bool) -> Optional[Message]:
        """Handle user move in normal mode."""
        if move not in game_state.game.legal_moves:
            logging.warning('illegal move [%s]', move)
            return None

        self.stop_search_and_clock(ponder_hit=False)
        if not sliding:
            self.clock_manager.add_time(game_state.turn())

        game_state.done_computer_fen = None
        game_state.done_move = chess.Move.null()
        fen = game_state.fen()
        turn = game_state.turn()
        game_state.push(move)
        self.move_processor.reset()

        msg = Message.USER_MOVE_DONE(move=move, fen=fen, turn=turn, game=game_state.copy())
        game_end = self.check_game_state(game_state, game_state.play_mode)
        if game_end:
            return game_end
        return msg

    def handle_computer_move_done(self, game_state: GameState) -> Optional[Message]:
        """Handle when computer move is done."""
        game_state.game.push(game_state.done_move)
        game_state.done_computer_fen = None
        game_state.done_move = chess.Move.null()
        game_end = self.check_game_state(game_state, game_state.play_mode)
        if game_end:
            return game_end
        self.move_processor.reset()
        self.clock_manager.add_time(not game_state.turn())
        return None

    def start_search(self, game_state: GameState, time_control: TimeControl, msg: Message):
        """Start search in normal mode."""
        from utilities import DisplayMsg, Observable
        from dgt.api import Message as DgtMessage
        DisplayMsg.show(msg)
        self.clock_manager.start(game_state.turn())
        tc_init = time_control.get_parameters()
        DisplayMsg.show(DgtMessage.CLOCK_START(turn=game_state.turn(), tc_init=tc_init, devs={'ser', 'i2c', 'web'}))
        time.sleep(0.4)
        book_res = self.move_processor.get_book_move(
            self.book_manager.get_reader(), game_state.game.copy())
        if book_res:
            Observable.fire(Event.BEST_MOVE(move=book_res.bestmove, ponder=book_res.ponder, inbook=True))
        else:
            while not self.engine_manager.is_waiting():
                time.sleep(0.05)
                logging.warning('engine is still not waiting')
            uci_dict = time_control.uci()
            uci_dict['searchmoves'] = self.move_processor.get_search_moves(game_state.game)
            self.engine_manager.position(copy.deepcopy(game_state.game))
            self.engine_manager.go(uci_dict)

    def stop_search_and_clock(self, ponder_hit: bool = False):
        """Stop search and clock in normal mode."""
        self.clock_manager.stop()
        from utilities import DisplayMsg
        DisplayMsg.show(Message.CLOCK_STOP(devs={'ser', 'i2c', 'web'}))
        time.sleep(0.4)
        if not ponder_hit:
            self.engine_manager.stop()
            while not self.engine_manager.is_waiting():
                time.sleep(0.05)
                logging.warning('engine is still not waiting')


class BrainModeHandler(NormalModeHandler):
    """Handler for BRAIN mode (permanent brain with pondering)."""

    def handle_user_move(self, game_state: GameState, move: chess.Move, sliding: bool) -> Optional[Message]:
        """Handle user move in brain mode."""
        if move not in game_state.game.legal_moves:
            logging.warning('illegal move [%s]', move)
            return None

        ponder_hit = (move == game_state.pb_move)
        logging.info('pondering move: [%s] res: Ponder%s', game_state.pb_move, 'Hit' if ponder_hit else 'Miss')
        if sliding and ponder_hit:
            logging.warning('sliding detected, turn ponderhit off')
            ponder_hit = False

        self.stop_search_and_clock(ponder_hit=ponder_hit)
        if not sliding:
            self.clock_manager.add_time(game_state.turn())

        game_state.done_computer_fen = None
        game_state.done_move = chess.Move.null()
        fen = game_state.fen()
        turn = game_state.turn()
        game_state.push(move)
        self.move_processor.reset()

        msg = Message.USER_MOVE_DONE(move=move, fen=fen, turn=turn, game=game_state.copy())
        game_end = self.check_game_state(game_state, game_state.play_mode)
        if game_end:
            return game_end

        if not ponder_hit:
            return msg
        else:
            logging.info('think() not started cause ponderhit')
            self.clock_manager.start(game_state.turn())
            self.engine_manager.hit()
            return msg

    def handle_computer_move_done(self, game_state: GameState) -> Optional[Message]:
        """Handle when computer move is done."""
        result = super().handle_computer_move_done(game_state)
        if result is None:
            self.start_brain(game_state)
        return result

    def start_brain(self, game_state: GameState):
        """Start permanent brain search."""
        assert not game_state.done_computer_fen, 'brain() called with displayed move'
        if game_state.pb_move:
            game_copy = copy.deepcopy(game_state.game)
            game_copy.push(game_state.pb_move)
            logging.info('start permanent brain with pondering move [%s] fen: %s', 
                        game_state.pb_move, game_copy.fen())
            self.engine_manager.position(game_copy)
            self.engine_manager.brain(self.clock_manager.get_uci_dict())
        else:
            logging.info('ignore permanent brain cause no pondering move available')

    def start_search(self, game_state: GameState, time_control: TimeControl, msg: Message):
        """Start search in brain mode."""
        super().start_search(game_state, time_control, msg)
        # After normal search, start brain if not done_computer_fen
        if not game_state.done_computer_fen:
            self.start_brain(game_state)

    def stop_search_and_clock(self, ponder_hit: bool = False):
        """Stop search and clock in brain mode."""
        self.clock_manager.stop()
        from utilities import DisplayMsg
        DisplayMsg.show(Message.CLOCK_STOP(devs={'ser', 'i2c', 'web'}))
        time.sleep(0.4)
        if ponder_hit:
            pass  # we send engine.hit() later
        else:
            self.engine_manager.stop()
            while not self.engine_manager.is_waiting():
                time.sleep(0.05)
                logging.warning('engine is still not waiting')


class RemoteModeHandler(ModeHandler):
    """Handler for REMOTE mode."""

    def handle_user_move(self, game_state: GameState, move: chess.Move, sliding: bool) -> Optional[Message]:
        """Handle user move in remote mode."""
        if move not in game_state.game.legal_moves:
            logging.warning('illegal move [%s]', move)
            return None

        self.stop_search_and_clock()
        if not sliding:
            self.clock_manager.add_time(game_state.turn())

        game_state.done_computer_fen = None
        game_state.done_move = chess.Move.null()
        fen = game_state.fen()
        turn = game_state.turn()
        game_state.push(move)
        self.move_processor.reset()

        msg = Message.USER_MOVE_DONE(move=move, fen=fen, turn=turn, game=game_state.copy())
        game_end = self.check_game_state(game_state, game_state.play_mode)
        if game_end:
            return game_end
        return msg

    def handle_computer_move_done(self, game_state: GameState) -> Optional[Message]:
        """Handle when remote move is done."""
        game_state.game.push(game_state.done_move)
        game_state.done_computer_fen = None
        game_state.done_move = chess.Move.null()
        game_end = self.check_game_state(game_state, game_state.play_mode)
        if game_end:
            return game_end
        self.move_processor.reset()
        self.clock_manager.add_time(not game_state.turn())
        return None

    def start_search(self, game_state: GameState, time_control: TimeControl, msg: Message):
        """Start observe search in remote mode."""
        from utilities import DisplayMsg
        from dgt.api import Message as DgtMessage
        DisplayMsg.show(msg)
        self.clock_manager.start(game_state.turn())
        tc_init = time_control.get_parameters()
        DisplayMsg.show(DgtMessage.CLOCK_START(turn=game_state.turn(), tc_init=tc_init, devs={'ser', 'i2c', 'web'}))
        time.sleep(0.4)
        self.engine_manager.position(copy.deepcopy(game_state.game))
        self.engine_manager.ponder()

    def stop_search_and_clock(self, ponder_hit: bool = False):
        """Stop search and clock in remote mode."""
        self.clock_manager.stop()
        from utilities import DisplayMsg
        DisplayMsg.show(Message.CLOCK_STOP(devs={'ser', 'i2c', 'web'}))
        time.sleep(0.4)
        self.engine_manager.stop()
        while not self.engine_manager.is_waiting():
            time.sleep(0.05)
            logging.warning('engine is still not waiting')


class ObserveModeHandler(RemoteModeHandler):
    """Handler for OBSERVE mode."""

    def handle_user_move(self, game_state: GameState, move: chess.Move, sliding: bool) -> Optional[Message]:
        """Handle move in observe mode."""
        if move not in game_state.game.legal_moves:
            logging.warning('illegal move [%s]', move)
            return None

        self.stop_search_and_clock()
        fen = game_state.fen()
        turn = game_state.turn()
        game_state.push(move)
        self.move_processor.reset()

        msg = Message.REVIEW_MOVE_DONE(move=move, fen=fen, turn=turn, game=game_state.copy())
        game_end = self.check_game_state(game_state, game_state.play_mode)
        if game_end:
            return game_end
        return msg


class AnalysisModeHandler(ModeHandler):
    """Handler for ANALYSIS, KIBITZ, and PONDER modes."""

    def handle_user_move(self, game_state: GameState, move: chess.Move, sliding: bool) -> Optional[Message]:
        """Handle move in analysis mode."""
        if move not in game_state.game.legal_moves:
            logging.warning('illegal move [%s]', move)
            return None

        self.stop_search_and_clock()
        fen = game_state.fen()
        turn = game_state.turn()
        game_state.push(move)
        self.move_processor.reset()

        msg = Message.REVIEW_MOVE_DONE(move=move, fen=fen, turn=turn, game=game_state.copy())
        game_end = self.check_game_state(game_state, game_state.play_mode)
        if game_end:
            return game_end
        return msg

    def handle_computer_move_done(self, game_state: GameState) -> Optional[Message]:
        """Not applicable in analysis mode."""
        return None

    def start_search(self, game_state: GameState, time_control: TimeControl, msg: Message):
        """Start analysis search."""
        from utilities import DisplayMsg
        DisplayMsg.show(msg)
        self.engine_manager.position(copy.deepcopy(game_state.game))
        self.engine_manager.ponder()

    def stop_search_and_clock(self, ponder_hit: bool = False):
        """Stop search in analysis mode."""
        self.engine_manager.stop()
        while not self.engine_manager.is_waiting():
            time.sleep(0.05)
            logging.warning('engine is still not waiting')


class ModeHandlerFactory:
    """Factory for creating mode handlers."""

    @staticmethod
    def create(mode: Mode, engine_manager: EngineManager, clock_manager: ClockManager,
               move_processor: MoveProcessor, book_manager: BookManager) -> ModeHandler:
        """Create appropriate mode handler."""
        if mode == Mode.NORMAL:
            return NormalModeHandler(engine_manager, clock_manager, move_processor, book_manager)
        elif mode == Mode.BRAIN:
            return BrainModeHandler(engine_manager, clock_manager, move_processor, book_manager)
        elif mode == Mode.REMOTE:
            return RemoteModeHandler(engine_manager, clock_manager, move_processor, book_manager)
        elif mode == Mode.OBSERVE:
            return ObserveModeHandler(engine_manager, clock_manager, move_processor, book_manager)
        elif mode in (Mode.ANALYSIS, Mode.KIBITZ, Mode.PONDER):
            return AnalysisModeHandler(engine_manager, clock_manager, move_processor, book_manager)
        else:
            raise ValueError(f'Unknown mode: {mode}')
