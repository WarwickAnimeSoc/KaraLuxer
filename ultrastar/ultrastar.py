from typing import Optional, List, Dict


class NoteLine():

    def __init__(
        self,
        note_type: str,
        start_beat: int,
        duration: Optional[int] = None,
        pitch: Optional[int] = None,
        text: Optional[str] = None
    ) -> None:
        """Sets up the NoteLine instance.

        Args:
            note_type (str): The type of note. Usually ":" but can be "*", "-", "R" or "F".
            start_beat (int): The beat on which the note starts.
            duration (Optional[int], optional): The duration of the note in beats. Defaults to None.
            pitch (Optional[int], optional): The pitch of the note. Defaults to None.
            text (Optional[str], optional): The text to display for the note. Defaults to None.
        """

        self.note_type = note_type
        self.start_beat = start_beat
        self.duration = duration
        self.pitch = pitch
        self.text = text

        # Separator lines only need the start beat, normal lines require all data.
        if self.note_type != '-' and not (duration and pitch and text):
            raise ValueError('Non "-" (linebreak) type lines require the duration, pitch and text to be specified.')

    def __str__(self) -> str:
        """Produces a string representation of the note.

        Returns:
            str: A string representation of the note in the format "TYPE START DURATION PITCH TEXT" or "- TIME" if the
                 note is a linebreak.
        """

        if self.note_type == '-':
            return '{0} {1}'.format(self.note_type, self.start_beat)
        else:
            return '{0} {1} {2} {3} {4}'.format(self.note_type, self.start_beat, self.duration, self.pitch, self.text)



class UltrastarSong():

    def __init__(self, bpm: int) -> None:
        """Sets up the UltrastarSong instance.

        Args:
            bpm (int): The bpm of the song.
        """

        self.bpm = bpm

        self.meta_lines = {}

        self.note_lines: Dict[str, List[NoteLine]] = {'P1': [], 'P2': []}

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
        note_type: str,
        start_beat: int,
        duration: Optional[int] = None,
        pitch: Optional[int] = None,
        text: Optional[str] = None,
        player: str = 'P1'
    ) -> None:
        """Adds a note to the ultrastar file.

        Note lines are written as "TYPE START DURATION PITCH TEXT" in the ultrastar file. Lines that specify a linebreak
        are written as "- TIME".

        Args:
            note_type (str): The type of note. Usually ":" but can be "*", "-", "R" or "F".
            start_beat (int): The beat on which the note starts.
            duration (Optional[int], optional): The duration of the note in beats. Defaults to None.
            pitch (Optional[int], optional): The pitch of the note. Defaults to None.
            text (Optional[str], optional): The text to display for the note. Defaults to None.
            player (str, optional): The player to add the note to (used for duets).
        """
        note = NoteLine(note_type, start_beat, duration, pitch, text)
        self.note_lines[player].append(note)


    def __str__(self) -> str:
        """Produces a string representation of the song.

        Returns:
            str: A string containing the full ultrastar file.
        """

        # Metatags are sorted alphabetically by key.
        sorted_metadata = sorted(self.meta_lines.items(), key=lambda i: i[0])

        ultrastar_file = ''

        for tag, value in sorted_metadata:
            ultrastar_file += '#{0}:{1}\n'.format(tag, value)

        sorted_notes_1 = sorted(self.note_lines['P1'], key=lambda n: n.start_beat)
        sorted_notes_2 = sorted(self.note_lines['P2'], key=lambda n: n.start_beat)

        if sorted_notes_2:
            # Duet map
            ultrastar_file += 'P1\n'
            for note in sorted_notes_1:
                ultrastar_file += str(note) + '\n'
            ultrastar_file += 'E\n'
            ultrastar_file += 'P2\n'
            for note in sorted_notes_2:
                ultrastar_file += str(note) + '\n'
            ultrastar_file += 'E\n'
        else:
            for note in sorted_notes_1:
                ultrastar_file += str(note) + '\n'
            ultrastar_file += 'E\n'

        return ultrastar_file
