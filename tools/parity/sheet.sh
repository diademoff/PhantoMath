#!/bin/sh
# Contact sheet of every captured stage of one card: sheet.sh TASK CARD  -> sheet_TASK_cCARD.png
cd "$(dirname "$0")/cap" || exit 1
rm -f t_*.png
for f in "$1"_c"$2"_[0-9]*.png; do
  case "$f" in *_steps.png) continue;; esac
  magick "$f" -crop 1080x1150+0+230 +repage -resize 42% "t_$f"
done
montage -label '%t' -pointsize 12 -tile 4x -geometry +2+2 t_*.png "../sheet_$1_c$2.png"
rm -f t_*.png
