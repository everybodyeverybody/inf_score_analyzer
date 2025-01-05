import logging
from typing import Optional
from dataclasses import dataclass, field

import polyleven  # type: ignore

from .local_dataclasses import OCRSongTitles, OCRGenres


@dataclass
class SongReference:
    by_artist: dict[str, set[str]] = field(default_factory=dict)
    by_difficulty: dict[tuple[str, int], set[str]] = field(default_factory=dict)
    by_title: dict[str, str] = field(default_factory=dict)
    by_bpm: dict[tuple[int, int], set[str]] = field(default_factory=dict)
    by_note_count: dict[int, set[str]] = field(default_factory=dict)
    by_difficulty_and_notes: dict[tuple[str, int, int], set[str]] = field(
        default_factory=dict
    )
    by_genre: dict[str, set[str]] = field(default_factory=dict)
    log = logging.getLogger(__name__)

    def resolve_by_song_select_metadata(
        self,
        difficulty: str,
        level: int,
        bpm_tuple: tuple[int, int],
        ocr_titles: OCRSongTitles,
        ocr_genres: OCRGenres,
    ) -> set[str]:
        difficulty_tuple = (difficulty, level)
        difficulty_set = self.by_difficulty[difficulty_tuple]
        bpm_set = self.by_bpm[bpm_tuple]
        diff_bpm_set = difficulty_set.intersection(bpm_set)
        genre_set = self.__resolve_genres(ocr_genres)
        genre_diff_bpm_set = diff_bpm_set.intersection(genre_set)
        self.log.debug(f"DIFFICULTY+BPM SET: {diff_bpm_set}")
        self.log.debug(f"GENRE+DIFFICULTY+BPM SET: {genre_diff_bpm_set}")
        if len(genre_diff_bpm_set) != 1:
            return diff_bpm_set
        else:
            return genre_diff_bpm_set

    def __resolve_genres(self, ocr_genres: OCRGenres) -> set[str]:
        genre_key_set = set([key for key in self.by_genre.keys()])
        en_genre_set = self.__get_lowest_leven_score(ocr_genres.en_genre, genre_key_set)
        jp_genre_set = self.__get_lowest_leven_score(ocr_genres.jp_genre, genre_key_set)
        all_genre_set = en_genre_set.union(jp_genre_set)
        result_set: set[str] = set([])
        for genre in all_genre_set:
            result_set = result_set.union(self.by_genre[genre])
        self.log.debug(f"GENRE RESULT SET: {result_set}")
        return result_set

    def resolve_by_play_metadata(
        self,
        difficulty_tuple: tuple[str, int],
        bpm_tuple: tuple[int, int],
        note_count: Optional[int] = None,
    ) -> set[str]:
        difficulty_set = self.by_difficulty[difficulty_tuple]
        bpm_set = self.by_bpm[bpm_tuple]
        if note_count is not None:
            notes_set = self.by_note_count[note_count]
            found_results = difficulty_set.intersection(bpm_set).intersection(notes_set)
        else:
            found_results = difficulty_set.intersection(bpm_set)
        self.log.debug(f"PLAY METADATA SET: {found_results}")
        return found_results

    def resolve_by_score_metadata(
        self, difficulty: str, level: int, notes: int
    ) -> set[str]:
        found_results = self.by_difficulty_and_notes[(difficulty, level, notes)]
        self.log.debug(f"SCORE METADATA SET: {found_results}")
        return found_results

    def _resolve_artist_ocr(
        self, song_title: OCRSongTitles, found_difficulty_textage_ids: set[str]
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
            self.log.debug(f"Matching artist/difficulty IDs: {matching_ids}")
            if len(matching_ids) == 1:
                found_artist_textage_id = list(matching_ids)[0]
            else:
                self.log.debug("Could not find single song to artist/difficulty.")
        return found_artist_textage_id

    def _resolve_title_ocr(
        self, song_title: OCRSongTitles, found_difficulty_textage_ids: set[str]
    ) -> Optional[str]:
        found_title_textage_id = None
        found_en_title_textage_id = self.by_title.get(song_title.en_title, None)
        found_jp_title_textage_id = self.by_title.get(song_title.jp_title, None)
        self.log.debug(f"found_en_title_textage_id: {found_en_title_textage_id}")
        self.log.debug(f"found_jp_title_textage_id: {found_jp_title_textage_id}")
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
        self, ocr_titles: OCRSongTitles, difficulty: str, level: int
    ) -> Optional[str]:
        difficulty_tuple: tuple[str, int] = (difficulty, level)
        found_difficulty_textage_ids = self.by_difficulty.get(difficulty_tuple, set([]))
        if not found_difficulty_textage_ids:
            self.log.debug(f"Could not lookup difficulty {difficulty_tuple}")
            return None
        found_title_textage_id = self._resolve_title_ocr(
            ocr_titles, found_difficulty_textage_ids
        )

        if found_title_textage_id in found_difficulty_textage_ids:
            self.log.debug(f"found_title_textage_id: {found_title_textage_id}")
            return found_title_textage_id

        found_artist_textage_id = self._resolve_artist_ocr(
            ocr_titles, found_difficulty_textage_ids
        )
        if found_artist_textage_id is not None:
            self.log.debug(f"found_artist_textage_id: {found_artist_textage_id}")
            return found_artist_textage_id

        self.log.warning("Could not resolve OCR-provided artist/song titles directly.")
        return None

    def resolve_ocr_and_metadata(
        self,
        ocr_titles: OCRSongTitles,
        metadata_titles: set[str],
        tiebreak_data: list[tuple[str, str, str, str]],
        difficulty: str,
        level: int,
        ocr_genres: Optional[OCRGenres] = None,
    ) -> Optional[str]:
        textage_id: Optional[str] = None
        resolved_song_id = self.resolve_ocr(ocr_titles, difficulty, level)
        if resolved_song_id:
            textage_id = resolved_song_id
        else:
            if len(metadata_titles) == 1:
                textage_id = next(iter(metadata_titles))
                self.log.debug(f"Using metadata title: {textage_id}")
            elif len(metadata_titles) > 1:
                self.log.warning(
                    f"Found too much metadata, {metadata_titles}, tiebreaking"
                )
                textage_id = self.metadata_lookup_tiebreaker(
                    metadata_titles, tiebreak_data, ocr_titles, ocr_genres
                )
                self.log.warning(f"Tiebreaker found: {textage_id}")
        return textage_id

    def metadata_lookup_tiebreaker(
        self,
        metadata_titles: set[str],
        tiebreak_data: list[tuple[str, str, str, str]],
        ocr_titles: OCRSongTitles,
        ocr_genres: Optional[OCRGenres] = None,
    ) -> Optional[str]:
        """
        Calculates the levenshtein distance on songs that match
        play metadata (note count, difficulty, bpm) versus
        what is provided by our OCR library to determine
        the song title.

        In cases of ties, this raises an exception, indicating
        we have missed some special case or overlap, or that
        OCR is underperforming or outputting garbage.

        https://en.wikipedia.org/wiki/Levenshtein_distance
        """
        lowest_score = -1
        lowest_has_tie = False
        scores = {}
        for textage_id, artist, title, genre in tiebreak_data:
            score = polyleven.levenshtein(ocr_titles.en_artist, artist)
            score += polyleven.levenshtein(ocr_titles.en_title, title)
            score += polyleven.levenshtein(ocr_titles.jp_artist, artist)
            score += polyleven.levenshtein(ocr_titles.jp_title, title)
            if ocr_genres:
                score += polyleven.levenshtein(ocr_genres.en_genre, genre)
                score += polyleven.levenshtein(ocr_genres.jp_genre, genre)
            scores[textage_id] = score

        # We only care about ties for the lowest score
        # so we sort to get the elements in ascending score order
        sorted_scores = {t: scores[t] for t in sorted(scores, key=scores.get)}  # type: ignore
        for textage_id, score in sorted_scores.items():
            if lowest_score != -1 and score == lowest_score:
                lowest_has_tie = True
            if lowest_score == -1 or score < lowest_score:
                lowest_textage_id: Optional[str] = textage_id
                lowest_score = score
        if lowest_has_tie:
            self.log.error(
                "Couldn't tiebreak song title from OCR data and metadata. "
                f"song metadata: {metadata_titles} "
                f"ocr data: {ocr_titles} "
                f"similarity scores: {sorted_scores} "
            )
            lowest_textage_id = None
        return lowest_textage_id

    def __get_lowest_leven_score(
        self, entry: str, values: set[str], lowest_count=1
    ) -> set[str]:
        def __sort(score: tuple[int, str]):
            return score[0]

        scores: list[tuple[int, str]] = []
        for value in values:
            score = polyleven.levenshtein(entry, value)
            score_tuple: tuple[int, str] = (score, value)
            scores.append(score_tuple)
        scores = sorted(scores, key=__sort)
        self.log.debug(f"LOWEST LEVEL SCORES: {scores[0:5]}")
        lowest_count_set = set([score[1] for score in scores[0:lowest_count]])
        return lowest_count_set
