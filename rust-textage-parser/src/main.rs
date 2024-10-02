use regex::Regex;
use reqwest;
use std::fs;
use std::fs::File;
use std::path::PathBuf;
use std::time::SystemTime;

#[derive(Debug)]
struct TextageJS {
    filename: String,
    start_regex: Regex,
    end_regex: Regex,
}

#[derive(Debug)]
struct PrecompiledRegexes {
    act_remove_comments: Regex,
    act_remove_html: Regex,
    scr_fontcolor: Regex,
    scr_spanstyle: Regex,
    scr_span: Regex,
    scr_div_class: Regex,
    scr_div: Regex,
    scr_break: Regex,
    scr_bold: Regex,
    scr_end_bold: Regex,
    scr_odd_characters: Regex,
    scr_tabs: Regex,
    ver_semicolon: Regex,
    ver_close_bracket: Regex,
    ver_bad_version: Regex,
}

fn precompile_regexes() -> PrecompiledRegexes {
    let x = PrecompiledRegexes {
        act_remove_comments: Regex::new(r"//\d+").unwrap(),
        act_remove_html: Regex::new(",\"<span.*span>\"").unwrap(),
        scr_fontcolor: Regex::new(r".fontcolor\(.*?\)").unwrap(),
        scr_spanstyle: Regex::new("<span style='.*?'>").unwrap(),
        scr_span: Regex::new(r"<\\/span>").unwrap(),
        scr_div_class: Regex::new(r"<div class=.*?>").unwrap(),
        scr_div: Regex::new(r"<\\/div>").unwrap(),
        scr_break: Regex::new(r"<br>").unwrap(),
        scr_bold: Regex::new(r"<b>").unwrap(),
        scr_end_bold: Regex::new(r"<\\/b>").unwrap(),
        scr_odd_characters: Regex::new(r"^\[SS").unwrap(),
        scr_tabs: Regex::new(r"\t").unwrap(),
        ver_semicolon: Regex::new(";").unwrap(),
        ver_close_bracket: Regex::new("]$").unwrap(),
        ver_bad_version: Regex::new(r"vertbl\[35\]=").unwrap(),
    };
    return x;
}

// TODO: figure out where this should go
#[tokio::main]
async fn download_textage_javascript(filename: &str) -> Result<String, reqwest::Error> {
    let textage_base_url = format!("https://textage.cc/score/{}", filename);
    println!("downloading from {}", textage_base_url);
    let response = reqwest::get(textage_base_url)
        .await?
        .text_with_charset("Shift_JIS")
        .await?;
    return Ok(response);
}

fn parse_song_difficulty_and_version_js(line: &str, regexes: &PrecompiledRegexes) -> String {
    let (mut key, mut values) = line.split_once(":").unwrap();
    key = key.trim();
    let cleaned_key = key.replace("'", "\"");
    values = values.trim();
    let hex_converted = values
        .replace("A", "10")
        .replace("B", "11")
        .replace("C", "12")
        .replace("D", "13")
        .replace("E", "14")
        .replace("F", "15");
    let no_comments = regexes.act_remove_comments.replace(&hex_converted, "");
    let cleaned_values = regexes.act_remove_html.replace(&no_comments, "");
    return format!("{}:{}", cleaned_key, cleaned_values);
}

fn parse_song_titles_js(line: &str, regexes: &PrecompiledRegexes) -> String {
    let (mut key, values) = line.split_once(":").unwrap();
    key = key.trim();
    let key = key.replace("'", "\"");
    let values = regexes.scr_fontcolor.replace_all(&values, "");
    let values = regexes.scr_spanstyle.replace(&values, "");
    let values = regexes.scr_span.replace(&values, "");
    let values = regexes.scr_div_class.replace(&values, "");
    let values = regexes.scr_div.replace(&values, "");
    let values = regexes.scr_break.replace(&values, "");
    let values = regexes.scr_bold.replace(&values, "");
    let values = regexes.scr_end_bold.replace(&values, "");
    let values = regexes.scr_odd_characters.replace(&values, "[-1");
    let cleaned_values = regexes.scr_tabs.replace(&values, "");
    return format!("{}:{}", key, cleaned_values);
}

fn parse_version_index_js(line: &str, regexes: &PrecompiledRegexes) -> String {
    let line = regexes.ver_semicolon.replace(&line, "");
    let line = regexes.ver_close_bracket.replace(&line, "");
    let line = regexes.ver_bad_version.replace(&line, ",");
    return String::from(line);
}

// TODO: this should probably be async
fn download_and_parse_textage_javascript(js: &TextageJS, target_path: &PathBuf) -> PathBuf {
    println!("download and parse");
    let javascript = download_textage_javascript(&js.filename).unwrap();
    let lines = javascript.lines();
    let mut capture_output = false;
    let mut valid_data: Vec<String> = Vec::new();
    let mut start_char = String::from("");
    let skip_blanks = Regex::new(r"^\s*$").unwrap();
    let skip_comments = Regex::new(r"^//.*").unwrap();
    let regexes = precompile_regexes();

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
                println!("{} stopping at {}", js.filename, line);
                break;
            } else {
                if skip_comments.is_match(line) || skip_blanks.is_match(line) {
                    continue;
                }
                let special_parsed_line;
                if js.filename == "actbl.js" {
                    special_parsed_line = parse_song_difficulty_and_version_js(&line, &regexes);
                } else if js.filename == "scrlist.js" {
                    special_parsed_line = parse_version_index_js(&line, &regexes);
                } else if js.filename == "titletbl.js" {
                    special_parsed_line = parse_song_titles_js(&line, &regexes);
                } else {
                    special_parsed_line = String::from(line)
                }
                valid_data.push(String::from(special_parsed_line));
            }
        }
    }

    _ = File::create(&target_path).unwrap();
    fs::write(&target_path, valid_data.join("\n")).expect("");
    let mut return_path = PathBuf::new();
    return_path.push(target_path);
    return return_path;
}

fn cache_exists_and_is_valid(cache_dir: &str, filename: &str) -> bool {
    // TODO: change this to result based stuff
    // this assumes a fs-based cache
    let cache_dir = PathBuf::from(cache_dir);
    let max_cache_age: f32 = 86400.0 * 2.0;
    if !std::fs::exists(cache_dir.as_path()).unwrap() {
        _ = std::fs::create_dir_all(cache_dir.as_path());
        return false;
    }
    let mut cache_file = PathBuf::new();
    cache_file.push(cache_dir);
    cache_file.push(filename);
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
    println!(
        "now {:?} cache time {:?} age {:?}",
        now, cache_time, cache_age
    );
    if cache_age < max_cache_age {
        return true;
    }
    return false;
}

fn check_textage_metadata_files(js: &TextageJS) -> PathBuf {
    println!("check textage metadata file");
    let cache_dir = String::from("./textage-data");
    let local_parsed_filename = format!("{}.parsed.json", js.filename);
    let cache_ok = cache_exists_and_is_valid(&cache_dir, &local_parsed_filename);
    let mut cached_filepath = PathBuf::from(cache_dir);
    cached_filepath.push(local_parsed_filename);
    if cache_ok {
        println!("cache ok");
        return cached_filepath;
    } else {
        println!("downloading");
        return download_and_parse_textage_javascript(&js, &cached_filepath);
    }
}

fn setup_config() -> Vec<TextageJS> {
    let song_difficulty_and_version_js = TextageJS {
        filename: String::from("actbl.js"),
        start_regex: Regex::new(r"^\s*actbl=(\{).*$").unwrap(),
        end_regex: Regex::new(r"\s*}\s*;\s*").unwrap(),
    };

    let version_index_js = TextageJS {
        filename: String::from("scrlist.js"),
        start_regex: Regex::new(r"^vertbl\s*=\s*(\[)(.*)$").unwrap(),
        end_regex: Regex::new(r"^\s*$").unwrap(),
    };

    let song_titles_js = TextageJS {
        filename: String::from("titletbl.js"),
        start_regex: Regex::new(r"^\s*titletbl=(\{).*$").unwrap(),
        end_regex: Regex::new(r"\s*}\s*;\s*").unwrap(),
    };

    let mut v: Vec<TextageJS> = Vec::new();
    v.push(song_difficulty_and_version_js);
    v.push(version_index_js);
    v.push(song_titles_js);
    return v;
}

fn main() {
    println!("whats up");
    let js_config = setup_config();
    for config in &js_config {
        println!("config {:?}", config);
        check_textage_metadata_files(&config);
    }
}
