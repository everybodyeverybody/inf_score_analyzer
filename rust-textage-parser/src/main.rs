use regex::Regex;
use reqwest;
use serde_json::Value;
use std::collections::HashMap;
use std::fs;
use std::fs::File;
use std::io::BufRead;
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
    SP_NORMAL = 2, // 2
    SP_HYPER = 3,
    SP_ANOTHER = 4,
    SP_LEGGENDARIA = 5,
    DP_NORMAL = 7,
    DP_HYPER = 8,
    DP_ANOTHER = 9,
    DP_LEGGENDARIA = 10,
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

// TODO: figure out where this should go
#[tokio::main]
async fn download_textage_javascript(http_filename: &str) -> Result<String, reqwest::Error> {
    let textage_base_url = format!("https://textage.cc/score/{}", http_filename);
    println!("downloading from {}", textage_base_url);
    let response = reqwest::get(textage_base_url)
        .await?
        .text_with_charset("Shift_JIS")
        .await?;
    return Ok(response);
}

fn parse_javascript(line: &str, regexes: &Vec<(Regex, String)>, is_list_not_map: &bool) -> String {
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

fn cache_exists_and_is_valid(cache_dir: &str, http_filename: &str) -> bool {
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

fn download_and_parse_textage_javascript(
    js: &TextageJSParser,
    raw_target_path: &PathBuf,
    cached_target_path: &PathBuf,
) -> (PathBuf, PathBuf) {
    let javascript = download_textage_javascript(&js.http_filename).unwrap();
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
            // TODO: there'd normally be a bounds check here but i know this works in python
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
                let special_parsed_line =
                    parse_javascript(&line, &js.file_specific_regexes, &js.is_list_not_map);
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

fn check_textage_metadata_files(js: &TextageJSParser, cache_dir: &String) -> (PathBuf, PathBuf) {
    println!("check textage song metadata files");
    // TODO: make this a config/global
    let raw_cache_ok = cache_exists_and_is_valid(&cache_dir, &js.http_filename);
    let parsed_cache_ok = cache_exists_and_is_valid(&cache_dir, &js.cache_filename);
    let mut raw_cached_filepath = PathBuf::from(cache_dir);
    let mut parsed_cached_filepath = PathBuf::from(cache_dir);
    raw_cached_filepath.push(&js.http_filename);
    parsed_cached_filepath.push(&js.cache_filename);
    if raw_cache_ok && parsed_cache_ok {
        println!("cache ok");
        return (raw_cached_filepath, parsed_cached_filepath);
    } else {
        println!("downloading");
        return download_and_parse_textage_javascript(
            &js,
            &raw_cached_filepath,
            &parsed_cached_filepath,
        );
    }
}

fn setup_config() -> Vec<TextageJSParser> {
    let mut song_and_diff_regexes: Vec<(Regex, String)> = vec![];
    // remove comments from song and difficulty js
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
    // there is a lot of extra html encoded in the song titles
    // so we strip all of it with these
    // TODO: set all the replace characters on these
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
    // TODO: have this unwrap the substream version from this text without needing json
    version_title_regexes.push((Regex::new(r"vertbl\[35\]=").unwrap(), String::from(",")));

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

fn match_title(title: Option<&Value>) -> Option<String> {
    match title {
        Some(_) => Some(String::from(title.unwrap().clone().as_str().unwrap())),
        None => None,
    }
}

fn check_song_suboptions(
    song_levels: &Vec<i8>,
    cs_levels: Option<&Vec<i8>>,
    difficulty_type: Difficulty,
) -> i8 {
    // textage has known magic bitfields in its url
    // i am not reversing those so we take the "ALL" query parameter
    // and derive the url generation strings from parts of it
    //
    // This does include the query separator
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

fn match_difficulty(
    song_levels: &Vec<i8>,
    cs_levels: Option<&Vec<i8>>,
    difficulty_type: Difficulty,
) -> Option<String> {
    let mut difficulty_type_url: Option<String> = None;
    let difficulty_level = check_song_suboptions(song_levels, cs_levels, difficulty_type);
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
            Difficulty::SP_NORMAL => Some(String::from(format!("N{}", level_url.unwrap()))),
            Difficulty::SP_HYPER => Some(String::from(format!("H{}", level_url.unwrap()))),
            Difficulty::SP_ANOTHER => Some(String::from(format!("A{}", level_url.unwrap()))),
            Difficulty::SP_LEGGENDARIA => Some(String::from(format!("X{}", level_url.unwrap()))),
            Difficulty::DP_NORMAL => Some(String::from(format!("N{}", level_url.unwrap()))),
            Difficulty::DP_HYPER => Some(String::from(format!("H{}", level_url.unwrap()))),
            Difficulty::DP_ANOTHER => Some(String::from(format!("A{}", level_url.unwrap()))),
            Difficulty::DP_LEGGENDARIA => Some(String::from(format!("X{}", level_url.unwrap()))),
        }
    }
    return difficulty_type_url;
}

fn merge_data(
    titles: &HashMap<String, Vec<Value>>,
    difficulties: &HashMap<String, Vec<i8>>,
    cs_rerated_difficulties: &HashMap<String, Vec<i8>>,
) -> HashMap<String, SongChartUrlMetadata> {
    // TODO: write a function in the parser that extends the array in the textage way
    // and finds the substream index
    let substream_index = "35";
    // textage.cc/score/scrlist.js lines 308-312
    //
    let mut song_metadata: HashMap<String, SongChartUrlMetadata> = HashMap::new();

    for (textage_id, title_info) in titles {
        if textage_id == "__dmy__" {
            continue;
        }

        let title: String;
        let title_prefix = match_title(title_info.get(5));
        let title_suffix = match_title(title_info.get(6));
        if title_suffix != None {
            title = [title_prefix.unwrap(), title_suffix.unwrap()].join(" ");
        } else {
            title = title_prefix.unwrap();
        }
        let mut version_id_url = format!("{}", title_info[0].clone().as_i64().unwrap());
        if version_id_url == substream_index {
            version_id_url = String::from("s");
        }
        let found_song_levels = difficulties.get(textage_id);
        if found_song_levels == None {
            continue;
        }
        let found_cs_levels = cs_rerated_difficulties.get(textage_id);
        let song_levels = found_song_levels.unwrap();
        let song = SongChartUrlMetadata {
            textage_id: textage_id.to_string(),
            version_id_url: version_id_url,
            sp_normal: match_difficulty(song_levels, found_cs_levels, Difficulty::SP_NORMAL),
            sp_hyper: match_difficulty(song_levels, found_cs_levels, Difficulty::SP_HYPER),
            sp_another: match_difficulty(song_levels, found_cs_levels, Difficulty::SP_ANOTHER),
            sp_leggendaria: match_difficulty(
                song_levels,
                found_cs_levels,
                Difficulty::SP_LEGGENDARIA,
            ),
            dp_normal: match_difficulty(song_levels, found_cs_levels, Difficulty::DP_NORMAL),
            dp_hyper: match_difficulty(song_levels, found_cs_levels, Difficulty::DP_HYPER),
            dp_another: match_difficulty(song_levels, found_cs_levels, Difficulty::DP_ANOTHER),
            dp_leggendaria: match_difficulty(
                song_levels,
                found_cs_levels,
                Difficulty::DP_LEGGENDARIA,
            ),
        };
        song_metadata.insert(title, song);
    }

    return song_metadata;
}

fn deserialize_textage_data() -> HashMap<String, SongChartUrlMetadata> {
    let js_config = setup_config();
    let cache_dir = String::from("./textage-data");
    let mut difficulties: HashMap<String, Vec<i8>> = HashMap::new();
    let mut cs_rerated_difficulties: HashMap<String, Vec<i8>> = HashMap::new();
    let mut titles: HashMap<String, Vec<Value>> = HashMap::new();
    let mut versions: Vec<String> = vec![];
    for config in &js_config {
        let (raw_file, parsed_file) = check_textage_metadata_files(&config, &cache_dir);
        println!("Serializing {:?}", parsed_file);
        let filehandle = File::open(&parsed_file).unwrap();
        let reader = BufReader::new(&filehandle);
        match config.js_type {
            TextageJSType::Difficulties => {
                difficulties = serde_json::from_reader(reader).unwrap();
            }
            TextageJSType::Versions => {
                versions = serde_json::from_reader(reader).unwrap();
            }
            TextageJSType::Titles => {
                titles = serde_json::from_reader(reader).unwrap();
            }
            TextageJSType::CsReratedDifficulties => {
                cs_rerated_difficulties = serde_json::from_reader(reader).unwrap();
            }
        }
    }
    return merge_data(&titles, &difficulties, &cs_rerated_difficulties);
}

fn generate_url(song: &SongChartUrlMetadata, side: String, difficulty: String) -> Option<String> {
    let mut found_difficulty: Option<String> = None;
    if difficulty == "NORMAL" {
        if side == "DP" {
            found_difficulty = song.dp_normal.clone();
        } else {
            found_difficulty = song.sp_normal.clone();
        }
    } else if difficulty == "HYPER" {
        if side == "DP" {
            found_difficulty = song.dp_hyper.clone();
        } else {
            found_difficulty = song.sp_hyper.clone();
        }
    } else if difficulty == "ANOTHER" {
        if side == "DP" {
            found_difficulty = song.dp_another.clone();
        } else {
            found_difficulty = song.sp_another.clone();
        }
    } else if difficulty == "LEGGENDARIA" {
        if side == "DP" {
            found_difficulty = song.dp_leggendaria.clone();
        } else {
            found_difficulty = song.sp_leggendaria.clone();
        }
    }

    match found_difficulty {
        None => None,
        Some(_) => {
            let diff = found_difficulty.unwrap();
            let url_base = "http://textage.cc/score";
            let side_prefix: String;
            if side == "DP" {
                side_prefix = String::from("D");
            } else if side == "2P" {
                side_prefix = String::from("2");
            } else {
                side_prefix = String::from("1");
            }
            let param = format!("{}{}00", side_prefix, diff);
            let thing = format!(
                "{}/{}/{}.html?{}",
                url_base, song.version_id_url, song.textage_id, param
            );
            Some(thing)
        }
    }
}

fn main() {
    // TODO: songs like 1989 do not use a difficulty parameter so have to figure out those urls
    let song_data = deserialize_textage_data();
    let url = generate_url(
        song_data.get("1989").unwrap(),
        String::from("1P"),
        String::from("NORMAL"),
    );
    println!("{}", url.unwrap());
    let url = generate_url(
        song_data.get("2002").unwrap(),
        String::from("1P"),
        String::from("NORMAL"),
    );
    println!("{}", url.unwrap());
    // should throw a panic
    let url = generate_url(
        song_data.get("Shake").unwrap(),
        String::from("1P"),
        String::from("NORMAL"),
    );
    println!("{}", url.unwrap());
}
