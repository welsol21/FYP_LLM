use std::io::{BufRead, BufReader, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::sync::OnceLock;
use tauri::Manager;

static MODEL_SERVER_PORT: OnceLock<u16> = OnceLock::new();

fn content_type_for_path(path: &std::path::Path) -> &'static str {
  match path.extension().and_then(|e| e.to_str()) {
    Some("json") => "application/json; charset=utf-8",
    Some("mjs") | Some("js") => "text/javascript; charset=utf-8",
    Some("txt") => "text/plain; charset=utf-8",
    Some("wasm") => "application/wasm",
    _ => "application/octet-stream",
  }
}

fn handle_connection(stream: TcpStream, root: PathBuf) {
  let mut reader = BufReader::new(&stream);
  let mut request_line = String::new();
  if reader.read_line(&mut request_line).is_err() {
    return;
  }
  // Consume remaining request headers
  loop {
    let mut line = String::new();
    match reader.read_line(&mut line) {
      Ok(0) | Err(_) => break,
      Ok(_) => {
        if line == "\r\n" || line == "\n" {
          break;
        }
      }
    }
  }

  // Parse path from "GET /path HTTP/1.1"
  let uri_path = request_line
    .split_whitespace()
    .nth(1)
    .unwrap_or("/")
    .to_string();

  let mut writer = std::io::BufWriter::new(&stream);

  if uri_path == "/" || uri_path.is_empty() {
    let _ = write!(writer, "HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK");
    let _ = writer.flush();
    return;
  }

  let file_path = root.join(uri_path.trim_start_matches('/'));

  match std::fs::File::open(&file_path) {
    Ok(mut file) => {
      let size = file.metadata().map(|m| m.len()).unwrap_or(0);
      let content_type = content_type_for_path(&file_path);
      let _ = write!(
        writer,
        "HTTP/1.1 200 OK\r\nContent-Type: {}\r\nContent-Length: {}\r\nAccess-Control-Allow-Origin: *\r\nCache-Control: no-cache\r\n\r\n",
        content_type, size
      );
      let _ = writer.flush();
      // Stream file in 64 KB chunks — avoids loading the entire file into memory.
      let _ = std::io::copy(&mut file, &mut writer);
      let _ = writer.flush();
    }
    Err(_) => {
      let body = b"Not Found";
      let _ = write!(
        writer,
        "HTTP/1.1 404 Not Found\r\nContent-Length: {}\r\n\r\n",
        body.len()
      );
      let _ = writer.write_all(body);
      let _ = writer.flush();
    }
  }
}

fn start_model_file_server(runtime_root: PathBuf) -> u16 {
  let listener =
    TcpListener::bind("127.0.0.1:0").expect("Failed to bind model file server");
  let port = listener
    .local_addr()
    .expect("Failed to get local addr")
    .port();
  std::thread::spawn(move || {
    for stream in listener.incoming() {
      if let Ok(stream) = stream {
        let root = runtime_root.clone();
        std::thread::spawn(move || handle_connection(stream, root));
      }
    }
  });
  port
}

#[tauri::command]
fn get_model_server_url() -> String {
  let port = MODEL_SERVER_PORT.get().copied().unwrap_or(0);
  format!("http://127.0.0.1:{}", port)
}

#[tauri::command]
fn save_to_downloads(filename: String, bytes: Vec<u8>) -> Result<String, String> {
  let home = std::env::var("HOME").unwrap_or_else(|_| "/tmp".to_string());
  let downloads = std::path::PathBuf::from(&home).join("Downloads");
  if !downloads.exists() {
    std::fs::create_dir_all(&downloads).map_err(|e| e.to_string())?;
  }
  let safe_name = std::path::Path::new(&filename)
    .file_name()
    .and_then(|n| n.to_str())
    .unwrap_or("artifact")
    .to_string();
  let dest = downloads.join(&safe_name);
  std::fs::write(&dest, &bytes).map_err(|e| e.to_string())?;
  Ok(format!("~/Downloads/{}", safe_name))
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      // Start local HTTP server that streams model files from resources/.
      // Uses io::copy (64 KB chunks) to avoid loading large ONNX files into memory.
      let resource_dir = app
        .path()
        .resource_dir()
        .unwrap_or_else(|_| PathBuf::from("."));
      let runtime_root = resource_dir.join("resources").join("desktop-runtime");
      let port = start_model_file_server(runtime_root);
      MODEL_SERVER_PORT.set(port).ok();
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![get_model_server_url, save_to_downloads])
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
