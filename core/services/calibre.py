import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from core.models import Book

logger = logging.getLogger(__name__)


def load_books_from_calibre(calibre_path: Path):
    db_path = calibre_path / 'metadata.db'

    if not db_path.exists():
        raise FileNotFoundError(f'Calibre database not found at {db_path}')

    logger.info(f'Connecting to Calibre database at {db_path}')
    
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT 
            b.id,
            b.title,
            b.path,
            b.pubdate,
            b.timestamp,
            (SELECT val FROM identifiers WHERE book = b.id AND type = 'isbn' LIMIT 1) as isbn,
            (SELECT name FROM data WHERE book = b.id AND format = 'EPUB' LIMIT 1) as epub_name,
            (SELECT GROUP_CONCAT(a.name, ' & ') 
             FROM authors a 
             JOIN books_authors_link bal ON a.id = bal.author 
             WHERE bal.book = b.id) as authors,
            (SELECT text FROM comments WHERE book = b.id) as description
        FROM books b
        JOIN books_tags_link btl ON b.id = btl.book
        JOIN tags t ON btl.tag = t.id
        JOIN data d ON b.id = d.book
        WHERE t.name = 'Food'
        AND d.format = 'EPUB'
        ORDER BY b.title
    """)

    books_data = cursor.fetchall()
    logger.info(f'Found {len(books_data)} books with "Food" tag and EPUB format')

    created_count = 0
    updated_count = 0

    for row in books_data:
        calibre_id = row['id']
        title = row['title']
        author = row['authors'] or ''
        path = row['path']
        pubdate_str = row['pubdate']
        timestamp_str = row['timestamp']
        isbn = row['isbn'] or ''
        description = row['description'] or ''

        pubdate = None
        if pubdate_str:
            try:
                pubdate = datetime.strptime(pubdate_str.split()[0], '%Y-%m-%d').date()
            except (ValueError, IndexError):
                logger.warning(f'Could not parse pubdate for book {calibre_id}: {pubdate_str}')

        calibre_added_at = None
        if timestamp_str:
            try:
                calibre_added_at = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
            except (ValueError, IndexError):
                logger.warning(f'Could not parse timestamp for book {calibre_id}: {timestamp_str}')

        _, created = Book.objects.update_or_create(
            calibre_id=calibre_id,
            defaults={
                'title': title,
                'author': author,
                'pubdate': pubdate,
                'calibre_added_at': calibre_added_at,
                'isbn': isbn,
                'description': description,
                'path': str(calibre_path / path),
            }
        )

        if created:
            created_count += 1
            logger.info(f'Created: {title}')
        else:
            updated_count += 1
            logger.info(f'Updated: {title}')

    conn.close()
    return created_count, updated_count


def refresh_single_book_from_calibre(book: Book):
    from django.conf import settings
    calibre_path = Path(settings.CALIBRE_LIBRARY_PATH)
    db_path = calibre_path / 'metadata.db'

    if not db_path.exists():
        raise FileNotFoundError(f'Calibre database not found at {db_path}')

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT DISTINCT 
            b.id,
            b.title,
            b.path,
            b.pubdate,
            b.timestamp,
            (SELECT val FROM identifiers WHERE book = b.id AND type = 'isbn' LIMIT 1) as isbn,
            (SELECT GROUP_CONCAT(a.name, ' & ') 
             FROM authors a 
             JOIN books_authors_link bal ON a.id = bal.author 
             WHERE bal.book = b.id) as authors,
            (SELECT text FROM comments WHERE book = b.id) as description
        FROM books b
        WHERE b.id = ?
    """, (book.calibre_id,))

    row = cursor.fetchone()
    conn.close()

    if not row:
        raise ValueError(f'Book with calibre_id {book.calibre_id} not found in Calibre database')

    pubdate = None
    if row['pubdate']:
        try:
            pubdate = datetime.strptime(row['pubdate'].split()[0], '%Y-%m-%d').date()
        except (ValueError, IndexError):
            pass

    calibre_added_at = None
    if row['timestamp']:
        try:
            calibre_added_at = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00'))
        except (ValueError, IndexError):
            pass

    book.title = row['title']
    book.author = row['authors'] or ''
    book.pubdate = pubdate
    book.calibre_added_at = calibre_added_at
    book.isbn = row['isbn'] or ''
    book.description = row['description'] or ''
    book.path = str(calibre_path / row['path'])
    book.save()

    logger.info(f'Refreshed metadata for: {book.title}')