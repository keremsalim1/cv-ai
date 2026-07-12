from fastapi import FastAPI

app = FastAPI(title="CV-AI API")

@app.get("/health")
def health():
    return {"status": "ok"}
