import logging
from enum import Enum
from concurrent.futures import Future
from dataclasses import dataclass, field
from typing import Optional

from numpy.typing import NDArray  # type: ignore

log = logging.getLogger(__name__)


class TitleType(Enum):
    NORMAL = "NORMAL"
    INFINITAS = "INFINITAS"
    LEGGENDARIA = "LEGGENDARIA"


class GameState(Enum):
    LOADING = "LOADING"
    SONG_SELECT = "SONG_SELECT"
    SONG_SELECTED = "SONG_SELECTED"
    P1_SP_PLAY = "P1_SP_PLAY"
    P2_SP_PLAY = "P2_SP_PLAY"
    P1_DP_PLAY = "P1_DP_PLAY"
    P2_DP_PLAY = "P2_DP_PLAY"
    P1_SCORE = "P1_SCORE"
    P2_SCORE = "P2_SCORE"
    UNKNOWN = "UNKNOWN"


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


class DifficultyType(Enum):
    NORMAL = 0
    HYPER = 1
    ANOTHER = 2
    LEGGENDARIA = 3
    UNKNOWN = 99


@dataclass
class GameStatePixel:
    state: GameState = GameState.UNKNOWN
    name: str = ""
    y: int = 0
    x: int = 0
    b: int = 0
    g: int = 0
    r: int = 0


@dataclass
class PlayMetadata:
    difficulty: Difficulty
    level: int
    lifebar_type: str
    min_bpm: int
    max_bpm: int
    left_side: bool = True
    is_double: bool = False


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
    total_score: int = 0
    miss_count: int = 0


class SingleOrDouble(Enum):
    SP = 2
    DP = 7


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
    NO_PLAY = 7
    UNKNOWN = 99


@dataclass
class DifficultyMetadata:
    level: int = 0
    notes: int = 0
    min_bpm: int = 0
    max_bpm: int = 0
    soflan: bool = False


def generate_difficulty_metadata() -> dict[Difficulty, DifficultyMetadata]:
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
    difficulty_metadata: dict[Difficulty, DifficultyMetadata] = field(
        default_factory=generate_difficulty_metadata
    )
    version: str = ""

    def to_dict(self) -> dict:
        return {
            "textage_id": self.textage_id,
            "title": self.title,
            "artist": self.artist,
            "genre": self.genre,
            "textage_version_id": self.version,
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
        unchecked_version_id: int = self.textage_version_id
        checked_version_id: float = 0.0
        # substream textage workaround
        if unchecked_version_id == -1:
            checked_version_id = 1.5
        else:
            checked_version_id = float(unchecked_version_id)
        return f"{checked_version_id:04.1f} {self.sort_by_alphanumeric()}"

    def __check_difficulty_rate(self, difficulty: Difficulty) -> str:
        """
        set any blanks to appear after other entries by setting them to ZZZ.
        Otherwise prepend 0s to any single digit difficulties for string
        based sorting.
        """
        if (
            difficulty not in self.difficulty_metadata
            or self.difficulty_metadata[difficulty].level == 0
        ):
            return "ZZZ"
        return f"{self.difficulty_metadata[difficulty].level:02d}"

    def sort_by_spn(self) -> str:
        rate = self.__check_difficulty_rate(Difficulty.SP_NORMAL)
        print(f"{rate} " + self.sort_by_alphanumeric())
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_sph(self) -> str:
        rate = self.__check_difficulty_rate(Difficulty.SP_HYPER)
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_spa(self) -> str:
        rate = self.__check_difficulty_rate(Difficulty.SP_ANOTHER)
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_spl(self) -> str:
        rate = self.__check_difficulty_rate(Difficulty.SP_LEGGENDARIA)
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_dpn(self) -> str:
        rate = self.__check_difficulty_rate(Difficulty.DP_NORMAL)
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_dph(self) -> str:
        rate = self.__check_difficulty_rate(Difficulty.DP_HYPER)
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_dpa(self) -> str:
        rate = self.__check_difficulty_rate(Difficulty.DP_ANOTHER)
        return f"{rate} " + self.sort_by_alphanumeric()

    def sort_by_dpl(self) -> str:
        rate = self.__check_difficulty_rate(Difficulty.DP_LEGGENDARIA)
        return f"{rate} " + self.sort_by_alphanumeric()


@dataclass
class OCRSongTitles:
    en_title: str
    en_artist: str
    jp_title: str
    jp_artist: str


@dataclass
class OCRGenres:
    en_genre: str
    jp_genre: str


@dataclass
class VideoProcessingState:
    score: Optional[Score] = None
    score_frame: Optional[NDArray] = None
    difficulty: Optional[Difficulty] = None
    level: Optional[int] = None
    lifebar_type: Optional[str] = None
    min_bpm: Optional[int] = None
    max_bpm: Optional[int] = None
    note_count: Optional[int] = None
    ocr_song_future: Optional[Future] = None
    ocr_song_title: Optional[OCRSongTitles] = None
    metadata_title: Optional[set[str]] = None
    left_side: Optional[bool] = None
    is_double: Optional[bool] = None
    previous_state: GameState = GameState.UNKNOWN
    current_state: GameState = GameState.UNKNOWN
    state_frame_count: int = 0

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
            f"is_double:{self.is_double}, "
            f"previous_state:{self.previous_state}, "
            f"current_state:{self.current_state}, "
            f"state_frame_count:{self.state_frame_count}"
            ")"
        )

    def can_resolve_song_via_metadata(self) -> bool:
        return (
            self.difficulty is not None
            and self.level is not None
            and self.min_bpm is not None
            and self.max_bpm is not None
            and self.note_count is not None
        )

    def returned_to_song_select_before_writing(self) -> bool:
        return (
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

    def play_metadata_missing(self) -> bool:
        return (
            self.difficulty is None
            or self.level is None
            or self.lifebar_type is None
            # TODO: fix
            # or self.lifebar_type == "UNKNOWN"
            or self.min_bpm is None
            or self.max_bpm is None
            or self.left_side is None
            or self.is_double is None
        )

    def update_current_state(self, state: GameState) -> None:
        self.previous_state = self.current_state
        if state == self.current_state:
            self.state_frame_count += 1
        else:
            self.current_state = state
            self.state_frame_count = 1

    def update_play_metadata(self, play_metadata: PlayMetadata) -> None:
        self.difficulty = play_metadata.difficulty
        self.level = play_metadata.level
        self.lifebar_type = play_metadata.lifebar_type
        self.min_bpm = play_metadata.min_bpm
        self.max_bpm = play_metadata.max_bpm
        self.left_side = play_metadata.left_side
        self.is_double = play_metadata.is_double


@dataclass
class NumberArea:
    start_x: int
    start_y: int
    x_offset: int
    y_offset: int
    rows: int
    digits_per_row: int
    name: str
    kerning_offset: Optional[list[int]] = None
