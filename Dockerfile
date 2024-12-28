FROM python:latest

# Set the working directory
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# upgrade pip
# RUN pip install --upgrade pip

# Install dependencies
RUN pip install flask gunicorn crawl4ai werkzeug quart asgiref

# Copy the application code
COPY . .

# Expose the port the app runs on
EXPOSE 5000

# Command to run the application
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000"]
