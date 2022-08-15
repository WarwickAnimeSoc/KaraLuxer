# Core Karaluxer functionality - CLI interface

from typing import Optional

from pathlib import Path

import re

from ultrastar.ultrastar import UltrastarSong

# Rather than estimate the BPM of each song, KaraLuxer uses a fixed BPM (specified here in Beats Per Second). Subtitle
# files for karaoke specify timings in centiseconds, therefore to avoid rounding KaraLuxer uses 100 beats per second.
# Using a fixed BPM, and a high one (6000 BPM) makes manual editing of the files produced by KaraLuxer harder.
KARALUXER_BPS = 100


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
        ignore_overlaps: bool = False
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
            ignore_overlaps (bool, optional): If True, overlaps will be left in the ultrastar file. Defaults to False.
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

