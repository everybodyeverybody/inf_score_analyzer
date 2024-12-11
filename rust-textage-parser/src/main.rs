use regex::Regex;
use reqwest;
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::fs::File;
use std::io::BufReader;
use std::path::PathBuf;
use std::time::SystemTime;

#[derive(Debug)]
enum TextageJSType {
    Difficulties,
    Versions,
    Titles,
    CsReratedDifficulties,
}

#[derive(Debug, Clone, Copy)]
enum Difficulty {
    SPNormal = 2, // 2
    SPHyper = 3,
    SPAnother = 4,
    SPLeggendaria = 5,
    DPNormal = 7,
    DPHyper = 8,
    DPAnother = 9,
    DPLeggendaria = 10,
}

#[derive(Debug)]
enum Side {
    LeftSide,
    RightSide,
    Double,
}

#[derive(Debug)]
struct TextageJSParser {
    http_filename: String,
    cache_filename: String,
    start_regex: Regex,
    end_regex: Regex,
    file_specific_regexes: Vec<(Regex, String)>,
    is_list_not_map: bool,
    js_type: TextageJSType,
}

#[derive(Debug)]
struct SongChartUrlMetadata {
    textage_id: String,
    textage_version_id: usize,
    version_name: String,
    version_id_url: String,
    sp_normal: Option<String>,
    sp_hyper: Option<String>,
    sp_another: Option<String>,
    sp_leggendaria: Option<String>,
    dp_normal: Option<String>,
    dp_hyper: Option<String>,
    dp_another: Option<String>,
    dp_leggendaria: Option<String>,
}

#[derive(Debug)]
struct TextageChartSearch {
    url_metadata: HashMap<String, SongChartUrlMetadata>,
}
impl TextageChartSearch {
    // I originally wrote this as a standalone application
    // that parsed from the commandline and refactored it into
    // a class so it can be more easily used by other parts
    // of this codebase.
    //
    // All of the application specific methods are private, and we provide
    // an API for creating new instances of this lookup, and for searching this
    // struct's key-value store based on more natural-language seeming queries.
    pub fn new() -> Self {
        // Static constructor
        let mut new_one = Self {
            url_metadata: HashMap::new(),
        };
        new_one.url_metadata = new_one.deserialize_textage_data();
        return new_one;
    }

    pub fn refresh(mut self) {
        // Update url_metadata in place. This method may not
        // be useful and instead you want to overwrite with new().
        self.url_metadata = self.deserialize_textage_data();
    }

    pub fn find(&self, query_string: String) -> String {
        // Take an input string that seems like a natural language query
        // and return the URL for the chart based on the parameters.
        //
        // If any lookups fail, provide an error string that attempts
        // to explain what went wrong.
        let query_parameters = self.parse_find_query(&query_string);
        let response = match query_parameters {
            Some((title, difficulty, side)) => {
                // TODO: have this use fuzzy matching
                let song_metadata = self.url_metadata.get(&title);
                let matched_return_string = match song_metadata {
                    Some(song_metadata) => {
                        let matched_url = self.generate_url(song_metadata, difficulty, side);
                        let url = match matched_url {
                            Some(url) => url,
                            None => format!("No chart available for '{}'", query_string),
                        };
                        url
                    }
                    None => format!(
                        "Could not find matching textage title for song title '{}'",
                        title
                    ),
                };
                matched_return_string
            }
            None => format!("Could not parse request as query '{}'", query_string),
        };
        return response;
    }

    pub(self) fn parse_find_query(
        &self,
        query_string: &String,
    ) -> Option<(String, Difficulty, Side)> {
        // Use regexes to parse natural seeming language queries.
        //
        // We expect a format like the following:
        // !command <song title> <optional difficulty> <optional side/dp>
        //
        // Defaults to parsing the query as <song title> ANOTHER 1P
        let parser = Regex::new(
            r"^\s*(?<title>.*?)\s*(?i)(?<difficulty>NORMAL|HYPER|ANOTHER|LEGGENDARIA|N|H|A|L|LEGG)?\s*(?<side>1P|2P|DP|SP)?\s*$",
        )
        .unwrap();
        if !parser.is_match(query_string) {
            return None;
        }

        let matched_groups = parser.captures(query_string);
        if matched_groups.is_none() {
            return None;
        }
        let song_data = matched_groups.unwrap();
        let mut side: Side = Side::LeftSide;
        let mut is_sp: bool = true;
        let mut difficulty: Difficulty = Difficulty::SPAnother;
        let title = String::from(song_data.name("title").unwrap().as_str());
        side = match song_data.name("side") {
            Some(side) => {
                let uc = side.as_str().to_uppercase();
                match uc.as_str() {
                    "1P" => Side::LeftSide,
                    "2P" => Side::RightSide,
                    "SP" => Side::RightSide,
                    "DP" => Side::Double,
                    _ => Side::LeftSide,
                }
            }
            _ => side,
        };

        is_sp = match song_data.name("side") {
            Some(side) => {
                let uc = side.as_str().to_uppercase();
                match uc.as_str() {
                    "1P" => true,
                    "2P" => true,
                    "SP" => true,
                    "DP" => false,
                    _ => true,
                }
            }
            _ => is_sp,
        };

        difficulty = match song_data.name("difficulty") {
            Some(diff) => {
                let uc = diff.as_str().to_uppercase();
                match uc.as_str() {
                    "NORMAL" | "N" => {
                        if is_sp {
                            Difficulty::SPNormal
                        } else {
                            Difficulty::DPNormal
                        }
                    }
                    "HYPER" | "H" => {
                        if is_sp {
                            Difficulty::SPHyper
                        } else {
                            Difficulty::DPHyper
                        }
                    }
                    "ANOTHER" | "A" => {
                        if is_sp {
                            Difficulty::SPAnother
                        } else {
                            Difficulty::DPAnother
                        }
                    }
                    "LEGGENDARIA" | "L" | "LEGG" => {
                        if is_sp {
                            Difficulty::SPLeggendaria
                        } else {
                            Difficulty::DPLeggendaria
                        }
                    }
                    _ => Difficulty::SPAnother,
                }
            }
            _ => difficulty,
        };
        return Some((title, difficulty, side));
    }

    pub(self) fn deserialize_textage_data(&self) -> HashMap<String, SongChartUrlMetadata> {
        // All of the work is done here.
        // We first read in our file and parser configuration, then
        // check for any locally cached data and redownload if necessary.
        // We then apply each parser to each downloaded or cached file,
        // and load it into a hashmap for later lookups via our API methods.
        let js_config = self.setup_config();
        let cache_dir = String::from("./textage-data");
        let mut difficulties: HashMap<String, Vec<i8>> = HashMap::new();
        let mut cs_rerated_difficulties: HashMap<String, Vec<i8>> = HashMap::new();
        let mut titles: HashMap<String, Vec<Value>> = HashMap::new();
        let mut versions: Vec<String> = vec![];
        let mut substream_offset: usize = 0;
        for config in &js_config {
            let (raw_file, parsed_file) = self.check_textage_metadata_files(&config, &cache_dir);
            println!("Serializing {:?}", parsed_file);
            let filehandle = File::open(&parsed_file).unwrap();
            let reader = BufReader::new(&filehandle);
            match config.js_type {
                TextageJSType::Difficulties => {
                    difficulties = serde_json::from_reader(reader).unwrap();
                }
                TextageJSType::Versions => {
                    versions = serde_json::from_reader(reader).unwrap();
                    println!("Serializing {:?}", raw_file);
                    (substream_offset, versions) = self.get_version_offset(&raw_file, &versions);
                }
                TextageJSType::Titles => {
                    titles = serde_json::from_reader(reader).unwrap();
                }
                TextageJSType::CsReratedDifficulties => {
                    cs_rerated_difficulties = serde_json::from_reader(reader).unwrap();
                }
            }
        }
        return self.merge_data(
            &titles,
            &difficulties,
            &cs_rerated_difficulties,
            &versions,
            substream_offset,
        );
    }

    pub(self) fn setup_config(&self) -> Vec<TextageJSParser> {
        // Configures collections of regexes to be run in order
        // against the textage JS data. Only run on initialization or refreshes.
        //
        // Both python and rust's json
        // parsers choke on different components of their JS, so the
        // intent is to transform the JS into standard JSON blobs,
        // then perform textage-derived logic on the data to generate our list.
        let mut song_and_diff_regexes: Vec<(Regex, String)> = vec![];
        // Replace hex bitfields with their numeric equivalents
        song_and_diff_regexes.push((Regex::new("A").unwrap(), String::from("10")));
        song_and_diff_regexes.push((Regex::new("B").unwrap(), String::from("11")));
        song_and_diff_regexes.push((Regex::new("C").unwrap(), String::from("12")));
        song_and_diff_regexes.push((Regex::new("D").unwrap(), String::from("13")));
        song_and_diff_regexes.push((Regex::new("E").unwrap(), String::from("14")));
        song_and_diff_regexes.push((Regex::new("F").unwrap(), String::from("15")));
        // there are comment strings with ids inside the json, remove them
        song_and_diff_regexes.push((Regex::new(r#"//\d+"#).unwrap(), String::from("")));
        // there are quoted strings as the last entry in the difficulty array, convert them to
        // -1 since we don't use them
        song_and_diff_regexes.push((Regex::new(r#"".*"]"#).unwrap(), String::from("-1]")));
        // remove html from song and difficulty js
        song_and_diff_regexes.push((Regex::new(",\"<span.*span>\"").unwrap(), String::from("")));

        let mut song_title_regexes: Vec<(Regex, String)> = vec![];
        // there is a lot of extra html encoded in the song titles that needs to be stripped
        song_title_regexes.push((Regex::new(r".fontcolor\(.*?\)").unwrap(), String::from("")));
        song_title_regexes.push((Regex::new("<span style='.*?'>").unwrap(), String::from("")));
        song_title_regexes.push((Regex::new(r"<\\/span>").unwrap(), String::from("")));
        song_title_regexes.push((Regex::new(r"<div class=.*?>").unwrap(), String::from("")));
        song_title_regexes.push((Regex::new(r"<\\/div>").unwrap(), String::from("")));
        song_title_regexes.push((Regex::new(r"<br>").unwrap(), String::from("")));
        song_title_regexes.push((Regex::new(r"<b>").unwrap(), String::from("")));
        song_title_regexes.push((Regex::new(r"<\\/b>").unwrap(), String::from("")));
        song_title_regexes.push((Regex::new(r"^\[SS").unwrap(), String::from("[-1")));
        song_title_regexes.push((Regex::new(r"\t").unwrap(), String::from("")));

        let mut version_title_regexes: Vec<(Regex, String)> = vec![];
        // we're pulling a list thats declared as a js array, remove the semicolon
        version_title_regexes.push((Regex::new(";").unwrap(), String::from("")));
        version_title_regexes.push((Regex::new("]$").unwrap(), String::from("")));
        version_title_regexes.push((Regex::new(r"vertbl\[35\]=").unwrap(), String::from(",")));

        // We then compile each list of regexes into a parser that chooses
        // when to apply the regexes. We note the textage filename, and what
        // we want it cached as locally. Each parser only applies the regexes between
        // a start regex and and end regex.
        //
        // We also note what kind of type we expect to extract from the JSON,
        // and assign this an enum type to use with a match block for assignment.
        let song_difficulty_and_version_js = TextageJSParser {
            http_filename: String::from("actbl.js"),
            cache_filename: String::from("actbl.js.parsed.json"),
            start_regex: Regex::new(r"^\s*actbl=(\{).*$").unwrap(),
            end_regex: Regex::new(r"\s*}\s*;\s*").unwrap(),
            file_specific_regexes: song_and_diff_regexes.clone(),
            is_list_not_map: false,
            js_type: TextageJSType::Difficulties,
        };

        let version_index_js = TextageJSParser {
            http_filename: String::from("scrlist.js"),
            cache_filename: String::from("scrlist.js.parsed.json"),
            start_regex: Regex::new(r"^vertbl\s*=\s*(\[)(.*)$").unwrap(),
            end_regex: Regex::new(r"^\s*$").unwrap(),
            file_specific_regexes: version_title_regexes,
            is_list_not_map: true,
            js_type: TextageJSType::Versions,
        };

        let song_titles_js = TextageJSParser {
            http_filename: String::from("titletbl.js"),
            cache_filename: String::from("titletbl.js.parsed.json"),
            start_regex: Regex::new(r"^\s*titletbl=(\{).*$").unwrap(),
            end_regex: Regex::new(r"\s*}\s*;\s*").unwrap(),
            file_specific_regexes: song_title_regexes,
            is_list_not_map: false,
            js_type: TextageJSType::Titles,
        };

        let rerated_js = TextageJSParser {
            http_filename: String::from("cstbl1.js"),
            cache_filename: String::from("cstbl1.js.parsed.json"),
            start_regex: Regex::new(r"^\s*cstbl\[7\]=(\{).*$").unwrap(),
            end_regex: Regex::new(r"\s*}\s*;\s*").unwrap(),
            file_specific_regexes: song_and_diff_regexes.clone(),
            is_list_not_map: false,
            js_type: TextageJSType::CsReratedDifficulties,
        };

        let mut v: Vec<TextageJSParser> = Vec::new();
        v.push(song_difficulty_and_version_js);
        v.push(version_index_js);
        v.push(song_titles_js);
        v.push(rerated_js);
        return v;
    }

    #[tokio::main]
    pub(self) async fn download_textage_javascript(
        &self,
        http_filename: &str,
    ) -> Result<String, reqwest::Error> {
        // Downloads the javascript metadata files from textage for parsing.
        //
        // I have generally shyed away from using async stuff in other
        // languages I've used, prefering threads or interprocess communication,
        // so this may be bad. This is the code I am least confident about in
        // this entire stack.
        let textage_base_url = format!("https://textage.cc/score/{}", http_filename);
        println!("downloading from {}", textage_base_url);
        let response = reqwest::get(textage_base_url)
            .await?
            .text_with_charset("Shift_JIS")
            .await?;
        return Ok(response);
    }

    pub(self) fn parse_javascript(
        &self,
        line: &str,
        regexes: &Vec<(Regex, String)>,
        is_list_not_map: &bool,
    ) -> String {
        // Transforms textage javascript files into JSON with no other inline code.
        //
        // This is not general purpose. The transforms are unique to each file and
        // dependent on each file's specific regexes.
        if !is_list_not_map {
            let (key, mut values) = line.split_once(":").unwrap();
            let key = key.trim().replace("'", "\"");
            values = values.trim();
            let mut cleaned_line = String::from(values);
            for (regex, replacement_string) in regexes {
                cleaned_line = regex
                    .replace_all(&cleaned_line, replacement_string)
                    .to_string();
            }
            return format!("{}:{}", key, cleaned_line);
        } else {
            let mut cleaned_line = String::from(line.trim());
            for (regex, replacement_string) in regexes {
                cleaned_line = regex
                    .replace_all(&cleaned_line, replacement_string)
                    .to_string();
            }
            return cleaned_line;
        }
    }

    pub(self) fn cache_exists_and_is_valid(&self, cache_dir: &str, http_filename: &str) -> bool {
        // Check if the on disk cash should be updated. We don't want to spam
        // textage with requests, nor do we want to frequently block the bot with
        // requests that are set to await on refresh, so we use a cache on reload if its availble
        // or if it has been less than 2 days since the last cache update. Otherwise we redownload
        // and update the cache.
        let cache_dir = PathBuf::from(cache_dir);
        let max_cache_age: f32 = 86400.0 * 2.0;
        if !std::fs::exists(cache_dir.as_path()).unwrap() {
            _ = std::fs::create_dir_all(cache_dir.as_path());
            return false;
        }
        let mut cache_file = PathBuf::new();
        cache_file.push(cache_dir);
        cache_file.push(http_filename);
        let cache_exists = std::fs::exists(cache_file.as_path()).unwrap();
        if !cache_exists {
            return false;
        }

        let now = SystemTime::now();
        let cache_time = std::fs::metadata(cache_file.as_path())
            .unwrap()
            .modified()
            .unwrap();
        let cache_age = now.duration_since(cache_time).unwrap().as_secs_f32();
        if cache_age < max_cache_age {
            return true;
        }
        return false;
    }

    pub(self) fn download_and_parse_textage_javascript(
        &self,
        js: &TextageJSParser,
        raw_target_path: &PathBuf,
        cached_target_path: &PathBuf,
    ) -> (PathBuf, PathBuf) {
        // Download and transforms the textage javascript into JSON in our cache dir.
        let javascript = self.download_textage_javascript(&js.http_filename).unwrap();
        let lines = javascript.lines();
        let mut capture_output = false;
        let mut valid_data: Vec<String> = Vec::new();
        let mut raw_data: Vec<String> = Vec::new();
        let mut start_char = String::from("");
        let skip_blanks = Regex::new(r"^\s*$").unwrap();
        let skip_comments = Regex::new(r"^//.*").unwrap();

        for line in lines {
            raw_data.push(String::from(line));
            if js.start_regex.is_match(line) {
                capture_output = true;
                let match_groups = js.start_regex.captures(line).unwrap();
                start_char = String::from(match_groups.get(1).unwrap().as_str());
                valid_data.push(start_char.clone());
                valid_data.push(String::from("\n"));
                if match_groups.len() == 3 {
                    valid_data.push(String::from(match_groups.get(2).unwrap().as_str()));
                }
                continue;
            }
            if capture_output {
                if js.end_regex.is_match(line) {
                    let mut end_char = String::from("");
                    if start_char == "{" {
                        end_char = String::from("}");
                    } else if start_char == "[" {
                        end_char = String::from("]");
                    }
                    valid_data.push(end_char);
                    println!("{} stopping at {}", js.http_filename, line);
                    break;
                } else {
                    if skip_comments.is_match(line) || skip_blanks.is_match(line) {
                        continue;
                    }
                    let special_parsed_line = self.parse_javascript(
                        &line,
                        &js.file_specific_regexes,
                        &js.is_list_not_map,
                    );
                    valid_data.push(special_parsed_line);
                }
            }
        }
        let raw_data_w_newlines = raw_data.join("\n");
        let valid_data_w_newlines = valid_data.join("\n");
        _ = File::create(&raw_target_path).unwrap();
        _ = File::create(&cached_target_path).unwrap();
        fs::write(&raw_target_path, raw_data_w_newlines).expect("");
        fs::write(&cached_target_path, valid_data_w_newlines).expect("");
        let mut raw_return_path = PathBuf::new();
        let mut cached_return_path = PathBuf::new();
        raw_return_path.push(&raw_target_path);
        cached_return_path.push(&cached_target_path);
        return (raw_return_path, cached_return_path);
    }

    pub(self) fn check_textage_metadata_files(
        &self,
        js: &TextageJSParser,
        cache_dir: &String,
    ) -> (PathBuf, PathBuf) {
        // Check the existence of our cache and verify they both exist and are valid
        //
        // If valid, read the data from disk. If they're not, redownload the data from textage.
        // TODO: have this maybe have a force update flag
        println!("check textage song metadata files");
        let raw_cache_ok = self.cache_exists_and_is_valid(&cache_dir, &js.http_filename);
        let parsed_cache_ok = self.cache_exists_and_is_valid(&cache_dir, &js.cache_filename);
        let mut raw_cached_filepath = PathBuf::from(cache_dir);
        let mut parsed_cached_filepath = PathBuf::from(cache_dir);
        raw_cached_filepath.push(&js.http_filename);
        parsed_cached_filepath.push(&js.cache_filename);
        if raw_cache_ok && parsed_cache_ok {
            println!("cache ok");
            return (raw_cached_filepath, parsed_cached_filepath);
        } else {
            println!("downloading");
            return self.download_and_parse_textage_javascript(
                &js,
                &raw_cached_filepath,
                &parsed_cached_filepath,
            );
        }
    }

    pub(self) fn match_title(&self, title: Option<&Value>) -> Option<String> {
        // Helper method for unwrapping regex matches into strings.
        match title {
            Some(_) => Some(String::from(title.unwrap().clone().as_str().unwrap())),
            None => None,
        }
    }

    pub(self) fn match_difficulty(
        &self,
        song_levels: &Vec<i8>,
        cs_levels: Option<&Vec<i8>>,
        difficulty_type: Difficulty,
    ) -> Option<String> {
        // Generates the difficulty part of the URL query string depending on the queried
        // difficulty type and the song's own metadata.
        let mut difficulty_type_url: Option<String> = None;
        let difficulty_level = self.check_song_suboptions(song_levels, cs_levels, difficulty_type);
        let level_url = match difficulty_level {
            i8::MIN..=-1 => None,
            n @ 0..=9 => Some(String::from(format!("{}", n))),
            10 => Some(String::from("A")),
            11 => Some(String::from("B")),
            12 => Some(String::from("C")),
            13..=i8::MAX => None,
        };

        if level_url != None {
            difficulty_type_url = match difficulty_type {
                Difficulty::SPNormal => Some(String::from(format!("N{}", level_url.unwrap()))),
                Difficulty::SPHyper => Some(String::from(format!("H{}", level_url.unwrap()))),
                Difficulty::SPAnother => Some(String::from(format!("A{}", level_url.unwrap()))),
                Difficulty::SPLeggendaria => Some(String::from(format!("X{}", level_url.unwrap()))),
                Difficulty::DPNormal => Some(String::from(format!("N{}", level_url.unwrap()))),
                Difficulty::DPHyper => Some(String::from(format!("H{}", level_url.unwrap()))),
                Difficulty::DPAnother => Some(String::from(format!("A{}", level_url.unwrap()))),
                Difficulty::DPLeggendaria => Some(String::from(format!("X{}", level_url.unwrap()))),
            }
        }
        return difficulty_type_url;
    }

    pub(self) fn check_song_suboptions(
        &self,
        song_levels: &Vec<i8>,
        cs_levels: Option<&Vec<i8>>,
        difficulty_type: Difficulty,
    ) -> i8 {
        // textage uses a lot of bit masking for generating its URLs. We only care
        // about getting links to charts, so we apply only the masks we need to get
        // the default chart layout and data. These song suboptions indicate
        // attributes of whether or not the song was rerated post-happy sky or in a CS
        // release. Songs that are not rerated will typically have a difficulty bit of 0,
        // implying that its old rating is no longer valid.
        let all_songs_query = String::from("?a011B000");
        let difficulty_usize = difficulty_type as usize;
        let options_index = difficulty_usize * 2 + 2;
        let difficulty_index = difficulty_usize * 2 + 1;
        let textage_option_one = all_songs_query
            .chars()
            .nth(7)
            .unwrap()
            .to_digit(10)
            .unwrap() as usize;
        let textage_option_two = all_songs_query
            .chars()
            .nth(3)
            .unwrap()
            .to_digit(16)
            .unwrap() as usize
            & 8;
        let options_value: i8;
        let difficulty_value: i8;
        if textage_option_one > 0
            && textage_option_two > 0
            && (2 <= difficulty_usize && difficulty_usize <= 4
                || 7 <= difficulty_usize && difficulty_usize <= 9)
        {
            options_value = match cs_levels {
                Some(_) => cs_levels.unwrap()[options_index],
                None => song_levels[options_index],
            };
            difficulty_value = match cs_levels {
                Some(_) => cs_levels.unwrap()[difficulty_index],
                None => song_levels[difficulty_index],
            }
        } else {
            options_value = song_levels[options_index];
            difficulty_value = song_levels[difficulty_index];
        }
        let cs_only_or_never_rerated: bool = options_value & 2 > 0;
        if difficulty_value <= 0 {
            return -1;
        }

        if !cs_only_or_never_rerated {
            return 0;
        }

        return difficulty_value;
    }

    pub(self) fn merge_data(
        &self,
        titles: &HashMap<String, Vec<Value>>,
        difficulties: &HashMap<String, Vec<i8>>,
        cs_rerated_difficulties: &HashMap<String, Vec<i8>>,
        versions: &Vec<String>,
        substream_index: usize,
    ) -> HashMap<String, SongChartUrlMetadata> {
        // Combines all the song metadata and generated url metadata
        // into a hashmap from which URLs can be derived. This can
        // also be used for other things but we only care about generating
        // URLs as far as this goes.
        //
        // textage.cc/score/scrlist.js lines 308-312
        let mut song_metadata: HashMap<String, SongChartUrlMetadata> = HashMap::new();

        for (textage_id, title_info) in titles {
            if textage_id == "__dmy__" {
                continue;
            }

            let title: String;
            let title_prefix = self.match_title(title_info.get(5));
            let title_suffix = self.match_title(title_info.get(6));
            if title_suffix != None {
                title = [title_prefix.unwrap(), title_suffix.unwrap()].join(" ");
            } else {
                title = title_prefix.unwrap();
            }
            let textage_version_id: i64 = title_info[0].clone().as_i64().unwrap();
            let mut textage_version_index: usize = textage_version_id as usize;
            if textage_version_id == -1 {
                textage_version_index = substream_index;
            }
            let version_id_url: String;
            if textage_version_index == substream_index {
                version_id_url = String::from("s");
            } else {
                version_id_url = format!("{}", textage_version_id);
            }
            let found_song_levels = difficulties.get(textage_id);
            if found_song_levels == None {
                continue;
            }
            let found_cs_levels = cs_rerated_difficulties.get(textage_id);
            let song_levels = found_song_levels.unwrap();
            let song = SongChartUrlMetadata {
                textage_id: textage_id.to_string(),
                textage_version_id: textage_version_index,
                version_name: versions[textage_version_index].clone(),
                version_id_url: version_id_url,
                sp_normal: self.match_difficulty(
                    song_levels,
                    found_cs_levels,
                    Difficulty::SPNormal,
                ),
                sp_hyper: self.match_difficulty(song_levels, found_cs_levels, Difficulty::SPHyper),
                sp_another: self.match_difficulty(
                    song_levels,
                    found_cs_levels,
                    Difficulty::SPAnother,
                ),
                sp_leggendaria: self.match_difficulty(
                    song_levels,
                    found_cs_levels,
                    Difficulty::SPLeggendaria,
                ),
                dp_normal: self.match_difficulty(
                    song_levels,
                    found_cs_levels,
                    Difficulty::DPNormal,
                ),
                dp_hyper: self.match_difficulty(song_levels, found_cs_levels, Difficulty::DPHyper),
                dp_another: self.match_difficulty(
                    song_levels,
                    found_cs_levels,
                    Difficulty::DPAnother,
                ),
                dp_leggendaria: self.match_difficulty(
                    song_levels,
                    found_cs_levels,
                    Difficulty::DPLeggendaria,
                ),
            };
            song_metadata.insert(title, song);
        }

        return song_metadata;
    }

    pub(self) fn get_version_offset(
        &self,
        raw_versions_file: &PathBuf,
        versions: &Vec<String>,
    ) -> (usize, Vec<String>) {
        // textage keeps track of iidx substream's index as a sentinel value in this array
        // and does text comparison to get it, we extract it via regex and provide
        // a vec similar to the js array it provides
        let raw_versions_data = std::fs::read_to_string(raw_versions_file).unwrap();
        let regex = Regex::new(r"^vertbl\[(\d+)\]=.*").unwrap();
        let mut new_vec: Vec<String> = Vec::new();
        let mut substream_index: usize = 0;
        for line in raw_versions_data.lines() {
            if regex.is_match(line) {
                substream_index = regex
                    .captures(line)
                    .unwrap()
                    .get(1)
                    .unwrap()
                    .as_str()
                    .parse::<usize>()
                    .unwrap();
                new_vec = Vec::with_capacity(substream_index);
                for value in versions.iter() {
                    if value == "substream" {
                        continue;
                    }
                    new_vec.push(String::from(value));
                }
                while new_vec.len() < substream_index {
                    new_vec.push(String::from(""));
                }
                new_vec.push(String::from("substream"));
            }
        }
        return (substream_index, new_vec);
    }

    pub(self) fn generate_url(
        &self,
        song: &SongChartUrlMetadata,
        difficulty: Difficulty,
        side: Side,
    ) -> Option<String> {
        // Generates a textage URL based on its javascript logic
        // from a given song title, difficulty (SP or DP), and play side
        // if necessary.
        //
        // Returns None if there is not a chart for a given parameter set
        // (ex. the safari Another DP, Dynamite Rave Leggendaria).
        //
        // We ignore beginner charts.
        let found_difficulty: Option<String>;

        found_difficulty = match difficulty {
            Difficulty::SPNormal => song.sp_normal.clone(),
            Difficulty::DPNormal => song.dp_normal.clone(),
            Difficulty::SPHyper => song.sp_hyper.clone(),
            Difficulty::DPHyper => song.dp_hyper.clone(),
            Difficulty::SPAnother => song.sp_another.clone(),
            Difficulty::DPAnother => song.dp_another.clone(),
            Difficulty::SPLeggendaria => song.sp_leggendaria.clone(),
            Difficulty::DPLeggendaria => song.dp_leggendaria.clone(),
        };

        match found_difficulty {
            None => None,
            Some(_) => {
                let diff = found_difficulty.unwrap();
                let url_base = "http://textage.cc/score";
                let side_prefix = match side {
                    Side::Double => String::from("D"),
                    Side::RightSide => String::from("2"),
                    Side::LeftSide => String::from("1"),
                };

                let param = format!("{}{}00", side_prefix, diff);
                let thing = format!(
                    "{}/{}/{}.html?{}",
                    url_base, song.version_id_url, song.textage_id, param
                );
                Some(thing)
            }
        }
    }
}

fn main() {
    let song_search = TextageChartSearch::new();
    println!("{}", song_search.find(String::from("1989")));
    println!("{}", song_search.find(String::from("1989 ANOTHER")));
    println!("{}", song_search.find(String::from("1989 Another")));
    println!("{}", song_search.find(String::from("1989 Another 1P")));
    println!("{}", song_search.find(String::from("1989 hyper DP")));
}
