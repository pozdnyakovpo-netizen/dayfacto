import os
import time

from services.clustering.story_builder import run_clustering_pass
from shared.logging import get_logger

os.environ.setdefault("SERVICE_NAME", "clustering")
logger = get_logger(__name__)

POLL_INTERVAL_SECONDS = int(os.environ.get("CLUSTERING_POLL_INTERVAL", "150"))


def main() -> None:
    logger.info(f"Clustering service starting, poll interval = {POLL_INTERVAL_SECONDS}s")
    while True:
        try:
            run_clustering_pass()
        except Exception as e:
            logger.error(f"Clustering pass failed: {e}", exc_info=True)
        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
