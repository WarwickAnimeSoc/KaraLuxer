import sys
import re
import threading


from PyQt5.QtWidgets import QApplication, QGridLayout, QGroupBox, QLabel, QLineEdit, QPushButton, QVBoxLayout, QDialog, QFileDialog
import karaluxer


class KaraLuxerApp(QDialog):
    """GUI for the KaraLuxer script."""

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

        self.essential_args_group.setLayout(essential_args_layout)

        # ----------------------------------------------------
        # Optional Arguments group
        # ----------------------------------------------------
        self.optional_args_group = QGroupBox('Optional Parameters')
        optional_args_layout = QGridLayout()
        optional_args_layout.setColumnStretch(0, 1)
        optional_args_layout.setColumnStretch(1, 2)
        optional_args_layout.setColumnStretch(2, 1)

        self.cover_input = QLineEdit()
        optional_args_layout.addWidget(QLabel('Cover Image:'), 0, 0)
        optional_args_layout.addWidget(self.cover_input, 0, 1)
        cover_button = QPushButton('Browse')
        cover_button.clicked.connect(lambda: self.get_file(self.cover_input, "Image files (*.jpg *.jpeg *.png)"))
        optional_args_layout.addWidget(cover_button, 0, 2)

        self.bg_input = QLineEdit()
        optional_args_layout.addWidget(QLabel('Background Image:'), 1, 0)
        optional_args_layout.addWidget(self.bg_input, 1, 1)
        bg_button = QPushButton('Browse')
        bg_button.clicked.connect(lambda: self.get_file(self.bg_input, "Image files (*.jpg *.jpeg *.png)"))
        optional_args_layout.addWidget(bg_button, 1, 2)

        self.bgv_input = QLineEdit()
        optional_args_layout.addWidget(QLabel('Background Video:'), 2, 0)
        optional_args_layout.addWidget(self.bgv_input, 2, 1)
        bgv_button = QPushButton('Browse')
        bgv_button.clicked.connect(lambda: self.get_file(self.bgv_input, "Mp4 files (*.mp4)"))
        optional_args_layout.addWidget(bgv_button, 2, 2)

        self.creator_input = QLineEdit()
        optional_args_layout.addWidget(QLabel('Creator:'), 3, 0)
        optional_args_layout.addWidget(self.creator_input, 3, 1)
        optional_args_layout.addWidget(QLabel('(Appended to the Kara.moe map creator)'), 3, 2)


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

        self.output_text = QLabel()
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

        self.show()

    def get_file(self, target: QLineEdit, filter: str) -> None:
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

    def run(self) -> None:
        """Method to run the KaraLuxer script."""

        if self.process_thread and self.process_thread.is_alive():
            print('Warning: Wait until the current run is finished before starting another!')
        else:
            self.flush()
            self.process_thread = threading.Thread(
                target=karaluxer.gui_entry_point,
                name='processing_thread',
                args=[
                    self.kara_url_input.text(),
                    self.cover_input.text(),
                    self.bg_input.text(),
                    self.bgv_input.text(),
                    self.creator_input.text()
                ])
            self.process_thread.start()

    def write(self, message) -> None:
        """Method used to override stdout to output to the window.

        Args:
            message ([type]): The message received.
        """

        clean_message = re.sub(r'\033\[((?:[0-9];[0-9]+)|(?:0))m', '', message)
        self.output_text.setText(self.output_text.text() + clean_message)

    def flush(self) -> None:
        """Method use to override stdout to clear to the window."""

        self.output_text.setText('')


if __name__ == '__main__':
    app = QApplication([])
    window = KaraLuxerApp()
    sys.stdout = window
    sys.stderr = window
    sys.exit(app.exec_())
