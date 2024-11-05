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
    //println!(
    //    "now {:?} cache time {:?} age {:?}",
    //    now, cache_time, cache_age
    //);
    if cache_age < max_cache_age {
        return true;
    }
    return false;
}

fn download_and_parse_textage_javascript(js: &TextageJSParser, target_path: &PathBuf) -> PathBuf {
    println!("download and parse");
    let javascript = download_textage_javascript(&js.http_filename).unwrap();
    let lines = javascript.lines();
    let mut capture_output = false;
    let mut valid_data: Vec<String> = Vec::new();
    let mut start_char = String::from("");
    let skip_blanks = Regex::new(r"^\s*$").unwrap();
    let skip_comments = Regex::new(r"^//.*").unwrap();

    for line in lines {
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
    let valid_data_w_newlines = valid_data.join("\n");
    _ = File::create(&target_path).unwrap();
    fs::write(&target_path, valid_data_w_newlines).expect("");
    let mut return_path = PathBuf::new();
    return_path.push(&target_path);
    return return_path;
}

fn check_textage_metadata_files(js: &TextageJSParser, cache_dir: &String) -> PathBuf {
    println!("check textage song metadata files");
    // TODO: make this a config/global
    let cache_ok = cache_exists_and_is_valid(&cache_dir, &js.cache_filename);
    let mut cached_filepath = PathBuf::from(cache_dir);
    cached_filepath.push(&js.cache_filename);
    if cache_ok {
        println!("cache ok");
        return cached_filepath;
    } else {
        println!("downloading");
        return download_and_parse_textage_javascript(&js, &cached_filepath);
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
        file_specific_regexes: song_and_diff_regexes,
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

    let mut v: Vec<TextageJSParser> = Vec::new();
    v.push(song_difficulty_and_version_js);
    v.push(version_index_js);
    v.push(song_titles_js);
    return v;
}

fn match_title(title: Option<&Value>) -> Option<String> {
    match title {
        Some(_) => Some(String::from(title.unwrap().clone().as_str().unwrap())),
        None => None,
    }
}

fn match_difficulty(difficulty_level: i8, difficulty_type: &str) -> Option<String> {
    let mut difficulty_type_url: Option<String> = None;
    let level_url = match difficulty_level {
        i8::MIN..=0 => None,
        n @ 1..=9 => Some(String::from(format!("{}", n))),
        10 => Some(String::from("A")),
        11 => Some(String::from("B")),
        12 => Some(String::from("C")),
        13..=i8::MAX => None,
    };

    if level_url != None {
        difficulty_type_url = match difficulty_type {
            "NORMAL" => Some(String::from(format!("N{}", level_url.unwrap()))),
            "HYPER" => Some(String::from(format!("H{}", level_url.unwrap()))),
            "ANOTHER" => Some(String::from(format!("A{}", level_url.unwrap()))),
            "LEGGENDARIA" => Some(String::from(format!("X{}", level_url.unwrap()))),
            _ => None,
        }
    }
    return difficulty_type_url;
}

fn merge_data(
    titles: &HashMap<String, Vec<Value>>,
    difficulties: &HashMap<String, Vec<i8>>,
) -> HashMap<String, SongChartUrlMetadata> {
    // TODO: this needs to be reworked sort of
    let substream_index = "35";
    let sp_normal_index = 2 * 2 + 1;
    let sp_hyper_index = 3 * 2 + 1;
    let sp_another_index = 4 * 2 + 1;
    let sp_leggendaria_index = 5 * 2 + 1;
    let dp_normal_index = 7 * 2 + 1;
    let dp_hyper_index = 8 * 2 + 1;
    let dp_another_index = 9 * 2 + 1;
    let dp_leggendaria_index = 10 * 2 + 1;
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
        let song_difficulty = difficulties.get(textage_id);
        if song_difficulty == None {
            continue;
        }
        let song = SongChartUrlMetadata {
            textage_id: textage_id.to_string(),
            version_id_url: version_id_url,
            sp_normal: match_difficulty(song_difficulty.unwrap()[sp_normal_index], "NORMAL"),
            sp_hyper: match_difficulty(song_difficulty.unwrap()[sp_hyper_index], "HYPER"),
            sp_another: match_difficulty(song_difficulty.unwrap()[sp_another_index], "ANOTHER"),
            sp_leggendaria: match_difficulty(
                song_difficulty.unwrap()[sp_leggendaria_index],
                "LEGGENDARIA",
            ),
            dp_normal: match_difficulty(song_difficulty.unwrap()[dp_normal_index], "NORMAL"),
            dp_hyper: match_difficulty(song_difficulty.unwrap()[dp_hyper_index], "HYPER"),
            dp_another: match_difficulty(song_difficulty.unwrap()[dp_another_index], "ANOTHER"),
            dp_leggendaria: match_difficulty(
                song_difficulty.unwrap()[dp_leggendaria_index],
                "LEGGENDARIA",
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
    let mut titles: HashMap<String, Vec<Value>> = HashMap::new();
    let mut versions: Vec<String> = vec![];
    for config in &js_config {
        let file = check_textage_metadata_files(&config, &cache_dir);
        let filehandle = File::open(&file).unwrap();
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
        }
    }
    return merge_data(&titles, &difficulties);
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
        song_data.get("ALL OK!!").unwrap(),
        String::from("1P"),
        String::from("NORMAL"),
    );
    println!("{}", url.unwrap());
}
