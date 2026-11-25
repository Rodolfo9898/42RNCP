# The `scraper` service: downloads the subject PDFs (and the files that come with a project) from the 42 intra into samples/ and artifacts/,
# when the editor asks for it (`Verdict: Download Subjects from the Intra`). Only the web app talks to it, with a token.
# It never logs in: there is no browser and no password in this image. The login is done once on your computer (`make samples-login`)
# and its session (cookies) is mounted read-only. Everything it needs is stdlib + httpx + fastapi (src/scraper/requirements-service.txt).
FROM python:3.14-slim

# Same uid as the web app, so a PDF it writes into samples/ is one the web app can read and replace.
RUN useradd --create-home --uid 1000 scraper \
    && mkdir /samples /artifacts /session && chown scraper:scraper /samples /artifacts

WORKDIR /app
COPY src/scraper/requirements-service.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY src/scraper ./scraper
COPY src/scraper_server.py ./

USER scraper
ENV SAMPLES_DIR=/samples \
    ARTIFACTS_DIR=/artifacts \
    SESSION_DIR=/session \
    PYTHONDONTWRITEBYTECODE=1

EXPOSE 8003
CMD ["uvicorn", "scraper_server:app", "--host", "0.0.0.0", "--port", "8003"]
