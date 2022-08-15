from typing import Optional, List


class NoteLine():

    def __init__(
        self,
        type: str,
        start_beat: int,
        duration: Optional[int] = None,
        pitch: Optional[int] = None,
        text: Optional[str] = None
    ) -> None:
        """Sets up the NoteLine instance.

        Args:
            type (str): The type of note. Usually ":" but can be "*", "-", "R" or "F".
            start_beat (int): The beat on which the note starts.
            duration (Optional[int], optional): The duration of the note in beats. Defaults to None.
            pitch (Optional[int], optional): The pitch of the note. Defaults to None.
            text (Optional[str], optional): The text to display for the note. Defaults to None.
        """

        self.type = type,
        self.start_beat = start_beat,
        self.duration = duration,
        self.pitch = pitch,
        self.text = text

        # Separator lines only need the start beat, normal lines require all data.
        if self.type != '-' and not (duration and pitch and text):
            raise ValueError('Non "-" (linebreak) type lines require the duration, pitch and text to be specified.')


    def __str__(self) -> str:
        """Produces a string representation of the note.

        Returns:
            str: A string representation of the note in the format "TYPE START DURATION PITCH TEXT" or "- TIME" if the
                 note is a linebreak.
        """

        if self.type == '-':
            return '{0} {1}'.format(self.type, self.start_beat)
        else:
            return '{0} {1} {2} {3} {4}'.format(self.type, self.start_beat, self.duration, self.pitch, self.text)



class UltrastarSong():

    def __init__(self, bpm: int) -> None:
        """Sets up the UltrastarSong instance.

        Args:
            bpm (int): The bpm of the song.
        """

        self.bpm = bpm

        self.meta_lines = {}

        self.note_lines: List[NoteLine] = []

    def add_metadata(self, tag: str, value: str) -> None:
        """Adds a metadata tag to the ultrastar file, will overwrite previous values.

        Metadata lines are written as "#TAG:VALUE" in the ultrastar file.

        Args:
            tag (str): The tag name.
            value (str): The tag value.
        """

        self.meta_lines[tag] = value

    def add_note(
        self,
        type: str,
        start_beat: int,
        duration: Optional[int] = None,
        pitch: Optional[int] = None,
        text: Optional[str] = None
    ) -> None:
        """Adds a note to the ultrastar file.

        Note lines are written as "TYPE START DURATION PITCH TEXT" in the ultrastar file. Lines that specify a linebreak
        are written as "- TIME".

        Args:
            type (str): The type of note. Usually ":" but can be "*", "-", "R" or "F".
            start_beat (int): The beat on which the note starts.
            duration (Optional[int], optional): The duration of the note in beats. Defaults to None.
            pitch (Optional[int], optional): The pitch of the note. Defaults to None.
            text (Optional[str], optional): The text to display for the note. Defaults to None.
        """
        note = NoteLine(type, start_beat, duration, pitch, text)
        self.note_lines.append(note)


    def __str__(self) -> str:
        """Produces a string representation of the song.

        Returns:
            str: A string containing the full ultrastar file.
        """

        # Metatags are sorted alphabetically by key.
        sorted_metadata = sorted(self.meta_lines.items(), key=lambda i: i[0])

        # Notes are sorted by their start beat.
        sorted_notes = sorted(self.note_lines, key=lambda n: n.start_beat)

        ultrastar_file = ''

        for tag, value in sorted_metadata:
            ultrastar_file += '#{0}:{1}\n'.format(tag, value)

        for note in sorted_notes:
            ultrastar_file += str(note) + '\n'

        ultrastar_file += 'E\n'

        return ultrastar_file
