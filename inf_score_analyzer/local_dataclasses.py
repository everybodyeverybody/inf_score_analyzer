import logging
from enum import Enum
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Dict, Set, Tuple, Optional

from numpy.typing import NDArray

log = logging.getLogger(__name__)


@dataclass
class StatePixel:
    state: str = ""
    name: str = ""
    y: int = 0
    x: int = 0
    b: int = 0
    g: int = 0
    r: int = 0


@dataclass
class Point:
    x: int
    y: int


@dataclass
class Score:
    fgreat: int = 0
    great: int = 0
    good: int = 0
    bad: int = 0
    poor: int = 0
    fast: int = 0
    slow: int = 0
    grade: str = "X"
    clear_type: str = "FAILED"


@dataclass
class MetadataZone:
    top_left_y: int = 0
    bottom_right_y: int = 0
    top_left_x: int = 0
    bottom_right_x: int = 0
    state: str = ""
    area: str = ""


class Difficulty(Enum):
    SP_NORMAL = 2
    SP_HYPER = 3
    SP_ANOTHER = 4
    SP_LEGGENDARIA = 5
    DP_NORMAL = 7
    DP_HYPER = 8
    DP_ANOTHER = 9
    DP_LEGGENDARIA = 10
    UNKNOWN = 99


class Alphanumeric(Enum):
    ABCD = 0
    EFGH = 1
    IJKL = 2
    MNOP = 3
    QRST = 4
    UVWXYZ = 5
    OTHERS = 6


class ClearType(Enum):
    FAILED = 0
    ASSIST = 1
    EASY = 2
    NORMAL = 3
    HARD = 4
    EXHARD = 5
    FULL_COMBO = 6
    UNKNOWN = 99


@dataclass
class DifficultyMetadata:
    level: int = 0
    notes: int = 0
    min_bpm: int = 0
    max_bpm: int = 0
    soflan: bool = False


def generate_difficulty_metadata() -> Dict[Difficulty, DifficultyMetadata]:
    return {
        Difficulty.SP_NORMAL: DifficultyMetadata(),
        Difficulty.SP_HYPER: DifficultyMetadata(),
        Difficulty.SP_ANOTHER: DifficultyMetadata(),
        Difficulty.SP_LEGGENDARIA: DifficultyMetadata(),
        Difficulty.DP_NORMAL: DifficultyMetadata(),
        Difficulty.DP_HYPER: DifficultyMetadata(),
        Difficulty.DP_ANOTHER: DifficultyMetadata(),
        Difficulty.DP_LEGGENDARIA: DifficultyMetadata(),
    }


@dataclass
class SongMetadata:
    textage_id: str
    title: str
    artist: str
    genre: str
    textage_version_id: int
    alphanumeric: Alphanumeric
    difficulty_metadata: Dict[Difficulty, DifficultyMetadata] = field(
        default_factory=generate_difficulty_metadata
    )
    version: str = ""

    def to_dict(self) -> dict:
        return {
            "textage_id": self.textage_id,
            "title": self.title,
            "artist": self.artist,
            "genre": self.genre,
            "textage_version_id": self.version_id,
            "version": self.version,
            "alphanumeric": self.alphanumeric.name,
            "difficulty_metadata": {
                difficulty.name: {
                    "level": self.difficulty_metadata[difficulty].level,
                    "notes": self.difficulty_metadata[difficulty].notes,
                    "soflan": self.difficulty_metadata[difficulty].soflan,
                    "min_bpm": self.difficulty_metadata[difficulty].min_bpm,
                    "max_bpm": self.difficulty_metadata[difficulty].max_bpm,
                }
                for difficulty in self.difficulty_metadata.keys()
                if self.difficulty_metadata[difficulty].notes != 0
                and self.difficulty_metadata[difficulty].level != 0
            },
        }

    def sort_by_alphanumeric(self) -> str:
        """
        Primary sorting method, also used as the secondary
        sorting method when generating the static site.
        """
        return f"{self.alphanumeric.value} {self.title}"

    def sort_by_version(self) -> str:
        """
        Return formatted version strings, then alphabetically.
        subtream has a special case in textage data we work around,
        by setting it to the last element of the version list,
        and then reformatting strings so it comes alphabetically
        between 1 and 2. (that's what all the 0 padding is for
        in the return string)
        """
        unchecked_version_id: int = self.version_id
        checked_version_id: float = 0.0
        # substream textage workaround
        if unchecked_version_id == -1:
            checked_version_id = 1.5
        else:
            checked_version_id = float(unchecked_version_id)
        return f"{checked_version_id:04.1f} {self.sort_by_alphanumeric()}"

    def __check_difficulty_rate(self, difficulty_level: int) -> str:
        """
        Set any blanks to appear after other entries by setting them to ZZZ.
        Otherwise prepend 0s to any single digit difficulties for string
        based sorting.
        """
        if difficulty_level < 1:
            return "ZZZ"
        return f"{difficulty_level:02d}"

    def sort_by_spn(self) -> str:
        rate = self.__check_difficulty_rate(
            self.difficulty_and_notes[Difficulty.SP_NORMAL][0]
        )
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_sph(self) -> str:
        rate = self.__check_difficulty_rate(
            self.difficulty_and_notes[Difficulty.SP_HYPER][0]
        )
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_spa(self) -> str:
        rate = self.__check_difficulty_rate(
            self.difficulty_and_notes[Difficulty.SP_ANOTHER][0]
        )
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_spl(self) -> str:
        rate = self.__check_difficulty_rate(
            self.difficulty_and_notes[Difficulty.SP_LEGGENDARIA][0]
        )
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_dpn(self) -> str:
        rate = self.__check_difficulty_rate(
            self.difficulty_and_notes[Difficulty.DP_NORMAL][0]
        )
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_dph(self) -> str:
        rate = self.__check_difficulty_rate(
            self.difficulty_and_notes[Difficulty.DP_HYPER][0]
        )
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_dpa(self) -> str:
        rate = self.__check_difficulty_rate(
            self.difficulty_and_notes[Difficulty.DP_ANOTHER][0]
        )
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_dpl(self) -> str:
        rate = self.__check_difficulty_rate(
            self.difficulty_and_notes[Difficulty.DP_LEGGENDARIA][0]
        )
        return f"{rate} " + self.sort_by_alphanumeric()


@dataclass
class OCRSongTitles:
    en_title: str
    en_artist: str
    jp_title: str
    jp_artist: str


@dataclass
class SongReference:
    by_artist: Dict[str, Set[str]] = field(default_factory=dict)
    by_difficulty: Dict[Tuple[str, int], Set[str]] = field(default_factory=dict)
    by_title: Dict[str, str] = field(default_factory=dict)
    by_bpm: Dict[Tuple[int, int], Set[str]] = field(default_factory=dict)
    by_note_count: Dict[int, Set[str]] = field(default_factory=dict)

    def resolve_by_play_metadata(
        self,
        difficulty_tuple: Tuple[str, int],
        bpm_tuple: Tuple[int, int],
        note_count: Optional[int] = None,
    ) -> Set[str]:
        difficulty_set = self.by_difficulty[difficulty_tuple]
        bpm_set = self.by_bpm[bpm_tuple]
        if note_count is not None:
            notes_set = self.by_note_count[note_count]
            found_results = difficulty_set.intersection(bpm_set).intersection(notes_set)
        else:
            found_results = difficulty_set.intersection(bpm_set)
        log.info(f"PLAY METADATA SET: {found_results}")
        return found_results

    def _resolve_artist_ocr(
        self, song_title: OCRSongTitles, found_difficulty_textage_ids: Set[str]
    ) -> Optional[str]:
        found_artist_textage_id = None
        found_en_artist_textage_ids = self.by_artist.get(song_title.en_artist, set([]))
        found_jp_artist_textage_ids = self.by_artist.get(song_title.jp_artist, set([]))
        found_artist_textage_ids = found_en_artist_textage_ids.union(
            found_jp_artist_textage_ids
        )
        if len(found_artist_textage_ids) > 0:
            matching_ids = found_artist_textage_ids.intersection(
                found_difficulty_textage_ids
            )
            log.info(f"Matching artist/difficulty IDs: {matching_ids}")
            if len(matching_ids) == 1:
                found_artist_textage_id = list(matching_ids)[0]
        return found_artist_textage_id

    def _resolve_title_ocr(
        self, song_title: OCRSongTitles, found_difficulty_textage_ids: Set[str]
    ) -> Optional[str]:
        found_title_textage_id = None
        found_en_title_textage_id = self.by_title.get(song_title.en_title, None)
        found_jp_title_textage_id = self.by_title.get(song_title.jp_title, None)
        log.info(f"found_en_title_textage_id: {found_en_title_textage_id}")
        log.info(f"found_jp_title_textage_id: {found_jp_title_textage_id}")
        if found_en_title_textage_id is not None and found_jp_title_textage_id is None:
            found_title_textage_id = found_en_title_textage_id
        elif (
            found_en_title_textage_id is None and found_jp_title_textage_id is not None
        ):
            found_title_textage_id = found_jp_title_textage_id
        elif (
            found_en_title_textage_id == found_jp_title_textage_id
            and found_en_title_textage_id is not None
        ):
            found_title_textage_id = found_en_title_textage_id
        return found_title_textage_id

    def resolve_ocr(
        self, song_title: OCRSongTitles, difficulty: str, level: int
    ) -> Optional[str]:
        difficulty_tuple: Tuple[str, int] = (difficulty, level)
        found_difficulty_textage_ids = self.by_difficulty.get(difficulty_tuple, set([]))
        if not found_difficulty_textage_ids:
            log.info(f"Could not lookup difficulty {difficulty_tuple}")
            return None
        found_title_textage_id = self._resolve_title_ocr(
            song_title, found_difficulty_textage_ids
        )
        log.info(f"found_title_textage_id: {found_title_textage_id}")
        if (
            found_title_textage_id is not None
            and found_title_textage_id in found_difficulty_textage_ids
        ):
            return found_title_textage_id
        else:
            log.info(f"Could not find {found_title_textage_id} in difficulties")

        found_artist_textage_id = self._resolve_artist_ocr(
            song_title, found_difficulty_textage_ids
        )
        if found_artist_textage_id is not None:
            return found_artist_textage_id
        log.debug("found_title_textage_id: {found_title_textage_id}")
        log.info(
            f"Could not find song_title: {song_title} "
            f"difficulty: {difficulty_tuple}"
        )
        return None

    def resolve_strings(self, title: OCRSongTitles, metadata_titles: Set[str]):
        pass


@dataclass
class VideoProcessingState:
    score: Optional[Score] = None
    score_frame: Optional[NDArray] = None
    difficulty: Optional[str] = None
    level: Optional[int] = None
    lifebar_type: Optional[str] = None
    min_bpm: Optional[int] = None
    max_bpm: Optional[int] = None
    note_count: Optional[int] = None
    ocr_song_future: Optional[Future] = None
    ocr_song_title: Optional[OCRSongTitles] = None
    metadata_title: Optional[Set[str]] = None
    left_side: Optional[bool] = None
    is_double: Optional[bool] = None

    def __repr__(self):
        return (
            "VideoProcessingState("
            f"score:{self.score}, "
            f"difficulty:{self.difficulty}, "
            f"level:{self.level}, "
            f"lifebar_type:{self.lifebar_type}, "
            f"min_bpm:{self.min_bpm}, "
            f"max_bpm:{self.max_bpm}, "
            f"note_count:{self.note_count}, "
            f"ocr_song_title:{self.ocr_song_title}, "
            f"metadata_title:{self.metadata_title}, "
            f"left_side:{self.left_side}, "
            f"is_double:{self.is_double}) "
        )

    def returned_to_song_select_before_writing(self) -> bool:
        didnt_write: bool = (
            self.score is not None
            or self.score_frame is not None
            or self.difficulty is not None
            or self.level is not None
            or self.lifebar_type is not None
            or self.min_bpm is not None
            or self.max_bpm is not None
            or self.metadata_title is not None
            or self.left_side is not None
            or self.is_double is not None
        )
        return didnt_write

    def score_data_found_at_score_screen(self) -> bool:
        return (
            self.score is not None
            and self.score_frame is not None
            and self.ocr_song_title is not None
            and self.difficulty is not None
            and self.level is not None
            and self.metadata_title is not None
        )

    def score_data_was_captured(self) -> bool:
        return (
            self.ocr_song_title is not None
            and self.score is not None
            and self.score_frame is None
        )

    def play_metadata_missing(self) -> bool:
        return (
            self.difficulty is None
            or self.level is None
            or self.lifebar_type is None
            or self.lifebar_type == "UNKNOWN"
            or self.min_bpm is None
            or self.max_bpm is None
            or self.left_side is None
            or self.is_double is None
        )

    def ocr_is_not_done_processing(self) -> bool:
        return self.ocr_song_title is None or (
            self.ocr_song_future is not None and not self.ocr_song_future.done()
        )
