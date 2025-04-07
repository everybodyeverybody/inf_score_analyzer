use std::env;
mod textage;
use textage::TextageChartSearch;

fn main() {
    let song_search = TextageChartSearch::new();
    let args: Vec<String> = env::args().collect();
    let query = String::from(&args[1]);
    let result = song_search.find(query);
    println!("{}", result);
}
