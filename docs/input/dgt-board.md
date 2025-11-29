# DGT Electronic Board Input

## Overview
Reads chess piece positions from DGT electronic board via serial/Bluetooth.

## Key Components
- Serial/Bluetooth communication
- FEN string generation
- Position change detection
- Automatic board detection

## Hardware Supported
- DGT e-Board (USB)
- DGT e-Board (Bluetooth)
- Board auto-detection

## Protocol
- Sends: Position updates as FEN
- Receives: LED commands (Revelation II)

## Implementation Details
File: `dgt/board.py` in PicoChess source
