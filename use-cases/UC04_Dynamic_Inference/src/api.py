from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from src.core import InferenceService
import os

app = FastAPI(title="Dynamic Inference Service")

# Initialize service with proper path resolution
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
config_path = os.path.join(BASE_DIR, 'config', 'clients.json')
service = InferenceService(config_path)

class InferenceRequest(BaseModel):
    client_id: str
    text: str

class InferenceResponse(BaseModel):
    client_id: str
    prediction: str
    original_input: str
    additional_info: dict = {}

@app.post("/predict")
async def predict(request: InferenceRequest):
    try:
        result = service.run_inference(request.client_id, request.text)
        return {
            "client_id": request.client_id,
            "prediction": result.pop("prediction"),
            "original_input": result.pop("original_input"),
            "additional_info": result
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health():
    return {"status": "healthy"}