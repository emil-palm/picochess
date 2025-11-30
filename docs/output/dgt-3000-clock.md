# DGT 3000 Clock Output

## Overview
8-character serial display.

## Display Specifications
- **Characters**: 8 (medium display)
- **Protocol**: Serial (DGT protocol)
- **Icons**: None
- **Beep**: Supported

## Display Modes
- **Text**: 8 characters
- **Move**: SAN format (1.e4)
- **Time**: MM:SS or H:MM:SS

## Example Output
```
"1.e4    "  # Move with number
"pls wait"  # Text message
"  5:00  "  # Time display
```

## Implementation Details
File: `dgt/hw.py` - `_display_on_dgt_3000()` method
