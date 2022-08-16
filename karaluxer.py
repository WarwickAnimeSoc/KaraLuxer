# Core Karaluxer functionality - CLI interface

from typing import Callable, Dict, Optional, List

from pathlib import Path
import re
import warnings
import json

import requests
import ass
import ass.line

from ultrastar.ultrastar import UltrastarSong

# Rather than estimate the BPM of each song, KaraLuxer uses a fixed BPM (specified here in Beats Per Second). Subtitle
# files for karaoke specify timings in centiseconds, therefore to avoid rounding KaraLuxer uses 100 beats per second.
# Using a fixed BPM, and a high one (6000 BPM) makes manual editing of the files produced by KaraLuxer harder.
KARALUXER_BPS = 100

# Regular expression to capture the timing/syllables from a line by stripping out the karaoke tags.
SYLLABLE_REGEX = re.compile(r'(\{\\(?:k|kf|ko|K)[0-9.]+\}[a-zA-Z _.\-,!"\']+\s*)|({\\(?:k|kf|ko|K)[0-9.]+[^}]*\})')

# THe default pitch to assign to notes.
DEFAULT_PITCH = 19

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
        ignore_overlaps: bool = False,
        force_dialogue_lines: bool = False
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
            ignore_overlaps (bool, optional): If True overlaps will be left in the ultrastar file. Defaults to False.
            force_dialogue_lines (bool, optional): If True only Dialogue lines will be parsed from the subtitle file.
                Not recommended unless specifying a manual subtitle file.
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
            'cover': Path(cover_file) if cover_file else None
        }
        self.ignore_overlaps = ignore_overlaps
        self.force_dialogue_lines = force_dialogue_lines

        # Parameter checks
        if kara_url and not re.match(r'https:\/\/kara\.moe\/kara\/[\w-]+\/[\w-]+', kara_url):
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

        self.ultrastar_song = UltrastarSong(KARALUXER_BPS * 60)

    def _load_subtitle_lines(self) -> List[ass.line._Event]:
        """Load, sort and filter the lines from the subtitle file. THis method must be run after a subtitle file has
           been provided, either manually or by downloading from Kara.

        Returns:
            List[ass.line._Event]: A list of all the lines in the subtitle file, sorted by their stating time.
        """

        if not self.files['subtitle']:
            raise ValueError('Subtitle file has not been provided.')

        with open(self.files['subtitle'], encoding='utf-8-sig') as f:
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

    def _filter_overlapping_lines(
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

                for j in range (i + 1, len(lines)):
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

    def _convert_lines(self, lines: List[ass.line._Event]) -> None:
        """Convert the subtitle lines to notes for the ultrastar song.

        Args:
            lines (List[ass.line._Event]): The subtitle lines to parse.
        """

        for line in lines:
            current_beat = round(line.start.total_seconds() * KARALUXER_BPS)

            # Get all syllables and their durations from the line.
            syllables = []
            for sound_pair, timing_pair in re.findall(SYLLABLE_REGEX, line.text):
                if sound_pair:
                    timing, syllable_text = sound_pair.split('}')
                elif timing_pair:
                    timing = timing_pair.split('\\')[1]
                    syllable_text = None
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

                self.ultrastar_song.add_note(':', current_beat, tweaked_duration, DEFAULT_PITCH, syllable_text)

                current_beat += converted_duration

            # Write a linebreak at the end of the line.
            self.ultrastar_song.add_note('-', current_beat)

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

        kara_data = {
            'title': data['titles'][data['titles_default_language']],
            'sub_file': data['subfile'],
            'media_file': data['mediafile'],
            'language': data['langs'][0]['i18n']['eng']
        }

        # Get song artists
        artists = ''
        for singer in data['singers']:
            artists += singer['name'] + ' & '
        kara_data['artists'] = artists[:-3]

        # Get map authors
        authors = ''
        for author in data['authors']:
            authors += author['name'] + ' & '
        kara_data['authors'] = authors[:-3]

        return kara_data

    def _fetch_kara_file(self, filename: str, download_directory: Path) -> None:
        file_path = Path(filename)

        if file_path.suffix == '.ass':
            response = requests.get('https://kara.moe/downloads/lyrics/' + filename)
        else:
            response = requests.get('https://kara.moe/downloads/medias/' + filename)

        if response.status_code != 200:
            raise ValueError('Unexpected response from kara.')

        with open(download_directory.joinpath(filename), 'wb') as f:
            f.write(response.content)
