import os
import uvicorn

from synaptic.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "synaptic.api.app:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 8000)),  
        reload=False, 
        log_level=settings.log_level.lower(),
    )
