from fastapi import FastAPI

app = FastAPI(title="Newsletter Engine")


@app.get("/health")
def health():
    return {"status": "ok"}
