from typing import List, Optional, Tuple, Union

from pathlib import Path
from datetime import datetime
import sys
import re
import shutil
import subprocess
from math import ceil, floor

from PyQt5 import QtCore
from PyQt5.QtWidgets import (QApplication, QMessageBox, QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
    QDialog, QFileDialog, QCheckBox, QVBoxLayout)

import ass
from ass.line import _Event, Dialogue, Comment

import kara_api.kara_api as kapi

# ----------------------------
# Type Aliases
# ----------------------------
CommentList = List[_Event]

# ----------------------------
# Regex
# ----------------------------

# Regex to extract timing information from a line.
TIMING_REGEX = re.compile(r'(\{\\(?:k|kf|ko|K)[0-9.]+\}[a-zA-Z _.\-,!"\']+\s*)|({\\(?:k|kf|ko|K)[0-9.]+[^}]*\})')

# Regex to check a kara.moe url is valid.
KARA_URL_REGEX = re.compile(r'https:\/\/kara\.moe\/kara\/[\w-]+\/[\w-]+')

# Regex to check if a character is valid to be used in a for Windows (10).
VALID_FILENAME_REGEX = re.compile(r'[^\w\-.() ]+')

# ----------------------------
# Constants
# ----------------------------
VERSION = '2.0.0'  # KaraLuxer script version.

OUTPUT_FOLDER = Path('./out')  # Directory where processed ultrastar songs are placed.
TMP_FOLDER = Path('./tmp')  # Directory where Kara.moe files are downloaded to.
NOTE_LINE = ': {start} {duration} {pitch} {sound}\n'  # Ultrastar format standard sung line.
SEP_LINE = '- {}\n'  # Ultrastar format line seperator.

BEATS_PER_SECOND = 100  # Beats per second for the ultrastar map. Subfiles use centiseconds for timing.
DEFAULT_PITCH = 19  # Default pitch to set notes to.

FFMPEG_PATH = Path(getattr(sys, '_MEIPASS'), 'ffmpeg.exe') if getattr(sys, '_MEIPASS', False) else 'ffmpeg.exe'

# ----------------------------
# Program
# ----------------------------

def clean_line_text(line: _Event) -> str:
    """Cleans all special data from the line text to get just the spoken Comment.

    Args:
        line (Comment): The Comment event to clean.

    Returns:
        str: A string of only the spoken Comment from the line.
    """

    return re.sub(r'\{(.*?)\}', '', line.text)


class OverlapSelectionWindow(QDialog):
    """Window used to choose between overlapping lines."""

    def select_line_callback(self, line_index: int) -> None:
        """Callback function connected to the line buttons. Used to set the selected line and close the window.

        Args:
            line_index (int): The index of the selected line in the self.lines list.
        """

        self.selected_line = self.lines[line_index]
        self.close()

    def __init__(self, overlapping_lines: CommentList) -> None:
        """Constructor for the OverlapSelectionWindow.

        Args:
            overlapping_lines (CommentList): A list containing all the overlapping Comment events.
        """
        super().__init__()

        # Line data
        self.lines = overlapping_lines
        self.selected_line = None

        # Window settings and Flags
        self.setWindowTitle('Choose a line to discard')
        self.setGeometry(20, 20, 600, 200)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)

        # Window layout
        window_layout = QGridLayout()
        self.setLayout(window_layout)

        # Information
        info_label = QLabel('The following lines overlap, please select one to DISCARD.')
        window_layout.addWidget(info_label, 0, 0)

        # Lines
        for i in range(0, len(self.lines)):
            current_line = self.lines[i]
            button_string = 'Time = {0} | Style = \"{1}\" | Text = {2}'.format(
                current_line.start,
                current_line.style,
                clean_line_text(current_line)
                )
            line_button = QPushButton(button_string)
            line_button.clicked.connect(lambda _, x=i: self.select_line_callback(x))
            window_layout.addWidget(line_button)


class KaraLuxer(QDialog):
    """Main KaraLuxer window."""

    # Message severity levels
    LVL_ERROR = 2
    LVL_WARNING = 1
    LVL_INFO = 0

    def get_file(self, target: QLineEdit, filter: str) -> None:
        """Method to get the path to a file and update a target to hold the filepath.

        Args:
            target (QLineEdit): The target widget to update.
            filter (str): The filter to use for the file picker.
        """

        file_Comment = QFileDialog()
        file_Comment.setFileMode(QFileDialog.ExistingFile)
        file_Comment.setNameFilter(filter)

        if file_Comment.exec_() == QDialog.Accepted:
            target.setText(file_Comment.selectedFiles()[0])

    def __init__(self) -> None:
        """Constructor for the KaraLuxer window."""
        super().__init__()

        self.setWindowTitle('KaraLuxer')
        self.setGeometry(20, 20, 600, 800)

        self.process_thread = None

        # ----------------------------------------------------
        # Essential Arguments group
        # ----------------------------------------------------
        self.essential_args_group = QGroupBox('Essential Parameters')
        essential_args_layout = QGridLayout()

        self.kara_url_input = QLineEdit()
        essential_args_layout.addWidget(QLabel('Kara.moe URL:'), 0, 0)
        essential_args_layout.addWidget(self.kara_url_input, 0, 1)

        self.cover_input = QLineEdit()
        essential_args_layout.addWidget(QLabel('Cover Image:'), 1, 0)
        essential_args_layout.addWidget(self.cover_input, 1, 1)
        cover_button = QPushButton('Browse')
        cover_button.clicked.connect(lambda: self.get_file(self.cover_input, "Image files (*.jpg *.jpeg *.png)"))
        essential_args_layout.addWidget(cover_button, 1, 2)

        self.essential_args_group.setLayout(essential_args_layout)

        # ----------------------------------------------------
        # Optional Arguments group
        # ----------------------------------------------------
        self.optional_args_group = QGroupBox('Optional Parameters')
        optional_args_layout = QGridLayout()
        optional_args_layout.setColumnStretch(0, 1)
        optional_args_layout.setColumnStretch(1, 2)
        optional_args_layout.setColumnStretch(2, 1)

        self.bg_input = QLineEdit()
        self.bg_input.setPlaceholderText('Only visible if no background video is available.')
        optional_args_layout.addWidget(QLabel('Background Image:'), 0, 0)
        optional_args_layout.addWidget(self.bg_input, 0, 1)
        bg_button = QPushButton('Browse')
        bg_button.clicked.connect(lambda: self.get_file(self.bg_input, "Image files (*.jpg *.jpeg *.png)"))
        optional_args_layout.addWidget(bg_button, 0, 2)

        self.bgv_input = QLineEdit()
        self.bgv_input.setPlaceholderText('Replaces the kara.moe video.')
        optional_args_layout.addWidget(QLabel('Background Video:'), 1, 0)
        optional_args_layout.addWidget(self.bgv_input, 1, 1)
        bgv_button = QPushButton('Browse')
        bgv_button.clicked.connect(lambda: self.get_file(self.bgv_input, "Mp4 files (*.mp4)"))
        optional_args_layout.addWidget(bgv_button, 1, 2)

        self.creator_input = QLineEdit()
        optional_args_layout.addWidget(QLabel('Creator:'), 2, 0)
        optional_args_layout.addWidget(self.creator_input, 2, 1)
        optional_args_layout.addWidget(QLabel('(Appended to the Kara.moe map creator)'), 2, 2)

        self.tv_checkbox = QCheckBox()
        optional_args_layout.addWidget(QLabel('TV Sized:'), 3, 0)
        optional_args_layout.addWidget(self.tv_checkbox, 3, 1)
        optional_args_layout.addWidget(QLabel('(Will add "(TV)" to the song title)'), 3, 2)
        
        self.overlap_checkbox = QCheckBox()
        optional_args_layout.addWidget(QLabel('Skip overlaps:'), 4, 0)
        optional_args_layout.addWidget(self.overlap_checkbox, 4, 1)
        optional_args_layout.addWidget(QLabel('([Advanced] For manual overlap handling)'), 4, 2)

        self.optional_args_group.setLayout(optional_args_layout)

        # ----------------------------------------------------
        # Run Button
        # ----------------------------------------------------

        run_button = QPushButton('Run')
        run_button.clicked.connect(self.run)

        # ----------------------------------------------------
        # Output
        # ----------------------------------------------------

        self.output_group = QGroupBox('Program Output')
        output_layout = QGridLayout()

        self.output_text = QLabel('Not Running')
        output_layout.addWidget(self.output_text)

        self.output_group.setLayout(output_layout)

        # ----------------------------------------------------
        # Base Window
        # ----------------------------------------------------
        window_layout = QVBoxLayout()
        window_layout.addWidget(self.essential_args_group)
        window_layout.addWidget(self.optional_args_group)
        window_layout.addWidget(run_button)
        window_layout.addWidget(self.output_group)

        window_layout.addStretch(3)

        self.setLayout(window_layout)

    def display_message(self, level: int, message: str):
        """Displays an Info, Warning or Error message.

        Args:
            level (int): The level of the message, should be a constant prefixed LVL_
            message (str): The message to display.
        """

        message_window = QMessageBox()
        if level == self.LVL_INFO:
            message_window.setIcon(QMessageBox.Information)
            message_window.setWindowTitle('Info')
        elif level == self.LVL_WARNING:
            message_window.setIcon(QMessageBox.Warning)
            message_window.setWindowTitle('Warning')
        else:
            message_window.setIcon(QMessageBox.Critical)
            message_window.setWindowTitle('Error')

        message_window.setText(message)
        message_window.exec()

    def get_sub_lines(self, sub_file: Path) -> CommentList:
        """Gets all the Comment events from a given subtitle file.

        Args:
            sub_file (Path): The path to the subtitle file.

        Returns:
            List[ass.Comment]: A list containing all the Comment events from the subtitle file, ordered by their starting
                                time.
        """

        with open(sub_file, 'r', encoding='utf-8-sig') as f:
            sub_data = ass.parse(f)

        # Filter out comment lines.
        line_list = [event for event in sub_data.events if isinstance(event, Comment)]

        # In the special case where comments are not used:
        # e.g https://kara.moe/kara/rock-over-japan/68a57800-9b23-4c62-bcc8-a77fb103b798
        # The Dialogue is used.
        if not line_list:
            line_list = [event for event in sub_data.events if isinstance(event, Dialogue)]

        # Sort lines to be in order of their starting time.
        line_list.sort(key=lambda line: line.start)

        return line_list

    def filter_overlaping_lines(self, lines: CommentList) -> CommentList:
        """Filters the Comment events to remove any overlapping lines.

        Args:
            lines (CommentList): The list of all Comment events in the subtitle file.

        Returns:
            CommentList: A filtered list of non-overlapping Comment events.
        """

        overlap_found = True

        while overlap_found:
            overlap_found = False

            remove_line = None

            for i in range(0, len(lines)):
                current_line = lines[i]

                current_line_end_beat = floor(current_line.end.total_seconds() * BEATS_PER_SECOND)

                overlap_group = [current_line]

                # Find any lines that overlap with the current one.
                for j in range(i + 1, len(lines)):
                    selected_line = lines[j]
                    selected_line_start_beat = ceil(selected_line.start.total_seconds() * BEATS_PER_SECOND)
                    if selected_line_start_beat < current_line_end_beat:
                        overlap_group.append(selected_line)


                if len(overlap_group) > 1:
                    overlap_found = True
                    # The user must select one of the overlapping lines to keep.
                    selection_window = OverlapSelectionWindow(overlap_group)
                    selection_window.exec()

                    remove_line = selection_window.selected_line
                    break

            if remove_line:
                lines.remove(remove_line)

        return lines

    def build_note_section(self, sub_file: Path, skip_overlaps: bool) -> str:
        """Produces the notes section of the Ultrastar song from the subtitle lines.

        Args:
            sub_file (Path): The path to the subtitle file.
            skip_overlaps (bool): If true, skips the call to filter overlapping lines.

        Returns:
            str: The note section of the Ultrastar song.
        """

        note_section = ''

        # Get subtitle data
        lines = self.get_sub_lines(sub_file)

        # Filter Comment to remove overlapping lines, but only when skip_overlaps is false
        filtered_lines = self.filter_overlaping_lines(lines) if not skip_overlaps else lines

        # Produce Ultrastar notes.
        for line in filtered_lines:
            # Get the starting beat for this line.
            current_beat = round(line.start.total_seconds() * BEATS_PER_SECOND)

            # Get all syllable/timing pairs from the line.
            syllables: List[Tuple[int, Optional[str]]] = []
            for sound_pair, timing_pair in re.findall(TIMING_REGEX, line.text):
                if sound_pair:
                    timing, sound = sound_pair.split('}')
                elif timing_pair:
                    timing = timing_pair.split('\\')[1]
                    sound = None
                else:
                    warning_text = 'Found something unexpected in line: \"{}\"'.format(clean_line_text(line))
                    self.display_message(self.LVL_WARNING, warning_text)
                    continue

                timing = re.sub(r'[^0-9.]', '', timing)
                syllables.append((round(float(timing)), sound))

            # Write out line for the Ultrastar format
            for duration, sound in syllables:
                # Timing pairs without sound simply increment the current beat counter.
                if not sound:
                    current_beat += duration
                    continue

                # Subtitle files will provide the duration of a note in centiseconds, this needs to be converted into
                # beats for the Ultrastar format.
                converted_duration = round((duration / 100) * BEATS_PER_SECOND)

                # Notes should be slightly shorter than their original duration, to make it easier to sing.
                # Currently this is done by simply reducing the duration by one. This could use improvement.
                tweaked_duration = converted_duration - 1 if converted_duration > 1 else converted_duration

                # Write note line
                note_section += NOTE_LINE.format(
                    start=current_beat,
                    duration=tweaked_duration,
                    pitch=DEFAULT_PITCH,
                    sound=sound
                )

                # Increment current beat by the non-tweaked duration.
                current_beat += converted_duration

            # Write end of line separator.
            note_section += SEP_LINE.format(current_beat)

        return note_section

    def check_parameters(self) -> bool:
        # Check the kara.moe url is valid.
        if not re.match(KARA_URL_REGEX, self.kara_url_input.text()):
            self.display_message(self.LVL_ERROR, 'Provided Kara.moe url is invalid.')
            return False

        # Check cover image.
        if self.cover_input.text():
            cover_path = Path(self.cover_input.text())

            if not cover_path.exists():
                self.display_message(self.LVL_ERROR, 'The specified cover image file can not be found!')
                return False
            elif cover_path.suffix not in ['.jpg', '.jpeg', '.png']:
                self.display_message(self.LVL_ERROR, 'The specified cover image is not an image!')
                return False
        else:
            self.display_message(self.LVL_ERROR, 'Please specify a cover image!')
            return False

        # Check background image.
        if self.bg_input.text():
            bg_path = Path(self.bg_input.text())

            if not bg_path.exists():
                self.display_message(self.LVL_ERROR, 'The specified background image file can not be found!')
                return False
            elif bg_path.suffix not in ['.jpg', '.jpeg', '.png']:
                self.display_message(self.LVL_ERROR, 'The specified background image is not an image!')
                return False

        # Check background video.
        if self.bgv_input.text():
            bgv_path = Path(self.bgv_input.text())

            if not bgv_path.exists():
                self.display_message(self.LVL_ERROR, 'The specified background video file can not be found!')
                return False
            elif bgv_path.suffix != '.mp4':
                self.display_message(self.LVL_ERROR, 'The specified background video is not a video!')
                return False

        return True

    def run(self) -> None:
        """Produces the Ultrastar map from the provided data."""

        # Check all the parameters are valid.
        if not self.check_parameters():
            return

        # Get data from the input
        kara_url = self.kara_url_input.text()
        cover_file = self.cover_input.text()
        bg_file = self.bg_input.text()
        bgv_file = self.bgv_input.text()
        tv_size = self.tv_checkbox.isChecked()
        overlap_skip = self.overlap_checkbox.isChecked()
        extra_creator = self.creator_input.text()

        """"""
        # --------------------------
        # Pull data from kara.moe
        # --------------------------

        # Get kara id from the url.
        kara_id = kara_url.split('/')[-1]

        # Create/Clear tmp folder for downloading.
        tmp_data = TMP_FOLDER.joinpath(kara_id)
        if tmp_data.exists():
            shutil.rmtree(tmp_data)
        tmp_data.mkdir(parents=True, exist_ok=False)

        # Download data from kara.
        self.output_text.setText('Getting data from kara.')
        kara_data = kapi.get_kara_data(kara_id)

        self.output_text.setText('Downloading subtitles.')
        kapi.get_sub_file(kara_data['sub_file'], tmp_data)

        self.output_text.setText('Downloading media.')
        kapi.get_media_file(kara_data['media_file'], tmp_data)

        # --------------------------
        # Load data
        # --------------------------

        subtitle_path = Path(tmp_data.joinpath(kara_data['sub_file']))
        media_path = Path(tmp_data.joinpath(kara_data['media_file']))

        # Convert the media to mp3 if it is a video.
        if media_path.suffix != '.mp3':
            self.output_text.setText('Converting media to mp3 using ffmpeg.')
            audio_path = tmp_data.joinpath('{0}.mp3'.format(media_path.stem))
            # Convert to mp3 using ffmpeg
            ret_val = subprocess.call([FFMPEG_PATH, '-i', str(media_path), '-b:a', '320k', str(audio_path)])

            if ret_val:
                self.display_message(self.LVL_ERROR, 'Could not convert media to mp3!')
                return

            if not bgv_file:
                bgv_file = media_path
        else:
            audio_path = media_path

        cover_path = Path(cover_file) if cover_file else None
        bg_path = Path(bg_file) if bg_file else None
        bgv_path = Path(bgv_file) if bgv_file else None

        self.output_text.setText('Mapping song.')

        # Create output folder
        title_string = kara_data['title'] + (' (TV)' if tv_size else '')
        base_name = '{0} - {1}'.format(kara_data['artists'], title_string)
        sanitized_base_name = re.sub(VALID_FILENAME_REGEX, '', base_name)
        sanitized_base_name = sanitized_base_name.strip()
        song_folder = OUTPUT_FOLDER.joinpath(sanitized_base_name)
        if song_folder.exists():
            self.display_message(self.LVL_WARNING, 'Overwriting existing song.')
            shutil.rmtree(song_folder)
        song_folder.mkdir(parents=True)

        # --------------------------
        # Generate song file
        # --------------------------

        # ---------------
        # Notes
        # ---------------

        # Parse subtitle file to get the notes section.
        notes_section = self.build_note_section(subtitle_path, overlap_skip)

        # ---------------
        # Metadata
        # ---------------

        metadata = '#TITLE:{0}\n#ARTIST:{1}\n'.format(title_string, kara_data['artists'])
        metadata += '#LANGUAGE:{0}\n'.format(kara_data['language'])

        creator_string = kara_data['authors'] + ('' if not extra_creator else (' & ' + extra_creator))
        metadata += '#CREATOR:{0}\n'.format(creator_string)

        # Custom tag not used by Ultrastar is used to mark the song as a KaraLuxer port.
        metadata += '#KARALUXERVERSION:{0}\n'.format(VERSION)

        # ---------------
        # Files
        # ---------------

        # Paths are made relative and files will be renamed to match the base name.
        mp3_name = '{0}.mp3'.format(sanitized_base_name)
        linked_files = '#MP3:{0}\n'.format(mp3_name)
        shutil.copy(audio_path, song_folder.joinpath(mp3_name))

        if cover_path:
            cover_name = '{0} [CO]{1}'.format(sanitized_base_name, cover_path.suffix)
            linked_files += '#COVER:{0}\n'.format(cover_name)
            shutil.copy(cover_path, song_folder.joinpath(cover_name))

        if bg_path:
            background_name = '{0} [BG]{1}'.format(sanitized_base_name, bg_path.suffix)
            linked_files += '#BACKGROUND:{0}\n'.format(background_name)
            shutil.copy(bg_path, song_folder.joinpath(background_name))

        if bgv_path:
            bg_video_name = '{0}{1}'.format(sanitized_base_name, bgv_path.suffix)
            linked_files += '#VIDEO:{0}\n'.format(bg_video_name)
            shutil.copy(bgv_path, song_folder.joinpath(bg_video_name))

        # ---------------
        # Song data
        # ---------------

        # Ultrastar requires the BPM opf the song.
        # This script uses a fixed 'beats per second' to produce timings, the BPM is calculated from the BPS.
        # The BPM put into the ultrastar file needs to be around 1/4 of the calculated BPM (I'm not sure why).
        beats_per_minute = (BEATS_PER_SECOND * 60) / 4

        song_data = '#BPM:{0}\n#GAP:0\n'.format(beats_per_minute)

        # ---------------
        # Write file
        # ---------------

        # Combine all the components of the file.
        ultrastar_file = metadata + linked_files + song_data + notes_section + 'E\n'

        # Write the file.
        ultrastar_file_path = song_folder.joinpath('{0}.txt'.format(sanitized_base_name))
        with open(ultrastar_file_path, 'w', encoding='utf-8') as f:
            f.write(ultrastar_file)

        # Clear downloads
        shutil.rmtree(tmp_data)

        self.output_text.setText('Finished.')
        self.display_message(self.LVL_INFO, 'Finished mapping the song. Check the output folder.')


if __name__ == '__main__':
    app = QApplication([])
    window = KaraLuxer()
    window.show()
    sys.exit(app.exec_())
