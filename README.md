# KaraLuxer

A python script to port songs from [Karaoke Mugen](https://karaokes.moe/en/) to [Vocaluxe](https://www.vocaluxe.org/).

As Karaoke Mugen does not feature pitch mapping, only timings will be generated by the script. Pitches can be automatically generated from the mapped file using [Ultrastar Pitch](https://github.com/paradigmn/ultrastar_pitch) (Accuracy will vary per map).

## How to run

The easiest way to use the script is with the packaged executable, these can be found on the
[releases](https://github.com/WarwickAnimeSoc/KaraLuxer/releases) page.

To run the script you need [python](https://www.python.org/) (Version 3.6 or newer) and
[ffmpeg](https://www.ffmpeg.org/) must be installed and on your path.

The requirements for the script can be installed using: `python -m pip install -r requirements.txt`.

Once the script is done it will place the converted song inside the `out` folder.

## TODO

- Improve note length adjustment.
- UI improvements (Program Output section of the UI doesn't work properly).
