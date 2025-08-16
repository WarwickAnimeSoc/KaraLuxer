# Core Karaluxer functionality - CLI interface
import os
import shutil
import tempfile
from typing import Callable, Dict, Optional, List, Tuple

from pathlib import Path
import sys
import subprocess
import re
import warnings
import json
import argparse
import urllib.parse

import requests
import ass
import ass.line
import ultrastar_pitch

from ultrastar.ultrastar import UltrastarSong

# FFMPEG is used for converting Kara.moe media files to mp3. The script will first check if FFMPEG has been bundled with
# it (through pyinstaller), secondly it will look for it in the "tools" folder and finally assume it is on PATH.
if getattr(sys, '_MEIPASS', False):
    FFMPEG_PATH = Path(getattr(sys, '_MEIPASS'), 'ffmpeg.exe')
elif Path('tools', 'ffmpeg.exe').exists():
    FFMPEG_PATH = Path('tools', 'ffmpeg.exe')
else:
    FFMPEG_PATH = 'ffmpeg'

# Rather than estimate the BPM of each song, KaraLuxer uses a fixed BPM (specified here in Beats Per Second). Subtitle
# files for karaoke specify timings in centiseconds, therefore to avoid rounding KaraLuxer uses 100 beats per second.
# Using a fixed BPM, and a high one (6000 BPM) makes manual editing of the files produced by KaraLuxer harder.
KARALUXER_BPS = 100
KARALUXER_BPM = 1500

# Regular expression to capture the timing/syllables from a line by stripping out the karaoke tags.
# Note: Supports multiple tags on a syllable (such as color) but first tries to assume the karaoke tag is the first one.
SYLLABLE_REGEX = re.compile(
    r'(\{\\(?:k|kf|ko|K)[0-9.]+(?:\\[0-9A-z&]+)*\}[A-zÀ-ÿ _.\-,!"\']+\s*)'
    r'|({\\(?:k|kf|ko|K)[0-9.]+[^}]*\})'
    r'|(\{(?:\\[0-9A-z&(), ]+?)*\\(?:k|kf|ko|K)[0-9.]+(?:\\[0-9A-z&]+)*}[A-zÀ-ÿ _.\-,!\"\']+\s*)'
)

# THe default pitch to assign to notes.
DEFAULT_PITCH = 19

# The threshold for normalisation using FFMPEG.
FFMPEG_NORMALISATION_THRESHOLD = 50

# Version number used to tag and identify Karaluxer produced maps.
KARALUXER_VERSION = '3.0.0'


class KaraLuxer():
    """A KaraLuxer instance. Processes one song."""

    def __init__(
        self,
        kara_url: Optional[str] = None,
        ass_file: Optional[str] = None,
        cover_file: Optional[str] = None,
        background_i_file: Optional[str] = None,
        background_v_file: Optional[str] = None,
        audio_file: Optional[str] = None,
        off_vocal: Optional[str] = None,
        vocals: Optional[str] = None,
        overlap_filter_method: Optional[str] = None,
        force_dialogue_lines: bool = False,
        tv_sized: bool = False,
        autopitch: bool = False,
        karaoke_bpm: float = 1500,
        song_bpm: float = 1500,
        enable_normalisation: bool = True
    ) -> None:
        """Sets up the KaraLuxer instance.

        Files passed manually to the KaraLuxer instance as arguments will override the files from the kara.moe website.
        Provided files (excluding the subtitle file) are not checked for the correct/valid extension.

        Args:
            kara_url (Optional[str], optional): The kara.moe URL for the song. One of kara_url or ass_file must be
                specified. Defaults to None.
            ass_file (Optional[str], optional): The path to the subtitle file for the song. One of kara_url or ass_file
                must be specified. Defaults to None.
            cover_file (Optional[str], optional): The path to the cover image to use. Defaults to None.
            background_i_file (Optional[str], optional): The path to the background image to use. Defaults to None.
            background_v_file (Optional[str], optional): The path to the background video to use. Defaults to None.
            audio_file (Optional[str], optional): The path to the audio to use. Defaults to None.
            off_vocal (Optional[str], optional): Either a path to and audio file containing the off-vocal track or
                the http address to the kara.moe song containing the off-vocal track to use. Defaults to None.
            vocals (Optional[str], optional): Either a path to and audio file containing the vocal track or
                the http address to the kara.moe song containing the vocal track to use. Defaults to None.
            overlap_filter_method (Optional[str], optional): Sets the behaviour for how overlapping lines should be
                handled. None will ignore overlaps, "style" will make the user select one subtitle style to keep,
                "individual" will allow the user to select lines to discard individually, and "duet" will map the song
                as a duet using the styles in the subtitle file.
            force_dialogue_lines (bool, optional): If True only Dialogue lines will be parsed from the subtitle file.
                Not recommended unless specifying a manual subtitle file.
            tv_sized (bool, optional): If True will append (TV) to the song title. (This is the convention that
                ultrastar.es uses).
            autopitch (bool, optional): If True Karaluxer will attempt to use ultrastar_pitch to pitch the notes.
            karaoke_bpm (float, optional): The BPM (beats per minute) for the karaoke txt file that will be used instead
                of the default 1500 BPM. For ultrastar maps, this tends to be approximately 300, even if the true BPM
                is often much lower.
            song_bpm (float, optional): The actual BPM of the song/audio. Having the karaoke BPM a 3 or 4 multiple
                of the Song BPM allows for easier creation of gaps in between notes. Providing this option will allow
                KaraLuxer to arrange the notes more closely to the correct timing.
            enable_normalisation (bool, optional): If True, the audio will be normalised dueing its extraction from the
                video file. Regardless of the flag, this happens only if the kara.moe source contains a video file and
                if its loudness is not already normalised to 0 dB.
        """

        # One of kara_url or ass_file must be passed to the Karaluxer instance.
        if not kara_url and not ass_file:
            raise ValueError('One of kara_url or ass_file must be passed to the KaraLuxer instance.')

        self.kara_url = kara_url
        self.files = {
            'subtitles': Path(ass_file) if ass_file else None,
            'audio': Path(audio_file) if audio_file else None,
            'background_image': Path(background_i_file) if background_i_file else None,
            'background_video': Path(background_v_file) if background_v_file else None,
            'cover': Path(cover_file) if cover_file else None,
            'off_vocal': off_vocal if off_vocal else None,
            'vocals': vocals if vocals else None,
        }
        self.overlap_filter_method = overlap_filter_method
        self.force_dialogue_lines = force_dialogue_lines
        self.tv_sized = tv_sized
        self.autopitch = autopitch

        self.bpm = karaoke_bpm

        self.bpm_multiplier = karaoke_bpm / song_bpm
        if self.bpm_multiplier % 1 < 1e-5:
            self.bpm_multiplier = int(self.bpm_multiplier)
        else:
            raise ValueError('The Karaoke BPM must be an integer multiple of the Song BPM (provided multiple='
                             f'{self.bpm_multiplier}). Either provide a valid combination of Karaoke and Song BPM or '
                             f'do not set the Song BPM.')
        self.enable_normalisation = enable_normalisation

        # Parameter checks
        kara_regex = r'https:\/\/kara\.moe\/kara\/[\w-]+\/[\w-]+'
        if kara_url and not re.match(kara_regex, kara_url):
            raise ValueError('Invalid kara.moe URL.')

        if self.files['subtitles']:
            if self.files['subtitles'].suffix != '.ass':
                raise ValueError('Subtitle file must be a .ass file.')
            if not self.files['subtitles'].exists():
                raise IOError('Subtitle file not found.')

        if self.files['audio'] and not self.files['audio'].exists():
            raise IOError('Audio file not found.')

        if self.files['background_image'] and not self.files['background_image'].exists():
            raise IOError('Background image not found.')

        if self.files['background_video'] and not self.files['background_video'].exists():
            raise IOError('Background video not found.')

        if self.files['cover'] and not self.files['cover'].exists():
            raise IOError('Cover image not found.')

        if self.files['off_vocal']:
            if not re.match(kara_regex, self.files['off_vocal']):
                self.files['off_vocal'] = Path(self.files['off_vocal'])
                if not self.files['off_vocal'].exists():
                    raise ValueError('Off-Vocal must be a valid path or a valid kara.moe URL.')

        if self.files['vocals']:
            if not re.match(kara_regex, self.files['vocals']):
                self.files['vocals'] = Path(self.files['vocals'])
                if not self.files['vocals'].exists():
                    raise ValueError('Vocals must be a valid path or a valid kara.moe URL.')

        if overlap_filter_method not in [None, 'style', 'individual', 'duet']:
            raise ValueError(
                'If specifying an overlap filter method it must be one of "individual", "style" or "duet".'
            )

        self.ultrastar_song = UltrastarSong(KARALUXER_BPS * 60)

    def _load_subtitle_lines(self) -> List[ass.line._Event]:
        """Load, sort and filter the lines from the subtitle file. THis method must be run after a subtitle file has
           been provided, either manually or by downloading from Kara.

        Returns:
            List[ass.line._Event]: A list of all the lines in the subtitle file, sorted by their stating time.
        """

        if not self.files['subtitles']:
            raise ValueError('Subtitle file has not been provided.')

        with open(self.files['subtitles'], encoding='utf-8-sig') as f:
            subtitle_data = ass.parse(f)

        # Using Comment lines instead of dialogue from Kara produces better results. However some songs, such as
        # https://kara.moe/kara/rock-over-japan/68a57800-9b23-4c62-bcc8-a77fb103b798 only have Dialogue lines, so they
        # are used if no Comments are found. Manually provided subtitle files might work better when using Dialogue, so
        # the force_dialogue_lines option can be used to force the use of Dialogue lines.
        comments = [event for event in subtitle_data.events if isinstance(event, ass.line.Comment)]
        dialogue = [event for event in subtitle_data.events if isinstance(event, ass.line.Dialogue)]

        if not comments or self.force_dialogue_lines:
            relevant_lines = dialogue
        else:
            relevant_lines = comments

        # Lines in the subtitle file are parsed in order of appearance, but this may differ from the order they occur
        # in.
        relevant_lines.sort(key=lambda l: l.start)

        return relevant_lines

    def _get_styles_in_lines(self, lines: List[ass.line._Event]) -> List[Tuple[str, int]]:
        """Finds all unique styles in a set of lines, as well as how many lines correspond to that style.

        Args:
            lines (List[ass.line._Event]): The list of lines to search for styles.

        Returns:
            List[Tuple[str, int]]: The list of styles found, along with how many lines in that style exist.
        """

        styles = {}
        for line in lines:
            line_count = styles.setdefault(line.style, 0)
            styles[line.style] = line_count + 1

        return list(styles.items())

    def _get_lines_in_style(self, style: str, lines: List[ass.line._Event]) -> List[ass.line._Event]:
        """Filters a list of lines to keep only those in a certain style.

        Args:
            style (str): The style to filter by.
            lines (List[ass.line._Event]): The list of lines to filter.

        Returns:
            List[ass.line._Event]: Lines with the correct style.
        """

        return list(filter(lambda l: l.style == style, lines))

    def _filter_overlapping_lines_style(
        self,
        lines: List[ass.line._Event],
        style_selection_function: Callable[[List[Tuple[str, int]]], str]
    ) -> List[ass.line._Event]:
        """Filters lines by removing any lines that are not in a selected style. Uses a user provided function to
        discard styles until there is only one remaining.

        Does not guarantee that there are no overlaps remaining within the selected style.

        Args:
            lines (List[ass.line._Event]): The list of lines to filter.
            style_selection_function (Callable[[List[Tuple[str, int]]], str]): The function that will be used to discard
                styles. It should return the name of the style to discard.

        Returns:
            List[ass.line._Event]: The filtered list of lines that match the selected style.
        """

        styles = self._get_styles_in_lines(lines)

        # If there is only one style then no filtering needs to be done. There may still be overlaps within an
        # individual style but these will be ignored.
        if len(styles) == 1:
            warnings.warn(
                'Style mode has been used for overlap filtering, but there is only one style. Overlaps will be ignored.'
            )
            return lines

        # Prompt user to discard styles until there is only one.
        while (len(styles) > 1):
            selected_style = style_selection_function(styles)
            styles = [style for style in styles if style[0] != selected_style]

        return self._get_lines_in_style(styles[0][0], lines)

    def _filter_overlapping_lines_individual(
        self,
        lines: List[ass.line._Event],
        decision_function: Callable[[List[ass.line._Event]], ass.line._Event]
    ) -> List[ass.line._Event]:
        """Filters lines that overlap. Uses a user provided decision function to decide between lines.

        Args:
            lines (List[ass.line._Event]): The list of lines to filter.
            decision_function (Callable[[List[ass.line._Event]], int]): The function that will be used to select between
                overlapping lines. It should return the line to remove.

        Returns:
            List[ass.line._Event]: The filtered list of lines, with no overlaps remaining.
        """

        overlap_exists = True
        while overlap_exists:
            overlap_exists = False

            for i in range(0, len(lines)):
                current_line = lines[i]
                overlap_group = [current_line]

                for j in range(i + 1, len(lines)):
                    selected_line = lines[j]
                    if current_line.end > selected_line.start:
                        overlap_group.append(selected_line)
                    else:
                        break

                if len(overlap_group) > 1:
                    overlap_exists = True

                    # Use the provided decision function to decide which line to remove.
                    discarded_line = decision_function(overlap_group)
                    lines.remove(discarded_line)
                    break

        return lines

    def _separate_duet_parts(
        self,
        lines: List[ass.line._Event],
        style_selection_function: Callable[[List[Tuple[str, int]]], str]
    ) -> Tuple[List[ass.line._Event], ...]:
        """Separates lines into two duet parts based on their style. Uses a user provided function to
        discard styles until there is only two remaining.

        Args:
            lines (List[ass.line._Event]): The lines to separate.
            style_selection_function (Callable[[List[Tuple[str, int]]], str]): The function that will be used to discard
            styles. It should return the name of the style to discard.

        Returns:
            Tuple[List[ass.line._Event], ...]: The parts of the duet. Tuple will have a length of 1 if the subtitles did
                not contain more than one style, otherwise it will have a length of 2.
        """

        styles = self._get_styles_in_lines(lines)

        # If there is only one style then a duet can not be produced, instead the song will be mapped as normal.
        if len(styles) == 1:
            warnings.warn(
                'Duet mode has been used but there is only one style. Song will be mapped as normal;.'
            )
            return (lines,)

        # Prompt user to discard styles until there is only two.
        while (len(styles) > 2):
            selected_style = style_selection_function(styles)
            styles = [style for style in styles if style[0] != selected_style]

        # Add metadata tags to the ultrastar file that name the duet sections according to their style.
        self.ultrastar_song.add_metadata('P1', styles[0][0])
        self.ultrastar_song.add_metadata('P2', styles[1][0])

        p1_lines = self._get_lines_in_style(styles[0][0], lines)
        p2_lines = self._get_lines_in_style(styles[1][0], lines)

        return (p1_lines, p2_lines)

    def _convert_lines(self, lines: List[ass.line._Event], duet_part: str = 'P1') -> None:
        """Convert the subtitle lines to notes for the ultrastar song.

        Args:
            lines (List[ass.line._Event]): The subtitle lines to parse.
            duet_part (str, optional): The duet part that lines should be assigned to. Defaults to P1. A song will only
                be mapped as a duet if at least 1 line with duet_part/player "P2" exists.
        """

        for line in lines:
            current_beat = round(line.start.total_seconds() * KARALUXER_BPS)

            # Get all syllables and their durations from the line.
            syllables = []
            for sound_pair, timing_pair, pair_with_tag_prefix in re.findall(SYLLABLE_REGEX, line.text):
                if sound_pair:
                    timing, syllable_text = sound_pair.split('}')
                    # Timing string might contain additional tags besides just the karaoke timings
                    # (e.g. {\k23\2c&H3AE2FA&}). They are filtered out here to keep only the first tag (this will cause
                    # issues if the first tag is not the karaoke timings).
                    timing = re.sub(r'(?<!{)\\[\0-9A-z&]*', '', timing)
                elif timing_pair:
                    timing = timing_pair.split('\\')[1]
                    syllable_text = None
                elif pair_with_tag_prefix:
                    # The case where there is a tag before the karaoke tag
                    timing, syllable_text = pair_with_tag_prefix.split('}')
                    timing = re.findall(r'\\(?:k|kf|ko|K)([0-9.]+)', timing)[0]
                else:
                    clean_line = re.sub(r'\{(.*?)\}', '', line.text)
                    warnings.warn('Found something unexpected in line: "{0}"'.format(clean_line))
                    continue

                timing = re.sub(r'[^0-9.]', '', timing)
                syllables.append((round(float(timing)), syllable_text))

            for duration, syllable_text in syllables:
                # Subtitle files will provide the duration of a note in centiseconds, this needs to be converted into
                # beats for the Ultrastar format.
                converted_duration = round((duration / 100) * KARALUXER_BPS)

                # Karaoke subtitles can have timings without a corresponding sound, these simply increment the beat.
                if not syllable_text:
                    current_beat += converted_duration
                    continue

                # Notes should be slightly shorter than their original duration, to make it easier to sing.
                # Currently this is done by simply reducing the duration by one. This could use improvement.
                tweaked_duration = converted_duration - 1 if converted_duration > 1 else converted_duration

                self.ultrastar_song.add_note(
                    ':',
                    int(round(current_beat * self.bpm / KARALUXER_BPM)),
                    int(round(tweaked_duration * self.bpm / KARALUXER_BPM)),
                    DEFAULT_PITCH,
                    syllable_text,
                    duet_part
                )

                current_beat += converted_duration

            # Write a linebreak at the end of the line.
            self.ultrastar_song.add_note('-', int(round(current_beat * self.bpm / KARALUXER_BPM)))

    def _fetch_kara_data(self, kara_id: str) -> Dict[str, str]:
        """Fetches relevant data about a map using the Kara api.

        Args:
            kara_id (str): The ID of the kara.

        Returns:
            Dict[str, str]: Data about the kara that is relevant to the conversion process.
        """

        response = requests.get('https://kara.moe/api/karas/' + kara_id)
        if response.status_code != 200:
            raise ValueError('Unexpected response from kara.')

        data = json.loads(response.content)

        for info in data['lyrics_infos']:
            if info['default'] is True:
                sub_file = info['filename']
                break
        else:
            sub_file = data['lyrics_infos'][0]['filename']

        kara_data = {
            'title': data['titles'][data['titles_default_language']],
            'sub_file': sub_file,
            'media_file': data['mediafile'],
            'language': data['langs'][0]['i18n']['eng'],
            'year': data['year'],
        }

        if self.files['off_vocal'] is None:
            kara_data['off_vocal'] = self._fetch_kara_off_vocal(data)

        # Get song artists. Prioritizes "singergroups" (band) field when present.
        artist_data = data['singergroups'] if data['singergroups'] else data['singers']
        kara_data['artists'] = ', '.join([singer['name'] for singer in artist_data])

        # Get map authors
        kara_data['authors'] = ', '.join([author['name'] for author in data['authors']])

        anime = []
        for series in data['series']:
            name = series['name'].replace(',', '')  # Default name

            try:
                anime.append(series['i18n']['eng'].replace(',', ''))

                # Only add the default name if it is different from the English name
                if anime[-1] != name:
                    anime.append(name)
            except KeyError:
                anime.append(name)

            if series['aliases']:
                for alias in series['aliases']:
                    anime.append(alias.replace(',', ''))

        song_types = []
        for song_type in data['songtypes']:
            try:
                song_types.append(song_type['i18n']['eng'])
            except KeyError:
                pass

        tags = ', '.join(filter(None, [', '.join(anime), ', '.join(song_types)]))
        kara_data['tags'] = tags

        return kara_data

    def _fetch_kara_off_vocal(self, og_data: dict) -> Optional[str]:
        """Searches through the kara.moe song's relatives for an off-vocal version and returns file name.

        Returns:
            Optional[str]: The file name of the off-vocal version's media file.
        """
        og_duration = og_data['duration']
        relatives = og_data['siblings'] + og_data['children'] + og_data['parents']

        for relative in relatives:
            response = requests.get('https://kara.moe/api/karas/' + relative)
            if response.status_code != 200:
                continue

            data = json.loads(response.content)
            if data['duration'] != og_duration:
                continue

            for version in data['versions']:
                if version['i18n']['eng'].lower() == 'off vocal':
                    print('Off-vocal version found!')
                    return data['mediafile']

    def _fetch_kara_file(self, filename: str, download_directory: Path) -> None:
        """Fetches a file from the Kara servers and places it in the specified directory.

        Args:
            filename (str): The name of the file to fetch.
            download_directory (Path): The directory to save the file to.
        """

        if download_directory.joinpath(filename).exists():
            return

        file_path = Path(filename)

        if file_path.suffix == '.ass':
            response = requests.get('https://kara.moe/downloads/lyrics/' + urllib.parse.quote(filename))
        else:
            response = requests.get('https://kara.moe/downloads/medias/' + urllib.parse.quote(filename))

        if response.status_code != 200:
            raise ValueError('Unexpected response from kara.')

        with open(download_directory.joinpath(filename), 'wb') as f:
            f.write(response.content)

    def _extract_audio(self, media_path: Path, download_directory: Path, error: bool = True) -> Optional[Path]:
        """Extracts an audio file from a media file and normalises if requested.

        Args:
            media_path (Path): The path to the media file from which to extract audio.
            download_directory (Path): The work directory.
            error (bool, optional): Whether to raise an exception when an error occurs.

        Returns:
            Optional[Path]: The path of the extracted audio. Only returns ``None`` if ``error==False`` and an error
                            occurs.
        """
        if not self.files['background_video']:
            self.files['background_video'] = media_path

        audio_path = download_directory.joinpath(media_path.stem + '.mp3')

        if self.enable_normalisation:
            normalisation_loudness = self._find_normalisation_loudness(media_path)

            failure = False
            if normalisation_loudness != 0:
                ret_val = subprocess.run([FFMPEG_PATH, '-i', str(media_path), '-b:a', '320k', '-filter:a',
                                          f'volume={normalisation_loudness}dB', str(audio_path)])
                if ret_val.returncode:
                    print('WARNING: The audio loudness could not be normalised due to FFMPEG error in the '
                          'conversion process.')
                    failure = True

        if not self.enable_normalisation or normalisation_loudness == 0 or failure:
            print('Extracting audio without normalising volume...')
            ret_val = subprocess.run([FFMPEG_PATH, '-i', str(media_path), '-b:a', '320k', str(audio_path)])
            if ret_val.returncode:
                if error:
                    raise IOError('Could not convert media to mp3 with FFMPEG.')
                return None

        return audio_path

    @staticmethod
    def _find_normalisation_loudness(media_path: Path) -> int:
        """
        Finds the loudness (in dB) to increase the kara.moe video by in order to normalise the audio as close to 0dB
        as possible without significantly degrading the quality.

        Args:
            media_path: The path to the kara.moe video file.

        Returns:
            loudness: loudness in dB
        """
        # FFMPEG for some reason writes both stdout and stderr into stderr.
        ret_val = subprocess.run([str(FFMPEG_PATH), '-i', str(media_path), '-af', 'volumedetect', '-vn', '-sn', '-dn',
                                  '-f', 'null', '-'],
                                 stderr=subprocess.PIPE)

        if ret_val.returncode:
            print(f'WARNING: Audio loudness detection failed due to an FFMPEG error:\n{ret_val.stderr.decode()}')
            return 0

        histograms = re.findall(r'histogram_([0-9]+)db:\s*([0-9]+)', ret_val.stderr.decode())
        if not histograms:
            print(f'WARNING: Audio loudness detection failed because no loudness information was found in the FFMPEG '
                  f'output. This may be a bug caused by change in the FFMPEG stdout.\n'
                  f'FFMPEG OUTPUT="""{ret_val.stderr.decode()}"""')
            return 0

        db = int(histograms[0][0])
        if int(histograms[0][1]) > FFMPEG_NORMALISATION_THRESHOLD:
            if db == 0:
                return 0
            else:
                return db - 1
        else:
            if len(histograms) == 1:
                return db

            highest = db
            for histogram in histograms[1:]:
                if int(histogram[1]) < FFMPEG_NORMALISATION_THRESHOLD:
                    highest = int(histogram[0])
                else:
                    return highest

    def _autopitch(self, song_folder: Path) -> None:
        """Pitches the ultrastar file using the ultrastar_pitch utility.

        Args:
            song_folder (Path): The path to the folder containing all the song files.
        """

        notes_file = song_folder.joinpath(song_folder.name + '.txt')
        pitched_file = song_folder.joinpath('pitched.txt')

        pitch_pipeline = ultrastar_pitch.DetectionPipeline(
            ultrastar_pitch.ProjectParser(),
            ultrastar_pitch.AudioPreprocessor(stride=128),
            ultrastar_pitch.PitchClassifier(),
            ultrastar_pitch.StochasticPostprocessor()
        )

        pitch_pipeline.transform(str(notes_file), str(pitched_file), True)

        notes_file.unlink()
        pitched_file.rename(notes_file)

    def run(
        self,
        overlap_decision_function: Optional[Callable[[List[ass.line._Event]], ass.line._Event]] = None,
        style_select_function: Optional[Callable[[List[Tuple[str, int]]], str]] = None
    ) -> None:
        """Runs this Karaluxer instance to produce the ultrastar song.

        Args:
            overlap_decision_function (Optional[Callable[[List[ass.line._Event]], ass.line._Event]], optional):
                The decision function to use when selecting overlapping lines. Must be specified if
                self.overlap_filter_method is "individual".
            style_select_function (Optional[Callable[[List[Tuple[str, int]]], str]], optional):
                The decision function to use when selecting a style to discard. Must be specified if
                self.overlap_filter_method is "duet" or "style".
        """
        if self.kara_url:
            kara_id = self.kara_url.split('/')[-1]
            kara_data = self._fetch_kara_data(kara_id)

            self.ultrastar_song.add_metadata('TITLE', kara_data['title'] +  (' (TV)' if self.tv_sized else ''))
            self.ultrastar_song.add_metadata('ARTIST', kara_data['artists'])
            self.ultrastar_song.add_metadata('CREATOR', kara_data['authors'])
            self.ultrastar_song.add_metadata('LANGUAGE', kara_data['language'])
            self.ultrastar_song.add_metadata('YEAR', kara_data['year'])
            if kara_data['tags']:
                self.ultrastar_song.add_metadata('TAGS', kara_data['tags'])
            self.ultrastar_song.add_metadata('VERSION', '1.1.0')

            temporary_folder_obj = tempfile.TemporaryDirectory()
            temporary_folder = Path(temporary_folder_obj.name)

            download_directory = temporary_folder.joinpath(kara_id)
            download_directory.mkdir(parents=True, exist_ok=True)

            if not self.files['subtitles']:
                self._fetch_kara_file(kara_data['sub_file'], download_directory)
                self.files['subtitles'] = download_directory.joinpath(kara_data['sub_file'])

            if not self.files['audio']:
                self._fetch_kara_file(kara_data['media_file'], download_directory)
                media_path = download_directory.joinpath(kara_data['media_file'])
                self.ultrastar_song.add_metadata(
                    'AUDIOURL', 'https://kara.moe/downloads/medias/' + urllib.parse.quote(kara_data['media_file'])
                )

                # Some songs on Kara have an mp3 as the media file. In the case where the media is not in mp3 form, it
                # will be converted to mp3 using ffmpeg.
                if media_path.suffix != '.mp3':
                    self.files['audio'] = self._extract_audio(media_path, download_directory, True)
                else:
                    self.files['audio'] = media_path

            # Fetch the background video if it wasn't already downloaded for the audio. Used when a user specifies an
            # audio file manually.
            if not self.files['background_video']:
                self._fetch_kara_file(kara_data['media_file'], download_directory)
                media_path = download_directory.joinpath(kara_data['media_file'])

                if media_path.suffix != '.mp3':
                    if not self.files['background_video']:
                        self.files['background_video'] = media_path

            if ((not self.files['off_vocal'] and kara_data['off_vocal'] is not None)
                    or isinstance(self.files['off_vocal'], str)):
                if not self.files['off_vocal']:
                    off_vocal = kara_data['off_vocal']
                else:
                    data = self._fetch_kara_data(self.files['off_vocal'].split('/')[-1])
                    off_vocal = data['media_file']

                self._fetch_kara_file(off_vocal, download_directory)
                media_path = download_directory.joinpath(off_vocal)

                if media_path != '.mp3':
                    audio_path = self._extract_audio(media_path, download_directory, False)
                    if audio_path is None:
                        warnings.warn('Could not extract the off-vocal version with FFMPEG')
                    else:
                        self.files['off_vocal'] = audio_path
                    os.remove(media_path)
                else:
                    self.files['off_vocal'] = media_path

            if isinstance(self.files['vocals'], str):
                data = self._fetch_kara_data(self.files['vocals'].split('/')[-1])
                self._fetch_kara_file(data['media_file'], download_directory)
                media_path = download_directory.joinpath(data['media_file'])

                if media_path != '.mp3':
                    audio_path = self._extract_audio(media_path, download_directory, False)
                    if audio_path is None:
                        warnings.warn('Could not extract the vocals version with FFMPEG')
                    else:
                        self.files['vocals'] = audio_path
                    os.remove(media_path)
                else:
                    self.files['vocals'] = media_path

        else:
            # Add default meta tags if Kara.moe is not used. These will need to be edited by hand in the produced
            # text file.
            self.ultrastar_song.add_metadata('TITLE', 'Song Title')
            self.ultrastar_song.add_metadata('ARTIST', 'Song Artist')
            self.ultrastar_song.add_metadata('CREATOR', 'Map Creator')
            self.ultrastar_song.add_metadata('LANGUAGE', 'Map Creator')

        # This tag is not recognized or used by any karaoke programs, it is added by Karaluxer to help identify which
        # maps have been produced using this script.
        self.ultrastar_song.add_metadata('KARALUXER-VERSION', KARALUXER_VERSION)

        # Like the KARALUXERVERSION tag, this tag is not recognized by karaoke programs, it is used to identify the
        # original source of the map.
        if self.kara_url:
            self.ultrastar_song.add_metadata('KARALUXER-KARAID', kara_id)
            self.ultrastar_song.add_metadata('PROVIDEDBY', 'https://kara.moe')

        self.ultrastar_song.add_metadata('GAP', '0')

        # The BPM of the song needs to be 1/4 of the actual BPS used in mapping. I'm not sure why.
        self.ultrastar_song.add_metadata('BPM', str(self.bpm))

        subtitle_lines = self._load_subtitle_lines()

        # Overlaps in the subtitles are handled in one of four ways:
        #   If self.overlap_filter_method is None, overlaps will be ignored and left in the ultrastar file.
        #   If self.overlap_filter_method is "style", users will be prompted to styles to discard until only one style
        #       remains, any lines not in that style will be discarded.
        #   If self.overlap_filter_method is "individual", users will discard overlapping lines by selecting lines
        #       individually whenever there is a set of overlaps.
        #   If self.overlap_filter_method is "duet", users will be asked to discard any styles in the subtitle file
        #       until there is exactly 2 styles left, these will then be mapped individually to produce the duet parts.
        if self.overlap_filter_method == 'style':
            if style_select_function:
                subtitle_lines = self._filter_overlapping_lines_style(subtitle_lines, style_select_function)
            else:
                raise ValueError('A valid decision function must be passed to select a style.')
        elif self.overlap_filter_method == 'individual':
            if overlap_decision_function:
                subtitle_lines = self._filter_overlapping_lines_individual(subtitle_lines, overlap_decision_function)
            else:
                raise ValueError('A valid decision function must be passed to filter overlapping lines.')
        elif self.overlap_filter_method == 'duet':
            if style_select_function:
                duet_parts = self._separate_duet_parts(subtitle_lines, style_select_function)
                # duet_parts may only contain one part. This happens if duet mode is selected but the subtitle file does
                # not have multiple styles to split into duet parts. If this happens the song will be mapped as normal.
                if len(duet_parts) == 1:
                    self.overlap_filter_method = None  # Set to prevent the program attempting to map as a duet.
                else:
                    self._convert_lines(duet_parts[0], 'P1')
                    self._convert_lines(duet_parts[1], 'P2')

                    if self.bpm_multiplier > 1:
                        for player in ['P1', 'P2']:
                            self.ultrastar_song.adjust_notes(self.bpm_multiplier, player)
            else:
                raise ValueError('A valid decision function must be passed to select a style.')

        # Duets are mapped before this line.
        if self.overlap_filter_method != 'duet':
            self._convert_lines(subtitle_lines)
            if self.bpm_multiplier > 1:
                self.ultrastar_song.adjust_notes(self.bpm_multiplier)

        song_folder_name = self.ultrastar_song.meta_lines['ARTIST'] + ' - ' + self.ultrastar_song.meta_lines['TITLE']
        song_folder_name = re.sub(r'[^\w\-.() ]+', '', song_folder_name)
        song_folder_name = song_folder_name.strip()

        output_folder = Path('output')
        song_folder = output_folder.joinpath(song_folder_name)
        song_folder.mkdir(parents=True)

        if self.files['audio']:
            cover_name = song_folder_name + self.files['audio'].suffix
            self.ultrastar_song.add_metadata('MP3', cover_name)
            shutil.copy(self.files['audio'], song_folder.joinpath(cover_name))

        if self.files['background_image']:
            cover_name = song_folder_name + self.files['background_image'].suffix
            self.ultrastar_song.add_metadata('BACKGROUND', cover_name)
            shutil.copy(self.files['background_image'], song_folder.joinpath(cover_name))

        if self.files['background_video']:
            cover_name = song_folder_name + self.files['background_video'].suffix
            self.ultrastar_song.add_metadata('VIDEO', cover_name)
            shutil.copy(self.files['background_video'], song_folder.joinpath(cover_name))

        if self.files['cover']:
            cover_name = song_folder_name + ' [CO]' + self.files['cover'].suffix
            self.ultrastar_song.add_metadata('COVER', cover_name)
            shutil.copy(self.files['cover'], song_folder.joinpath(cover_name))

        if self.files['off_vocal']:
            cover_name = song_folder_name + ' [INSTR]' + self.files['off_vocal'].suffix
            self.ultrastar_song.add_metadata('INSTRUMENTAL', cover_name)
            shutil.copy(self.files['off_vocal'], song_folder.joinpath(cover_name))

        if self.files['vocals']:
            cover_name = song_folder_name + ' [VOC]' + self.files['vocals'].suffix
            self.ultrastar_song.add_metadata('VOCALS', cover_name)
            shutil.copy(self.files['vocals'], song_folder.joinpath(cover_name))

        ultrastar_file = song_folder.joinpath(song_folder_name + '.txt')
        with open(ultrastar_file, 'w', encoding='utf-8') as f:
            f.write(str(self.ultrastar_song))

        if self.kara_url:
            shutil.rmtree(download_directory)
            temporary_folder_obj.cleanup()

        if self.autopitch:
            self._autopitch(song_folder)


def main() -> None:
    """Command Line Interface for Karaluxer."""

    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument('-k', '--kara_url', type=str, help='The Kara.moe url to use.')
    argument_parser.add_argument('-s', '--sub_file', type=str, help='The subtitle file to use.')
    argument_parser.add_argument('-c', '--cover', type=str, help='The cover image for the song.')
    argument_parser.add_argument('-bg', '--background', type=str, help='The background image for the song.')
    argument_parser.add_argument('-bv', '--video', type=str, help='The video file for the song.')
    argument_parser.add_argument('-a', '--audio', type=str, help='The audio file for the song.')
    argument_parser.add_argument('-ov', '--off-vocal', type=str,
                                 help='The off-vocal track for the song. This can be either a path to file or a kara.moe URL.')
    argument_parser.add_argument('-vs', '--vocals', type=str,
                                 help='The vocals track for the song. This can be either a path to file or a kara.moe URL.')
    argument_parser.add_argument('-fd', '--force_dialogue',
                                 action='store_true', help='Force use of lines marked "Dialogue".')
    argument_parser.add_argument('-tv', '--tv_sized', action='store_true', help='Mark this song as TV sized.')
    argument_parser.add_argument('-ap', '--autopitch',
                                 action='store_true', help='Pitch the song using ultrastar_pitch.')
    argument_parser.add_argument('--karaoke-bpm', type=float, default=1500.,
                                 help='The Karaoke BPM, i.e. the BPM that will be used in the karaoke txt file. '
                                      'If not provided, 1500 will be used as default.')
    argument_parser.add_argument('--song-bpm', type=int, default=0,
                                 help='The true Song BPM, i.e. the BPM of the song. This should be different from the '
                                      'Karaoke BPM; Karaoke BPM has to be an integer multiple of the Song BPM. '
                                      'If provided, this is used to calculate the multiple which is used to remove '
                                      'overlaps and otherwise clean up the timings to make mapping easier.')
    argument_parser.add_argument('-en', '--disable-normalisation', action='store_false',
                                 help='If provided, disables audio normalisation that occurs when the kara.moe source '
                                      'contains a video file whose loudness is not normalised to 0 dB.')

    group = argument_parser.add_mutually_exclusive_group()
    group.add_argument('-io', '--ignore_overlaps', action='store_true',
                       help='Ignore overlapping lines (default).')
    group.add_argument('-fi', '--filter-individually', action='store_true',
                       help='Filter overlapping lines individually.')
    group.add_argument('-fs', '--filter-by-style', action='store_true',
                       help='Filter overlapping lines by their style.')
    group.add_argument('-md', '--map-duet', action='store_true', help='Map the song as a duet.')

    argument_parser.set_defaults(ignore_overlaps=True, force_dialogue=False, tv_sized=False, autopitch=False)

    arguments = argument_parser.parse_args()

    if arguments.filter_individually:
        overlap_filter_method = 'individual'
    elif arguments.filter_by_style:
        overlap_filter_method = 'style'
    elif arguments.map_duet:
        overlap_filter_method = 'duet'
    else:
        overlap_filter_method = None

    karaluxer_instance = KaraLuxer(
        arguments.kara_url,
        arguments.sub_file,
        arguments.cover,
        arguments.background,
        arguments.video,
        arguments.audio,
        arguments.off_vocal,
        arguments.vocals,
        arguments.ignore_overlaps,
        arguments.force_dialogue,
        arguments.tv_sized,
        arguments.autopitch,
        arguments.karaoke_bpm,
        arguments.song_bpm if arguments.song_bpm != 0 else arguments.karaoke_bpm,
        arguments.disable_normalisation
    )

    def cli_overlap_decision_function(overlapping_lines: List[ass.line._Event]) -> ass.line._Event:
        for i in range(0, len(overlapping_lines)):
            clean_line = re.sub(r'\{(.*?)\}', '', str(overlapping_lines[i].text))
            print('{0}.) {1}'.format(i, clean_line))

        print('Select a line to DISCARD.')
        while True:
            try:
                selection = int(input(':>'))
            except ValueError:
                print('Please specify a valid integer.')
                continue

            if 0 <= selection < len(overlapping_lines):
                return overlapping_lines[selection]
            else:
                print('Please specify an integer in the correct range.')
                continue

    def cli_style_selection_function(styles: List[Tuple[str, int]]) -> str:
        for i in range(0, len(styles)):
            print('{0}.) {1} ({2} lines in this style)'.format(i, styles[i][0], styles[i][1]))

        print('Select a style to DISCARD. All lines in this style will be discarded.')
        while True:
            try:
                selection = int(input(':>'))
            except ValueError:
                print('Please specify a valid integer.')
                continue

            if 0 <= selection < len(styles):
                return styles[selection][0]
            else:
                print('Please specify an integer in the correct range.')
                continue

    karaluxer_instance.run(cli_overlap_decision_function, cli_style_selection_function)


if __name__ == '__main__':
    main()

