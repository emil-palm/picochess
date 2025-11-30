# DGT Clock Button Input

## Overview
Handles button presses from DGT clocks for menu navigation and game control.

## Button Layout
- Button 0: Up/Previous
- Button 1: Down/Next
- Button 2: OK/Select
- Button 3: Right/Forward
- Button 4: Back/Help

## Communication Methods
- Serial (DGT XL/3000): Via serial protocol
- I2C (DGT Pi): Via i2c bus
- Lever: Special codes (-0x40 / 0x40)

## Special Combinations
- Button 0+4: Power off
- Lever movement: Side clock activation

## Implementation Details
Files: `dgt/hw.py`, `dgt/pi.py` in PicoChess source
