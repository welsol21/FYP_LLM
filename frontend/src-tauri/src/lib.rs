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
    // Custom protocol: model://localhost/<path-relative-to-resources/>
    // Serves bundled model files directly from the resource directory.
    // Bypasses asset:// protocol scope/glob/encoding issues on Linux.
    .register_uri_scheme_protocol("model", |ctx, request| {
      let resource_dir = ctx.app_handle().path().resource_dir()
        .expect("failed to resolve resource dir");
      let rel = request.uri().path().trim_start_matches('/');
      let file_path = resource_dir.join(rel);
      match std::fs::read(&file_path) {
        Ok(data) => tauri::http::Response::builder()
          .status(200)
          .header("Content-Type", mime_for_path(rel))
          .header("Access-Control-Allow-Origin", "*")
          .body(data)
          .unwrap(),
        Err(_) => tauri::http::Response::builder()
          .status(404)
          .body(vec![])
          .unwrap(),
      }
    })
    .run(tauri::generate_context!())
    .expect("error while running tauri application");
}

fn mime_for_path(path: &str) -> &'static str {
  if path.ends_with(".json") { "application/json" }
  else if path.ends_with(".txt") { "text/plain" }
  else { "application/octet-stream" }
}
