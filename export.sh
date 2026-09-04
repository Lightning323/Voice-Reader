#!/bin/bash

source .venv/bin/activate

ffmpeg_path="$(command -v ffmpeg)"
if [ -z "$ffmpeg_path" ]; then
  echo "FFmpeg is required to build mobile HLS playback. Install it and try again."
  exit 1
fi

pyinstaller --onefile --windowed --add-binary "$ffmpeg_path:." main.py
