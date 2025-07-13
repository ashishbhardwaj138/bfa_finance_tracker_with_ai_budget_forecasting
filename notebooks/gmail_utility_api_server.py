from datetime import datetime, timedelta
import calendar

def build_query(self, use_incremental=True):
    """
    Constructs Gmail search query from config or defaults.

    Logic:
    - If start and end date are in config → use them
    - Else, default to current month start-end
    - If use_incremental = True, and last_run_timestamp exists → override with that

    Returns:
        str: Gmail-compatible query string
    """

    q_parts = []
    cfg = self.config['EMAIL']

    # Add sender filter
    if cfg.get('from_email'):
        q_parts.append(f"from:{cfg.get('from_email')}")

    # Add attachment filter
    if cfg.getboolean('has_attachment', fallback=False):
        q_parts.append("has:attachment")

    # Add keyword
    if cfg.get('keyword'):
        q_parts.append(cfg.get('keyword'))

    # --- Date logic begins ---
    after_date = cfg.get('after_date', '').strip()
    before_date = cfg.get('before_date', '').strip()

    if not after_date or not before_date:
        # Default to current month
        today = datetime.today()
        first_day = today.replace(day=1)
        last_day = today.replace(day=calendar.monthrange(today.year, today.month)[1])

        after_date = first_day.strftime("%Y/%m/%d")
        before_date = last_day.strftime("%Y/%m/%d")

        logging.info(f"No dates in config. Defaulting to current month: {after_date} to {before_date}")

    # If incremental is True and last timestamp exists → override after_date
    if use_incremental:
        last_ts = self._load_last_timestamp()
        if last_ts:
            logging.info(f"Using incremental load. Overriding after_date to last_run: {last_ts}")
            after_date = last_ts

    q_parts.append(f"after:{after_date}")
    q_parts.append(f"before:{before_date}")
    # --- Date logic ends ---

    return " ".join(q_parts)
