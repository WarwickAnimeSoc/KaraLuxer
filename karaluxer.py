import sys
from argparse import ArgumentParser, Namespace
from pathlib import Path
from math import floor
import re
import shutil
import subprocess

import ass
from ass.line import Dialogue

import kara_api.kara_api as kapi

# Globals
OUTPUT_FOLDER = Path('./out')
TMP_FOLDER = Path('./tmp')
NOTE_LINE = ': {start} {duration} {pitch} {sound}\n'
SEP_LINE = '- {0} \n'
BEATS_PER_SECOND = 20
TIMING_REGEX = re.compile(r'(\{\\(?:k|kf|ko|K)[0-9]+\}[a-zA-Z _.\-,!"\']+\s*)|({\\(?:k|kf|ko|K)[0-9]+[^}]*\})')
KARA_URL_REGEX = re.compile(r'https:\/\/kara\.moe\/kara\/[\w-]+\/[\w-]+')

# FFMPEG path can either be bundled (./tools) or system.
try:
    FFMPEG_PATH = Path(getattr(sys, '_MEIPASS'), 'ffmpeg.exe')
except AttributeError:
    FFMPEG_PATH = 'ffmpeg'


def log(message: str):
    """Procedure to log a message.

    Args:
        message (str): The message to log.
    """

    print(message)


def parse_subtitles(sub_file: Path) -> str:
    """Function to parse an ass file and convert the karaoke timings to the ultrastar format.

    Args:
        sub_file (Path): The path to the ass file.

    Returns:
        str: The notes, mapped to the ultrastar format.
    """

    with open(sub_file, 'r', encoding='utf-8-sig') as f:
        sub_data = ass.parse(f)

    # Output.
    notes_string = ''

    # Filter out comments.
    dialogue_lines = [event for event in sub_data.events if isinstance(event, Dialogue)]

    # Parse lines
    for line in dialogue_lines:
        # Set start of line markers.
        current_beat = floor(line.start.total_seconds() * BEATS_PER_SECOND)

        # Get all syllables and timings for the line.
        syllables = []
        for sound_line, timing_line in re.findall(TIMING_REGEX, line.text):
            if sound_line:
                timing, sound = sound_line.split('}')
            elif timing_line:
                timing = timing_line.split('\\')[1]
                sound = None
            else:
                log('\033[1;33mWarning:\033[0m Something unexpected was found in line - {0}'.format(line.text))
                continue

            timing = re.sub(r'[^0-9]', '', timing)
            syllables.append((int(timing), sound))

        # Write out ultrastar timings.
        for duration_cs, sound in syllables:
            # Karaoke timings in ass files are given in centiseconds.
            duration = floor((duration_cs / 100) * BEATS_PER_SECOND)

            if sound:
                # Duration is reduced by 1 to give gaps.
                notes_string += NOTE_LINE.format(start=current_beat, duration=duration - 1, sound=sound, pitch=19)

            current_beat += duration

        # Write line separator for ultrastar.
        notes_string += SEP_LINE.format(current_beat)

    return notes_string


def main(args: Namespace) -> None:
    """The main driver for the script.

    Args:
        args (Namespace): The command line arguments.
    """

    # Get ID from URL
    kara_id = args.url.split('/')[-1]

    # Make temp directory
    tmp_data = TMP_FOLDER.joinpath(kara_id)
    if tmp_data.exists():
        shutil.rmtree(tmp_data)
    tmp_data.mkdir(parents=True, exist_ok=False)

    # Get data from Kara
    kara_data = kapi.get_kara_data(kara_id)

    log('\033[0;34mInfo:\033[0m Downloading subtitles!')
    kapi.get_sub_file(kara_data['sub_file'], tmp_data)
    log('\033[0;34mInfo:\033[0m Downloading media!')
    kapi.get_media_file(kara_data['media_file'], tmp_data)

    bg_video_path = None

    # Load downloaded file.
    ass_path = Path(tmp_data.joinpath(kara_data['sub_file']))
    media_path = Path(tmp_data.joinpath(kara_data['media_file']))
    if media_path.suffix != '.mp3':
        log('\033[0;34mInfo:\033[0m Converting media to mp3 using ffmpeg!')
        audio_path = tmp_data.joinpath('{0}.mp3'.format(media_path.stem))
        # Convert to mp3 using ffmpeg
        ret_val = subprocess.call([str(FFMPEG_PATH), '-i', str(media_path), '-b:a', '320k', str(audio_path)])

        if ret_val:
            log('\033[0;31mError:\033[0m ffmpeg was not able to properly convert the media to mp3!')
            return
        if not args.background_video:
            bg_video_path = media_path
    else:
        audio_path = media_path

    # Load remaining files
    cover_path = Path(args.cover) if args.cover else None
    background_path = Path(args.background) if args.background else None

    # If a BG video file is provided via the command line, it will overwrite the downloaded one.
    bg_video_path = Path(args.background_video) if args.background_video else bg_video_path

    # Parse subtitle file.
    notes_section = parse_subtitles(ass_path)

    # Create output folder
    title_string = kara_data['title'] + (' (TV)' if args.tv else '')
    base_name = '{0} - {1}'.format(kara_data['artists'], title_string)
    song_folder = OUTPUT_FOLDER.joinpath(base_name)
    if song_folder.exists():
        log('\033[1;33mWarning:\033[0m Overwriting existing output.')
        shutil.rmtree(song_folder)
    song_folder.mkdir(parents=True)

    # Calculate BPM for ultrastar.
    # This script uses a fixed 'beats per second' to produce timings, the BPM for ultrastar is based off the fixed bps.
    # The BPM put into the ultrastar file needs to be around 1/4 of the calculated BPM (I'm not sure why).
    beats_per_minute = (BEATS_PER_SECOND * 60) / 4

    # Produce metadata section of the ultrastar file.
    metadata = '#TITLE:{0}\n#ARTIST:{1}\n'.format(title_string, kara_data['artists'])

    metadata += '#LANGUAGE:{0}\n'.format(kara_data['language'])

    creator_string = kara_data['authors'] + ('' if not args.creator else (' & ' + args.creator))
    metadata += '#CREATOR:{0}\n'.format(creator_string)

    # Produce files section of the ultrastar file.
    # Paths are made relative and files will be renamed to match the base name.
    mp3_name = '{0}.mp3'.format(base_name)
    linked_files = '#MP3:{0}\n'.format(mp3_name)
    shutil.copy(audio_path, song_folder.joinpath(mp3_name))

    if cover_path:
        cover_name = '{0} [CO]{1}'.format(base_name, cover_path.suffix)
        linked_files += '#COVER:{0}\n'.format(cover_name)
        shutil.copy(cover_path, song_folder.joinpath(cover_name))

    if background_path:
        background_name = '{0} [BG]{1}'.format(base_name, background_path.suffix)
        linked_files += '#BACKGROUND:{0}\n'.format(background_name)
        shutil.copy(background_path, song_folder.joinpath(background_name))

    if bg_video_path:
        bg_video_name = '{0}{1}'.format(base_name, bg_video_path.suffix)
        linked_files += '#VIDEO:{0}\n'.format(bg_video_name)
        shutil.copy(bg_video_path, song_folder.joinpath(bg_video_name))

    # Produce song data section of the ultrastar file.
    song_data = '#BPM:{0}\n#GAP:0\n'.format(beats_per_minute)

    # Combine ultrastar file components
    ultrastar_file = metadata + linked_files + song_data + notes_section + 'E\n'

    # Write file
    ultrastar_file_path = song_folder.joinpath('{0}.txt'.format(base_name))
    with open(ultrastar_file_path, 'w', encoding='utf-8') as f:
        f.write(ultrastar_file)

    # Delete downloads
    shutil.rmtree(tmp_data)

    log('\033[0;32mSuccess:\033[0m The ultrastar project has been placed in the output folder!')
    log('\033[1;33mThe song should be checked manually for any mistakes\033[0m')


def init_argument_parser() -> ArgumentParser:
    '''Function to setup the command line argument parser.

    Adds the following arguments:
        * `url`           The karas.moe URL for the song.
        * `-co`           Path to the cover image for the song.
        * `-bg`           Path to the background image for the song.
        * `-bv`           Path to the background video for the song.
        * `-l`            Specifies the language the song is in.
        * `-c`            Specifies the creator of the map (appends to the creator of the karas map).
        * `tv`            If set then (TV) is appended to the song title.

    Returns:
        ArgumentParser: The command line parser for this program.
    '''

    parser = ArgumentParser()

    parser.add_argument(
        'url',
        help='The karas.moe URL for the song.',
        type=str
    )
    parser.add_argument(
        '-co',
        '--cover',
        help='The path to the cover image for the song.',
        type=str
    )
    parser.add_argument(
        '-bg',
        '--background',
        help='The path to the background image for the song.',
        type=str
    )
    parser.add_argument(
        '-bv',
        '--background_video',
        help='The path to the background video for the song.',
        type=str
    )
    parser.add_argument(
        '-c',
        '--creator',
        help='The creator of this map (appends to the creator of the karas map).',
        type=str
    )
    parser.add_argument(
        '-tv',
        help='Pass this flag if the song is TV sized, it will edit the song title to include (TV).',
        action='store_true'
    )

    parser.set_defaults(tv=False)

    return parser


def check_arg_paths(args: Namespace) -> bool:
    """Function to check if all the specified paths are valid.

    Does not check that files are actually valid, only checks the file extension.

    Args:
        args (Namespace): The command line arguments.

    Returns:
        bool: True if all the paths are valid, else False.
    """

    if args.cover and not Path(args.cover).exists():
        log('\033[0;31mError:\033[0m The specified cover image file can not be found!')
        return False
    elif args.cover:
        if Path(args.cover).suffix in ['jpg', 'jpeg', 'png']:
            log('\033[0;31mError:\033[0m The specified cover image is not an image!')
            return False

    if args.background and not Path(args.background).exists():
        log('\033[0;31mError:\033[0m The specified background image file can not be found!')
        return False
    elif args.cover:
        if Path(args.background).suffix in ['jpg', 'jpeg', 'png']:
            log('\033[0;31mError:\033[0m The specified background image is not an image!')
            return False

    if args.background_video and not Path(args.background_video).exists():
        log('\033[0;31mError:\033[0m The specified background videofile can not be found!')
        return False
    elif args.background_video:
        if Path(args.background_video).suffix != '.mp4':
            log(Path(args.background).suffix)
            log('\033[0;31mError:\033[0m The specified background video is not a mp4!')
            return False

    return True


def check_arg_url(args: Namespace) -> bool:
    if re.match(KARA_URL_REGEX, args.url):
        return True
    else:
        log('\033[0;31mError:\033[0m Provided URL is not in the correct format!')
        return False


def gui_entry_point(url: str, cover: str, background: str, video:str, creator: str, tv: bool) -> None:
    """Function that serves as an entry-point for the GUI to use this file.

    Args:
        Correspond to the respective command line arguments.
    """

    args = Namespace(url=url, cover=cover, background=background, background_video=video, creator=creator, tv=tv)
    if check_arg_paths(args) and check_arg_url(args):
        main(args)


if __name__ == '__main__':
    parser = init_argument_parser()
    args = parser.parse_args()
    if check_arg_paths(args) and check_arg_url(args):
        main(args)
