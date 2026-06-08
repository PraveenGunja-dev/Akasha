import uvicorn
import sys

if __name__ == "__main__":
    print("Starting Akasha Platform Backend on Port 3510...")
    # Run the FastAPI application on host 0.0.0.0 and port 3510
    uvicorn.run("main:app", host="0.0.0.0", port=3510, reload=False)
