# DGT Pi Clock Output

## Overview
11-character i2c display with icons.

## Display Specifications
- **Characters**: 11 (large display)
- **Protocol**: I2C (dgtpicom library)
- **Icons**: Left/Right icons available
- **Beep**: Supported

## Display Modes
- **Text**: 11 characters
- **Move**: Move number + SAN (001 e4)
- **Time**: H:MM:SS format

## Example Output
```
"001 e4     "  # Move with number
"please wait"  # Text message
"  0:05:00  "  # Time display
```

## Implementation Details
File: `dgt/pi.py` - `_display_on_dgt_pi()` method
Requires: `dgtpicom.so` library
