from typing import Optional, List, Dict, Iterator

import warnings


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
            # Special case where a note has a duration of 0. This should still be allowed but warn the user.
            if duration == 0:
                warnings.warn('0 beat long note')
            else:
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

    def adjust_notes(
        self,
        bpm_multiplier: int,
        player: str = 'P1'
    ) -> None:
        """
        Adjusts all the notes so that they are of a length that is a multiple of the BPM multiplier. All notes are also
        moved so that they start and end at a beat that is divisible by the BPM multiplier. This should theoretically
        result in all notes being closer to correct (as long as the correct BPM is being used) and so that they follow
        the rhythm of the song. However, depending on rounding/etc., it may mess up the timings instead.

        Nevertheless, true note overlaps should be respected, so any notes should not be moved too far off and will
        still be of the correct length; besides, they will always be displaced by a multiple of the BPM multiplier.

        Args:
            bpm_multiplier: The BPM multiplier, i.e. the karaoke BPM divided by the true song BPM. This is also the
                            length of the shortest notes.
            player: which player to perform the adjustment for

        Returns:
            None
        """
        notes = self.note_lines[player]
        for i, note in enumerate(notes):
            if note.note_type != '-':
                start = i
                break
        else:
            return

        start_beat = notes[start].start_beat

        if notes[start].duration < bpm_multiplier:
            notes[start].duration = bpm_multiplier
        else:
            notes[start].duration = bpm_multiplier * round(notes[start].duration / bpm_multiplier)

        last_break_idx = []
        for i, note in enumerate(notes[start+1:]):
            if note.note_type == '-':
                last_break_idx.append(i+start+1)
                continue

            for previous_note in notes[start+i::-1]:
                if previous_note.note_type != '-':
                    break
            else:
                continue

            previous_note_end = previous_note.start_beat + previous_note.duration

            if previous_note_end > note.start_beat > previous_note_end - bpm_multiplier:
                # If notes are overlapping due to the BPM change rather than because there is an overlap
                note.start_beat = previous_note_end
            else:
                modulus = (note.start_beat - start_beat) % bpm_multiplier
                if modulus != 0:
                    if round(modulus / bpm_multiplier) == 1:
                        note.start_beat += bpm_multiplier - modulus
                    else:
                        note.start_beat -= modulus

            if note.duration < bpm_multiplier:
                note.duration = bpm_multiplier
            else:
                note.duration = bpm_multiplier * round(note.duration / bpm_multiplier)

            if last_break_idx:
                for idx in last_break_idx:
                    notes[idx].start_beat = note.start_beat
                last_break_idx = []

    def sort_metadata(self) -> Iterator[tule[str, str]]:
        """Sorts the metadata headers in a spefific order and yields the results.

        Iterates over the key-value pairs from ``meta_lines`` using a specific 
        ordering, generally:

        1. ``VERSION`` header
        2. Song information, like title, artist, genre, year, etc.
        3. File headers, like mp3, cover, video, etc.
        4. Karaoke information, like bpm, gap, etc.
        5. Karaluxer metadata - ``PROVIDEDBY`` and karaluxer-unique tags
        6. Unknown headers
        """
        headers = self.meta_lines.copy()

        for header in ['VERSION', 'TITLE', 'ARTIST', 'LANGUAGE', 'GENRE', 'CREATOR', 'TAGS', 'YEAR', 
                       'AUDIO', 'MP3', 'INSTRUMENTAL', 'VOCALS', 'BACKGROUND', 'COVER', 'VIDEO',
                       'BPM', 'GAP', 'START', 'END', 'PREVIEWSTART', 'VIDEOGAP', 'COMMENT',
                       'PROVIDEDBY', 'KARALUXER-KARAID', 'KARALUXER-VERSION']:
            value = headers.pop(header, None)
            if value is not None:
                yield header, value

        for header, value in headers.items():
            yield header, value

    def __str__(self) -> str:
        """Produces a string representation of the song.

        Returns:
            str: A string containing the full ultrastar file.
        """
        ultrastar_file = ''

        for tag, value in self.sort_metadata():
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
