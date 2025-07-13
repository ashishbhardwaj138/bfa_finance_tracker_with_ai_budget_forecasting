"""
GmailUtility class

Objective:
-----------
A production-grade utility class designed to securely authenticate and interface with Gmail API to fetch, filter,
and process email messages with a focus on data extraction for downstream analytics.

Features:
---------
- OAuth2 authentication and credential reuse
- Configurable email filters (sender, keyword, date, etc.)
- Support for incremental loading using last-run timestamp
- Downloading and parsing of email attachments
- Extraction of email metadata and content
- Logging and job statistics for pipeline observability
"""

import os
import json
import base64
import configparser
import logging
from datetime import datetime
import pandas as pd
from email import message_from_bytes
from bs4 import BeautifulSoup
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


class GmailUtility:
    def __init__(self, config_path='config.ini'):
        """
        Initializes the GmailUtility class using the provided config file.

        Args:
            config_path (str): Path to the .ini configuration file

        Example:
            >>> gmail = GmailUtility(config_path='config.ini')
        """
        self.job_start_time = datetime.now()
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.attachment_dir = self.config.get('PATHS', 'attachment_dir')
        self.output_csv = self.config.get('PATHS', 'output_csv')
        self.tracker_path = self.config.get('PATHS', 'last_run_tracker')

        os.makedirs(self.attachment_dir, exist_ok=True)
        os.makedirs(os.path.dirname(self.output_csv), exist_ok=True)

        self.creds = self.authenticate()
        self.service = build('gmail', 'v1', credentials=self.creds)

        self.processed_count = 0
        self.error_count = 0

        logging.info("Initialized GmailUtility with config at %s", config_path)

    def authenticate(self):
        """
        Handles Gmail OAuth2 authentication using saved token or client secret.

        Returns:
            Credentials object for Gmail API access
        """
        token_file = self.config.get('AUTH', 'token_file')
        credentials_file = self.config.get('AUTH', 'credentials_file')
        creds = None

        if os.path.exists(token_file):
            creds = Credentials.from_authorized_user_file(token_file, ['https://www.googleapis.com/auth/gmail.readonly'])

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                logging.info("Token refreshed successfully.")
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_file, ['https://www.googleapis.com/auth/gmail.readonly'])
                creds = flow.run_local_server(port=0)
                logging.info("Authenticated via browser flow.")

            with open(token_file, 'w') as token:
                token.write(creds.to_json())
                logging.info("New token saved to %s", token_file)

        return creds

    def build_query(self, use_incremental=True):
        """
        Constructs Gmail search query based on config file.

        Args:
            use_incremental (bool): Whether to include last_run timestamp in search

        Returns:
            str: Gmail search query string
        """
        q_parts = []
        cfg = self.config['EMAIL']
        if cfg.get('from_email'):
            q_parts.append(f"from:{cfg.get('from_email')}")
        if cfg.getboolean('has_attachment', fallback=False):
            q_parts.append("has:attachment")
        if cfg.get('keyword'):
            q_parts.append(cfg.get('keyword'))
        if cfg.get('after_date'):
            q_parts.append(f"after:{cfg.get('after_date')}")
        if cfg.get('before_date'):
            q_parts.append(f"before:{cfg.get('before_date')}")

        if use_incremental:
            last_ts = self._load_last_timestamp()
            if last_ts:
                q_parts.append(f"after:{last_ts}")
        return " ".join(q_parts)

    def list_messages(self, query, max_results=None):
        """
        Lists message IDs based on query string.

        Args:
            query (str): Gmail-compatible search string
            max_results (int): Maximum number of results to return

        Returns:
            list: List of message metadata dictionaries
        """
        max_results = max_results or int(self.config.get('EMAIL', 'max_results'))
        try:
            result = self.service.users().messages().list(userId='me', q=query, maxResults=max_results).execute()
            return result.get('messages', [])
        except Exception as e:
            logging.error("Error listing messages: %s", str(e))
            self.error_count += 1
            return []

    def get_message_detail(self, msg_id):
        """
        Retrieves full email message using message ID.

        Args:
            msg_id (str): Gmail message ID

        Returns:
            dict: Full message detail JSON
        """
        try:
            return self.service.users().messages().get(userId='me', id=msg_id, format='full').execute()
        except Exception as e:
            logging.error("Error fetching message ID %s: %s", msg_id, str(e))
            self.error_count += 1
            return {}

    def get_email_body(self, message):
        """
        Extracts plain text from email body (text/plain or text/html).

        Args:
            message (dict): Gmail message detail JSON

        Returns:
            str: Extracted message body as plain text
        """
        payload = message.get('payload', {})
        parts = payload.get('parts', [])
        body = ''
        if 'data' in payload.get('body', {}):
            body += base64.urlsafe_b64decode(payload['body']['data']).decode('utf-8', errors='ignore')
        for part in parts:
            if 'data' in part.get('body', {}):
                decoded = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='ignore')
                if part.get('mimeType') == 'text/plain':
                    body += decoded
                elif part.get('mimeType') == 'text/html':
                    body += BeautifulSoup(decoded, 'html.parser').get_text()
        return body

    def download_attachments(self, message):
        """
        Downloads attachments from a Gmail message.

        Args:
            message (dict): Gmail message detail JSON

        Returns:
            list: List of saved attachment file paths
        """
        attachments = []
        parts = message.get('payload', {}).get('parts', [])
        for part in parts:
            filename = part.get('filename')
            body = part.get('body', {})
            if filename and 'attachmentId' in body:
                att_id = body['attachmentId']
                attachment = self.service.users().messages().attachments().get(
                    userId='me', messageId=message['id'], id=att_id
                ).execute()
                data = base64.urlsafe_b64decode(attachment['data'])
                filepath = os.path.join(self.attachment_dir, filename)
                with open(filepath, 'wb') as f:
                    f.write(data)
                attachments.append(filepath)
        return attachments

    def extract_metadata(self, message):
        """
        Extracts sender, subject, date, body, and attachments from message.

        Args:
            message (dict): Gmail message detail

        Returns:
            dict: Parsed metadata and body content
        """
        headers = message.get('payload', {}).get('headers', [])
        data = {'Subject': '', 'From': '', 'Date': '', 'Body': '', 'Attachments': []}
        for h in headers:
            name = h.get('name', '').lower()
            if name == 'subject':
                data['Subject'] = h['value']
            elif name == 'from':
                data['From'] = h['value']
            elif name == 'date':
                data['Date'] = h['value']
        data['Body'] = self.get_email_body(message)
        data['Attachments'] = self.download_attachments(message)
        return data

    def _load_last_timestamp(self):
        if os.path.exists(self.tracker_path):
            with open(self.tracker_path) as f:
                return json.load(f).get('last_timestamp')
        return None

    def _save_last_timestamp(self, date_str):
        with open(self.tracker_path, 'w') as f:
            json.dump({'last_timestamp': date_str}, f)

    def fetch_and_store_emails(self):
        """
        Master function to extract emails, parse metadata, and save to CSV.
        Logs performance metrics and stores job stats to Excel for monitoring.
        """
        try:
            query = self.build_query()
            messages = self.list_messages(query)
            records = []
            latest_date = None

            for msg in messages:
                detail = self.get_message_detail(msg['id'])
                meta = self.extract_metadata(detail)
                records.append(meta)
                self.processed_count += 1

                try:
                    msg_date = datetime.strptime(meta['Date'][:16], '%a, %d %b %Y')
                    if not latest_date or msg_date > latest_date:
                        latest_date = msg_date
                except Exception:
                    continue

            if not records:
                logging.info("No new emails found.")
                return

            df = pd.DataFrame(records)
            if os.path.exists(self.output_csv):
                df_existing = pd.read_csv(self.output_csv)
                df = pd.concat([df_existing, df]).drop_duplicates()

            df.to_csv(self.output_csv, index=False)
            logging.info("Saved %d emails to %s", len(records), self.output_csv)

            if latest_date:
                self._save_last_timestamp(latest_date.strftime('%Y/%m/%d'))

        except Exception as e:
            logging.exception("Job failed due to error: %s", str(e))

        finally:
            self._log_job_stats()

    def _log_job_stats(self):
        """
        Append job statistics to an Excel file for performance monitoring.
        """
        end_time = datetime.now()
        duration = (end_time - self.job_start_time).total_seconds()

        row = {
            "Job_Name": "Gmail_Email_Ingestion",
            "Start_Time": self.job_start_time.strftime('%Y-%m-%d %H:%M:%S'),
            "End_Time": end_time.strftime('%Y-%m-%d %H:%M:%S'),
            "Duration_Seconds": duration,
            "Emails_Processed": self.processed_count,
            "Errors_Encountered": self.error_count,
            "Output_File": self.output_csv,
            "Status": "Completed" if self.error_count == 0 else "Completed with errors"
        }

        stats_path = "data/job_stats.xlsx"
        if os.path.exists(stats_path):
            df_stats = pd.read_excel(stats_path)
        else:
            df_stats = pd.DataFrame(columns=row.keys())

        df_stats = pd.concat([df_stats, pd.DataFrame([row])])
        df_stats.to_excel(stats_path, index=False)
        logging.info("Job stats logged to %s", stats_path)

