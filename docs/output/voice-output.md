# Voice Output

## Overview
Audio announcements of moves and game events using pre-recorded .ogg files.

## Audio Components
- **Move files**: a1.ogg through h8.ogg
- **Piece files**: knight.ogg, bishop.ogg, etc.
- **Action files**: takes.ogg, check.ogg, checkmate.ogg
- **Event files**: newgame.ogg, draw.ogg, etc.

## Voice Configuration
- **Languages**: 6 supported (en/de/nl/fr/es/it)
- **Speakers**: Multiple per language
- **Speed**: Adjustable (90%-135%)
- **User/Computer**: Separate voices

## Playback
- **Tool**: ogg123 (vorbis-tools) or play (sox)
- **Speed**: tempo control via sox
- **Threading**: Non-blocking playback

## Implementation Details
Files: `talker/picotalker.py`, `talker/voices/` directory

See voice examples in PICOCHESS_FEATURES_ANALYSIS.md Feature 7.
