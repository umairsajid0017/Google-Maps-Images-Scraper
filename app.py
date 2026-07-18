import os
import sys
import threading
import queue
from datetime import datetime
from flask import Flask, request, jsonify

# Add current directory to path
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

from google_maps_image_scraper import GoogleMapsImageScraper

app = Flask(__name__)

# ─── Concurrency Configuration ────────────────────────────────────────────────
# Maximum number of Chrome/Selenium scraping jobs that run at the same time.
# Each active job spins up a headless Chrome instance (~300–500 MB RAM each).
# Raise this only if your machine has plenty of RAM; lower it if you see crashes.
MAX_CONCURRENT_SCRAPERS = 3

# Semaphore that limits how many jobs can run simultaneously
scraper_semaphore = threading.Semaphore(MAX_CONCURRENT_SCRAPERS)

# FIFO queue for jobs waiting for a free slot
pending_queue = queue.Queue()

# ─── Job Registry ─────────────────────────────────────────────────────────────
# keys: location name (string)
# values: {
#     "status": "queued" | "running" | "done" | "error",
#     "images": [ {url, thumbUrl, description, author}, ... ],
#     "error": str | None,
#     "queued_at": datetime,
#     "started_at": datetime | None,
#     "completed_at": datetime | None,
#     "queue_position": int | None
# }
jobs = {}
jobs_lock = threading.Lock()


def _run_next_from_queue():
    """
    Called after a scrape job finishes (or errors).
    Pops the next pending job from the queue and starts it so the freed
    semaphore slot is immediately reused.
    """
    try:
        location, max_images, skip_images = pending_queue.get_nowait()
        app.logger.info(f"[QUEUE] Dequeued '{location}' (skip_images={skip_images}), starting now.")
        _start_scrape_thread(location, max_images, skip_images)
    except queue.Empty:
        pass  # Nothing waiting — semaphore slot stays free


def _start_scrape_thread(location, max_images, skip_images=0):
    """Launch the actual scrape in a daemon thread."""
    thread = threading.Thread(
        target=background_scrape_task,
        args=(location, max_images, skip_images),
        daemon=True
    )
    thread.start()


def background_scrape_task(location, max_images, skip_images=0):
    """
    The main scraping worker.
    Acquires the concurrency semaphore before starting Chrome,
    releases it when done — then kicks off the next queued job.
    """
    scraper = None
    scraper_semaphore.acquire()  # Block here until a slot is free

    try:
        # Mark the job as running now that we have a slot
        with jobs_lock:
            if location in jobs:
                jobs[location]['status'] = 'running'
                jobs[location]['started_at'] = datetime.now()
                jobs[location]['queue_position'] = None

        app.logger.info(f"[JOB - {location}] Starting scraper (slot acquired) with skip_images={skip_images}.")

        # Callback: called by the scraper each time a new image URL is found
        def on_image_found(url):
            with jobs_lock:
                if location not in jobs:
                    return
                if "googleusercontent.com" in url:
                    thumb_url = url.replace('=w0-h0-k-no', '=w300-h300-k-no')
                else:
                    thumb_url = url

                img_obj = {
                    'url': url,
                    'thumbUrl': thumb_url,
                    'description': f'Google Maps Photo of {location}',
                    'author': 'Google Maps User'
                }

                if not any(x['url'] == url for x in jobs[location]['images']):
                    jobs[location]['images'].append(img_obj)
                    app.logger.info(
                        f"[JOB - {location}] Found image "
                        f"#{len(jobs[location]['images'])}: {url[:60]}..."
                    )

        scraper = GoogleMapsImageScraper(
            headless=True,
            timeout=30,
            save_csv=False
        )
        scraper.extract_urls_only(location, max_images=max_images, callback=on_image_found, skip_images=skip_images)

        with jobs_lock:
            if location in jobs:
                jobs[location]['status'] = 'done'
                jobs[location]['completed_at'] = datetime.now()
                app.logger.info(
                    f"[JOB - {location}] Completed. "
                    f"Total images: {len(jobs[location]['images'])}"
                )

    except Exception as e:
        app.logger.error(f"[JOB - {location}] Failed: {str(e)}")
        with jobs_lock:
            if location in jobs:
                jobs[location]['status'] = 'error'
                jobs[location]['error'] = str(e)
                jobs[location]['completed_at'] = datetime.now()
    finally:
        if scraper:
            try:
                scraper.close()
            except Exception:
                pass

        scraper_semaphore.release()   # Free the slot
        _run_next_from_queue()        # Start next queued job if any


# ─── Routes ───────────────────────────────────────────────────────────────────

@app.route('/scrape', methods=['GET'])
def scrape():
    location = request.args.get('location')
    if not location:
        return jsonify({'success': False, 'error': 'Location parameter is required'}), 400

    max_images_str = request.args.get('max_images', '20')
    try:
        max_images = int(max_images_str)
    except ValueError:
        max_images = 20

    skip_images_str = request.args.get('skip_images', '0')
    try:
        skip_images = int(skip_images_str)
    except ValueError:
        skip_images = 0

    force_refresh = request.args.get('refresh', '0') == '1'

    with jobs_lock:
        job = jobs.get(location)

        # Start a new job if: no existing job, force-refresh, or previous error
        if not job or force_refresh or job['status'] == 'error':
            # How many slots are currently free (read under jobs_lock for consistency)
            slots_free = scraper_semaphore._value

            # If skip_images > 0, preserve already scraped images so we append to them
            existing_images = []
            if skip_images > 0 and job and 'images' in job:
                existing_images = job['images']

            if slots_free > 0:
                # A slot is available — start immediately
                app.logger.info(f"[SCRAPE] Slot available, starting '{location}' immediately (skip_images={skip_images}).")
                jobs[location] = {
                    'status': 'running',
                    'images': existing_images,
                    'error': None,
                    'queued_at': datetime.now(),
                    'started_at': datetime.now(),
                    'completed_at': None,
                    'queue_position': None,
                }
                _start_scrape_thread(location, max_images, skip_images)
            else:
                # All slots busy — enqueue
                queue_pos = pending_queue.qsize() + 1
                app.logger.info(
                    f"[SCRAPE] All {MAX_CONCURRENT_SCRAPERS} slots busy. "
                    f"Queuing '{location}' at position #{queue_pos} (skip_images={skip_images})."
                )
                jobs[location] = {
                    'status': 'queued',
                    'images': existing_images,
                    'error': None,
                    'queued_at': datetime.now(),
                    'started_at': None,
                    'completed_at': None,
                    'queue_position': queue_pos,
                }
                pending_queue.put((location, max_images, skip_images))

            job = jobs[location]

        else:
            app.logger.info(
                f"[SCRAPE] Poll for '{location}' "
                f"(status={job['status']}, images={len(job['images'])})"
            )

        return jsonify({
            'success': True,
            'status': job['status'],          # "queued" | "running" | "done" | "error"
            'images': job['images'],
            'error': job.get('error'),
            'queue_position': job.get('queue_position'),
            'max_concurrent': MAX_CONCURRENT_SCRAPERS,
        })


@app.route('/status', methods=['GET'])
def status():
    """Returns a summary of all known jobs and current concurrency state."""
    with jobs_lock:
        summary = {
            'max_concurrent': MAX_CONCURRENT_SCRAPERS,
            'active_slots_used': MAX_CONCURRENT_SCRAPERS - scraper_semaphore._value,
            'queued_count': pending_queue.qsize(),
            'jobs': {
                loc: {
                    'status': j['status'],
                    'images_found': len(j['images']),
                    'queue_position': j.get('queue_position'),
                    'started_at': j['started_at'].isoformat() if j.get('started_at') else None,
                    'completed_at': j['completed_at'].isoformat() if j.get('completed_at') else None,
                }
                for loc, j in jobs.items()
            }
        }
    return jsonify(summary)


if __name__ == '__main__':
    app.logger.info(
        f"Starting scraper service — max concurrent jobs: {MAX_CONCURRENT_SCRAPERS}"
    )
    app.run(host='127.0.0.1', port=5000, threaded=True)


