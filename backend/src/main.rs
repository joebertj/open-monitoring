use actix_web::{web, App, HttpResponse, HttpServer, Result};

async fn simple_test() -> Result<HttpResponse> {
    println!("Simple test endpoint called");
    Ok(HttpResponse::Ok().body(r#"{"test":"simple","status":"ok"}"#))
}

async fn root() -> Result<HttpResponse> {
    Ok(HttpResponse::Ok().body(r#"{"message":"BetterGovPH API","status":"running"}"#))
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    println!("🚀 Starting Rust API server on port 8000");

    HttpServer::new(|| {
        App::new()
            .route("/", web::get().to(root))
            .route("/simple-test", web::get().to(simple_test))
    })
    .bind("0.0.0.0:8000")?
    .run()
    .await
}
