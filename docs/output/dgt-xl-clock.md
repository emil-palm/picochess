# DGT XL Clock Output

## Overview
6-character serial display with icons.

## Display Specifications
- **Characters**: 6 (small display)
- **Protocol**: Serial (DGT protocol)
- **Icons**: Left/Right icons available
- **Beep**: Supported

## Display Modes
- **Text**: 6 characters
- **Move**: UCI format (e2e4) with spacing
- **Time**: MM:SS format

## Example Output
```
"e2  e4"  # Move display
"bk mv "  # Black move
" 5:00 "  # Time display
```

## Implementation Details
File: `dgt/hw.py` - `_display_on_dgt_xl()` method
