#!/bin/sh
# Contact sheets of the typed expressions: one crop per task, 12 per sheet.
cd "$(dirname "$0")/cap" || exit 1
for f in *_input.png; do magick "$f" -crop 1080x230+0+270 +repage "crop_${f%_input.png}.png"; done
ls crop_*.png | xargs -n 12 | nl -w1 | while read n files; do
  montage -label '%t' -pointsize 14 -tile 2x -geometry 540x115+4+4 $files "../sheet_$n.png"
done
