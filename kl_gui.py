# GUI for KaraLuxer

from typing import List, Callable, Tuple

import re
import sys
from threading import Thread
from PyQt5 import QtCore
from PyQt5.QtWidgets import (QApplication, QMessageBox, QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton,
                             QDialog, QFileDialog, QCheckBox, QVBoxLayout, QProgressBar, QButtonGroup)

import ass
import ass.line

from karaluxer import KaraLuxer


class KaraLuxerThread(QtCore.QThread):
    """Custom Thread for running a KaraLuxer instance. Will raise any exceptions produced by Karaluxer."""

    discard_line_signal = QtCore.pyqtSignal(object)
    discard_style_signal = QtCore.pyqtSignal(str)

    def __init__(
        self,
        parent: QtCore.QObject,
        karaluxer_instance: KaraLuxer
    ) -> None:
        """Constructor for the Karaluxer Thread.

        Args:
            karaluxer_instance (KaraLuxer): The KaraLuxer instance to execute.
        """
        super().__init__(parent)

        self.karaluxer_instance = karaluxer_instance

        self.discard_line_signal.connect(self._on_line_discard)
        self.discard_style_signal.connect(self._on_style_discard)

        self.selected_line = None
        self.selected_style = None
        self.raised_exception = None

    def _on_line_discard(self, discarded_line: ass.line._Event) -> None:
        """Slot used to set the selected line from the GUI thread."""

        self.selected_line = discarded_line

    def _on_style_discard(self, discarded_style: str) -> None:
        """Slot used to set the selected style from the GUI thread."""

        self.selected_style = discarded_style

    def _overlap_decision(self, overlapping_lines: List[ass.line._Event]) -> ass.line._Event:
        """Generates a popup window to select between overlapping lines.

        Args:
            overlapping_lines (List[ass.line._Event]): A set of overlapping lines.

        Returns:
            ass.line._Event: The line to discard.
        """

        self.parent().overlap_window_signal.emit(overlapping_lines)

        while (not self.selected_line):
            pass

        discard_line = self.selected_line
        self.selected_line = None

        return discard_line

    def _style_selection(self, styles: List[Tuple[str, int]]) -> str:
        """Generates a popup window to select between overlapping lines.

        Args:
            styles (List[Tuple[str, int]]): A set of styles, each style tuple contains its name and how many lines are
            in style.

        Returns:
            str: The style to discard.
        """

        self.parent().style_window_signal.emit(styles)

        while (not self.selected_style):
            pass

        discard_style = self.selected_style
        self.selected_style = None

        return discard_style

    def run(self) -> None:
        """Executes the KaraLuxer instance."""

        try:
            self.karaluxer_instance.run(self._overlap_decision, self._style_selection)
        except (ValueError, IOError) as e:
            self.raised_exception = e


class OverlapSelectionWindow(QDialog):
    """Window used to choose between overlapping lines."""

    def __init__(self, overlapping_lines: List[ass.line._Event]) -> None:
        """Constructor for the OverlapSelectionWindow.

        Args:
            overlapping_lines (List[ass.line._Event]): The lines to choose between.
        """

        super().__init__()

        # Window settings and flags
        self.setWindowTitle('Choose a line to discard')
        self.setGeometry(20, 20, 600, 200)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)

        # Window layout
        window_layout = QVBoxLayout()
        self.setLayout(window_layout)

        # Information
        window_layout.addWidget(QLabel('The following lines overlap, please select one to DISCARD.'))

        # Line selection buttons
        for i in range(0, len(overlapping_lines)):
            current_line = overlapping_lines[i]
            clean_line = re.sub(r'\{(.*?)\}', '', str(overlapping_lines[i].text))
            button_string = 'Time = {0} to {1} | Style = \"{2}\" | Text = {3}'.format(
                current_line.start,
                current_line.end,
                current_line.style,
                clean_line
            )
            line_button = QPushButton(button_string)
            line_button.clicked.connect(lambda _, index=i: self._line_select_callback(index))
            window_layout.addWidget(line_button)

    def _line_select_callback(self, line_index: int) -> None:
        """Callback function used by the buttons to set the line to discard and close the window.

        The selected line can then be retrieved from the `selected_line` attribute.

        Args:
            line_index (int): The index of the line to discard.
        """

        self.selected_line = line_index
        self.close()


class StyleSelectionWindow(QDialog):
    """Window used to choose between different styles."""

    def __init__(self, styles: List[Tuple[str, int]]) -> None:
        """Constructor for the StyleSelectionWindow.

        Args:
            styles (List[Tuple[str, int]]): A list of styles to choose between. Each style provides its name and how
                many lines in that style exist.
        """

        super().__init__()

        # Window settings and flags
        self.setWindowTitle('Choose a style to discard')
        self.setGeometry(20, 20, 600, 200)
        self.setWindowFlag(QtCore.Qt.WindowCloseButtonHint, False)

        # Window layout
        window_layout = QVBoxLayout()
        self.setLayout(window_layout)

        # Information
        window_layout.addWidget(QLabel('Select a style to DISCARD. All lines in this style will be discarded.'))

        # Style selection buttons
        for style in styles:
            button_string = 'Style = "{0}" | {1} lines in this style.'.format(
                style[0],
                style[1]
            )
            style_button = QPushButton(button_string)
            style_button.clicked.connect(lambda _, style_name=style[0]: self._style_select_callback(style_name))
            window_layout.addWidget(style_button)

    def _style_select_callback(self, style_name: str) -> None:
        """Callback function used by the buttons to set the style to discard and close the window.

        The selected style can then be retrieved from the `selected_style` attribute.

        Args:
            style_name (str): The name of the style to discard.
        """

        self.selected_style = style_name
        self.close()


class KaraLuxerWindow(QDialog):
    """Main window for the script interface."""

    overlap_window_signal = QtCore.pyqtSignal(object)
    style_window_signal = QtCore.pyqtSignal(object)

    def __init__(self) -> None:
        """Constructor for the KaraLuxer window."""

        super().__init__()

        # Set message severity constants. Used for displaying popup messages.
        self.LVL_ERROR = 2
        self.LVL_WARNING = 1
        self.LVL_INFO = 0

        # Thread for running KaraLuxer.
        self.karaluxer_thread = None
        self.overlap_window_signal.connect(self._overlap_decision)
        self.style_window_signal.connect(self._style_decision)

        # Window settings and flags
        self.setWindowTitle('KaraLuxer')
        self.setGeometry(20, 20, 700, 800)

        # Subtitle source group
        sub_source_group = QGroupBox('Subtitle Source')
        sub_source_layout = QGridLayout()

        sub_source_layout.addWidget(QLabel('Please specify one and only one of the following.'), 0, 0, 1, 3)

        self.kara_url_input = QLineEdit()
        sub_source_layout.addWidget(QLabel('Kara.moe URL:'), 1, 0)
        sub_source_layout.addWidget(self.kara_url_input, 1, 1)

        self.sub_file_input = QLineEdit()
        sub_source_layout.addWidget(QLabel('Subtitle File:'), 2, 0)
        sub_source_layout.addWidget(self.sub_file_input, 2, 1)

        sub_file_button = QPushButton('Browse')
        sub_file_button.clicked.connect(
            lambda: self._get_file_path(self.sub_file_input, "Subtitles (*.ass)")
        )
        sub_source_layout.addWidget(sub_file_button, 2, 2)

        sub_source_group.setLayout(sub_source_layout)

        # Essential arguments group
        essential_args_group = QGroupBox('Essential Arguments')
        essential_args_layout = QGridLayout()

        self.cover_input = QLineEdit()
        essential_args_layout.addWidget(QLabel('Cover Image:'), 0, 0)
        essential_args_layout.addWidget(self.cover_input, 0, 1)
        cover_button = QPushButton('Browse')
        cover_button.clicked.connect(lambda: self._get_file_path(self.cover_input, "Image files (*.jpg *.jpeg *.png)"))
        essential_args_layout.addWidget(cover_button, 0, 2)

        essential_args_group.setLayout(essential_args_layout)

        # Optional arguments group
        optional_args_group = QGroupBox('Optional Arguments')
        optional_args_layout = QGridLayout()
        optional_args_layout.setColumnStretch(0, 1)
        optional_args_layout.setColumnStretch(1, 2)
        optional_args_layout.setColumnStretch(2, 1)

        self.bg_input = QLineEdit()
        optional_args_layout.addWidget(QLabel('Background Image:'), 0, 0)
        optional_args_layout.addWidget(self.bg_input, 0, 1)
        bg_button = QPushButton('Browse')
        bg_button.clicked.connect(lambda: self._get_file_path(self.bg_input, "Image files (*.jpg *.jpeg *.png)"))
        optional_args_layout.addWidget(bg_button, 0, 2)

        self.bgv_input = QLineEdit()
        self.bgv_input.setPlaceholderText('Will override the Kara.moe video.')
        optional_args_layout.addWidget(QLabel('Background Video:'), 1, 0)
        optional_args_layout.addWidget(self.bgv_input, 1, 1)
        bgv_button = QPushButton('Browse')
        bgv_button.clicked.connect(lambda: self._get_file_path(self.bgv_input, "Video files (*.mp4)"))
        optional_args_layout.addWidget(bgv_button, 1, 2)

        self.audio_input = QLineEdit()
        self.audio_input.setPlaceholderText('Will override the Kara.moe audio.')
        optional_args_layout.addWidget(QLabel('Audio:'), 2, 0)
        optional_args_layout.addWidget(self.audio_input, 2, 1)
        audio_button = QPushButton('Browse')
        audio_button.clicked.connect(lambda: self._get_file_path(self.audio_input, "Audio files (*.mp3)"))
        optional_args_layout.addWidget(audio_button, 2, 2)

        self.bpm = QLineEdit()
        self.bpm.setPlaceholderText('Default is 1500.')
        optional_args_layout.addWidget(QLabel('BPM:'), 3, 0)
        optional_args_layout.addWidget(self.bpm, 3, 1)
        optional_args_layout.addWidget(QLabel('For easier mapping and singing'), 3, 2)

        self.tv_checkbox = QCheckBox()
        optional_args_layout.addWidget(QLabel('TV Sized:'), 4, 0)
        optional_args_layout.addWidget(self.tv_checkbox, 4, 1)
        optional_args_layout.addWidget(QLabel('Appends "(TV)" to the song title'), 4, 2)

        optional_args_group.setLayout(optional_args_layout)

        # Overlap handing group
        overlap_handling_group = QGroupBox('Overlap Handling')
        overlap_handling_layout = QGridLayout()
        overlap_handling_layout.setColumnStretch(0, 1)
        overlap_handling_layout.setColumnStretch(1, 2)
        overlap_handling_layout.setColumnStretch(2, 1)

        overlap_handling_button_group = QButtonGroup(self)
        overlap_handling_button_group.setExclusive(True)

        self.ignore_overlaps_checkbox = QCheckBox()
        self.ignore_overlaps_checkbox.setChecked(True)
        overlap_handling_button_group.addButton(self.ignore_overlaps_checkbox)
        overlap_handling_layout.addWidget(QLabel('Ignore Overlaps:'), 0, 0)
        overlap_handling_layout.addWidget(self.ignore_overlaps_checkbox, 0, 1)
        overlap_handling_layout.addWidget(
            QLabel('Ignore overlapping lines (Will potentially require manual editing)'), 0, 2)

        self.individual_overlaps_checkbox = QCheckBox()
        overlap_handling_button_group.addButton(self.individual_overlaps_checkbox)
        overlap_handling_layout.addWidget(QLabel('Filter Individually:'), 1, 0)
        overlap_handling_layout.addWidget(self.individual_overlaps_checkbox, 1, 1)
        overlap_handling_layout.addWidget(
            QLabel('Filter overlapping lines individually'), 1, 2)

        self.style_overlaps_checkbox = QCheckBox()
        overlap_handling_button_group.addButton(self.style_overlaps_checkbox)
        overlap_handling_layout.addWidget(QLabel('Filter by Style:'), 2, 0)
        overlap_handling_layout.addWidget(self.style_overlaps_checkbox, 2, 1)
        overlap_handling_layout.addWidget(
            QLabel('Filter overlapping lines by their style'), 2, 2)

        self.duet_overlaps_checkbox = QCheckBox()
        overlap_handling_button_group.addButton(self.duet_overlaps_checkbox)
        overlap_handling_layout.addWidget(QLabel('Map as Duet:'), 3, 0)
        overlap_handling_layout.addWidget(self.duet_overlaps_checkbox, 3, 1)
        overlap_handling_layout.addWidget(
            QLabel('Map the song as a Duet'), 3, 2)

        overlap_handling_group.setLayout(overlap_handling_layout)

        # Advanced arguments group
        advanced_args_group = QGroupBox('Advanced Arguments')
        advanced_args_layout = QGridLayout()
        advanced_args_layout.setColumnStretch(0, 1)
        advanced_args_layout.setColumnStretch(1, 2)
        advanced_args_layout.setColumnStretch(2, 1)

        self.force_dialogue_checkbox = QCheckBox()
        advanced_args_layout.addWidget(QLabel('Force Dialogue:'), 0, 0)
        advanced_args_layout.addWidget(self.force_dialogue_checkbox, 0, 1)
        advanced_args_layout.addWidget(
            QLabel('Forces the script to use lines marked "Dialogue" (Not recommended for Kara.moe maps)'), 0, 2)

        self.autopitch_checkbox = QCheckBox()
        advanced_args_layout.addWidget(QLabel('Generate pitches:'), 1, 0)
        advanced_args_layout.addWidget(self.autopitch_checkbox, 1, 1)
        advanced_args_layout.addWidget(QLabel('Will pitch the file using "ultrastar_pitch"'), 1, 2)

        advanced_args_group.setLayout(advanced_args_layout)

        # Progress indicator
        self.indicator_bar = QProgressBar()
        self.indicator_bar.setStyleSheet("QProgressBar::chunk { background-color: #328CC1; }")
        self.indicator_bar.setTextVisible(False)

        # Run button
        run_button = QPushButton('Run')
        run_button.clicked.connect(self._run)

        # Window layout
        window_layout = QVBoxLayout()
        window_layout.addWidget(sub_source_group)
        window_layout.addWidget(essential_args_group)
        window_layout.addWidget(optional_args_group)
        window_layout.addWidget(overlap_handling_group)
        window_layout.addWidget(advanced_args_group)
        window_layout.addWidget(self.indicator_bar)
        window_layout.addWidget(run_button)

        window_layout.addStretch(3)

        self.setLayout(window_layout)

    def _indicator_bar_start(self) -> None:
        """Starts the busy indicator."""

        self.setEnabled(False)
        self.indicator_bar.setRange(0, 0)

    def _indicator_bar_stop(self) -> None:
        """Stops the busy indicator."""

        self.setEnabled(True)
        self.indicator_bar.setRange(0, 1)

    def _get_file_path(self, target: QLineEdit, filter: str) -> None:
        """Method to get the path to a file and update a target to hold the filepath.

        Args:
            target (QLineEdit): The target widget to update.
            filter (str): The filter to use for the file picker.
        """

        file_dialogue = QFileDialog()
        file_dialogue.setFileMode(QFileDialog.ExistingFile)
        file_dialogue.setNameFilter(filter)

        if file_dialogue.exec_() == QDialog.Accepted:
            target.setText(file_dialogue.selectedFiles()[0])

    def _display_message(self, message: str, severity: int) -> None:
        """Displays a message in a popup window.

        Args:
            message (str): The message to display.
            severity (int): The severity of the message.
        """

        message_window = QMessageBox()
        if severity == self.LVL_INFO:
            message_window.setIcon(QMessageBox.Information)
            message_window.setWindowTitle('Info')
        elif severity == self.LVL_WARNING:
            message_window.setIcon(QMessageBox.Warning)
            message_window.setWindowTitle('Warning')
        else:
            message_window.setIcon(QMessageBox.Critical)
            message_window.setWindowTitle('Error')

        message_window.setText(message)
        message_window.exec()

    def _overlap_decision(self, overlapping_lines: List[ass.line._Event]) -> None:
        """Slot which generates a popup window to select between overlapping lines.

        Args:
            overlapping_lines (List[ass.line._Event]): A set of overlapping lines.
        """

        selection_window = OverlapSelectionWindow(overlapping_lines)
        selection_window.exec()

        self.karaluxer_thread.discard_line_signal.emit(overlapping_lines[selection_window.selected_line])

    def _style_decision(self, styles: List[Tuple[str, int]]) -> None:
        """Slot which generates a popup window to select between styles.

        Args:
            overlapping_lines (List[Tuple[str, int]]): A set of styles. Each style tuple stores its name and how many
                lines correspond to that style.
        """

        selection_window = StyleSelectionWindow(styles)
        selection_window.exec()

        self.karaluxer_thread.discard_style_signal.emit(selection_window.selected_style)

    def _on_karaluxer_terminate(self) -> None:
        """Called when the KaraLuxer thread terminates."""

        self._indicator_bar_stop()
        if self.karaluxer_thread.raised_exception:
            self._display_message(str(self.karaluxer_thread.raised_exception), self.LVL_ERROR)
            return
        else:
            self._display_message('Finished. Song folder can be found in the "output" folder.', self.LVL_INFO)

    def _run(self) -> None:
        """Produces and runs the KaraLuxer instance."""

        self._indicator_bar_start()

        # Get data from the inputs
        kara_url = self.kara_url_input.text() if self.kara_url_input.text() else None
        sub_file = self.sub_file_input.text() if self.sub_file_input.text() else None

        if kara_url and sub_file:
            self._display_message('Please specify either a subtitle file or kara.moe url, not both.', 2)
            self._indicator_bar_stop()
            return
        elif not (kara_url or sub_file):
            self._display_message('Please specify a subtitle file or kara.moe url.', 2)
            self._indicator_bar_stop()
            return

        cover_file = self.cover_input.text() if self.cover_input.text() else None

        if not cover_file:
            self._display_message('Please specify a cover image file.', 2)
            self._indicator_bar_stop()
            return

        bg_file = self.bg_input.text() if self.bg_input.text() else None
        bgv_file = self.bgv_input.text() if self.bgv_input.text() else None
        audio_file = self.audio_input.text() if self.audio_input.text() else None
        tv_sized = self.tv_checkbox.isChecked()

        try:
            bpm = float(self.bpm.text()) if self.bpm.text() else 1500
        except ValueError:
            self._display_message(f'BPM must be a number, but "{self.bpm.text()}" was provided.', self.LVL_ERROR)
            self._indicator_bar_stop()
            return

        overlap_filter_mode = None
        overlap_filter_mode = "style" if self.style_overlaps_checkbox.isChecked() else overlap_filter_mode
        overlap_filter_mode = "individual" if self.individual_overlaps_checkbox.isChecked() else overlap_filter_mode
        overlap_filter_mode = "duet" if self.duet_overlaps_checkbox.isChecked() else overlap_filter_mode

        force_dialogue = self.force_dialogue_checkbox.isChecked()
        generate_pitches = self.autopitch_checkbox.isChecked()

        try:
            karaluxer_instance = KaraLuxer(
                kara_url,
                sub_file,
                cover_file,
                bg_file,
                bgv_file,
                audio_file,
                overlap_filter_mode,
                force_dialogue,
                tv_sized,
                generate_pitches,
                bpm
            )
        except (ValueError, IOError) as e:
            self._display_message(str(e), self.LVL_ERROR)
            self._indicator_bar_stop()
            return

        self.karaluxer_thread = KaraLuxerThread(self, karaluxer_instance)
        self.karaluxer_thread.finished.connect(self._on_karaluxer_terminate)
        self.karaluxer_thread.start()


if __name__ == '__main__':
    app = QApplication([])
    window = KaraLuxerWindow()
    window.show()
    sys.exit(app.exec_())
