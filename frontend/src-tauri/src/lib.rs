use std::path::PathBuf;
use tauri::http::{Response, StatusCode};
use tauri::Manager;

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
      Ok(())
    })
    .register_uri_scheme_protocol("model", |ctx, request| {
      let uri_path = request.uri().path().trim_start_matches('/').to_string();
      let resource_dir = ctx
        .app_handle()
        .path()
        .resource_dir()
        .unwrap_or_else(|_| PathBuf::from("."));
      let file_path = resource_dir
        .join("resources")
        .join("desktop-runtime")
        .join(&uri_path);

      match std::fs::read(&file_path) {
        Ok(data) => {
          let content_type = if uri_path.ends_with(".json") {
            "application/json; charset=utf-8"
          } else if uri_path.ends_with(".mjs") || uri_path.ends_with(".js") {
            "text/javascript; charset=utf-8"
          } else if uri_path.ends_with(".txt") {
            "text/plain; charset=utf-8"
          } else if uri_path.ends_with(".wasm") {
            "application/wasm"
          } else {
            "application/octet-stream"
          };
          Response::builder()
            .status(StatusCode::OK)
            .header("Content-Type", content_type)
            .header("Access-Control-Allow-Origin", "tauri://localhost")
            .body(data)
            .unwrap()
        }
        Err(_) => Response::builder()
          .status(StatusCode::NOT_FOUND)
          .header("Content-Type", "text/plain; charset=utf-8")
          .body(b"404 Not Found".to_vec())
          .unwrap(),
      }
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}
