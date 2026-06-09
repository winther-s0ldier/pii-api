FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies (required for some python packages)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# --- THE MAGIC TRICK ---
# We write a tiny python script to download the GLiNER model DURING the Docker build.
# This "bakes" the 400MB model directly into the Docker image. 
# When AWS spins up your app, it doesn't need to download anything from the internet!
RUN python -c "from gliner2 import GLiNER2; GLiNER2.from_pretrained('fastino/gliner2-privacy-filter-PII-multi')"

# Copy the rest of the application
COPY . .

# Expose the port FastAPI runs on
EXPOSE 8000

# Command to run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
