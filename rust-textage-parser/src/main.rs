use regex::Regex;
use reqwest;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::error::Error;
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

#[derive(Debug, Serialize, Deserialize)]
#[serde(untagged)]
enum StringOrInteger {
    String(String),
    Integer(i16),
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

fn deserialize_textage_data() {
    let js_config = setup_config();
    let cache_dir = String::from("./textage-data");
    let mut song_and_difficulty: HashMap<String, Vec<i8>>;
    let mut titles: HashMap<String, Vec<StringOrInteger>>;
    let mut versions: Vec<String>;
    for config in &js_config {
        let file = check_textage_metadata_files(&config, &cache_dir);
        let filehandle = File::open(&file).unwrap();
        let reader = BufReader::new(&filehandle);
        match config.js_type {
            TextageJSType::Difficulties => {
                song_and_difficulty = serde_json::from_reader(reader).unwrap();
            }
            TextageJSType::Versions => {
                versions = serde_json::from_reader(reader).unwrap();
            }
            TextageJSType::Titles => {
                titles = serde_json::from_reader(reader).unwrap();
            }
        }
    }
}

fn main() {
    deserialize_textage_data();
}
