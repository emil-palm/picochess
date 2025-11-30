# DGT Revelation II Output

## Overview
11-character serial display with LED board lighting.

## Display Specifications
- **Characters**: 11 (large display)
- **Protocol**: Serial (DGT protocol)
- **LEDs**: 64 square LEDs
- **Beep**: Supported

## Unique Features
- Light squares to show moves
- Full LED control per square
- Same protocol as DGT XL (extended)

## Display Modes
- **Text**: 11 characters
- **Move**: SAN format with number
- **LEDs**: Light from/to squares
- **Time**: H:MM:SS format

## LED Control
```python
# Light squares for move
light_squares('e2e4')  # Lights e2 and e4

# Clear all LEDs
clear_leds()
```

## Implementation Details
File: `dgt/hw.py` - `_display_on_rev2_pi()` method
Special LED commands in `dgt/board.py`
