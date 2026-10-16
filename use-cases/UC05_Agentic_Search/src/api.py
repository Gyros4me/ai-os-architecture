"""
FastAPI application for Agentic Search Agent
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn
import time

from .models import SearchQuery, AgentResponse
from .agent import BookSearchAgent
from .data_loader import generate_sample_books, load_books_from_csv
import os

# Initialize FastAPI app
app = FastAPI(
    title="Agentic Search Agent API",
    description="Conversational AI agent for book search with fuzzy matching and context tracking",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global agent instance
agent: BookSearchAgent = None


@app.on_event("startup")
async def startup_event():
    """Initialize agent on startup"""
    global agent
    
    # Try to load from CSV, otherwise use sample data
    books_csv_path = os.environ.get("BOOKS_CSV_PATH", "books.csv")
    
    if os.path.exists(books_csv_path):
        print(f"Loading books from {books_csv_path}")
        books_data = load_books_from_csv(books_csv_path)
    else:
        print("Using sample books dataset")
        books_data = generate_sample_books()
    
    agent = BookSearchAgent(books_data)
    print(f"Agent initialized with {len(books_data)} books")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "message": "Agentic Search Agent API",
        "version": "1.0.0",
        "endpoints": {
            "search": "/api/search",
            "stats": "/api/stats",
            "health": "/health"
        }
    }


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "timestamp": time.time()
    }


@app.post("/api/search", response_model=AgentResponse)
async def search_books(query: SearchQuery):
    """
    Main search endpoint
    
    Example queries:
    - "Cerco un libro di J. K. Rowling"
    - "Come si chiama quel libro con la parola 'sole' nel titolo?"
    - "Sto cercando Muradami" (fuzzy matching for Murakami)
    """
    if agent is None:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    try:
        response = agent.process_query(query)
        return response
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/stats")
async def get_stats():
    """Get agent statistics"""
    if agent is None:
        raise HTTPException(status_code=500, detail="Agent not initialized")
    
    return agent.get_statistics()


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
