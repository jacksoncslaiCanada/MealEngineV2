FROM python:3.11-slim-bookworm

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's Chromium browser + all its OS-level dependencies.
# This replaces the manual WeasyPrint system lib list (Cairo, Pango, etc.).
RUN playwright install --with-deps chromium

COPY . .

CMD ["python", "start.py"]
